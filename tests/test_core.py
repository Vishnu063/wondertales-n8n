import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from wondertales.core import Pipeline, StopJob, Store, allowed_file, validate


def settings(root):
    return {'accounts': {'flow-main': {'profile': 'dedicated'}},
            'youtubeDestinations': ['channel-main'], 'importsDir': str(root/'imports')}


def body():
    return {'title':'A small adventure','story':'Two friends help a tiny bird.', 'language':'English',
            'aspectRatio':'9:16','durationSeconds':30,'flowAccount':'flow-main',
            'youtubeDestination':'channel-main','creditCostPerClip':1,'maxCreditsPerJob':20,
            'consistencyMode':'text','selectedCharacters':[
                {'name':'A','facePrompt':'round face','bodyPrompt':'blue coat'},
                {'name':'B','facePrompt':'long ears','bodyPrompt':'yellow coat'}]}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.config=settings(self.root); self.store=Store(self.root/'test.sqlite3')
    def tearDown(self):
        self.tmp.cleanup()
    def submit(self):
        return self.store.submit(validate(body(),self.config))[0]
    def test_private_kids_model_and_credit_cap_are_enforced(self):
        b=body(); b.update(uploadVisibility='public',madeForKids=False,model='expensive')
        value=validate(b,self.config)
        self.assertEqual((value['uploadVisibility'],value['madeForKids'],value['model']),('private',True,'veo-lite'))
        self.assertEqual(value['plannedSceneCount'],4)
        b['maxCreditsPerJob']=2
        with self.assertRaises(ValueError): validate(b,self.config)
    def test_invalid_inputs_and_account_routes_are_rejected(self):
        for k,v in [('durationSeconds',31),('flowAccount','other'),('language','Other'),
                    ('creditCostPerClip',float('nan')),('maxCreditsPerJob',True)]:
            b=body(); b[k]=v
            with self.subTest(k=k), self.assertRaises(ValueError): validate(b,self.config)
    def test_deduplication_ignores_request_id(self):
        first=body(); first['requestId']='one'
        second=body(); second['requestId']='two'
        a,created=self.store.submit(validate(first,self.config))
        b,again=self.store.submit(validate(second,self.config))
        self.assertTrue(created); self.assertFalse(again); self.assertEqual(a['id'],b['id'])
    def test_concurrent_upload_claim_only_one_wins(self):
        job=self.submit(); self.store.update(job['id'],'ready')
        outcomes=[]
        def claim():
            try: outcomes.append(self.store.claim_upload(job['id'],'channel-main'))
            except ValueError: pass
        threads=[threading.Thread(target=claim) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(len(outcomes),1)
    def test_wrong_channel_cannot_claim(self):
        j=self.submit(); self.store.update(j['id'],'ready')
        with self.assertRaises(ValueError): self.store.claim_upload(j['id'],'wrong-channel')
    def test_restart_preserves_completed_scene_and_blocks_uncertain(self):
        j=self.submit(); clip=self.root/'saved.mp4'; clip.write_bytes(b'saved')
        self.store.scene(j['id'],0,'done',clip)
        self.store.scene(j['id'],1,'generating'); self.store.update(j['id'],'generating')
        queued=self.store.recover_after_restart(); recovered=self.store.get(j['id'])
        self.assertNotIn(j['id'],queued); self.assertEqual(recovered['state'],'needs_reconciliation')
        self.assertEqual(recovered['scenes'][0]['state'],'done')
        self.assertEqual(recovered['scenes'][1]['state'],'uncertain')
    def test_ambiguous_upload_cannot_be_reclaimed(self):
        j=self.submit(); self.store.update(j['id'],'ready')
        claim=self.store.claim_upload(j['id'],'channel-main'); self.store.recover_after_restart()
        with self.assertRaises(ValueError): self.store.claim_upload(j['id'],'channel-main')
        self.store.complete_upload(j['id'],claim,'abcdefghijk')
        self.assertEqual(self.store.get(j['id'])['state'],'uploaded')
        self.store.complete_upload(j['id'],claim,'abcdefghijk')
    def test_failed_credit_check_does_not_submit_generation(self):
        pipeline=Pipeline(self.store,self.config,self.root)
        pipeline.command=Mock(return_value=Mock(returncode=0,stdout='{"credits":0,"authenticated":true}'))
        with self.assertRaises(StopJob): pipeline.preflight(validate(body(),self.config))
        self.assertEqual(pipeline.command.call_count,1)
        self.assertEqual(pipeline.command.call_args.args[0][:3],['gflow','credits','user'])
    def test_unknown_balance_and_login_fail_closed(self):
        pipeline=Pipeline(self.store,self.config,self.root)
        for response in [Mock(returncode=1,stdout=''),Mock(returncode=0,stdout='{"credits":null}')]:
            pipeline.command=Mock(return_value=response)
            with self.assertRaises(StopJob): pipeline.preflight(validate(body(),self.config))
    def test_import_paths_cannot_escape_with_symlinks(self):
        imports=self.root/'imports'; imports.mkdir()
        outside=self.root/'outside.png'; outside.write_bytes(b'example')
        (imports/'linked.png').symlink_to(outside)
        with self.assertRaises(ValueError): allowed_file(imports/'linked.png',imports)
    def test_missing_reference_stops_before_balance_or_generation(self):
        pipeline=Pipeline(self.store,self.config,self.root); pipeline.command=Mock()
        b=body(); b['consistencyMode']='reference'
        with self.assertRaises(StopJob): pipeline.preflight(validate(b,self.config))
        pipeline.command.assert_not_called()
    def test_no_generation_retry_for_uncertain_scene(self):
        j=self.submit(); self.store.scene(j['id'],0,'uncertain')
        pipeline=Pipeline(self.store,self.config,self.root); pipeline.command=Mock()
        with self.assertRaises(StopJob): pipeline.execute(j['id'])
        pipeline.command.assert_not_called()


class ProviderFailureTests(unittest.TestCase):
    def test_timeout_creates_uncertain_scene_without_retry_or_next_scene(self):
        import subprocess
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); config=settings(root); store=Store(root/'jobs.sqlite3')
            value=validate(body(),config); job,_=store.submit(value)
            work=root/'jobs'/job['id']; work.mkdir(parents=True)
            (work/'narration.mp3').write_bytes(b'placeholder')
            (work/'captions.srt').write_text('captions')
            pipe=Pipeline(store,config,root); calls=[]
            def command(args,**kwargs):
                if args[:3]==['gflow','credits','user']:
                    return Mock(returncode=0,stdout='{"credits":1000}')
                if args[0]=='ffmpeg': return Mock(returncode=0,stdout='subtitles')
                calls.append(args)
                raise subprocess.TimeoutExpired('gflow',900)
            pipe.command=command
            with patch('wondertales.core.shutil.which',return_value='/fake/tool'), patch('wondertales.core.probe',return_value={'format':{'duration':'1'}}):
                with self.assertRaises(StopJob) as caught: pipe.execute(job['id'])
            self.assertEqual(caught.exception.state,'needs_reconciliation')
            self.assertEqual(len(calls),1)
            scenes=store.get(job['id'])['scenes']
            self.assertEqual(scenes[0]['state'],'uncertain')
            self.assertTrue(all(s['state']=='pending' for s in scenes[1:]))


if __name__=='__main__': unittest.main()
