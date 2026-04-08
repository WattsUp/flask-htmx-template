# flask-htmx-template

[![Unit Test][unittest-image]][unittest-url] [![Static Analysis][static-analysis-image]][static-analysis-url] [![Coverage][coverage-image]][coverage-url] [![Latest Version][pypi-image]][pypi-url]

A production-ready Flask + HTMX template for building modern web applications without a JavaScript framework. Clone it, rename it, and ship.

---

## What's Included

| Feature               | Details                                                                        |
| --------------------- | ------------------------------------------------------------------------------ |
| **Authentication**    | Flask-Login with secure session cookies, `@login_exempt` decorator             |
| **Database**          | SQLAlchemy 2 with active-record helpers, optional SQLCipher encryption         |
| **Migrations**        | Versioned schema migrations with auto-detection on startup                     |
| **Material Design 3** | Icons, dynamic color palettes from a single swatch color + mood selector       |
| **Theme editor**      | Live-preview dialog with hue slider and mood picker, saved to cookies          |
| **HTMX patterns**     | Dialog system, snackbar notifications, partial page swaps, nav components      |
| **JSON API**          | Type-validated JSON endpoints with full error reporting                        |
| **CLI**               | `create`, `migrate`, `backup`, `restore`, `unlock`, `change-password`, `clean` |
| **Metrics**           | Prometheus exporter on a separate port                                         |
| **Asset pipeline**    | Tailwind CSS v4, JS minification, automatic rebuild on package install         |
| **Testing**           | 100% coverage enforced, migration tests                                        |
| **Docker**            | Multi-stage build, non-root user, configurable via environment variables       |

---

## Project Structure

```
flask_htmx_template/
├── controllers/        # Route handlers (auth, common, items)
├── commands/           # CLI subcommands
├── models/             # SQLAlchemy ORM models
├── migrations/         # Versioned schema migrations
├── encryption/         # Optional AES database encryption
├── templates/          # Jinja2 HTML (shared components + per-controller)
├── static/src/         # Tailwind CSS + JavaScript source
├── static/dist/        # Compiled assets (generated, not committed)
├── web.py              # Flask app factory + extension
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
- Node 18+ (for Prettier formatters only — not needed at runtime)
- Python packages: `sqlalchemy`, `colorama`, `flask`, `flask-assets`, `flask-login`, `argcomplete`, `prometheus-flask-exporter`, `packaging`, `materialyoucolor`

### Optional — Encryption

Encrypts the SQLite database file using SQLCipher.

- `sqlcipher3-binary`, `Cipher`, `pycryptodome`

---

## Installation / Build / Deployment

Install module

```bash
python -m pip install .
# For autocomplete
activate-global-python-argcomplete
```

Install with encryption support

```bash
uv pip install .[encrypt]
```

For development (editable install + pre-commit hooks)

```bash
uv pip install -e .[dev]
prek install
# Prettier formatters for Jinja/CSS/JS
npm install --save-dev prettier prettier-plugin-tailwindcss prettier-plugin-jinja-template @tailwindcss/typography
```

---

## Usage

```bash
# Create a new database
flask_htmx_template create

# Start the development server
flask --app flask_htmx_template.web run
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
| `DB_PATH`          | `/data/database.db` | Path to database inside `data` volume         |
| `DB_KEY_PATH`      | `/data/.key.secret` | File containing database encryption key       |
| `DB_WEB_KEY`       | `web-admin`         | Web password set when creating a new database |
| `WEB_PORT`         | `8000`              | Port to bind server to                        |
| `WEB_PORT_METRICS` | `8001`              | Port to bind metrics server to                |
| `WEB_CONCURRENCY`  | n(CPU) × 2 + 1      | Number of gunicorn workers                    |
| `WEB_N_THREADS`    | `1`                 | Threads per worker                            |
| `WEB_TIMEOUT`      | `30`                | Worker silent timeout (seconds)               |

---

## Running Tests

```bash
# All tests
python -m pytest

# Coverage report (must reach 100%)
python -m coverage run && python -m coverage report
```

Tests do not cover front-end behavior or browser interaction.

---

## Development

Code style follows the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html).

### Linters

- `ruff` — Python (all rules enabled)
- `basedpyright` — strict type checking
- `djlint` — Jinja templates
- `codespell` — spell checking

### Formatters

- `black` + `isort` — Python
- `prettier` — Jinja, CSS, JS
- `taplo` — TOML

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
[coverage-image]: https://gist.githubusercontent.com/WattsUp/36d9705addcd44fb0fccec1d23dc1338/raw/flask-htmx-template__heads_master.svg
[coverage-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/coverage.yml
