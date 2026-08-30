# flask-htmx-template

[![Unit Test][unittest-image]][unittest-url] [![Static Analysis][static-analysis-image]][static-analysis-url] [![Coverage][coverage-image]][coverage-url] [![Latest Version][pypi-image]][pypi-url]

A production-ready Flask + HTMX template for building modern web applications without a JavaScript framework. Clone it, rename it, and ship.

---

## What's Included

| Feature               | Details                                                                         |
| --------------------- | ------------------------------------------------------------------------------- |
| **Authentication**    | Password/session authentication, debug login, and database-backed bearer tokens |
| **Database**          | SQLAlchemy 2 with active-record helpers, PostgreSQL support                     |
| **Migrations**        | Versioned schema migrations with automatic detection on startup                 |
| **Material Design 3** | Icons, dynamic color palettes from a single swatch color + mood selector        |
| **Theme editor**      | Live-preview dialog with hue slider and mood picker, saved to cookies           |
| **HTMX patterns**     | Dialog system, snackbar notifications, partial page swaps, nav components       |
| **JSON API**          | Type-validated JSON endpoints with full error reporting                         |
| **MCP server**        | Authenticated Streamable HTTP endpoint with typed tool registration             |
| **CLI**               | `create`, `migrate`, `backup`, `restore`, `unlock`, `change-password`, `clean`  |
| **Metrics**           | Prometheus exporter on a separate port                                          |
| **Asset pipeline**    | Tailwind CSS v4, JS minification, automatic rebuild on package install          |
| **Testing**           | 100% coverage enforced, migration tests                                         |
| **Docker**            | Multi-stage build, non-root user, configurable via environment variables        |

---

## Project Structure

```
flask_htmx_template/
├── controllers/        # Route handlers (auth, common, items)
├── commands/           # CLI subcommands
├── models/             # SQLAlchemy ORM models
├── migrations/         # Versioned schema migrations
├── templates/          # Jinja2 HTML (shared components + per-controller)
├── static/src/         # Tailwind CSS + JavaScript source
├── static/dist/        # Compiled assets (generated, not committed)
├── web.py              # Flask app factory + extension
├── asgi.py             # Combined Flask + MCP ASGI app factory
├── mcp.py              # MCP server, tool registration, and metrics
├── web_theme.py        # Material Design 3 color generation
└── main.py             # CLI entry point
```

---

## Using This Template

1. Clone or use "Use this template" on GitHub
1. Find and replace `flask_htmx_template` with your project name (files, folders, pyproject.toml)
1. Update the package description in `pyproject.toml` and `main.py`
1. Add your models in `flask_htmx_template/models/`
1. Add your controllers in `flask_htmx_template/controllers/` and register them in `web.py`
1. Update `flask_htmx_template/static/src/css/main.css` fallback theme values if desired

---

## Environment

### Required

- Python 3.12+
- Node 18+ (for Prettier formatters only -- not needed at runtime)
- Vale (for prose linting only -- not needed at runtime)
- Python packages: `sqlalchemy`, `colorama`, `flask`, `flask-assets`, `flask-login`, `argcomplete`, `prometheus-flask-exporter`, `packaging`, `materialyoucolor`, `mcp`, `asgiref`

---

## Installation / Build / Deployment

Install module

```bash
python -m pip install .
# For autocomplete
activate-global-python-argcomplete
```

For development (editable install + pre-commit hooks)

```bash
uv pip install -e .[dev]
# Download the prose-linting styles declared in .vale.ini
vale sync
# Install the default pre-commit and commit-msg hook shims
prek install
# Prettier formatters for Markdown/Jinja/CSS/JS
npm install --save-dev prettier prettier-plugin-tailwindcss prettier-plugin-jinja-template @tailwindcss/typography
```

---

## Usage

```bash
# Create a new database
flask_htmx_template create

# Start the development server
flask --app flask_htmx_template.web run

# Start the combined web and MCP service
uvicorn --factory flask_htmx_template.asgi:create_app --host 127.0.0.1 --port 5000
```

### API bearer token

New databases receive an opaque API token in `ConfigKey.API_BEARER_TOKEN`. Send it
as `Authorization: Bearer <token>` to authenticate API requests. The token is stored
only in the database and isn't issued or validated by an external identity provider.

### Model Context Protocol

The combined ASGI service exposes a stateless Streamable HTTP MCP endpoint at
`http://127.0.0.1:5000/mcp`. Its item tools support the same list, get, create,
update, and delete operations as the HTML and JSON interfaces. The server records
per-tool call count and duration metrics in the web application's Prometheus registry.

The `get_items` response reports `count` as the number of items matching the
`before` filter before `limit` and `offset` are applied. Its `total` is the sum of
the `value` fields in the returned page, rather than the sum across all matches.
Missing item URIs return an MCP tool error with `_meta.errorCode` set to `-32004`
and the safe message `Requested resource was not found.`

Clients can discover stable JSON metadata with `resources/list` and
`resources/read`:

- `flask-htmx-template://metadata/server` identifies the application and version.
- `flask-htmx-template://metadata/capabilities` lists the transport,
  authentication method, tools, and resource URIs.

MCP requests must send the same database-backed API token as the JSON API:

```text
Authorization: Bearer <ConfigKey.API_BEARER_TOKEN>
```

Add tools in a controller's `mcp.py` and decorate each one with `base.mcp_tool`. The
plain Flask development command doesn't expose MCP; use the ASGI command above.

Use the project-local client to inspect a running server without putting the bearer
token in shell history or the process list:

```bash
export BEARER_TOKEN="<ConfigKey.API_BEARER_TOKEN>"
python tools/mcp_connect.py list-tools
python tools/mcp_connect.py list-resources
python tools/mcp_connect.py read-resource flask-htmx-template://metadata/server
python tools/mcp_connect.py read-resource flask-htmx-template://metadata/capabilities
python tools/mcp_connect.py call get_items
```

---

## Docker

```bash
docker run \
  --name flask_htmx_template \
  --detach \
  --publish 8000:8000 \
  --publish 8001:8001 \
  --volume flask_htmx_template-data:/data \
  flask_htmx_template
```

### Configuration

| Env                | Default             | Description                                   |
| ------------------ | ------------------- | --------------------------------------------- |
| `DB_PATH`          | `/data/database.db` | SQLite path or PostgreSQL URL                 |
| `DB_WEB_KEY`       | `web-admin`         | Web password set when creating a new database |
| `WEB_PORT`         | `8000`              | Port to bind server to                        |
| `WEB_PORT_METRICS` | `8001`              | Port to bind metrics server to                |
| `WEB_CONCURRENCY`  | n(CPU) × 2 + 1      | Number of gunicorn workers                    |
| `WEB_N_THREADS`    | `1`                 | Threads per worker                            |
| `WEB_TIMEOUT`      | `30`                | Worker silent timeout (seconds)               |

### Database Query Time Limits

Use `sql.time_limit()` inside an active SQLAlchemy session to bound a specific
query or group of queries:

```python
from sqlalchemy import text

from flask_htmx_template import sql

with database.begin_session() as session:
    with sql.time_limit(session, timeout_ms=2_000):
        result = session.execute(text("SELECT 1")).scalar_one()
```

Timeouts must be positive integers in milliseconds. SQLite limits are
approximate because they're checked between virtual-machine instruction
batches. PostgreSQL applies the limit to each statement in the context. A
PostgreSQL cancellation can leave the transaction aborted, so callers that
catch `TimeoutError` may need to roll it back. Unsupported database drivers
raise `TypeError`.

---

## PostgreSQL Deployment

PostgreSQL is supported as an alternative to SQLite. Connections always use TLS (`sslmode=require`).
`DB_PATH` accepts `postgres://` and `postgresql://` URLs, including optional
SQLAlchemy driver suffixes such as `postgresql+psycopg://`.

### 1. Generate a Self-Signed Certificate

```bash
mkdir -p certs

openssl req -new -x509 -days 3650 -nodes \
  -out certs/server.crt \
  -keyout certs/server.key \
  -subj "/CN=postgres"

# The official postgres Docker image runs as UID/GID 999.
# The key file must be owned by that user or postgres will refuse to start.
sudo chown 999:999 certs/server.crt certs/server.key
chmod 600 certs/server.key
```

### 2. Create a Password Secret

```bash
mkdir -p secrets
python3 -c "import secrets; print(secrets.token_hex())" > secrets/db_password.txt
```

### 3. docker-compose.yml

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
      POSTGRES_DB: appdb
    secrets:
      - db_password
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./certs/server.crt:/var/lib/postgresql/server.crt:ro
      - ./certs/server.key:/var/lib/postgresql/server.key:ro
    command: >
      postgres
        -c ssl=on
        -c ssl_cert_file=/var/lib/postgresql/server.crt
        -c ssl_key_file=/var/lib/postgresql/server.key
    restart: unless-stopped

  app:
    image: flask_htmx_template
    depends_on:
      - postgres
    environment:
      DB_PATH: postgresql://appuser:password@postgres:5432/appdb
      DB_WEB_KEY: web-admin
    secrets:
      - db_password
    ports:
      - "8000:8000"
      - "8001:8001"
    restart: unless-stopped

secrets:
  db_password:
    file: ./secrets/db_password.txt

volumes:
  postgres-data:
```

The app uses `sslmode=require` by default so no extra configuration is needed on the app side. The schema is created automatically on first start; subsequent starts skip creation and run migrations only.

---

## Running Tests

```bash
# All tests
python -m pytest

# Coverage report (must reach 100%)
python -m coverage run && python -m coverage report
```

Tests don't cover front-end behavior or browser interaction.

---

## Development

Code style follows the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).

### Linters

- `ruff` -- Python (all rules enabled)
- `basedpyright` -- strict type checking
- `djlint` -- Jinja templates
- `codespell` -- spell checking
- `vale` -- Markdown, reStructuredText, AsciiDoc, and plain text

### Formatters

- `black` + `isort` -- Python
- `prettier` -- Markdown, Jinja, CSS, JS
- `taplo` -- TOML

### Tools

```bash
./tools/formatters.sh      # Run all formatters
./tools/linters.sh         # Run all linters
./tools/run_tailwindcss.sh # Watch and rebuild Tailwind CSS
```

---

## Versioning

Follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html), implemented via git tags with `setuptools-scm`.

[pypi-image]: https://img.shields.io/pypi/v/flask-htmx-template.svg
[pypi-url]: https://pypi.org/project/flask-htmx-template/
[unittest-image]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/test.yml/badge.svg
[unittest-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/test.yml
[static-analysis-image]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/static-analysis.yml/badge.svg
[static-analysis-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/static-analysis.yml
[coverage-image]: https://gist.githubusercontent.com/WattsUp/36d9705addcd44fb0fccec1d23dc1338/raw/flask-htmx-template__heads_main.svg
[coverage-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/coverage.yml
