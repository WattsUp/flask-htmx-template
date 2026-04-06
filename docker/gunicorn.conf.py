"""Gunicorn configuration."""

from __future__ import annotations

import multiprocessing
import os
from typing import TYPE_CHECKING

from prometheus_flask_exporter.multiprocess import GunicornPrometheusMetrics

if TYPE_CHECKING:
    import gunicorn.workers.base

bind = f"0.0.0.0:{os.getenv('WEB_PORT', '8000')}"

accesslog = "-"  # stdout
access_log_format = "%(h)s %(l)s %(t)s '%(r)s' %(s)s %(b)s '%(f)s' '%(a)s' in %(D)sμs"

workers = int(os.getenv("WEB_CONCURRENCY") or multiprocessing.cpu_count() * 2 + 1)
threads = int(os.getenv("WEB_N_THREADS") or 1)
timeout = int(os.getenv("WEB_TIMEOUT") or 30)
preload_app = True


def when_ready(_) -> None:
    """When gunicorn server is ready, start metrics server."""
    GunicornPrometheusMetrics.start_http_server_when_ready(
        int(os.getenv("WEB_PORT_METRICS") or 8001),
        host="0.0.0.0",
    )


def child_exit(_, worker: gunicorn.workers.base.Worker) -> None:
    """When gunicorn worker exits, kill metrics server."""
    GunicornPrometheusMetrics.mark_process_dead_on_child_exit(worker.pid)
