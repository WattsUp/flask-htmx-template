# syntax=docker/dockerfile:1

################################################################################
FROM python:3.12-slim-bullseye AS app-build
LABEL maintainer="Bradley Davis <me@bradleydavis.tech>"

WORKDIR /app
ARG UID=1000
ARG GID=1000

RUN apt-get update \
  && apt-get install -y --no-install-recommends git \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean \
  && groupadd -g "${GID}" python \
  && useradd --create-home --no-log-init -u "${UID}" -g "${GID}" python \
  && chown python:python -R /app

USER python

COPY --chown=python:python . .

ENV PYTHONUNBUFFERED="true" \
  PYTHONPATH="." \
  PATH="${PATH}:/home/python/.local/bin" \
  USER="python"

RUN pip3 install --no-cache-dir "build>=1.2.2" "setuptools-scm>=8" \
  && rm -rf dist \
  && python -m build -w

CMD [ "bash" ]

################################################################################
FROM python:3.12-slim-bullseye AS app
LABEL maintainer="Bradley Davis <me@bradleydavis.tech>"

WORKDIR /app
ARG UID=1000
ARG GID=1000

RUN apt-get update \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean \
  && groupadd -g "${GID}" python \
  && useradd --create-home --no-log-init -u "${UID}" -g "${GID}" python \
  && chown python:python -R /app \
  && mkdir /data \
  && chown python:python -R /data
VOLUME /data


COPY --chown=python:python docker/* .
RUN chmod +x ./*.sh

USER python

COPY --chown=python:python --from=app-build /app/dist/* .
RUN whl=$(echo flask_htmx_template*.whl) \
  && pip3 install --no-warn-script-location --no-cache-dir "$whl[deploy]"

ENV PYTHONUNBUFFERED="true" \
  PYTHONPATH="." \
  USER="python"


EXPOSE 8000
EXPOSE 8001

ENTRYPOINT [ "/app/entrypoint.sh" ]
