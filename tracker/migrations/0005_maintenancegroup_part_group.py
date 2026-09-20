from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0004_part_note'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaintenanceGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='part',
            name='group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='parts',
                to='tracker.maintenancegroup',
            ),
        ),
    ]