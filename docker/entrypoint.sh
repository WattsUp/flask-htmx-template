#!/bin/sh

set -e

# Clear prometheus dir
prom_dir=${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}
rm -rf $prom_dir
mkdir $prom_dir

database=${DB_PATH:-/data/database.db}

web_key=${DB_WEB_KEY:-web-admin}

is_postgres_url() {
  case "$1" in
  postgres://* | postgresql://*) return 0 ;;
  *) return 1 ;;
  esac
}

if /home/python/.local/bin/flask_htmx_template --database "$database" create; then
  /home/python/.local/bin/flask_htmx_template --database "$database" change-password --new-pass "$web_key"
fi

/home/python/.local/bin/flask_htmx_template --database "$database" migrate

# Start server
export PROMETHEUS_MULTIPROC_DIR=$prom_dir
export DB_PATH="$database"
/home/python/.local/bin/gunicorn -c gunicorn.conf.py "flask_htmx_template.web:create_app()"
