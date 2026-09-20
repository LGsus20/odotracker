from django.contrib import admin
from .models import MaintenanceEntry, MaintenanceGroup, Part, ServiceRecord


@admin.register(MaintenanceEntry)
class MaintenanceEntryAdmin(admin.ModelAdmin):
    list_display = ('name', 'kilometers', 'cost', 'date', 'created_at')


@admin.register(MaintenanceGroup)
class MaintenanceGroupAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = ('name', 'group', 'interval_km', 'interval_months', 'created_at')


@admin.register(ServiceRecord)
class ServiceRecordAdmin(admin.ModelAdmin):
    list_display = ('part', 'entry', 'created_at')
