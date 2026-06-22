from django.contrib import admin
from .models import MaintenanceEntry


@admin.register(MaintenanceEntry)
class MaintenanceEntryAdmin(admin.ModelAdmin):
    list_display = ('name', 'kilometers', 'cost', 'date', 'created_at')
