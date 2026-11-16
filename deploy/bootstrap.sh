#!/usr/bin/env bash
# Prepares the database and starts the API.
#
# 1. Waits until Postgres answers at DATABASE_URL.
# 2. If the database has not been restored yet, downloads fires.dump (Google Drive by default),
#    checks its sha256 and restores it with pg_restore.
# 3. Starts the API with uvicorn.
#
# Works inside the container (Railway, Docker) and on any Linux machine with Postgres:
#   DATABASE_URL=postgresql:///fires PYTHON=.venv/bin/python bash deploy/bootstrap.sh
set -euo pipefail

DATABASE_URL="${DATABASE_URL:-postgresql:///fires}"
DUMP_URL="${DUMP_URL:-https://drive.usercontent.google.com/download?id=1k76VcDl7RQq5hpKhayTXl_3URC_kQIAl&export=download&confirm=t}"
DUMP_SHA256="${DUMP_SHA256:-5382be98a0221e528995f2d44470d03f0e2bcc2307bc0a61410744c745aa7e71}"
DUMP_PATH="${DUMP_PATH:-/tmp/fires.dump}"
PYTHON="${PYTHON:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

log() { echo "[bootstrap] $*"; }

if [ -n "${RAILWAY_ENVIRONMENT:-}" ] && [ "$DATABASE_URL" = "postgresql:///fires" ]; then
  log "DATABASE_URL is missing or empty: on Railway set it to \${{Postgres.DATABASE_URL}}."
  exit 1
fi

log "Waiting for Postgres…"
for i in $(seq 1 60); do
  if psql "$DATABASE_URL" -Atqc "select 1" >/dev/null 2>&1; then break; fi
  if [ "$i" -eq 60 ]; then log "Postgres does not answer at DATABASE_URL"; exit 1; fi
  sleep 2
done

# bootstrap_ok is created only after pg_restore finished cleanly. Tables without that marker
# mean the previous restore stopped halfway (e.g. disk full): they are dropped and it starts over.
if [ "$(psql "$DATABASE_URL" -Atqc "select to_regclass('public.bootstrap_ok') is not null")" = "t" ]; then
  log "The database already has the data: nothing to download."
else
  if [ "$(psql "$DATABASE_URL" -Atqc "select count(*) from pg_tables where schemaname = 'public'")" != "0" ]; then
    log "Previous restore was incomplete: dropping the tables and restoring again."
    psql "$DATABASE_URL" -qc "drop schema public cascade; create schema public;"
  fi
  if [ ! -s "$DUMP_PATH" ] || ! echo "$DUMP_SHA256  $DUMP_PATH" | sha256sum -c --status; then
    log "Downloading fires.dump (132 MB)…"
    curl -fL --retry 3 -o "$DUMP_PATH" "$DUMP_URL"
  fi
  if ! echo "$DUMP_SHA256  $DUMP_PATH" | sha256sum -c --status; then
    log "The dump sha256 does not match: incomplete download or wrong link."
    exit 1
  fi
  log "Restoring the database (about 2 minutes)…"
  pg_restore --no-owner --no-privileges --exit-on-error -d "$DATABASE_URL" "$DUMP_PATH"
  psql "$DATABASE_URL" -qc "create table bootstrap_ok as select now() as restored_at"
  log "Database ready: $(psql "$DATABASE_URL" -Atqc "select count(*) from events") events."
  [ "${KEEP_DUMP:-0}" = "1" ] || rm -f "$DUMP_PATH"
fi

log "Starting the API at http://$HOST:$PORT (docs at /docs)…"
exec "$PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
