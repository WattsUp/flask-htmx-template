#!/bin/sh

set -e

# Clear prometheus dir
prom_dir=${PROMETHEUS_MULTIPROC_DIR:-/tmp/prometheus}
rm -rf $prom_dir
mkdir $prom_dir

key_file=${DB_KEY_PATH:-/data/.key.secret}
database=${DB_PATH:-/data/database.db}

web_key=${DB_WEB_KEY:-web-admin}

is_postgres_url() {
  case "$1" in
    postgres://*|postgresql://*) return 0 ;;
    *) return 1 ;;
  esac
}

if is_postgres_url "$database"; then
  # Postgres: credentials must be supplied via DB_KEY_PATH.
  # Attempt schema creation on first run; a non-zero exit means already initialized.
  if /home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" create; then
    echo -e "db:\nweb:$web_key" >new.key
    /home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" change-password --new-pass-file new.key
    rm new.key
    /home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" clean
  fi
else
  # SQLite: create database file on first run.
  if [ ! -f "$database" ]; then
    if [ ! -f "$key_file" ]; then
      python3 -c "import secrets;print(secrets.token_hex())" >"$key_file"
    fi

    /home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" create

    echo -e "db:\nweb:$web_key" >new.key
    /home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" change-password --new-pass-file new.key
    rm new.key
    /home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" clean
  fi
fi

/home/python/.local/bin/flask_htmx_template --database "$database" --pass-file "$key_file" migrate

# Start server
export PROMETHEUS_MULTIPROC_DIR=$prom_dir
export DB_PATH="$database"
export DB_KEY_PATH="$key_file"
/home/python/.local/bin/gunicorn -c gunicorn.conf.py "flask_htmx_template.web:create_app()"
