# flask-htmx-template

[![Unit Test][unittest-image]][unittest-url] [![Static Analysis][static-analysis-image]][static-analysis-url] [![Coverage][coverage-image]][coverage-url] [![Latest Version][pypi-image]][pypi-url]

A template repository for flask with htmx

---

## Environment

List of dependencies for package to run.

### Required

- Python modules
  - sqlalchemy
  - colorama
  - flask
  - flask-assets
  - flask-login
  - argcomplete
  - prometheus-flask-exporter
  - packaging

### Optional

- Encryption extension to encrypt database file
  - sqlcipher3-binary
  - Cipher
  - pycryptodome

---

## Installation / Build / Deployment

Install module

```bash
> python -m pip install .
> # For autocomplete, activate completion hook
> activate-global-python-argcomplete
```

Install module with encryption

```bash
> uv pip install .[encrypt]
```

For development, install as a link to repository such that code changes are used. It is recommended to install prek hooks

```bash
> uv pip install -e .[dev]
> prek install
```

### Node Modules

Install the following node modules for prettier to work.

```bash
> npm install --save-dev prettier prettier-plugin-tailwindcss prettier-plugin-jinja-template @tailwindcss/typography
```

---

## Usage

Run `create` command to make a new database. Then start a web server using flask.

```bash
> flask_htmx_template create
> flask --app flask_htmx_template.web run
```

---

## Docker

A better way to use flask_htmx_template is hosting the web server on in a docker instance.

```bash
> docker run \
  --name flask_htmx_template \
  --detach \
  --publish 8000:8000 \
  --publish 8001:8001 \
  --volume flask_htmx_template-data:/data \
  flask_htmx_template
```

### Configuration

The following environment variables are used to configure the instance.

| Env                | Default             | Description                                                                      |
| ------------------ | ------------------- | -------------------------------------------------------------------------------- |
| `DB_PATH`          | `/data/database.db` | Path to database inside `data` volume.                                           |
| `DB_KEY_PATH`      | `/data/.key.secret` | File containing database key for encryption                                      |
| `DB_WEB_KEY`       | `web-admin`         | Web key used when creating a new database                                        |
| `WEB_PORT`         | `8000`              | Port to bind server to                                                           |
| `WEB_PORT_METRICS` | `8001`              | Port to bind metrics server to                                                   |
| `WEB_CONCURRENCY`  | n(CPU) \* 2 + 1     | Number of gunicorn workers to spawn                                              |
| `WEB_N_THREADS`    | `1`                 | Number of gunicorn workers threads to spawn                                      |
| `WEB_TIMEOUT`      | `30`                | Gunicorn workers silent for more than this many seconds are killed and restarted |

---

## Running Tests

Does not test front-end at all and minimally tests web controllers. This is out of scope for the foreseeable future.

Unit tests

```bash
> python -m tests
```

Coverage report

```bash
> python -m coverage run && python -m coverage report
```

---

## Development

Code development of this project adheres to [Google Python Guide](https://google.github.io/styleguide/pyguide.html)

Linters

- `ruff` for Python
- `basedpyright` for Python type analysis
- `djlint` for Jinja HTML templates
- `codespell` for all files

Formatters

- `isort` for Python import order
- `black` for Python
- `prettier` for Jinja HTML templates, CSS, and JS
- `taplo` for TOML

### Tools

- `formatters.sh` will run every formatter
- `linters.sh` will run every linter
- `run_tailwindcss.sh` will run tailwindcss with proper arguments

---

## Configuration

Most configuration is made per database via the web interface

---

## Versioning

Versioning of this projects adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) and is implemented using git tags.

[pypi-image]: https://img.shields.io/pypi/v/flask-htmx-template.svg
[pypi-url]: https://pypi.org/project/flask-htmx-template/
[unittest-image]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/test.yml/badge.svg
[unittest-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/test.yml
[static-analysis-image]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/static-analysis.yml/badge.svg
[static-analysis-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/static-analysis.yml
[coverage-image]: https://gist.githubusercontent.com/WattsUp/36d9705addcd44fb0fccec1d23dc1338/raw/flask-htmx-template__heads_master.svg
[coverage-url]: https://github.com/WattsUp/flask-htmx-template/actions/workflows/coverage.yml
