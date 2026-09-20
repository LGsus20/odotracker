from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracker', '0003_part_servicerecord'),
    ]

    operations = [
        migrations.AddField(
            model_name='part',
            name='note',
            field=models.TextField(blank=True, default='', max_length=524),
        ),
    ]