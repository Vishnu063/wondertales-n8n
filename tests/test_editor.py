import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from wondertales.core import Pipeline, StopJob, Store, validate, run
from wondertales import editor
from test_core import body, settings

spec = importlib.util.spec_from_file_location('mpt_bridge', editor.REPO/'scripts/mpt_render.py')
bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.config = settings(self.root); self.store = Store(self.root/'jobs.db')
    def tearDown(self):
        self.tmp.cleanup()
    def test_editor_inputs_cannot_enable_other_providers_or_escape_music_limits(self):
        for values in ({'editor': 'paid-provider'}, {'musicVolume': float('nan')},
                       {'musicVolume': True}, {'musicVolume': 0.9}, {'musicFile': '/tmp/song.mp3'},
                       {'subtitleStyle': 'kids'}, {'rightsNote': []}):
            b = body(); b.update(values)
            with self.assertRaises(ValueError): validate(b, self.config)
    def test_missing_optional_editor_stops_before_flow_balance_or_generation(self):
        b = body(); b['editor'] = 'moneyprinterturbo'
        pipe = Pipeline(self.store, self.config, self.root); pipe.command = Mock()
        with patch('wondertales.editor.status', return_value={'available': False, 'action': 'Install optional editor'}):
            with self.assertRaises(StopJob) as caught: pipe.preflight(validate(b, self.config))
        self.assertEqual(caught.exception.state, 'needs_setup')
        pipe.command.assert_not_called()
    def test_renderer_environment_excludes_credentials_and_proxy(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'secret', 'HTTP_PROXY': 'private', 'GOOGLE_APPLICATION_CREDENTIALS': '/secret'}):
            env = editor.environment(self.root)
        for key in ('OPENAI_API_KEY', 'HTTP_PROXY', 'GOOGLE_APPLICATION_CREDENTIALS'):
            self.assertNotIn(key, env)
        self.assertEqual(env['HOME'], env['MPT_HOME'])
    def test_bridge_uses_existing_assets_and_no_random_music(self):
        render = Mock(return_value=True)
        data = {'video': '/video', 'audio': '/voice', 'subtitles': '/captions', 'output': '/output',
                'aspect': '9:16', 'font': 'font.ttf', 'style': 'kids', 'music': None, 'musicVolume': 0.12}
        bridge.render_manifest(data, SimpleNamespace, render)
        values = render.call_args.kwargs
        self.assertEqual(values['audio_path'], '/voice')
        self.assertEqual(values['params'].video_source, 'local')
        self.assertEqual(values['params'].bgm_type, '')
        self.assertEqual(values['params'].bgm_volume, 0)
        data['music'] = '/licensed-music'; render.return_value = False
        with self.assertRaises(RuntimeError): bridge.render_manifest(data, SimpleNamespace, render)
    def test_editor_failure_keeps_completed_scene_and_cannot_call_flow(self):
        b = body(); b['editor'] = 'moneyprinterturbo'
        job, _ = self.store.submit(validate(b, self.config))
        clip = self.root/'clip.mp4'; clip.write_bytes(b'saved')
        self.store.scene(job['id'], 0, 'done', clip)
        work = self.root/'work'; work.mkdir(); font = self.root/'font.ttf'; font.write_bytes(b'font')
        calls = []
        def command(args, **kw):
            self.assertNotEqual(str(args[0]), 'gflow')
            calls.append(args)
            return subprocess.CompletedProcess(args, 1 if str(args[0]).endswith('python') else 0)
        with patch('wondertales.editor.assets', return_value=(font, None)):
            with self.assertRaises(StopJob): editor.render(b, self.config, self.root, work, command)
        self.assertTrue(clip.exists())
        self.assertEqual(self.store.get(job['id'])['scenes'][0]['state'], 'done')
        self.assertEqual(len(calls), 3)
    def test_duplicate_story_stops_before_any_external_command(self):
        self.store.submit(validate(body(), self.config))
        b = body(); b['title'] = 'Repeated under another title'
        job, _ = self.store.submit(validate(b, self.config))
        pipe = Pipeline(self.store, self.config, self.root); pipe.command = Mock()
        with self.assertRaises(StopJob) as caught: pipe.execute(job['id'])
        self.assertIn('repeats', caught.exception.detail)
        pipe.command.assert_not_called()


if __name__ == '__main__': unittest.main()


@unittest.skipUnless(editor.shutil.which('ffmpeg') and editor.shutil.which('ffprobe'), 'FFmpeg required')
class EditorMediaPreparationTests(unittest.TestCase):
    def test_real_media_preparation_passes_timed_local_assets_to_isolated_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); work = root/'work'; work.mkdir(); config = settings(root)
            clip = work/'normalized-00.mp4'; voice = work/'narration.mp3'
            self.assertEqual(run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=blue:s=720x1280:r=2',
                                  '-t','1','-c:v','libx264','-preset','ultrafast',clip]).returncode, 0)
            self.assertEqual(run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=440:duration=0.5',voice]).returncode, 0)
            (work/'concat.txt').write_text("file 'normalized-00.mp4'\n")
            (work/'captions.srt').write_text('1\n00:00:00,000 --> 00:00:00,500\nA story.\n')
            font = root/'font.ttf'; font.write_bytes(b'fixture font; renderer is mocked')
            b = body(); b.update(editor='moneyprinterturbo', durationSeconds=1)
            called = []
            def command(args, **kw):
                if str(args[0]) == str(editor.interpreter(config)):
                    data = json.loads((work/'mpt-render.json').read_text())
                    called.append(data)
                    self.assertEqual(kw['env']['MPT_HOME'], str(root/'mpt'))
                    info = editor.probe(data['audio'])
                    self.assertAlmostEqual(float(info['format']['duration']), 1, delta=0.05)
                    picture = editor.probe(data['video'])
                    video = next(s for s in picture['streams'] if s['codec_type']=='video')
                    self.assertEqual((video['width'],video['height']), (1080,1920))
                    # Contract fixture only: real upstream caption/music rendering still needs a live install.
                    return run(['ffmpeg','-v','error','-y','-i',data['video'],'-i',data['audio'],
                                '-c:v','copy','-c:a','aac',data['output']],cwd=work)
                self.assertNotEqual(str(args[0]), 'gflow')
                return run(args, **kw)
            with patch('wondertales.editor.assets', return_value=(font, None)):
                editor.render(b, config, root, work, command)
            self.assertEqual(len(called), 1)
            self.assertTrue((work/'final.mp4').is_file())
            self.assertTrue(clip.is_file())
