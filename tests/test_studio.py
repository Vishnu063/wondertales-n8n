import copy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from wondertales.core import Pipeline, StopJob, Store, validate
from wondertales.growth import Growth, cost_report
from wondertales.studio import Studio
from test_core import body, settings
from test_growth import snapshot, VIDEO, CHANNEL


def plan():
    return [{'characters':['A','B'], 'setting':'A garden', 'action':'The friends help a bird.',
             'narration':'The friends help.'} for _ in range(4)]


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.config=settings(self.root); self.store=Store(self.root/'jobs.db')
        self.growth=Growth(self.store,self.config); self.studio=Studio(self.store,self.config,self.root)
    def tearDown(self): self.tmp.cleanup()
    def completed(self, uploaded=False):
        job,_=self.store.submit(validate(body(),self.config))
        folder=self.root/'jobs'/job['id']; folder.mkdir(parents=True)
        for n in range(4):
            file=folder/f'clip-{n:02}.mp4'; file.write_bytes(f'original {n}'.encode())
            self.store.scene(job['id'],n,'done',file,'media-'+str(n))
        for name in ('narration.mp3','captions.srt'): (folder/name).write_bytes(b'saved audio or captions')
        self.store.update(job['id'],'ready')
        if uploaded:
            claim=self.store.claim_upload(job['id'],'channel-main'); self.store.complete_upload(job['id'],claim,VIDEO)
        return self.store.get(job['id'])
    def request(self):
        return {'sceneIndex':1,'creditCostPerClip':2,'additionalCreditCap':3,'direction':'Show the bird landing clearly.',
                'requestLabel':'revision-one','confirmation':'REPLACE_ONE_SCENE'}
    def test_storyboard_checks_count_cast_and_narration_before_spending(self):
        b=body(); b['storyboard']=plan(); value=validate(b,self.config)
        self.assertEqual(value['story'],' '.join(s['narration'] for s in plan()))
        self.assertEqual(value['storyOutline'],b['story'])
        for mutate in (lambda b:b.update(storyboard=plan()[:3]),
                       lambda b:b['storyboard'][0].update(characters=['Unknown']),
                       lambda b:b['storyboard'][0].update(narration=''),
                       lambda b:b.update(audioFile='/audio.wav'),
                       lambda b:b.update(visualStyle='')):
            wrong=copy.deepcopy(b); mutate(wrong)
            with self.assertRaises(ValueError): validate(wrong,self.config)
    def test_character_library_is_immutable_and_job_snapshot_independent(self):
        characters=body()['selectedCharacters']
        self.studio.save_library({'version':'v1','characters':characters})
        b=body(); b.update(selectedCharacters=self.studio.library()['characters'],characterLibraryVersion='v1')
        job,_=self.store.submit(validate(b,self.config))
        changed=copy.deepcopy(characters); changed[0]['bodyPrompt']='green coat'
        with self.assertRaises(ValueError): self.studio.save_library({'version':'v1','characters':changed})
        self.studio.save_library({'version':'v2','characters':changed})
        self.assertEqual(self.studio.library()['version'],'v2')
        self.assertEqual(self.store.get(job['id'])['body']['selectedCharacters'][0]['bodyPrompt'],'blue coat')
    def test_library_reference_changes_stop_before_balance(self):
        imports=self.root/'imports'; imports.mkdir(); image=imports/'face.png'; image.write_bytes(b'original-image')
        chars=body()['selectedCharacters']; chars[0]['referenceImage']=str(image); chars[1]['referenceImage']=str(image)
        self.studio.save_library({'version':'images-v1','characters':chars})
        b=body(); b.update(consistencyMode='reference',selectedCharacters=self.studio.library()['characters'])
        image.write_bytes(b'changed-image')
        from unittest.mock import Mock
        pipe=Pipeline(self.store,self.config,self.root); pipe.command=Mock()
        with self.assertRaises(StopJob) as caught: pipe.preflight(validate(b,self.config))
        self.assertEqual(caught.exception.state,'needs_references'); pipe.command.assert_not_called()
    def test_preview_changes_no_jobs_files_or_provider_state(self):
        job=self.completed(); preview=self.studio.replacement(job['id'],self.request())
        self.assertEqual(preview['estimatedNewCredits'],2)
        self.assertEqual(len(self.store.list()),1)
        self.assertEqual(self.store.get(job['id'])['state'],'ready')
    def test_revision_reuses_other_scenes_and_repeated_request_is_idempotent(self):
        job=self.completed()
        with patch('wondertales.studio.probe',return_value={'format':{'duration':'8'},'streams':[{'codec_type':'video'}]}):
            result=self.studio.replacement(job['id'],self.request(),create=True)
        revision=self.store.get(result['jobId'])
        self.assertEqual([s['state'] for s in revision['scenes']],['done','pending','done','done'])
        self.assertEqual(self.store.get(job['id'])['state'],'superseded')
        for n in (0,2,3): self.assertEqual(Path(revision['scenes'][n]['path']).read_bytes(),f'original {n}'.encode())
        self.assertTrue((self.root/'jobs'/job['id']/'clip-01.mp4').exists())
        again=self.studio.replacement(job['id'],self.request(),create=True)
        self.assertTrue(again['duplicate']); self.assertEqual(again['jobId'],revision['id'])
        self.assertEqual(len(self.store.list()),2)
        self.assertEqual(cost_report(revision)['submittedSceneCreditEstimate'],0)
        self.store.scene(revision['id'],1,'uncertain')
        self.assertEqual(cost_report(self.store.get(revision['id']))['submittedSceneCreditEstimate'],2)
        changed=self.request(); changed['direction']='Different direction'
        with self.assertRaises(ValueError): self.studio.replacement(job['id'],changed,create=True)
    def test_revision_rejects_missing_confirmation_low_cap_uncertain_and_missing_files(self):
        job=self.completed()
        wrong=self.request(); wrong['confirmation']=''
        with self.assertRaises(ValueError): self.studio.replacement(job['id'],wrong,create=True)
        wrong=self.request(); wrong['additionalCreditCap']=1
        with self.assertRaises(ValueError): self.studio.replacement(job['id'],wrong,create=True)
        self.store.scene(job['id'],1,'uncertain')
        with self.assertRaises(ValueError): self.studio.replacement(job['id'],self.request(),create=True)
        self.store.scene(job['id'],1,'done',self.root/'missing.mp4')
        with self.assertRaises(ValueError): self.studio.replacement(job['id'],self.request(),create=True)
        self.assertEqual(len(self.store.list()),1)
    def test_uploaded_original_and_youtube_id_remain_unchanged(self):
        job=self.completed(uploaded=True)
        with patch('wondertales.studio.probe',return_value={'format':{'duration':'8'},'streams':[{'codec_type':'video'}]}):
            revision=self.studio.replacement(job['id'],self.request(),create=True)
        old=self.store.get(job['id'])
        self.assertEqual((old['state'],old['youtube_id']),('uploaded',VIDEO))
        self.assertIsNone(self.store.get(revision['jobId'])['youtube_id'])
    def test_replacement_extra_credit_cap_is_checked_before_balance(self):
        from unittest.mock import Mock
        b=validate(body(),self.config); b.update(replacementCreditCap=1)
        pipe=Pipeline(self.store,self.config,self.root); pipe.command=Mock()
        with self.assertRaises(StopJob): pipe.preflight(b,2)
        pipe.command.assert_not_called()
    def retention(self, job):
        sample=snapshot()
        return {**{k:sample[k] for k in ('destination','channelId','startDate','endDate')},'jobId':job['id'],'video':VIDEO,
                'points':[{'elapsedVideoTimeRatio':0,'audienceWatchRatio':1.2,'relativeRetentionPerformance':0.8},
                          {'elapsedVideoTimeRatio':0.5,'audienceWatchRatio':0.6,'relativeRetentionPerformance':0.4}]}
    def test_retention_is_account_bound_and_marks_inspection_not_causation(self):
        job=self.completed(uploaded=True); self.growth.save(snapshot())
        data=self.retention(job); self.studio.save_retention(data)
        report=self.studio.retention_report()[0]
        self.assertEqual(report['inspectIntervals'][0]['toSeconds'],15)
        self.assertIn('do not prove',report['note'])
        self.assertEqual(report['points'][0]['audienceWatchRatio'],1.2)
        for change in ({'video':'12345678901'},{'channelId':'UC'+'b'*22},{'destination':'another'}):
            bad=copy.deepcopy(data); bad.update(change)
            with self.assertRaises(ValueError): self.studio.save_retention(bad)
        with self.store.connect() as db: db.execute('UPDATE retention SET updated=?',(time.time()-4*86400,))
        self.assertFalse(self.studio.retention_report()[0]['inspectIntervals'])
    def test_retention_rejects_bad_ratios_and_replaces_windows(self):
        job=self.completed(uploaded=True); self.growth.save(snapshot()); data=self.retention(job)
        self.studio.save_retention(data); self.studio.save_retention(data)
        self.assertEqual(len(self.studio.retention_report()),1)
        for field,value in [('elapsedVideoTimeRatio',1.1),('audienceWatchRatio',float('nan')),('relativeRetentionPerformance',-1)]:
            bad=copy.deepcopy(data); bad['points'][0][field]=value
            with self.assertRaises(ValueError): self.studio.save_retention(bad)
        data['points']=[]; self.studio.save_retention(data)
        self.assertEqual(self.studio.retention_report()[0]['inspectIntervals'],[])


if __name__=='__main__': unittest.main()
