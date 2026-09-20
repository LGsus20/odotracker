from datetime import date, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import GroupForm
from .models import MaintenanceEntry, MaintenanceGroup, Part, ServiceRecord
from .services import (
    DUE_SOON_DAYS,
    DUE_SOON_KM,
    SORT_GROUPS,
    STATE_DUE_SOON,
    STATE_NO_SERVICE,
    STATE_OK,
    STATE_OVERDUE,
    add_months,
    build_part_statuses,
    part_status,
)

TODAY = date(2026, 7, 20)


def make_entry(kilometers, on=TODAY, name='Entry', cost='0', reason=''):
    """Create an entry at noon UTC of the given date."""
    return MaintenanceEntry.objects.create(
        name=name,
        kilometers=kilometers,
        cost=cost,
        date=timezone.datetime(on.year, on.month, on.day, 12, 0, tzinfo=dt_timezone.utc),
        reason=reason,
    )


def make_service(part, kilometers, on, **entry_kwargs):
    """Log a service the same way the view does: entry + linked record."""
    return ServiceRecord.objects.create(
        part=part,
        entry=make_entry(kilometers, on, name=part.name, **entry_kwargs),
    )


class PartModelTests(TestCase):
    def test_related_actions_can_share_a_group(self):
        group = MaintenanceGroup.objects.create(name='Brake fluid')
        inspection = Part.objects.create(
            name='Inspection', group=group, interval_km=10000, interval_months=6
        )
        replacement = Part.objects.create(
            name='Replacement', group=group, interval_km=40000, interval_months=24
        )

        self.assertEqual(list(group.parts.order_by('name')), [inspection, replacement])
        self.assertNotEqual(inspection.interval_km, replacement.interval_km)

    def test_group_form_rejects_case_insensitive_duplicate(self):
        MaintenanceGroup.objects.create(name='Brake fluid')
        form = GroupForm({'name': ' brake FLUID '})
        self.assertFalse(form.is_valid())
        self.assertIn('already exists', str(form.errors['name']))

    def test_requires_at_least_one_interval(self):
        with self.assertRaises(ValidationError):
            Part(name='Oil').full_clean()

    def test_km_only_is_valid(self):
        Part(name='Oil', interval_km=10000).full_clean()

    def test_months_only_is_valid(self):
        Part(name='Oil', interval_months=12).full_clean()

    def test_intervals_must_be_at_least_one(self):
        with self.assertRaises(ValidationError):
            Part(name='Oil', interval_km=0).full_clean()
        with self.assertRaises(ValidationError):
            Part(name='Oil', interval_months=0).full_clean()

    def test_interval_label(self):
        self.assertEqual(Part(name='x', interval_km=15000).interval_label, '15,000 km')
        self.assertEqual(Part(name='x', interval_months=12).interval_label, '12 months')
        self.assertEqual(
            Part(name='x', interval_km=15000, interval_months=12).interval_label,
            '15,000 km or 12 months',
        )


class AddMonthsTests(TestCase):
    def test_simple_shift(self):
        self.assertEqual(add_months(date(2025, 11, 25), 6), date(2026, 5, 25))

    def test_year_rollover(self):
        self.assertEqual(add_months(date(2025, 12, 15), 2), date(2026, 2, 15))

    def test_day_clamped_to_month_end(self):
        self.assertEqual(add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_leap_year_clamp(self):
        self.assertEqual(add_months(date(2024, 1, 31), 1), date(2024, 2, 29))


class PartStatusTests(TestCase):
    def setUp(self):
        self.part = Part.objects.create(name='Air filter', interval_km=15000, interval_months=12)

    def test_no_services(self):
        status = part_status(self.part, [], current_km=20000, today=TODAY)
        self.assertEqual(status.state, STATE_NO_SERVICE)
        self.assertIsNone(status.last_service)
        self.assertIsNone(status.km)
        self.assertIsNone(status.time)

    def test_ok(self):
        service = make_service(self.part, 10000, TODAY - timedelta(days=30))
        status = part_status(self.part, [service], current_km=13200, today=TODAY)
        self.assertEqual(status.state, STATE_OK)
        self.assertEqual(status.km.remaining, 11800)  # 15000 - 3200
        self.assertEqual(status.km.progress, 21)  # 3200 / 15000
        self.assertEqual(status.km.due_label, '25,000 km')

    def test_due_soon_by_km(self):
        service = make_service(self.part, 10000, TODAY - timedelta(days=30))
        status = part_status(self.part, [service], current_km=10000 + 15000 - DUE_SOON_KM, today=TODAY)
        self.assertEqual(status.state, STATE_DUE_SOON)

    def test_overdue_by_km(self):
        service = make_service(self.part, 10000, TODAY - timedelta(days=30))
        status = part_status(self.part, [service], current_km=26000, today=TODAY)
        self.assertEqual(status.state, STATE_OVERDUE)
        self.assertEqual(status.km.progress, 100)  # clamped

    def test_due_soon_by_time(self):
        service = make_service(self.part, 10000, add_months(TODAY, -12) + timedelta(days=DUE_SOON_DAYS - 5))
        status = part_status(self.part, [service], current_km=10000, today=TODAY)
        self.assertEqual(status.state, STATE_DUE_SOON)

    def test_overdue_by_time(self):
        service = make_service(self.part, 10000, add_months(TODAY, -13))
        status = part_status(self.part, [service], current_km=10000, today=TODAY)
        self.assertEqual(status.state, STATE_OVERDUE)

    def test_canonical_example(self):
        """The example from the feature spec: services at 13,045 km (05/05/2025)
        and 14,081 km (25/11/2025); interval 1,500 km or 6 months ->
        next due 15,581 km or 25/05/2026."""
        part = Part.objects.create(name='Spec part', interval_km=1500, interval_months=6)
        s1 = make_service(part, 13045, date(2025, 5, 5))
        s2 = make_service(part, 14081, date(2025, 11, 25))
        status = part_status(part, [s1, s2], current_km=14081, today=date(2025, 11, 25))
        self.assertEqual(status.last_service, s2)
        self.assertEqual(status.km.due_label, '15,581 km')
        self.assertEqual(status.time.due_label, '25/05/2026')

    def test_backfilled_service_does_not_steal_baseline(self):
        """A back-filled record (older km AND older date, logged after the
        newest service) leaves the newest service as the baseline."""
        newest = make_service(self.part, 10000, TODAY - timedelta(days=10))
        make_service(self.part, 9000, TODAY - timedelta(days=50))  # back-fill
        status = part_status(self.part, list(self.part.services.all()), current_km=12000, today=TODAY)
        self.assertEqual(status.last_service, newest)
        self.assertEqual(status.km.due_label, '25,000 km')

    def test_build_part_statuses_sorts_by_urgency(self):
        # setUp's part has no services, so it sorts last as 'no_service'.
        ok_part = Part.objects.create(name='B ok', interval_km=100000)
        overdue_part = Part.objects.create(name='A overdue', interval_km=1000)
        make_service(ok_part, 0, TODAY)
        make_service(overdue_part, 0, TODAY)
        statuses = build_part_statuses(Part.objects.all(), current_km=5000, today=TODAY)
        self.assertEqual(
            [s.state for s in statuses],
            [STATE_OVERDUE, STATE_OK, STATE_NO_SERVICE],
        )
        self.assertEqual(statuses[0].part, overdue_part)

    def test_group_sort_orders_groups_alphabetically_and_parts_by_urgency(self):
        alpha = MaintenanceGroup.objects.create(name='Alpha')
        beta = MaintenanceGroup.objects.create(name='Beta')
        alpha_ok = Part.objects.create(name='Z action', group=alpha, interval_km=100000)
        alpha_overdue = Part.objects.create(name='A action', group=alpha, interval_km=1000)
        beta_overdue = Part.objects.create(name='B action', group=beta, interval_km=1000)
        make_service(alpha_ok, 0, TODAY)
        make_service(alpha_overdue, 0, TODAY)
        make_service(beta_overdue, 0, TODAY)

        statuses = build_part_statuses(
            Part.objects.all(), current_km=5000, today=TODAY, sort_mode=SORT_GROUPS
        )

        self.assertEqual(
            [status.part for status in statuses],
            [alpha_overdue, alpha_ok, beta_overdue, self.part],
        )


class DeletionTests(TestCase):
    def setUp(self):
        self.part = Part.objects.create(name='Oil', interval_km=10000)

    def test_deleting_entry_cascades_to_record(self):
        service = make_service(self.part, 5000, TODAY)
        service.entry.delete()
        self.assertEqual(ServiceRecord.objects.count(), 0)

    def test_deleting_record_keeps_entry(self):
        # The ORM-level path used when a part is deleted.
        service = make_service(self.part, 5000, TODAY)
        entry_pk = service.entry.pk
        service.delete()
        self.assertTrue(MaintenanceEntry.objects.filter(pk=entry_pk).exists())

    def test_deleting_part_removes_records_but_keeps_entries(self):
        make_service(self.part, 5000, TODAY)
        make_service(self.part, 14000, TODAY)
        self.part.delete()
        self.assertEqual(ServiceRecord.objects.count(), 0)
        self.assertEqual(MaintenanceEntry.objects.count(), 2)


class MaintenanceViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='x' * 14)
        self.client.force_login(self.user)
        self.part = Part.objects.create(name='Oil', interval_km=10000, interval_months=6)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse('maintenance'))
        self.assertRedirects(response, '/login/?next=/maintenance/')

    def test_maintenance_defaults_to_urgency_sort(self):
        response = self.client.get(reverse('maintenance'))
        self.assertEqual(response.context['sort_mode'], 'urgency')

    def test_maintenance_accepts_group_sort(self):
        response = self.client.get(reverse('maintenance'), {'sort': 'groups'})
        self.assertEqual(response.context['sort_mode'], 'groups')

    def test_maintenance_rejects_unknown_sort(self):
        response = self.client.get(reverse('maintenance'), {'sort': 'unknown'})
        self.assertEqual(response.context['sort_mode'], 'urgency')

    def test_add_part(self):
        response = self.client.post(reverse('maintenance'), {
            'action': 'add_part',
            'name': 'Brake pads',
            'interval_km': '30000',
            'interval_months': '',
        })
        self.assertRedirects(response, reverse('maintenance'))
        self.assertTrue(Part.objects.filter(name='Brake pads', interval_km=30000).exists())

    def test_add_part_creates_shared_group(self):
        group = MaintenanceGroup.objects.create(name='Brake fluid')
        response = self.client.post(reverse('maintenance'), {
            'action': 'add_part',
            'group': str(group.pk),
            'name': 'Inspection',
            'interval_km': '10000',
            'interval_months': '6',
        })
        self.assertRedirects(response, reverse('maintenance'))
        part = Part.objects.get(name='Inspection')
        self.assertEqual(part.group.name, 'Brake fluid')

    def test_add_group(self):
        response = self.client.post(reverse('maintenance'), {
            'action': 'add_group',
            'name': ' Brake fluid ',
        })
        self.assertRedirects(response, reverse('maintenance'))
        self.assertTrue(MaintenanceGroup.objects.filter(name='Brake fluid').exists())

    def test_add_part_without_intervals_shows_error(self):
        response = self.client.post(reverse('maintenance'), {
            'action': 'add_part', 'name': 'Brake pads',
            'interval_km': '', 'interval_months': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Part.objects.filter(name='Brake pads').exists())

    def test_log_service_creates_entry_and_record(self):
        response = self.client.post(reverse('maintenance'), {
            'action': 'log_service',
            'part': str(self.part.pk),
            'kilometers': '21000',
            'cost': '49.99',
            'date': '2026-07-20T10:30',
            'note': 'OEM filter',
        })
        self.assertRedirects(response, reverse('maintenance'))
        record = ServiceRecord.objects.get(part=self.part)
        self.assertEqual(record.entry.kilometers, 21000)
        self.assertEqual(str(record.entry.cost), '49.99')
        self.assertEqual(record.entry.reason, 'OEM filter')
        self.assertEqual(record.entry.name, 'Oil')

    def test_log_service_defaults_cost_to_zero(self):
        self.client.post(reverse('maintenance'), {
            'action': 'log_service',
            'part': str(self.part.pk),
            'kilometers': '21000',
            'cost': '',
            'date': '2026-07-20T10:30',
            'note': '',
        })
        self.assertEqual(str(ServiceRecord.objects.get().entry.cost), '0.00')

    def test_log_service_bypasses_odometer_rule(self):
        """Back-filling a service at an older km must succeed even though a
        higher odometer reading already exists (unlike manual entries)."""
        make_entry(30000, TODAY)
        response = self.client.post(reverse('maintenance'), {
            'action': 'log_service',
            'part': str(self.part.pk),
            'kilometers': '15000',
            'cost': '',
            'date': '2026-07-01T09:00',
            'note': '',
        })
        self.assertRedirects(response, reverse('maintenance'))
        self.assertTrue(ServiceRecord.objects.filter(entry__kilometers=15000).exists())

    def test_delete_service_removes_entry_too(self):
        service = make_service(self.part, 21000, TODAY)
        entry_pk = service.entry.pk
        response = self.client.post(reverse('delete_service', args=[service.pk]))
        self.assertRedirects(response, reverse('maintenance'))
        self.assertFalse(ServiceRecord.objects.exists())
        self.assertFalse(MaintenanceEntry.objects.filter(pk=entry_pk).exists())

    def test_delete_entry_removes_service_record(self):
        service = make_service(self.part, 21000, TODAY)
        response = self.client.post(reverse('delete_entry', args=[service.entry.pk]))
        self.assertRedirects(response, reverse('index'))
        self.assertFalse(ServiceRecord.objects.exists())

    def test_edit_part(self):
        response = self.client.post(reverse('edit_part', args=[self.part.pk]), {
            'name': 'Engine oil',
            'interval_km': '7500',
            'interval_months': '6',
        })
        self.assertRedirects(response, reverse('maintenance'))
        self.part.refresh_from_db()
        self.assertEqual((self.part.name, self.part.interval_km), ('Engine oil', 7500))

    def test_delete_part_keeps_cost_entries(self):
        make_service(self.part, 21000, TODAY)
        response = self.client.post(reverse('delete_part', args=[self.part.pk]))
        self.assertRedirects(response, reverse('maintenance'))
        self.assertFalse(Part.objects.exists())
        self.assertEqual(MaintenanceEntry.objects.count(), 1)


class LoginRateLimitTests(TestCase):
    """django-axes locks the account after AXES_FAILURE_LIMIT bad attempts."""

    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='x' * 14)

    def _bad_login(self):
        return self.client.post(reverse('login'), {
            'username': 'tester', 'password': 'wrong-password',
        })

    def test_lockout_after_repeated_failures(self):
        # Failures below the limit just re-render the login page.
        for _ in range(settings.AXES_FAILURE_LIMIT - 1):
            self.assertEqual(self._bad_login().status_code, 200)

        # Reaching the limit locks the account (429 Too Many Requests)...
        self.assertEqual(self._bad_login().status_code, 429)

        # ...and even the CORRECT password is refused while locked out.
        response = self.client.post(reverse('login'), {
            'username': 'tester', 'password': 'x' * 14,
        })
        self.assertEqual(response.status_code, 429)


class ReportViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='x' * 14)
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse('report'))
        self.assertRedirects(response, '/login/?next=/report/')

    def test_totals_split_services_vs_other_entries(self):
        part = Part.objects.create(name='Oil', interval_km=10000)
        make_service(part, 21000, TODAY, cost='25.50')
        make_entry(21100, TODAY, name='Gasolina', cost='50.00')
        make_entry(21155, TODAY, name='Car wash', cost='30.00')

        response = self.client.get(reverse('report'))
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx['grand_total'], Decimal('105.50'))
        self.assertEqual(ctx['services_total'], Decimal('25.50'))
        self.assertEqual(ctx['services_count'], 1)
        self.assertEqual(ctx['entries_total'], Decimal('80.00'))
        self.assertEqual(ctx['entries_count'], 2)

    def test_empty_state(self):
        response = self.client.get(reverse('report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['grand_total'], Decimal('0'))
        self.assertContains(response, 'No spending recorded yet')
