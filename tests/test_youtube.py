import copy
import tempfile
import unittest

from wondertales.planner import DEFAULTS, make_plan
from wondertales.store import Store
from wondertales.youtube import CHANNEL_DEFAULTS, Uploads, channel_settings, metadata, validate_metadata


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.config = {**CHANNEL_DEFAULTS, "channel_id": "UC" + "a"*22, "made_for_kids": True,
                       "tags": ["original story"], "hashtags": ["#Story"]}
        self.store.settings({**DEFAULTS, "youtube": self.config})
        self.job = self.store.create(make_plan({"title": "Milo helps a bird", "story": "Milo helped a bird find its nest. The bird thanked him.", "duration": 8}, DEFAULTS))
        self.store.update(self.job["id"], status="complete")
        self.uploads = Uploads(self.store)

    def prepared(self, approve=True):
        job = self.uploads.prepare(self.job["id"])
        if approve:
            job = self.uploads.approve(job["id"], job["upload"]["metadata"])
        return job

    def video(self, claim):
        m = claim["metadata"]
        return {"id": "abcdefghijk", "snippet": {"channelId": claim["channel_id"], "title": m["title"],
            "description": m["description"], "categoryId": m["category_id"], "defaultLanguage": m["language"], "tags": m["tags"]},
            "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": m["made_for_kids"]}}

    def test_extracts_description_without_inventing_facts(self):
        job = self.prepared(False)
        m = job["upload"]["metadata"]
        self.assertEqual(m["title"], self.job["title"])
        self.assertIn(self.job["story"], m["description"])
        self.assertTrue(m["description"].endswith("#Story"))
        self.assertEqual(m["privacy"], "private")
        self.assertEqual(job["upload"]["state"], "review")
        self.assertIsNone(self.uploads.next())

    def test_requires_channel_and_explicit_audience(self):
        for config in (CHANNEL_DEFAULTS, {**self.config, "made_for_kids": None}):
            with self.assertRaises(ValueError):
                metadata(self.job, config)
        with self.assertRaises(ValueError):
            channel_settings({**CHANNEL_DEFAULTS, "auto_upload": True})

    def test_unicode_description_byte_limit_and_private_only(self):
        m = self.prepared(False)["upload"]["metadata"]
        for change in ({"title": "x"*101}, {"description": "अ"*1700}, {"privacy": "public"}, {"made_for_kids": None}, {"tags": ["a,b"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_metadata({**m, **change})

    def test_wrong_channel_and_duplicate_claim_never_upload(self):
        self.prepared()
        with self.assertRaises(ValueError):
            self.uploads.claim(self.job["id"], "UC" + "b"*22)
        claim = self.uploads.claim(self.job["id"], self.config["channel_id"])
        self.assertIsNone(self.uploads.next())
        with self.assertRaises(ValueError):
            self.uploads.claim(self.job["id"], self.config["channel_id"])
        restarted = Uploads(Store(self.temp.name))
        self.assertIsNone(restarted.next())
        with self.assertRaises(ValueError):
            restarted.prepare(self.job["id"])
        with self.assertRaises(ValueError):
            restarted.complete(self.job["id"], "wrong", self.video(claim))

    def test_completion_verifies_details_and_is_idempotent(self):
        self.prepared()
        claim = self.uploads.claim(self.job["id"], self.config["channel_id"])
        video = self.video(claim)
        for change in ("wrong-channel", "public", "wrong-title"):
            invalid = copy.deepcopy(video)
            if change == "wrong-channel": invalid["snippet"]["channelId"] = "other"
            if change == "public": invalid["status"]["privacyStatus"] = "public"
            if change == "wrong-title": invalid["snippet"]["title"] = "unapproved"
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.uploads.complete(self.job["id"], claim["claim"], invalid)
        for _ in range(2):
            saved = self.uploads.complete(self.job["id"], claim["claim"], video)
            self.assertEqual(saved["upload"]["state"], "uploaded")
        self.assertIsNone(self.uploads.next())

    def test_auto_private_upload_is_opt_in_and_snapshots_defaults(self):
        self.store.settings({**DEFAULTS, "youtube": {**self.config, "auto_upload": True}})
        saved = self.prepared(False)
        self.assertEqual(saved["upload"]["state"], "ready")
        self.store.settings({**DEFAULTS, "youtube": {**self.config, "channel_id": "UC"+"b"*22}})
        self.assertEqual(self.uploads.next()["channel_id"], self.config["channel_id"])

    def test_old_settings_gain_new_channel_defaults(self):
        import json
        with self.store.transaction() as db:
            old = {k: v for k, v in DEFAULTS.items() if k != "youtube"}
            db.execute("UPDATE settings SET data=? WHERE id=1", (json.dumps(old),))
        self.assertIsNone(self.store.settings()["youtube"]["made_for_kids"])
