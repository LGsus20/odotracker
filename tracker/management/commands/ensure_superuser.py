import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import OperationalError


class Command(BaseCommand):
    help = 'Create or update the superuser from DJANGO_SUPERUSER_* env vars.'

    def handle(self, *args, **options):
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', '').strip()
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '').strip()

        if not username or not password:
            self.stdout.write('Skipping superuser: DJANGO_SUPERUSER_USERNAME '
                              'or DJANGO_SUPERUSER_PASSWORD not set.')
            return

        User = get_user_model()
        try:
            user, created = User.objects.update_or_create(
                username=username,
                defaults={'email': email, 'is_staff': True, 'is_superuser': True},
            )
            user.set_password(password)
            user.save()
        except OperationalError:
            self.stdout.write(self.style.WARNING(
                'Skipping superuser: auth tables not found. '
                'Run "python manage.py migrate" first.'))
            return

        action = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{action} superuser "{username}".'))
