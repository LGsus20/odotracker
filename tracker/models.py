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
