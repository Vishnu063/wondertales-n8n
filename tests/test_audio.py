from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from wondertales import audio
from wondertales.core import StopJob, run
from test_core import body, settings


class CaptionTests(unittest.TestCase):
    def test_srt_round_trip_and_timing_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'captions.srt'
            cues=[(0,0.5,'Hello'),(1,1.5,'नमस्ते')]
            audio.write_srt(path,cues); self.assertEqual(audio.parse_srt(path,2),cues)
            for content in ('1\n00:00:00,000 --> 00:00:03,000\nToo long',
                            '1\n00:00:01,000 --> 00:00:00,000\nReverse',
                            '1\n00:00:00,000 --> 00:00:01,000\nA\n\n2\n00:00:00,500 --> 00:00:01,500\nOverlap'):
                path.write_text(content)
                with self.assertRaises(ValueError): audio.parse_srt(path,2)
    def test_owner_paths_cannot_escape_imports_even_with_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); imports=root/'imports'; imports.mkdir()
            outside=root/'audio.wav'; outside.write_bytes(b'outside')
            (imports/'link.wav').symlink_to(outside)
            b=body(); b.update(audioFile=str(imports/'link.wav'),captionFile=str(imports/'captions.srt'))
            with self.assertRaises(StopJob): audio.owner_assets(b,settings(root))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class AudioMediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.config=settings(self.root); (self.root/'imports').mkdir(); self.work=self.root/'work'; self.work.mkdir()
    def tearDown(self): self.tmp.cleanup()
    def sine(self,path,duration):
        result=run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'sine=frequency=440:duration={duration}',path])
        self.assertEqual(result.returncode,0,result.stderr)
    def test_owner_audio_is_converted_with_existing_captions_without_tts(self):
        source=self.root/'imports/voice.wav'; captions=self.root/'imports/voice.srt'
        self.sine(source,1); audio.write_srt(captions,[(0,0.9,'Original song lyrics')])
        b=body(); b.update(audioFile=str(source),captionFile=str(captions))
        calls=[]
        def command(args,**kwargs):
            calls.append(str(args[0])); self.assertNotIn(str(args[0]),('gflow','edge-tts')); return run(args,**kwargs)
        audio.prepare(b,self.config,self.work,command)
        self.assertTrue((self.work/'narration.mp3').is_file())
        self.assertEqual((self.work/'captions.srt').read_text(),captions.read_text())
        cached=Mock(); source.unlink(); captions.unlink()
        audio.prepare(b,self.config,self.work,cached); cached.assert_not_called()
    def test_storyboard_voice_slots_and_caption_offsets_are_aligned_before_flow(self):
        b=body(); b.update(durationSeconds=10,storyboard=[{'narration':'First scene.'},{'narration':'Second scene.'}])
        for n in range(2):
            self.sine(self.work/f'scene-voice-{n:02}.mp3',0.5)
            audio.write_srt(self.work/f'scene-captions-{n:02}.srt',[(0,0.4,'First' if n==0 else 'Second')])
        def command(args,**kwargs):
            self.assertEqual(str(args[0]),'ffmpeg'); return run(args,**kwargs)
        audio.prepare(b,self.config,self.work,command)
        cues=audio.parse_srt(self.work/'captions.srt',10.1)
        self.assertEqual(cues[1][0],8)
        self.assertAlmostEqual(float(audio.probe(self.work/'narration.mp3')['format']['duration']),10,delta=0.1)
    def test_overlong_scene_stops_before_any_provider_call(self):
        b=body(); b.update(durationSeconds=1,storyboard=[{'narration':'Overlong narration'}])
        self.sine(self.work/'scene-voice-00.mp3',2)
        audio.write_srt(self.work/'scene-captions-00.srt',[(0,1.5,'Too long')])
        command=Mock()
        with self.assertRaises(StopJob) as caught: audio.prepare(b,self.config,self.work,command)
        self.assertEqual(caught.exception.state,'story_too_long'); command.assert_not_called()


if __name__=='__main__': unittest.main()
