import json
from pathlib import Path
import shutil

from . import media
from .planner import scene_prompt


class Engine:
    def __init__(self, store, runner=media.command):
        self.store, self.run = store, runner

    def work(self, ident):
        path = self.store.root / "jobs" / ident
        (path / "assets").mkdir(parents=True, exist_ok=True)
        return path

    def tools(self):
        hypit = media.local_hypit()
        tools = {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
                 "gflow": shutil.which("gflow"), "hypit": hypit}
        return {"tools": {k: bool(v) for k, v in tools.items()},
                "ready": all(tools.values()), "planner": self.store.settings()["planner"],
                "note": "Tool presence only. Google login, selected model, actual rate, and Hypit browser need live validation."}

    def process_next(self):
        job = self.store.claim()
        if job is None:
            return None
        ident = job["id"]
        work = self.work(ident)
        try:
            if not self.tools()["ready"]:
                raise ValueError("Missing tools. Run scripts/setup.sh and check Diagnostics")
            hypit = media.local_hypit()
            self.run([hypit, "--version"])
            # A shared prepared profile is reused; no hosted endpoint is configured.
            marker = self.store.root / "hypit/prepared"
            if not marker.is_file() or marker.read_text() != self.store.settings()["chrome_path"]:
                raise ValueError("Prepare the local Hypit renderer with scripts/prepare-renderer.sh first")
            media.author_project(work, job, self.store.settings()["chrome_path"])
            for scene in job["scenes"]:
                i = scene["index"]
                clip = work / f"assets/scene-{i}.mp4"
                if scene["state"] == "done":
                    media.probe(clip, 8, job["aspect"], 720)
                    continue
                if scene["state"] != "pending":
                    raise ValueError(f"Scene {i+1} has an uncertain provider outcome. Recover its existing clip first")
                balance = json.loads(self.run(["gflow", "credits", "user", "--profile", job["flow_profile"], "--json"]))
                credits = balance.get("credits")
                from .planner import number
                credits = number(credits, "Flow balance")
                if balance.get("authenticated") is False or credits < job["credits_per_clip"]:
                    raise ValueError("Flow login/balance is unavailable or insufficient; no scene submitted")
                self.store.reserve(ident, i)
                try:
                    out = work / f"download-{i}"
                    out.mkdir(exist_ok=True)
                    result = json.loads(self.run(["gflow", "video", "t2v", scene_prompt(job, scene),
                        "--model", job["flow_model"], "--duration", "8", "--count", "1",
                        "--aspect", job["aspect"], "--profile", job["flow_profile"], "--out-dir", out, "--json"], timeout=1200))
                    path = Path(result.get("local_path", "")).resolve()
                    if not result.get("succeeded") or not path.is_relative_to(out.resolve()) or not path.is_file():
                        raise ValueError("Flow did not return a verified download")
                    # Keep returned media even if its quality checks fail. Never regenerate it automatically.
                    shutil.copyfile(path, clip)
                    self.store.scene(ident, i, "done")
                    media.probe(clip, 8, job["aspect"], 720)
                except Exception:
                    if self.store.get(ident)["scenes"][i]["state"] == "submitting":
                        self.store.scene(ident, i, "uncertain")
                    raise ValueError(f"Scene {i+1} needs review. Check Flow/downloads; this scene will not be generated again automatically") from None
            self.store.update(ident, "All clips saved. Hypit is assembling picture and sound.")
            job = self.store.get(ident)
            checks = media.render(work, job, hypit,
                lambda build: self.store.update(ident, hypit_build=build), job.get("hypit_build"))
            self.store.update(ident, "Video ready for your review. Captions follow planned scene slots, not measured speech timing.", status="complete", checks=checks)
            from .youtube import Uploads
            try:
                Uploads(self.store).prepare(ident)
            except ValueError:
                self.store.update(ident, "Video ready. Configure YouTube channel/audience in Settings to prepare upload details.")
        except Exception as exc:
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else "Tool operation failed. Check the local tool and resume; paid scenes remain checkpointed."
            self.store.update(ident, message, status="attention")
        return self.store.get(ident)

    def recover(self, ident, index, filename):
        job = self.store.get(ident)
        if job["status"] != "attention" or not 0 <= index < len(job["scenes"]):
            raise ValueError("Choose a stopped job and valid scene number")
        if job["scenes"][index]["state"] not in ("uncertain", "done"):
            raise ValueError("Scene is not awaiting recovery")
        imports = self.store.root / "imports"
        imports.mkdir(exist_ok=True)
        source = (imports / filename).resolve()
        if not source.is_relative_to(imports.resolve()) or not source.is_file():
            raise ValueError("Place the recovered clip inside the private imports folder")
        media.probe(source, 8, job["aspect"], 720)
        shutil.copyfile(source, self.work(ident) / f"assets/scene-{index}.mp4")
        self.store.scene(ident, index, "done")
        return self.store.update(ident, f"Recovered scene {index+1}. Its reserved credits remain counted. Safe resume is available.")

    def revise(self, ident, index, direction):
        old = self.store.get(ident)
        if old["status"] != "complete" or not 0 <= index < len(old["scenes"]) or not isinstance(direction, str) or not 5 <= len(direction) <= 1500:
            raise ValueError("Choose a complete job, valid scene and a 5–1500 character direction")
        import copy
        plan = copy.deepcopy(old)
        for key in ("id", "events", "cap", "created", "message", "hypit_build", "checks", "upload"):
            plan.pop(key, None)
        plan.update(parent=ident, reserved=0, estimate=old["credits_per_clip"])
        plan["scenes"][index].update(state="pending", visual=direction)
        new = self.store.create(plan)
        try:
            for scene in new["scenes"]:
                if scene["index"] != index:
                    shutil.copyfile(self.work(ident) / f"assets/scene-{scene['index']}.mp4",
                                    self.work(new["id"]) / f"assets/scene-{scene['index']}.mp4")
        except OSError:
            self.store.update(new["id"], "Original clip is missing. Restore files before creating a revision.", status="attention")
            raise ValueError("Original clips could not be reused") from None
        return new

    def retry_render(self, ident):
        job = self.store.get(ident)
        if job["status"] != "attention" or not job.get("hypit_build") or any(s["state"] != "done" for s in job["scenes"]):
            raise ValueError("A stopped local render with all saved clips is required")
        work = self.work(ident)
        result = json.loads(self.run([media.local_hypit(), "inspect", job["hypit_build"], "--project", work, "--json"]))
        # A finished failed/cancelled Result is different from a lost observer.
        if result.get("build", {}).get("outcome") not in ("failed", "cancelled"):
            raise ValueError("Build is not confirmed failed/cancelled. Use Safe resume to reattach it")
        self.store.update(ident, "Confirmed failed local render cleared; saved Flow clips retained.", hypit_build=None)
        return self.store.resume(ident)
