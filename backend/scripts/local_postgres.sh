#!/usr/bin/env bash
# Disposable loopback test runtime, not included in deployment artifacts.
set -euo pipefail
cd "$(dirname "$0")/../.local"
mkdir -p postgres-runtime
cd postgres-runtime
# The available base-release package is sufficient for isolated compatibility tests.
# Never deploy this extracted runtime; hosted PostgreSQL is provided by Neon.
if [ ! -f root/usr/lib/postgresql/16/bin/postgres ]; then
  apt download postgresql-16=16.2-1ubuntu4 libpq5=16.2-1ubuntu4
  for package in ./*.deb; do dpkg-deb -x "$package" root; done
fi
export LD_LIBRARY_PATH="$PWD/root/usr/lib/x86_64-linux-gnu"
bin="$PWD/root/usr/lib/postgresql/16/bin"
ldd "$bin/postgres"
data=/tmp/spotter-atlas-assessment-pg-55432
if [ ! -f "$data/PG_VERSION" ]; then
  "$bin/initdb" -D "$data" -L "$PWD/root/usr/share/postgresql/16" --locale=C.UTF-8 --encoding=UTF8 --auth=trust -U atlas_test
fi
"$bin/pg_ctl" -D "$data" -l "$PWD/postgres.log" -o "-h 127.0.0.1 -p 55432 -k /tmp -c shared_buffers=32MB -c max_connections=20" start
