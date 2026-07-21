from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class MaintenanceEntry(models.Model):
    name = models.CharField(max_length=200)
    kilometers = models.PositiveIntegerField()
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField()
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name_plural = 'maintenance entries'

    def __str__(self):
        return f"{self.name} @ {self.kilometers} km"

    def clean(self):
        super().clean()
        # Skip the odometer rule when km failed field validation (it will be
        # None here); the field's own error already covers that case.
        if self.kilometers is None:
            return
        # Domain rule: the odometer never goes backwards. Enforced in the
        # model so it cannot be bypassed by the admin, fixtures, or a future
        # API. Comparing against the highest recorded km (excluding self so
        # editing an entry doesn't trigger a false positive).
        qs = MaintenanceEntry.objects.exclude(pk=self.pk)
        last = qs.order_by('-kilometers').first()
        if last and self.kilometers < last.kilometers:
            raise ValidationError(
                {'kilometers': f'Odometer cannot go backwards. '
                               f'Last recorded: {last.kilometers:,} km.'}
            )


class Part(models.Model):
    """A car part tracked on a recurring maintenance interval.

    At least one interval must be set; when both are set the part is due as
    soon as EITHER is reached (e.g. air filter: 15,000 km or 12 months).
    """
    name = models.CharField(max_length=200)
    interval_km = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    interval_months = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def interval_label(self):
        """Human-readable intervals, e.g. '15,000 km or 12 months'."""
        labels = []
        if self.interval_km:
            labels.append(f'{self.interval_km:,} km')
        if self.interval_months:
            labels.append(f'{self.interval_months} months')
        return ' or '.join(labels)

    def clean(self):
        super().clean()
        if self.interval_km is None and self.interval_months is None:
            raise ValidationError(
                'Set at least one maintenance interval (kilometers or months).'
            )


class ServiceRecord(models.Model):
    """One performed service of a Part.

    Linked 1:1 to the MaintenanceEntry created when the service was logged;
    km, date, cost and note all live on that entry (single source of truth).
    The FK directions give the deletion semantics for free: deleting the
    entry removes this record, while deleting the part removes only its
    records and keeps the cost entries.
    """
    part = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='services')
    entry = models.OneToOneField(MaintenanceEntry, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.part.name} service @ {self.entry.kilometers:,} km'
