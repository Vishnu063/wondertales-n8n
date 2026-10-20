import copy
import json
import tempfile
import unittest

from wondertales.planner import DEFAULTS, STORY_PROFILE, make_plan, scene_prompt, validate_settings
from wondertales.store import Store


class StoryProfileTests(unittest.TestCase):
    def setUp(self):
        self.body = {"title": "A little adventure", "story": "Milo helps a bird. The happy bird finds its way home.", "duration": 16}
        self.settings = copy.deepcopy(DEFAULTS)
        self.settings["story_profile"] = {"audience": "बच्चों के लिए छोटी कहानियाँ", "tone": "Gentle and cheerful",
                                           "boundaries": "Keep repeated rhyme lines; no frightening visuals"}

    def test_hindi_and_english_repetition_are_not_scored_or_removed(self):
        for text, language in (("Hop hop little fox. Hop hop little fox. Home we go.", "English"),
                               ("मिलो चला घर। मिलो चला घर। चिड़िया भी उसके साथ चली।", "Hindi")):
            with self.subTest(language=language):
                plan = make_plan({**self.body, "story": text, "language": language}, self.settings)
                self.assertEqual(' '.join(s["narration"] for s in plan["scenes"]), text)
                self.assertEqual(plan["story"], text)
                self.assertEqual(plan["planner"], "rules")

    def test_profile_and_story_guidance_reach_local_planner(self):
        captured = {}
        self.settings["planner"] = "ollama"
        def reply(req):
            captured.update(json.loads(req.data))
            return {"message": {"content": json.dumps({"visuals": ["The fox gently guides the bird beside a tree.", "The bird reaches its home while Milo waves."]})}}
        plan = make_plan(self.body, self.settings, reply)
        material = json.loads(captured["messages"][1]["content"])
        self.assertEqual(material["story_profile"], self.settings["story_profile"])
        self.assertIn("Establish", material["scene_guidance"][0])
        self.assertIn("supplied ending", material["scene_guidance"][-1])
        self.assertEqual(' '.join(material["scenes"]), self.body["story"])
        self.assertEqual(plan["planner"], "ollama")

    def test_fallback_keeps_profile_in_scene_prompts(self):
        self.settings["planner"] = "ollama"
        def failed(_):
            raise TimeoutError("offline fixture")
        plan = make_plan(self.body, self.settings, failed)
        self.assertEqual(plan["planner"], "rules")
        self.assertIn("unavailable", plan["warning"])
        prompt = scene_prompt(plan, plan["scenes"][0])
        self.assertIn(self.settings["story_profile"]["tone"], prompt)
        self.assertIn(self.settings["story_profile"]["audience"], prompt)
        self.assertIn("Preserve intentional repeated words", prompt)

    def test_settings_changes_do_not_change_existing_job_profile(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings(self.settings)
            job = store.create(make_plan(self.body, store.settings()))
            changed = copy.deepcopy(self.settings)
            changed["story_profile"]["tone"] = "Different future tone"
            store.settings(changed)
            saved = store.get(job["id"])
            self.assertEqual(saved["story_profile"]["tone"], "Gentle and cheerful")
            self.assertNotIn("Different future tone", scene_prompt(saved, saved["scenes"][0]))

    def test_old_settings_and_old_jobs_remain_usable(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            old = {k: v for k, v in self.settings.items() if k != "story_profile"}
            with store.transaction() as db:
                db.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(old),))
            self.assertEqual(store.settings()["story_profile"], STORY_PROFILE)
            plan = make_plan(self.body, old)
            plan.pop("story_profile")
            self.assertIn("Story profile:", scene_prompt(plan, plan["scenes"][0]))

    def test_invalid_profile_is_rejected_without_overwriting_settings(self):
        for value in (None, [], "text", {"tone": " "}, {"tone": "x"*601}, {"audience": 7}, {"extra": "unknown"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_settings({**self.settings, "story_profile": value})
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            store.settings(self.settings)
            with self.assertRaises(ValueError):
                store.settings({**self.settings, "story_profile": {"tone": ""}})
            self.assertEqual(store.settings()["story_profile"], self.settings["story_profile"])
