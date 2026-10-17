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
    def test_submission_queues_once(self):
        a,first=self.request('/v1/jobs',body()); b,second=self.request('/v1/jobs',body())
        self.assertEqual((a,b),(202,200)); self.assertTrue(second['duplicate'])
        self.assertEqual(first['id'],second['id']); self.service.enqueue.assert_called_once()
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


if __name__=='__main__': unittest.main()
