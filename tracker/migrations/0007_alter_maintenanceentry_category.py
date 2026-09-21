from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0006_maintenanceentry_category'),
    ]

    operations = [
        migrations.AlterField(
            model_name='maintenanceentry',
            name='category',
            field=models.CharField(
                blank=True,
                choices=[
                    ('fuel', 'Fuel'),
                    ('credit', 'Credit payments'),
                    ('paperwork', 'Vehicle Paperwork'),
                ],
                default=None,
                max_length=20,
                null=True,
            ),
        ),
    ]