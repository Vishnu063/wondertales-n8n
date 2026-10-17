from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from wondertales.core import Pipeline, StopJob, Store, validate
from wondertales.queue import QueueManager
from test_core import body, settings


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.config=settings(self.root); self.store=Store(self.root/'state.sqlite3')
        self.service=SimpleNamespace(store=self.store,mutations=threading.Lock(),enqueue=Mock())
        self.queue=QueueManager(self.service)
        self.now=stamp('2030-01-01T10:00:00')
    def tearDown(self):
        self.tmp.cleanup()
    def job(self,title='First'):
        b=body(); b['title']=title
        return self.store.submit(validate(b,self.config))[0]
    def finish(self,ident):
        self.store.update(ident,'ready')
        claim=self.store.claim_upload(ident,'channel-main')
        self.store.complete_upload(ident,claim,'abcdefghijk')
    def test_one_daily_slot_cannot_be_bypassed_by_more_ticks(self):
        first,second=self.job(),self.job('Second')
        self.assertTrue(self.queue.tick(self.now)['dispatched'])
        self.finish(first['id'])
        result=self.queue.tick(self.now+60)
        self.assertEqual(result['reason'],'daily_limit')
        self.assertEqual(self.store.get(second['id'])['state'],'waiting')
        self.service.enqueue.assert_called_once_with(first['id'])
    def test_calendar_reset_uses_india_midnight_not_utc_midnight(self):
        first,second=self.job(),self.job('Second')
        before=stamp('2030-01-01T18:29:00'); after=stamp('2030-01-01T18:30:00')
        self.queue.tick(before); self.finish(first['id'])
        self.assertEqual(self.queue.day(before),'2030-01-01')
        self.assertEqual(self.queue.day(after),'2030-01-02')
        self.assertTrue(self.queue.tick(after)['dispatched'])
        self.assertEqual(self.service.enqueue.call_count,2)
    def test_pause_and_daily_reservations_survive_restart(self):
        first,second=self.job(),self.job('Second')
        self.queue.tick(self.now); self.finish(first['id']); self.store.set_paused(True)
        restarted=Store(self.root/'state.sqlite3')
        self.assertTrue(restarted.is_paused())
        self.assertFalse(restarted.reserve_day(self.queue.day(self.now),second['id']))
        restarted.set_paused(False)
        self.assertFalse(restarted.reserve_day(self.queue.day(self.now),second['id']))
    def test_pause_prevents_generation_and_new_upload_claims(self):
        j=self.job(); self.store.set_paused(True)
        self.assertEqual(self.queue.tick(self.now)['reason'],'paused')
        self.service.enqueue.assert_not_called()
        pipeline=Pipeline(self.store,self.config,self.root); pipeline.command=Mock()
        with self.assertRaises(StopJob) as stop: pipeline.execute(j['id'])
        self.assertEqual(stop.exception.state,'paused'); pipeline.command.assert_not_called()
        self.store.update(j['id'],'ready')
        with self.assertRaises(ValueError): self.store.claim_upload(j['id'],'channel-main')
    def test_credit_retry_waits_and_only_releases_original_job(self):
        first,second=self.job(),self.job('Second')
        self.queue.tick(self.now); self.service.enqueue.reset_mock()
        self.store.update(first['id'],'blocked_credit',retry_after=self.now+3600)
        self.assertEqual(self.queue.tick(self.now+3599)['reason'],'waiting_for_credit_check')
        self.service.enqueue.assert_not_called()
        self.assertTrue(self.queue.tick(self.now+3600)['dispatched'])
        self.service.enqueue.assert_called_once_with(first['id'])
        self.assertEqual(self.store.get(second['id'])['state'],'waiting')
    def test_login_or_uncertain_billing_never_retries_automatically(self):
        j=self.job(); self.job('Second')
        for state in ('blocked_login','blocked_balance','needs_reconciliation','upload_uncertain'):
            self.store.update(j['id'],state)
            self.assertEqual(self.queue.tick(self.now)['reason'],'needs_you')
        self.service.enqueue.assert_not_called()
    def test_concurrent_ticks_dispatch_only_once(self):
        self.job(); self.job('Second')
        threads=[threading.Thread(target=lambda:self.queue.tick(self.now)) for _ in range(8)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.service.enqueue.assert_called_once()
    def test_batch_save_is_deduplicated_and_preserves_order(self):
        a=body(); b=body(); b['title']='Second'
        rows=self.store.submit_many([validate(a,self.config),validate(b,self.config),validate(a,self.config)])
        self.assertEqual([created for _,created in rows],[True,True,False])
        self.assertEqual(rows[0][0]['id'],rows[2][0]['id'])
        self.assertEqual(len(self.store.list()),2)
        self.queue.tick(self.now)
        self.service.enqueue.assert_called_once_with(rows[0][0]['id'])
    def test_ready_video_holds_queue_until_private_upload_finishes(self):
        j=self.job(); self.job('Second'); self.store.update(j['id'],'ready')
        self.assertEqual(self.queue.tick(self.now)['reason'],'awaiting_private_upload')
        self.service.enqueue.assert_not_called()
    def test_summary_explains_exact_next_action(self):
        j=self.job(); self.store.update(j['id'],'needs_references','Image file is missing.')
        summary=self.queue.summary()
        self.assertEqual(summary['attentionRequired'],1)
        self.assertEqual(summary['needsYou'][0]['problem'],'Image file is missing.')
        self.assertIn('reference',summary['needsYou'][0]['nextAction'])
        self.assertEqual(summary['dailyLimit'],1)
    def test_interrupted_queue_is_not_dispatched_during_restart(self):
        j=self.job(); self.store.update(j['id'],'queued')
        self.assertEqual(self.store.recover_after_restart(),[])
        self.assertEqual(self.store.get(j['id'])['state'],'waiting')
    def test_second_private_upload_cannot_use_same_local_day(self):
        first,second=self.job(),self.job('Second')
        self.finish(first['id'])
        self.store.update(second['id'],'ready')
        with self.assertRaises(ValueError): self.store.claim_upload(second['id'],'channel-main')
    def test_migration_preserves_existing_jobs(self):
        path=self.root/'old.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE jobs(id TEXT PRIMARY KEY,fingerprint TEXT UNIQUE NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL,detail TEXT NOT NULL DEFAULT '',progress INTEGER DEFAULT 0,report TEXT NOT NULL DEFAULT '{}',claim TEXT,youtube_id TEXT,created REAL NOT NULL,updated REAL NOT NULL)")
            old=validate(body(),self.config)
            db.execute('INSERT INTO jobs(id,fingerprint,body,state,created,updated) VALUES(?,?,?,?,?,?)',('old-job','old-fingerprint',json.dumps(old),'queued',self.now,self.now))
        migrated=Store(path)
        self.assertEqual(migrated.get('old-job')['body']['title'],old['title'])
        migrated.recover_after_restart()
        self.assertEqual(migrated.get('old-job')['state'],'waiting')
        with migrated.connect() as db:
            cols={row[1] for row in db.execute('PRAGMA table_info(jobs)')}
        self.assertTrue({'retry_after','ready_at','uploaded_at'}.issubset(cols))
        self.assertFalse(migrated.is_paused())
