import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request


class ApiTests(unittest.TestCase):
    def test_real_http_auth_plan_and_approval_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            proc = subprocess.Popen([sys.executable, "-m", "wondertales.app", "--port", str(port)],
                env={**os.environ, "WONDERTALES_HOME": root}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                token_path = Path(root) / "api-token"
                url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 8
                while True:
                    try:
                        with urllib.request.urlopen(url, timeout=.3) as r:
                            self.assertIn(b"Bring your story to life", r.read())
                        break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() >= deadline:
                            self.fail("Worker did not start")
                        time.sleep(.05)
                with self.assertRaises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(url + "/api/jobs")
                self.assertEqual(exc.exception.code, 401)
                headers = {"X-Wondertales-Token": token_path.read_text().strip(), "Content-Type": "application/json"}
                req = urllib.request.Request(url + "/api/plan", json.dumps({"title": "A kind fox", "story": "A small fox helped a little bird find its way home.", "duration": 8}).encode(), headers)
                with urllib.request.urlopen(req) as r:
                    job = json.load(r)
                self.assertEqual(job["status"], "planned")
                req = urllib.request.Request(url + "/api/approve", json.dumps({"id": job["id"], "cap": 100}).encode(), headers)
                with self.assertRaises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(req)
                self.assertEqual(exc.exception.code, 400)
                with urllib.request.urlopen(urllib.request.Request(url + "/api/jobs", headers=headers)) as r:
                    saved = json.load(r)[0]
                self.assertEqual(saved["status"], "planned")
                self.assertEqual(saved["reserved"], 0)
            finally:
                proc.terminate()
                proc.wait(timeout=5)
