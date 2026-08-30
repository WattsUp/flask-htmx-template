#!/bin/sh

set -e

# Clear prometheus dir
prom_dir=${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}
rm -rf "$prom_dir"
mkdir "$prom_dir"

database=${DB_PATH:-/data/database.db}

web_key=${DB_WEB_KEY:-web-admin}
cli=/home/python/.local/bin/flask_htmx_template
database_already_initialized_exit_code=2

is_postgres_url() {
  case "$1" in
  postgres://* | postgresql://* | postgres+*://* | postgresql+*://*)
    return 0
    ;;
  *) return 1 ;;
  esac
}

database_created=false

if is_postgres_url "$database"; then
  if output=$("$cli" --database "$database" create 2>&1); then
    printf '%s\n' "$output"
    database_created=true
  else
    create_status=$?
    printf '%s\n' "$output" >&2
    # NOTE: Keep this status synchronized with the create command's named code.
    if [ "$create_status" -eq "$database_already_initialized_exit_code" ]; then
      echo "Database already exists, using existing"
    else
      exit "$create_status"
    fi
  fi
elif [ -f "$database" ]; then
  echo "Database already exists, using existing"
else
  "$cli" --database "$database" create
  database_created=true
fi

if [ "$database_created" = true ]; then
  "$cli" --database "$database" change-password --new-pass "$web_key"
fi

"$cli" --database "$database" migrate

# Start server
export PROMETHEUS_MULTIPROC_DIR=$prom_dir
export DB_PATH="$database"
/home/python/.local/bin/gunicorn -c gunicorn.conf.py "flask_htmx_template.asgi:create_app()"
