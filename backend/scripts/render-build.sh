#!/usr/bin/env bash
set -euo pipefail
python -m pip install --no-cache-dir -r requirements.deploy.txt
python manage.py check --deploy --fail-level ERROR
# W005/W021 remain visible: managed-domain subdomain/preload opt-in is intentional.
