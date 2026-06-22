from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import MaintenanceEntry


@login_required
def index(request):
    errors = []

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        kilometers_raw = request.POST.get('kilometers', '')
        cost_raw = request.POST.get('cost', '')
        date_raw = request.POST.get('date', '')
        reason = (request.POST.get('reason') or '').strip()

        # --- Validation ---
        if not name:
            errors.append('Name is required.')
        if not date_raw:
            errors.append('Date is required.')

        date = None
        if date_raw:
            try:
                date = parse_datetime(date_raw)
            except ValueError:
                date = None
            if date is None:
                errors.append('Date must be a valid date and time.')
            elif timezone.is_naive(date):
                date = timezone.make_aware(date, timezone.get_current_timezone())

        kilometers = None
        try:
            kilometers = int(kilometers_raw)
            if kilometers < 0:
                errors.append('Kilometers must be a positive number.')
        except (ValueError, TypeError):
            errors.append('Kilometers must be a whole number.')

        cost = None
        try:
            cost = Decimal(cost_raw)
            if cost < 0:
                errors.append('Cost must be a positive number.')
        except (InvalidOperation, TypeError):
            errors.append('Cost must be a valid number.')

        # Odometer validation: new entry must be >= highest recorded km
        if kilometers is not None and kilometers >= 0:
            last = MaintenanceEntry.objects.order_by('-kilometers').first()
            if last and kilometers < last.kilometers:
                errors.append(
                    f'Odometer cannot go backwards. Last recorded: {last.kilometers:,} km.'
                )

        if not errors:
            MaintenanceEntry.objects.create(
                name=name,
                kilometers=kilometers,
                cost=cost,
                date=date,
                reason=reason,
            )
            return redirect('index')

    entries = MaintenanceEntry.objects.all()
    latest = MaintenanceEntry.objects.order_by('-kilometers').first()
    current_km = latest.kilometers if latest else 0

    return render(request, 'tracker/index.html', {
        'entries': entries,
        'errors': errors,
        'current_km': current_km,
    })


@require_POST
@login_required
def delete_entry(request, pk):
    if request.method == 'POST':
        entry = get_object_or_404(MaintenanceEntry, pk=pk)
        entry.delete()
    return redirect('index')
