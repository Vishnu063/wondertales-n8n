"""Local authenticated API and simple browser UI. One worker owns generation."""
import argparse
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlparse

from .engine import Engine
from .planner import make_plan
from .store import Store
from .youtube import Uploads


def main():
    os.umask(0o077)
    args = argparse.ArgumentParser()
    args.add_argument("--doctor", action="store_true")
    args.add_argument("--port", type=int, default=8099)
    opt = args.parse_args()
    root = Path(os.environ.get("WONDERTALES_HOME", "~/.local/share/wondertales-v2")).expanduser().resolve()
    store = Store(root)
    token_path = root / "api-token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32))
    token = token_path.read_text().strip()
    engine = Engine(store)
    uploads = Uploads(store)
    if opt.doctor:
        print(json.dumps(engine.tools(), indent=2))
        return
    lock = (root / "worker.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Worker or Flow login already running for this state directory")
    store.recover_startup()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                if engine.process_next() is None:
                    stop.wait(2)
            except Exception:
                # Never terminate the queue thread because one tool/store operation failed.
                stop.wait(5)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # tokens/job text never enter access logs

        def reply(self, value, status=200):
            data = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                data = Path(__file__).with_name("index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
                return
            if not self.authorized():
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/settings":
                    return self.reply(store.settings())
                if path == "/api/jobs":
                    return self.reply(store.list())
                if path == "/api/doctor":
                    return self.reply(engine.tools())
                if path == "/api/upload/next":
                    candidate = uploads.next()
                    return self.reply({"jobs": [] if candidate is None else [candidate]})
                if path.startswith("/api/jobs/"):
                    return self.reply(store.get(path.split("/")[-1]))
                if path.startswith("/api/video/"):
                    job = store.get(path.split("/")[-1])
                    if job["status"] != "complete":
                        raise ValueError("Video is not complete")
                    file = engine.work(job["id"]) / "final.mp4"
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", str(file.stat().st_size))
                    self.send_header("Content-Disposition", 'attachment; filename="wondertales.mp4"')
                    self.end_headers()
                    with file.open("rb") as f:
                        import shutil
                        shutil.copyfileobj(f, self.wfile)
                    return
                self.reply({"error": "Not found"}, 404)
            except ValueError as exc:
                self.reply({"error": str(exc)}, 400)
            except Exception:
                self.reply({"error": "Local operation failed; inspect your worker files"}, 500)

        def authorized(self):
            if not secrets.compare_digest(self.headers.get("X-Wondertales-Token", ""), token):
                self.reply({"error": "Worker token required"}, 401)
                return False
            return True

        def do_POST(self):
            if not self.authorized():
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 64000 or self.headers.get_content_type() != "application/json":
                    raise ValueError("Send JSON, up to 64 KB")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Send a JSON object")
                if self.path == "/api/plan":
                    return self.reply(store.create(make_plan(body, store.settings())))
                if self.path == "/api/settings":
                    return self.reply(store.settings(body))
                if self.path == "/api/approve":
                    return self.reply(store.approve(body["id"], body["cap"]))
                if self.path == "/api/resume":
                    return self.reply(store.resume(body["id"]))
                if self.path == "/api/recover":
                    return self.reply(engine.recover(body["id"], int(body["scene"]) - 1, body["filename"]))
                if self.path == "/api/revise":
                    return self.reply(engine.revise(body["id"], int(body["scene"]) - 1, body["direction"]))
                if self.path == "/api/retry-render":
                    return self.reply(engine.retry_render(body["id"]))
                if self.path == "/api/upload/prepare":
                    return self.reply(uploads.prepare(body["id"]))
                if self.path == "/api/upload/approve":
                    return self.reply(uploads.approve(body["id"], body["metadata"]))
                if self.path == "/api/upload/claim":
                    return self.reply(uploads.claim(body["id"], body["channel_id"]))
                if self.path == "/api/upload/complete":
                    return self.reply(uploads.complete(body["id"], body["claim"], body["video"]))
                if self.path == "/api/tick":
                    # Worker already polls. n8n can monitor/wake without a second processing owner.
                    return self.reply({"queued": sum(j["status"] == "queued" for j in store.list()), "worker": "automatic"})
                self.reply({"error": "Not found"}, 404)
            except (ValueError, KeyError, TypeError) as exc:
                self.reply({"error": str(exc)}, 400)
            except Exception:
                self.reply({"error": "Local operation failed; inspect your worker files"}, 500)

    server = ThreadingHTTPServer(("127.0.0.1", opt.port), Handler)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    print(f"WonderTales: http://127.0.0.1:{opt.port} — token file: {token_path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        print("Waiting for current scene/render to finish. Do not force-kill during submission.", flush=True)
        thread.join()


if __name__ == "__main__":
    main()
