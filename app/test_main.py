import json
import os
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

import main


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["APP_NAME"] = "kbcicdlab-test"
        os.environ["APP_MESSAGE"] = "test message"
        os.environ["DB_PASSWORD"] = "test-password"
        main.APP_NAME = os.environ["APP_NAME"]
        main.APP_MESSAGE = os.environ["APP_MESSAGE"]
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), main.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()

    def _get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as resp:
            return resp.status, json.loads(resp.read())

    def test_root(self):
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertEqual(body["app"], "kbcicdlab-test")
        self.assertEqual(body["message"], "test message")
        self.assertTrue(body["secret_configured"])

    def test_healthz(self):
        status, body = self._get("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})

    def test_readyz(self):
        status, body = self._get("/readyz")
        self.assertEqual(status, 200)
        self.assertTrue(body["ready"])

    def test_not_found(self):
        try:
            self._get("/nope")
            self.fail("expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == "__main__":
    unittest.main()
