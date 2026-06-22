#!/bin/sh
set -e

if [ "$DEBUG" != "True" ]; then
  python manage.py collectstatic --noinput
fi

python manage.py ensure_superuser

exec "$@"
