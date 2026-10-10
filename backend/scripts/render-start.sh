#!/usr/bin/env bash
set -euo pipefail
# Free services have no pre-deploy command or shell. Migrate at single-instance start.
python manage.py migrate --noinput
python manage.py purge_expired_analyses
python manage.py initialize_assessment_budget
exec gunicorn config.wsgi:application --config gunicorn.conf.py
