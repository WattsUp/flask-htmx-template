#!/bin/sh

set -eu

case "${1-}" in
  --asgi|--mcp)
    shift
    # The MCP endpoint is mounted by the combined ASGI application, so --mcp
    # intentionally uses the same target as --asgi.
    exec uvicorn \
      --factory flask_htmx_template.asgi:create_app \
      --reload \
      --host 127.0.0.1 \
      --port 5000 \
      "$@"
    ;;
  *)
    exec flask --app flask_htmx_template.web run --debug "$@"
    ;;
esac
