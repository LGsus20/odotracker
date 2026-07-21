from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('delete/<int:pk>/', views.delete_entry, name='delete_entry'),
    path('maintenance/', views.maintenance, name='maintenance'),
    path('maintenance/part/<int:pk>/edit/', views.edit_part, name='edit_part'),
    path('maintenance/part/<int:pk>/delete/', views.delete_part, name='delete_part'),
    path('maintenance/service/<int:pk>/delete/', views.delete_service, name='delete_service'),
    path('report/', views.report, name='report'),
    path('export/csv/', views.export_csv, name='export_csv'),
    path('export/backup/', views.export_backup, name='export_backup'),
    path('import/backup/', views.import_backup, name='import_backup'),
]
