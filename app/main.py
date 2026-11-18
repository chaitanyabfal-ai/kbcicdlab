import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = os.environ.get("APP_NAME", "kbcicdlab")
APP_MESSAGE = os.environ.get("APP_MESSAGE", "hello from kbcicdlab")
PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    server_version = "kbcicdlab/1.0"

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/readyz":
            ready = bool(os.environ.get("APP_MESSAGE"))
            self._send_json(200 if ready else 503, {"ready": ready})
        elif self.path == "/":
            self._send_json(200, {
                "app": APP_NAME,
                "message": APP_MESSAGE,
                "secret_configured": bool(os.environ.get("DB_PASSWORD")),
            })
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        pass


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
