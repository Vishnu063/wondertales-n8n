"""Real FFmpeg assembly with synthetic media; no provider, browser, TTS, or credits."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from wondertales.core import Pipeline, Store, quality, run
from test_core import body, settings


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class MediaTests(unittest.TestCase):
    def test_real_assembly_and_completed_scene_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); config=settings(root); store=Store(root/'jobs.sqlite3')
            b=body(); b.update(durationSeconds=4,plannedSceneCount=1,estimatedCredits=1)
            job,_=store.submit(b); pipe=Pipeline(store,config,root)
            calls=[]
            def fake(args,**kw):
                args=[str(x) for x in args]
                if args[0]=='gflow':
                    if args[1:3]==['credits','user']:
                        return subprocess.CompletedProcess(args,0,'{"credits":1000,"authenticated":true}','')
                    calls.append(args)
                    self.assertEqual(args[args.index('--count')+1],'1')
                    folder=Path(args[args.index('--out-dir')+1]); file=folder/'provider.mp4'
                    r=run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=720x1280:r=2',
                           '-t','8','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',file])
                    self.assertEqual(r.returncode,0,r.stderr)
                    return subprocess.CompletedProcess(args,0,json.dumps({'succeeded':True,'local_path':str(file),'media_id':'test-media'}),'')
                if args[0]=='edge-tts':
                    audio=Path(args[args.index('--write-media')+1]); srt=Path(args[args.index('--write-subtitles')+1])
                    r=run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=1','-c:a','libmp3lame',audio])
                    srt.write_text('1\n00:00:00,000 --> 00:00:01,000\nTwo friends help a bird.\n')
                    return r
                return run(args,**kw)
            pipe.command=fake
            original=shutil.which
            with patch('wondertales.core.shutil.which',side_effect=lambda x: '/fake/'+x if x in ('gflow','edge-tts') else original(x)):
                pipe.execute(job['id'])
                self.assertEqual(store.get(job['id'])['state'],'ready')
                self.assertEqual(len(store.get(job['id'])['report']['thumbnailCandidates']),3)
                self.assertEqual(len(calls),1)
                pipe.execute(job['id'])
                self.assertEqual(len(calls),1,'Assembly resume must not regenerate a completed clip')
            report=quality(root/'jobs'/job['id']/'final.mp4','9:16',4)
            self.assertTrue(report['hasAudio'])
