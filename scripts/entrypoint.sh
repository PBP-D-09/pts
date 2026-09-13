#!/bin/sh
set -e

python manage.py migrate --noinput || echo "Migration failed, continuing anyway..."

exec "$@"