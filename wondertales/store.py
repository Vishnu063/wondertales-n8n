"""SQLite checkpoints: commit a credit reservation before invoking Flow."""
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import threading
import uuid
from zoneinfo import ZoneInfo

from .planner import DEFAULTS, number, validate_settings


def today():
    return datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = self.root / "agent.sqlite3"
        with self.transaction() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY, data TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS ledger(day TEXT, job TEXT, scene INTEGER, credits REAL);
            """)
            db.execute("INSERT OR IGNORE INTO settings VALUES(1, ?)", (json.dumps(DEFAULTS),))

    @contextmanager
    def transaction(self):
        with self.lock:
            db = sqlite3.connect(self.db, timeout=30)
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def settings(self, data=None):
        with self.transaction() as db:
            if data is not None:
                data = validate_settings(data)
                db.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(data),))
            return json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])

    def _read(self, db, ident):
        row = db.execute("SELECT data FROM jobs WHERE id=?", (ident,)).fetchone()
        if not row:
            raise ValueError("Job not found")
        return json.loads(row[0])

    def _write(self, db, job, message=None):
        if message:
            job["message"] = message
            job["events"].append({"time": datetime.now().astimezone().isoformat(), "message": message})
        db.execute("INSERT OR REPLACE INTO jobs VALUES(?,?)", (job["id"], json.dumps(job, ensure_ascii=False)))
        return job

    def create(self, plan):
        job = {**plan, "id": uuid.uuid4().hex, "status": "planned", "events": [], "cap": 0,
               "created": datetime.now().astimezone().isoformat()}
        with self.transaction() as db:
            return self._write(db, job, "Plan ready. Review prompts and estimated credits before approval.")

    def get(self, ident):
        with self.transaction() as db:
            return self._read(db, ident)

    def list(self):
        with self.transaction() as db:
            return sorted([json.loads(r[0]) for r in db.execute("SELECT data FROM jobs")], key=lambda j: j["created"], reverse=True)

    def update(self, ident, message=None, **fields):
        with self.transaction() as db:
            job = self._read(db, ident)
            job.update(fields)
            return self._write(db, job, message)

    def scene(self, ident, index, state, **fields):
        with self.transaction() as db:
            job = self._read(db, ident)
            job["scenes"][index].update(state=state, **fields)
            return self._write(db, job)

    def approve(self, ident, cap):
        cap = number(cap, "Job credit cap", 0.01)
        with self.transaction() as db:
            job = self._read(db, ident)
            if job["status"] != "planned":
                raise ValueError("Only a reviewed planned job can be approved")
            if job["credits_per_clip"] <= 0:
                raise ValueError("Set the current Flow per-clip rate in Settings, then create a new plan")
            remaining = sum(s["state"] == "pending" for s in job["scenes"]) * job["credits_per_clip"]
            if job["reserved"] + remaining > cap:
                raise ValueError("Estimated cost exceeds your cap")
            settings = json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])
            if settings["daily_credit_cap"] <= 0:
                raise ValueError("Set a daily credit cap in Settings first")
            job.update(status="queued", cap=cap)
            return self._write(db, job, "Approved and queued within the displayed credit cap.")

    def claim(self):
        with self.transaction() as db:
            for row in db.execute("SELECT data FROM jobs ORDER BY rowid"):
                job = json.loads(row[0])
                if job["status"] == "queued":
                    job["status"] = "running"
                    return self._write(db, job, "Preparing tools before any new Flow generation.")

    def reserve(self, ident, index):
        with self.transaction() as db:
            job = self._read(db, ident)
            if job["status"] != "running" or job["scenes"][index]["state"] != "pending":
                raise ValueError("Scene is not available for submission")
            rate = job["credits_per_clip"]
            settings = json.loads(db.execute("SELECT data FROM settings WHERE id=1").fetchone()[0])
            spent = db.execute("SELECT COALESCE(SUM(credits),0) FROM ledger WHERE day=?", (today(),)).fetchone()[0]
            if rate <= 0 or job["reserved"] + rate > job["cap"] or spent + rate > settings["daily_credit_cap"]:
                raise ValueError("Credit cap reached. No generation submitted; review limits before resuming.")
            db.execute("INSERT INTO ledger VALUES(?,?,?,?)", (today(), ident, index, rate))
            job["reserved"] += rate
            job["scenes"][index]["state"] = "submitting"
            self._write(db, job, f"Submitting scene {index+1}; {job['reserved']:g} estimated credits reserved.")

    def resume(self, ident):
        with self.transaction() as db:
            job = self._read(db, ident)
            if job["status"] != "attention" or any(s["state"] in ("uncertain", "submitting") for s in job["scenes"]):
                raise ValueError("Resolve uncertain scenes before resuming; running and completed jobs cannot restart")
            if not job["cap"]:
                raise ValueError("Approve the plan first")
            job["status"] = "queued"
            return self._write(db, job, "Safe resume queued. Completed scenes will be reused.")

    def recover_startup(self):
        with self.transaction() as db:
            for row in list(db.execute("SELECT data FROM jobs")):
                job = json.loads(row[0])
                if job["status"] == "running":
                    for scene in job["scenes"]:
                        if scene["state"] == "submitting":
                            scene["state"] = "uncertain"
                    job["status"] = "attention"
                    self._write(db, job, "Worker restarted. Check any uncertain Flow scene before resuming.")
