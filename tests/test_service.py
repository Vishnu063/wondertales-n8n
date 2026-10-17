import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from wondertales.app import Service, load_settings, make_handler
from test_core import body


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root,self.settings,self.token=load_settings(Path(self.tmp.name))
        self.service=Service(self.root,self.settings)
        self.service.enqueue=Mock()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.service,self.token))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.service.executor.shutdown(wait=True); self.tmp.cleanup()
    def request(self,path,data=None,token=True):
        headers={'Content-Type':'application/json'}
        if token: headers['X-WonderTales-Key']=self.token
        req=Request(f'http://127.0.0.1:{self.server.server_port}'+path,
                    data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=3) as response: return response.status,json.load(response)
        except HTTPError as response: return response.code,json.load(response)
    def test_jobs_require_token(self):
        code,_=self.request('/v1/jobs',token=False); self.assertEqual(code,401)
        code,result=self.request('/health',token=False); self.assertEqual(code,200)
        self.assertNotIn('token',result)
    def test_submission_saves_once_without_bypassing_daily_queue(self):
        a,first=self.request('/v1/jobs',body()); b,second=self.request('/v1/jobs',body())
        self.assertEqual((a,b),(202,200)); self.assertTrue(second['duplicate'])
        self.assertEqual(first['id'],second['id']); self.service.enqueue.assert_not_called()
        self.assertEqual(first['state'],'waiting')
    def test_diagnostics_do_not_reveal_secrets(self):
        code,data=self.request('/v1/setup'); self.assertEqual(code,200)
        self.assertNotIn(self.token,json.dumps(data)); self.assertEqual(data['browserConcurrency'],1)
    def test_unsafe_resume_is_rejected(self):
        _,job=self.request('/v1/jobs',body())
        self.service.store.scene(job['id'],0,'uncertain')
        self.service.store.update(job['id'],'needs_reconciliation')
        code,_=self.request('/v1/jobs/'+job['id']+'/resume',{})
        self.assertEqual(code,400)
    def test_other_jobs_do_not_open_browser_after_login_failure(self):
        _,first=self.request('/v1/jobs',body()); self.service.store.update(first['id'],'blocked_login')
        other=body(); other['title']='Another story'
        _,second=self.request('/v1/jobs',other)
        self.service.pipeline.execute=Mock(); self.service.work(second['id'])
        self.service.pipeline.execute.assert_not_called()
        self.assertEqual(self.service.store.get(second['id'])['state'],'blocked_browser')

    def test_uncertain_scene_requires_explicit_unsubmitted_confirmation(self):
        _,job=self.request('/v1/jobs',body())
        self.service.store.scene(job['id'],0,'uncertain')
        self.service.store.update(job['id'],'needs_reconciliation')
        route='/v1/jobs/'+job['id']+'/confirm-unsubmitted'
        status,_=self.request(route,{'sceneIndex':0})
        self.assertEqual(status,400)
        status,_=self.request(route,{'sceneIndex':0,'confirmation':'NOT_SUBMITTED'})
        self.assertEqual(status,200)
        self.assertEqual(self.service.store.get(job['id'])['state'],'needs_attention')
    def test_account_mapping_is_private_and_existing_job_stays_pinned(self):
        _,job=self.request('/v1/jobs',body())
        self.assertEqual(job['body']['flowProfile'],'wondertales')
        code,result=self.request('/v1/setup/accounts',{'flowAlias':'flow-main','profile':'spare-two','destination':'channel-two'})
        self.assertEqual(code,200)
        self.assertIn('channel-two',result['youtubeDestinations'])
        old=self.service.store.get(job['id'])
        self.assertEqual(old['body']['flowProfile'],'wondertales')
        self.assertEqual(self.service.settings['accounts']['flow-main']['profile'],'spare-two')
        self.assertEqual((self.root/'settings.json').stat().st_mode & 0o777,0o600)
    def test_reset_narration_keeps_successful_clips(self):
        _,job=self.request('/v1/jobs',body())
        folder=self.root/'jobs'/job['id']; folder.mkdir(parents=True)
        for name in ('narration.mp3','captions.srt','final.mp4','clip-00.mp4'):
            (folder/name).write_bytes(b'test')
        self.service.store.update(job['id'],'needs_attention')
        code,_=self.request('/v1/jobs/'+job['id']+'/reset-narration',{})
        self.assertEqual(code,200)
        self.assertTrue((folder/'clip-00.mp4').exists())
        self.assertFalse((folder/'narration.mp3').exists())

    def test_story_bank_validation_is_all_or_nothing(self):
        valid=body(); invalid=body(); invalid['durationSeconds']=999
        status,_=self.request('/v1/stories',{'stories':[valid,invalid]})
        self.assertEqual(status,400)
        self.assertEqual(len(self.service.store.list()),0)
        other=body(); other['title']='Second story'
        status,data=self.request('/v1/stories',{'stories':[valid,other]})
        self.assertEqual(status,202)
        self.assertEqual(len(data['jobs']),2)
        self.service.enqueue.assert_not_called()
    def test_pause_and_resume_commands_preserve_story_bank(self):
        _,job=self.request('/v1/jobs',body())
        status,data=self.request('/v1/queue/command',{'action':'pause'})
        self.assertEqual(status,200); self.assertTrue(data['paused'])
        self.request('/v1/queue/command',{'action':'tick'})
        self.service.enqueue.assert_not_called()
        status,data=self.request('/v1/queue/command',{'action':'resume'})
        self.assertFalse(data['paused'])
        self.service.enqueue.assert_called_once_with(job['id'])
    def test_safe_resume_does_not_bypass_queue_or_global_pause(self):
        _,job=self.request('/v1/jobs',body())
        self.service.store.update(job['id'],'needs_attention')
        self.service.store.set_paused(True)
        status,_=self.request('/v1/jobs/'+job['id']+'/resume',{})
        self.assertEqual(status,200)
        self.assertEqual(self.service.store.get(job['id'])['state'],'waiting')
        self.service.enqueue.assert_not_called()
    def test_archiving_stopped_job_preserves_scene_records(self):
        _,job=self.request('/v1/jobs',body())
        self.service.store.scene(job['id'],0,'done',self.root/'clip.mp4')
        self.service.store.update(job['id'],'story_too_long')
        status,_=self.request('/v1/jobs/'+job['id']+'/archive',{})
        self.assertEqual(status,200)
        self.assertEqual(self.service.store.get(job['id'])['scenes'][0]['state'],'done')

    def test_pause_hides_ready_jobs_from_automatic_upload(self):
        _,job=self.request('/v1/jobs',body())
        self.service.store.update(job['id'],'ready')
        _,data=self.request('/v1/jobs/'+job['id'])
        self.assertTrue(data['canClaimUpload'])
        self.service.store.set_paused(True)
        _,data=self.request('/v1/jobs/'+job['id'])
        self.assertFalse(data['canClaimUpload'])

    def test_growth_endpoints_require_auth_and_story_check_spends_nothing(self):
        from test_growth import snapshot
        for path, data in [('/v1/growth/report', None), ('/v1/analytics/snapshot', snapshot()),
                           ('/v1/analytics/jobs', None), ('/v1/stories/check', body())]:
            status, _ = self.request(path, data, token=False)
            self.assertEqual(status, 401)
        self.service.pipeline.command = Mock()
        status, result = self.request('/v1/stories/check', body())
        self.assertEqual(status, 200); self.assertIn('warnings', result)
        self.service.pipeline.command.assert_not_called()
        self.assertEqual(self.service.store.list(), [])
        status, _ = self.request('/v1/analytics/snapshot', snapshot())
        self.assertEqual(status, 200)
        status, result = self.request('/v1/growth/report')
        self.assertEqual(result['channels'][0]['subscriberCount'], 42)


if __name__=='__main__': unittest.main()
