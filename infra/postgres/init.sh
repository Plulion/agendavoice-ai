#!/bin/sh
set -eu
: "${APP_DB_PASSWORD:=local_app_change_me}"
: "${MIGRATOR_DB_PASSWORD:=local_migrator_change_me}"
export APP_DB_PASSWORD MIGRATOR_DB_PASSWORD
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$APP_DB_PASSWORD" \
  --set=migrator_password="$MIGRATOR_DB_PASSWORD" \
  --file=/opt/agendavoice/01-roles.sql
