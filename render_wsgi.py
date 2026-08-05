"""Fast WSGI entry point for Render health checks.

Use ``gunicorn render_wsgi:app`` on Render. The full Flask application is
loaded on the first real request, while health probes return immediately.
"""

import json
import threading


class LazyRenderApplication:
    def __init__(self):
        self._application = None
        self._lock = threading.Lock()

    @staticmethod
    def _health_response(start_response):
        body = json.dumps({"status": "ok"}).encode("utf-8")
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/json"),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [body]

    def __call__(self, environ, start_response):
        if environ.get("PATH_INFO") == "/health":
            return self._health_response(start_response)

        if self._application is None:
            with self._lock:
                if self._application is None:
                    from app import create_app

                    self._application = create_app()

        return self._application(environ, start_response)


app = LazyRenderApplication()
