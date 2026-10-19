import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from wondertales.engine import Engine
from wondertales.media import author_project, probe
from wondertales.planner import DEFAULTS, make_plan, validate_settings
from wondertales.store import Store


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.settings = {**DEFAULTS, "credits_per_clip": 10, "daily_credit_cap": 30}
        self.store.settings(self.settings)
        self.body = {"title": "A kind fox", "story": "A small fox helped a little bird find its way home.", "duration": 8}

    def job(self):
        return self.store.create(make_plan(self.body, self.settings))

    def test_script_preserved_and_character_memory_snapshotted(self):
        self.settings["characters"] = [{"name": "Milo", "description": "Orange fox with blue scarf"}]
        body = {**self.body, "characters": ["Milo"]}
        plan = make_plan(body, self.settings)
        self.assertEqual(plan["scenes"][0]["narration"], self.body["story"])
        self.assertEqual(plan["cast"], self.settings["characters"])

    def test_ai_response_changes_visuals_only(self):
        self.settings["planner"] = "ollama"
        plan = make_plan(self.body, self.settings, lambda r: {"message": {"content": json.dumps({"visuals": ["Wide shot: the fox lifts the bird gently toward its nest."]})}})
        self.assertEqual(plan["planner"], "ollama")
        self.assertEqual(plan["story"], self.body["story"])

    def test_unavailable_ai_has_explicit_fallback(self):
        self.settings["planner"] = "ollama"
        plan = make_plan(self.body, self.settings, lambda r: {"message": {"content": "not json"}})
        self.assertEqual(plan["planner"], "rules")
        self.assertIn("unavailable", plan["warning"])

    def test_validation_rejects_nonfinite_prices_and_remote_ollama(self):
        for change in ({"credits_per_clip": float("nan")}, {"daily_credit_cap": True}, {"ollama_url": "http://example.com"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_settings({**DEFAULTS, **change})
        for body in ({"duration": 15}, {"characters": ["unknown"]}, {"story": ""}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                make_plan({**self.body, **body}, self.settings)

    def test_approval_and_claim_are_single_use(self):
        job = self.job()
        with self.assertRaises(ValueError):
            self.store.approve(job["id"], 9)
        self.store.approve(job["id"], 10)
        with self.assertRaises(ValueError):
            self.store.approve(job["id"], 10)
        self.assertIsNotNone(self.store.claim())
        self.assertIsNone(self.store.claim())

    def test_zero_price_never_approves(self):
        plan = make_plan(self.body, {**self.settings, "credits_per_clip": 0})
        j = self.store.create(plan)
        with self.assertRaises(ValueError):
            self.store.approve(j["id"], 100)

    def test_reservation_is_durable_and_cannot_be_repeated(self):
        j = self.job()
        self.store.approve(j["id"], 10)
        self.store.claim()
        self.store.reserve(j["id"], 0)
        with self.assertRaises(ValueError):
            self.store.reserve(j["id"], 0)
        restarted = Store(self.tmp.name)
        restarted.recover_startup()
        saved = restarted.get(j["id"])
        self.assertEqual(saved["reserved"], 10)
        self.assertEqual(saved["scenes"][0]["state"], "uncertain")
        with self.assertRaises(ValueError):
            restarted.resume(j["id"])

    def test_global_daily_cap_spans_jobs(self):
        self.store.settings({**self.settings, "daily_credit_cap": 10})
        for n in range(2):
            j = self.job()
            self.store.approve(j["id"], 10)
            self.store.claim()
            if n == 0:
                self.store.reserve(j["id"], 0)
                self.store.update(j["id"], status="attention")
            else:
                with self.assertRaises(ValueError):
                    self.store.reserve(j["id"], 0)

    def test_timeout_is_uncertain_and_not_auto_retried(self):
        j = self.job()
        self.store.approve(j["id"], 10)
        marker = self.store.root / "hypit/prepared"
        marker.parent.mkdir()
        marker.write_text("")
        calls = []
        def runner(args, **kw):
            calls.append(args)
            if "credits" in args:
                return '{"authenticated":true,"credits":100}'
            if "t2v" in args:
                raise subprocess.TimeoutExpired(args, 1)
            return "0.3.1"
        engine = Engine(self.store, runner)
        with patch.object(engine, "tools", return_value={"ready": True}), patch("wondertales.media.local_hypit", return_value="hypit"):
            engine.process_next()
            self.assertIsNone(engine.process_next())
        saved = self.store.get(j["id"])
        self.assertEqual(saved["status"], "attention")
        self.assertEqual(saved["scenes"][0]["state"], "uncertain")
        self.assertEqual(sum("t2v" in c for c in calls), 1)

    def test_recovery_rejects_path_traversal(self):
        j = self.job()
        self.store.update(j["id"], status="attention")
        self.store.scene(j["id"], 0, "uncertain")
        outside = self.store.root / "outside.mp4"
        outside.write_bytes(b"x")
        with self.assertRaises(ValueError):
            Engine(self.store).recover(j["id"], 0, "../outside.mp4")

    def test_resume_reuses_saved_clip_without_new_generation(self):
        j = self.job()
        self.store.approve(j["id"], 10)
        self.store.scene(j["id"], 0, "done")
        marker = self.store.root / "hypit/prepared"
        marker.parent.mkdir()
        marker.write_text("")
        calls = []
        engine = Engine(self.store, lambda args, **kw: calls.append(args) or "0.3.1")
        with patch.object(engine, "tools", return_value={"ready": True}), patch("wondertales.media.local_hypit", return_value="hypit"), patch("wondertales.media.probe", return_value={}), patch("wondertales.media.render", return_value={"has_audio": True}):
            saved = engine.process_next()
        self.assertEqual(saved["status"], "complete")
        self.assertFalse(any("t2v" in c for c in calls))
        self.assertEqual(saved["reserved"], 0)

    def test_render_retry_requires_confirmed_failed_build(self):
        j = self.job()
        self.store.approve(j["id"], 10)
        self.store.scene(j["id"], 0, "done")
        self.store.update(j["id"], status="attention", hypit_build="build-123")
        engine = Engine(self.store, lambda *a, **k: '{"build":{"outcome":"complete"}}')
        with self.assertRaises(ValueError):
            engine.retry_render(j["id"])
        engine.run = lambda *a, **k: '{"build":{"outcome":"failed"}}'
        saved = engine.retry_render(j["id"])
        self.assertEqual(saved["status"], "queued")
        self.assertIsNone(saved["hypit_build"])
        self.assertEqual(saved["scenes"][0]["state"], "done")

    def test_revision_reuses_other_scenes_and_requires_new_approval(self):
        body = {**self.body, "duration": 16}
        old = self.store.create(make_plan(body, self.settings))
        engine = Engine(self.store)
        for i in range(2):
            (engine.work(old["id"]) / f"assets/scene-{i}.mp4").write_bytes(b"fixture")
            self.store.scene(old["id"], i, "done")
        self.store.update(old["id"], status="complete", hypit_build="old-build")
        new = engine.revise(old["id"], 1, "Close-up: the fox waves goodbye beside the nest.")
        self.assertEqual(new["status"], "planned")
        self.assertEqual(new["estimate"], 10)
        self.assertEqual(new["reserved"], 0)
        self.assertNotIn("hypit_build", new)
        self.assertEqual(new["scenes"][0]["state"], "done")
        self.assertEqual(new["scenes"][1]["state"], "pending")
        self.assertTrue((engine.work(new["id"]) / "assets/scene-0.mp4").exists())

    def test_hypit_source_has_only_local_endpoints_and_both_tracks(self):
        plan = make_plan(self.body, self.settings)
        author_project(self.store.root, plan)
        source = (self.store.root / "film.svml").read_text()
        self.assertIn("<visual:Clip", source)
        self.assertIn("<audio:Clip", source)
        self.assertIn('from="0s" for="8s"', source)
        profile = json.loads((self.store.root / "hypit.runtime.json").read_text())
        self.assertEqual(set(profile["endpoints"]), {"media.local", "html.local"})
        self.assertEqual(profile["credentials"], {})

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required")
    def test_real_media_decode_and_wrong_duration_rejected(self):
        path = self.store.root / "sample.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=180x320:r=30:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)
        self.assertTrue(probe(path, 1, "9:16")["has_audio"])
        with self.assertRaises(ValueError):
            probe(path, 8, "9:16")


if __name__ == "__main__":
    unittest.main()
