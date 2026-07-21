"""Maintenance rules engine: per-part service status from km/time intervals.

Pure domain logic — no HTTP and no database queries (callers pass already
fetched parts/services plus the current odometer and today's date), which
keeps every rule here directly unit-testable.
"""
import calendar
from dataclasses import dataclass

from django.utils import timezone

from .models import Part, ServiceRecord

# Global "due soon" warning window: a part is due soon when it is within this
# distance of its due point on ANY configured dimension.
DUE_SOON_KM = 2000
DUE_SOON_DAYS = 31  # ~ 1 month

STATE_OK = 'ok'
STATE_DUE_SOON = 'due_soon'
STATE_OVERDUE = 'overdue'
STATE_NO_SERVICE = 'no_service'

# Urgency order used to sort the status page.
_STATE_ORDER = [STATE_OVERDUE, STATE_DUE_SOON, STATE_OK, STATE_NO_SERVICE]
_STATE_LABELS = {
    STATE_OK: 'OK',
    STATE_DUE_SOON: 'Due soon',
    STATE_OVERDUE: 'Overdue',
    STATE_NO_SERVICE: 'No records',
}


@dataclass
class Dimension:
    """One tracked interval dimension (kilometers or time) of a part."""
    progress: int   # percent of the interval consumed, clamped to 0-100
    remaining: int  # km or days until due; <= 0 means overdue
    caption: str    # e.g. "3,200 / 15,000 km" or "4 / 12 months"
    due_label: str  # e.g. "18,200 km" or "25/05/2026"


@dataclass
class PartStatus:
    """Everything the status page needs to render one part."""
    part: Part
    state: str
    last_service: ServiceRecord | None
    services: list  # ServiceRecords oldest-first, for the numbered history
    km: Dimension | None
    time: Dimension | None

    @property
    def label(self):
        return _STATE_LABELS[self.state]


def add_months(day, months):
    """Return ``day`` shifted by ``months`` calendar months.

    The day of month is clamped to the target month's length
    (Jan 31 + 1 month -> Feb 28/29).
    """
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def _whole_months_between(start, end):
    """Complete calendar months elapsed from ``start`` to ``end`` (>= 0)."""
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def _km_dimension(part, last_km, current_km):
    interval = part.interval_km
    elapsed = current_km - last_km
    return Dimension(
        progress=_percent(elapsed, interval),
        remaining=interval - elapsed,
        caption=f'{elapsed:,} / {interval:,} km',
        due_label=f'{last_km + interval:,} km',
    )


def _time_dimension(part, last_date, today):
    interval = part.interval_months
    due = add_months(last_date, interval)
    return Dimension(
        progress=_percent((today - last_date).days, (due - last_date).days),
        remaining=(due - today).days,
        caption=f'{_whole_months_between(last_date, today)} / {interval} months',
        due_label=due.strftime('%d/%m/%Y'),
    )


def _percent(elapsed, total):
    return min(100, max(0, round(elapsed / total * 100)))


def part_status(part, services, current_km, today):
    """Build the status of one part from its service records.

    The baseline is the LAST service: highest km for the km dimension and most
    recent date for the time dimension. Both normally come from the same
    record, but back-filled services can make them differ.
    """
    services = sorted(services, key=lambda s: (s.entry.date, s.entry.kilometers, s.pk))
    if not services:
        return PartStatus(part, STATE_NO_SERVICE, None, [], None, None)

    last_service = services[-1]
    last_km = max(s.entry.kilometers for s in services)
    last_date = max(timezone.localtime(s.entry.date).date() for s in services)

    km = _km_dimension(part, last_km, current_km) if part.interval_km else None
    time = _time_dimension(part, last_date, today) if part.interval_months else None

    state = STATE_OK
    for dim, warning in ((km, DUE_SOON_KM), (time, DUE_SOON_DAYS)):
        if dim is None:
            continue
        if dim.remaining <= 0:
            state = STATE_OVERDUE
            break
        if dim.remaining <= warning:
            state = STATE_DUE_SOON

    return PartStatus(part, state, last_service, services, km, time)


def build_part_statuses(parts, current_km, today):
    """Statuses for all parts, sorted by urgency (overdue first)."""
    statuses = [
        part_status(part, list(part.services.all()), current_km, today)
        for part in parts
    ]
    statuses.sort(key=lambda s: (_STATE_ORDER.index(s.state), s.part.name.lower()))
    return statuses
