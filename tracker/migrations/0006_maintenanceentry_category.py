from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0005_maintenancegroup_part_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='maintenanceentry',
            name='category',
            field=models.CharField(
                blank=True,
                choices=[('fuel', 'Fuel')],
                default=None,
                max_length=20,
                null=True,
            ),
        ),
    ]