#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
base="$PWD/.local/postgres-runtime"
export LD_LIBRARY_PATH="$base/root/usr/lib/x86_64-linux-gnu"
bin="$base/root/usr/lib/postgresql/16/bin"
data=/tmp/spotter-atlas-assessment-pg-55432
if [ ! -f "$data/server.crt" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj /CN=localhost -addext 'subjectAltName=DNS:localhost,IP:127.0.0.1' -keyout "$data/server.key" -out "$data/server.crt" 2>/dev/null
  chmod 600 "$data/server.key"
  "$bin/pg_ctl" -D "$data" stop -m fast
  "$bin/pg_ctl" -D "$data" -l "$base/postgres.log" -o "-h 127.0.0.1 -p 55432 -k /tmp -c ssl=on -c ssl_cert_file=$data/server.crt -c ssl_key_file=$data/server.key -c shared_buffers=32MB -c max_connections=20" start
fi
runtime=/tmp/spotter-atlas-release-venv
if [ ! -f "$runtime/bin/python" ]; then python3 -m venv "$runtime"; fi
"$runtime/bin/python" -m pip install --no-compile -r requirements.lock.txt
export DATABASE_URL="postgresql://atlas_test@127.0.0.1:55432/atlas_release?sslmode=verify-full&sslrootcert=$data/server.crt"
"$runtime/bin/python" - <<'PY'
import psycopg
with psycopg.connect('postgresql://atlas_test@127.0.0.1:55432/postgres?sslmode=verify-full&sslrootcert=/tmp/spotter-atlas-assessment-pg-55432/server.crt', autocommit=True) as conn:
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname='atlas_release'").fetchone(): conn.execute('CREATE DATABASE atlas_release')
    print('Verified local PostgreSQL TLS connection:', conn.info.ssl_in_use if hasattr(conn.info,'ssl_in_use') else conn.pgconn.ssl_in_use)
PY
"$runtime/bin/python" manage.py migrate --noinput
"$runtime/bin/python" -m pytest -q --basetemp=/tmp/spotter-atlas-pytest-postgres | tee ../docs/implementation/evidence/deployment-preparation/backend-postgres.txt
"$runtime/bin/python" scripts/benchmark_release.py
