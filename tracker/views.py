import csv
import io
import json

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.db.models import Prefetch, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import EntryForm, PartForm, ServiceForm
from .models import MaintenanceEntry, Part, ServiceRecord
from .services import build_part_statuses

# Maximum accepted size for an uploaded backup file (10 MB).
IMPORT_MAX_BYTES = 10 * 1024 * 1024
# Only tracker objects are ever written back to the database when restoring a
# backup through the web UI, in FK dependency order (a service record points
# to its part and entry). Keeping auth/permissions out of the import path
# means a crafted (or stale) backup can never change credentials, create
# superusers, or alter permission tables.
IMPORT_MODELS = {
    'tracker.part': Part,
    'tracker.maintenanceentry': MaintenanceEntry,
    'tracker.servicerecord': ServiceRecord,
}
IMPORT_ORDER = list(IMPORT_MODELS)  # dicts preserve insertion order


def _create_entry(request):
    if request.method != 'POST':
        return EntryForm(), False
    form = EntryForm(request.POST)
    if form.is_valid():
        form.save()
        return form, True
    return form, False


def _display_date_from_post(request):
    raw = (request.POST.get('date') or '').strip()
    if not raw:
        return ''
    try:
        dt = timezone.datetime.fromisoformat(raw)
        return dt.strftime('%d/%m/%Y %H:%M')
    except ValueError:
        return raw


def _current_km():
    latest = MaintenanceEntry.objects.order_by('-kilometers').first()
    return latest.kilometers if latest else 0


@login_required
def index(request):
    form, created = _create_entry(request)
    if created:
        return redirect('index')

    return render(request, 'tracker/index.html', {
        'form': form,
        'entries': MaintenanceEntry.objects.all(),
        'current_km': _current_km(),
        'date_display': _display_date_from_post(request) if form.is_bound else '',
    })


@require_POST
@login_required
def delete_entry(request, pk):
    entry = get_object_or_404(MaintenanceEntry, pk=pk)
    entry.delete()
    messages.success(request, f'"{entry.name}" was deleted.')
    return redirect('index')


def _create_service_record(data):
    """Create the cost entry + service record for a logged service.

    The entry is saved WITHOUT full_clean() on purpose: service logs may be
    back-filled with an older odometer reading, so the "odometer never goes
    backwards" rule enforced on manual entries does not apply here.
    """
    part = data['part']
    entry = MaintenanceEntry(
        name=part.name,
        kilometers=data['kilometers'],
        cost=data['cost'] if data['cost'] is not None else Decimal('0'),
        date=data['date'],
        reason=data['note'],
    )
    entry.save()
    return ServiceRecord.objects.create(part=part, entry=entry)


def _render_maintenance(request, *, part_form=None, service_form=None, editing_part=None):
    """Render the maintenance page, creating whichever forms are not given.

    Bound forms (after a failed validation) are passed in so the user's input
    and errors survive; unbound forms are built here with sensible defaults.
    """
    current_km = _current_km()
    parts = Part.objects.prefetch_related(
        Prefetch('services', queryset=ServiceRecord.objects.select_related('entry'))
    )
    if part_form is None:
        part_form = PartForm(instance=editing_part) if editing_part else PartForm()
    if service_form is None:
        initial = {'kilometers': current_km}
        if request.method == 'GET':
            # "Log service" shortcut on a part card preselects that part.
            initial['part'] = request.GET.get('part')
        service_form = ServiceForm(initial=initial)

    return render(request, 'tracker/maintenance.html', {
        'statuses': build_part_statuses(parts, current_km, timezone.localdate()),
        'part_form': part_form,
        'service_form': service_form,
        'editing_part': editing_part,
        'current_km': current_km,
        'date_display': _display_date_from_post(request) if request.method == 'POST' else '',
        'service_open': bool(request.GET.get('part')) or service_form.is_bound,
    })


@login_required
def maintenance(request):
    """The parts status page; also handles both of its creation forms."""
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_part':
            part_form = PartForm(request.POST)
            if part_form.is_valid():
                part = part_form.save()
                messages.success(request, f'Part "{part.name}" was added.')
                return redirect('maintenance')
            return _render_maintenance(request, part_form=part_form)
        if action == 'log_service':
            service_form = ServiceForm(request.POST)
            if service_form.is_valid():
                record = _create_service_record(service_form.cleaned_data)
                messages.success(request, f'Service for "{record.part.name}" was logged.')
                return redirect('maintenance')
            return _render_maintenance(request, service_form=service_form)
    return _render_maintenance(request)


@login_required
def edit_part(request, pk):
    part = get_object_or_404(Part, pk=pk)
    if request.method == 'POST':
        part_form = PartForm(request.POST, instance=part)
        if part_form.is_valid():
            part_form.save()
            messages.success(request, f'Part "{part.name}" was updated.')
            return redirect('maintenance')
        return _render_maintenance(request, part_form=part_form, editing_part=part)
    return _render_maintenance(request, editing_part=part)


@require_POST
@login_required
def delete_part(request, pk):
    part = get_object_or_404(Part, pk=pk)
    # Service records cascade away with the part; the cost entries created
    # for those services are deliberately kept as regular entries.
    part.delete()
    messages.success(request, f'Part "{part.name}" was deleted. Its cost entries were kept.')
    return redirect('maintenance')


@require_POST
@login_required
def delete_service(request, pk):
    record = get_object_or_404(ServiceRecord, pk=pk)
    # Deleting the entry cascade-deletes the record, so both sides stay in sync.
    record.entry.delete()
    messages.success(request, f'Service record for "{record.part.name}" was deleted.')
    return redirect('maintenance')


@login_required
def report(request):
    """Spending overview: logged services (part-linked entries) vs. the rest."""
    entries = MaintenanceEntry.objects.all()
    service_entries = entries.filter(servicerecord__isnull=False)
    other_entries = entries.filter(servicerecord__isnull=True)
    services_total = service_entries.aggregate(total=Sum('cost'))['total'] or Decimal('0')
    entries_total = other_entries.aggregate(total=Sum('cost'))['total'] or Decimal('0')

    return render(request, 'tracker/report.html', {
        'grand_total': services_total + entries_total,
        'services_total': services_total,
        'services_count': service_entries.count(),
        'entries_total': entries_total,
        'entries_count': other_entries.count(),
    })


@login_required
def export_csv(request):
    """Download all maintenance entries as a CSV file (UTF-8, Excel-friendly)."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="odotracker_entries.csv"'
    # UTF-8 BOM so spreadsheet apps detect encoding correctly.
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Name', 'Date (UTC)', 'Kilometers', 'Cost', 'Reason', 'Created At (UTC)'])
    for entry in MaintenanceEntry.objects.order_by('date'):
        writer.writerow([
            entry.name,
            entry.date.isoformat(),
            entry.kilometers,
            f'{entry.cost:.2f}',
            entry.reason,
            entry.created_at.isoformat(),
        ])
    return response


@login_required
def export_backup(request):
    """Download a full database backup as a Django JSON fixture."""
    buffer = io.StringIO()
    try:
        call_command(
            'dumpdata',
            '--natural-foreign',
            '--natural-primary',
            '--exclude', 'sessions',
            '--exclude', 'contenttypes',
            indent=2,
            stdout=buffer,
        )
    except CommandError as exc:
        messages.error(request, f'Could not generate backup: {exc}')
        return redirect('index')

    stamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f'odotracker_backup_{stamp}.json'
    response = HttpResponse(buffer.getvalue(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _import_sort_key(obj):
    """Order backup objects so FK targets are imported before their dependents."""
    if not isinstance(obj, dict):
        return len(IMPORT_ORDER)
    try:
        return IMPORT_ORDER.index(obj.get('model'))
    except ValueError:
        return len(IMPORT_ORDER)


def _import_defaults(label, fields):
    """Map a fixture's fields to model defaults for update_or_create."""
    if label == 'tracker.part':
        return {
            'name': fields.get('name', ''),
            'interval_km': fields.get('interval_km'),
            'interval_months': fields.get('interval_months'),
        }
    if label == 'tracker.maintenanceentry':
        return {
            'name': fields.get('name', ''),
            'kilometers': fields.get('kilometers', 0),
            'cost': fields.get('cost', 0),
            'date': fields.get('date'),
            'reason': fields.get('reason', ''),
        }
    # tracker.servicerecord
    return {
        'part_id': fields.get('part'),
        'entry_id': fields.get('entry'),
    }


@require_POST
@login_required
def import_backup(request):
    """Restore tracker data from an uploaded backup fixture.

    For safety the import is restricted to the ``tracker`` app: only Part,
    MaintenanceEntry and ServiceRecord objects are written back, wrapped in a
    single atomic transaction so a malformed file cannot leave the database
    half-changed. A complete restore (including auth users) remains possible
    from the CLI with ``python manage.py loaddata backup.json``.
    """
    uploaded = request.FILES.get('backup_file')
    if not uploaded:
        messages.error(request, 'No file was selected.')
        return redirect('index')

    if uploaded.size > IMPORT_MAX_BYTES:
        messages.error(request, f'File is too large (max {IMPORT_MAX_BYTES // (1024 * 1024)} MB).')
        return redirect('index')

    if not uploaded.name.lower().endswith('.json'):
        messages.error(request, 'Only .json backups exported by this app are allowed.')
        return redirect('index')

    try:
        raw = uploaded.read().decode('utf-8')
    except UnicodeDecodeError:
        messages.error(request, 'File is not valid UTF-8 text.')
        return redirect('index')

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        messages.error(request, 'File is not valid JSON.')
        return redirect('index')

    if not isinstance(data, list):
        messages.error(request, 'Invalid backup format (expected a JSON array).')
        return redirect('index')

    loaded = 0
    try:
        with transaction.atomic():
            for obj in sorted(data, key=_import_sort_key):
                if not isinstance(obj, dict):
                    raise ValueError('backup contains a non-object entry')
                label = obj.get('model')
                if label not in IMPORT_MODELS:
                    # Silently skip objects from other apps (auth, etc.).
                    continue
                fields = obj.get('fields')
                pk = obj.get('pk')
                if not isinstance(fields, dict) or pk is None:
                    raise ValueError('backup entry is missing pk or fields')
                IMPORT_MODELS[label].objects.update_or_create(
                    pk=pk,
                    defaults=_import_defaults(label, fields),
                )
                loaded += 1
    except (ValueError, TypeError, InvalidOperation) as exc:
        messages.error(request, f'Import failed, no changes were made: {exc}')
        return redirect('index')

    messages.success(request, f'Imported {loaded} records from backup.')
    return redirect('index')
