import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import wave

from wondertales.core import Pipeline, StopJob, Store, validate
from wondertales.voicestudio import Client, base_url, profile
from test_core import body, settings


def config(root, language='English'):
    cfg=settings(root)
    cfg['voiceStudio']={'url':'http://127.0.0.1:3900','asrEngine':'faster-whisper','profiles':{
      'english-main':{'engine':'kittentts','voice':'expr-voice-2-f','language':'English','speed':1},
      'hindi-main':{'engine':'omnivoice-gguf','voice':'profile-one','language':'Hindi','speed':1}}}
    return cfg


def wav_bytes():
    out=io.BytesIO()
    with wave.open(out,'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(24000)
        file.writeframes(struct.pack('<h',200)*12000)
    return out.getvalue()


class VoiceValidationTests(unittest.TestCase):
    def test_provider_mapping_is_pinned_and_hindi_rejects_english_only_engine(self):
        cfg=config(Path('/tmp')); b=body(); b['ttsProvider']='voicestudio'
        v=validate(b,cfg); cfg['voiceStudio']['profiles']['english-main']['voice']='expr-voice-3-f'
        self.assertEqual(v['voiceStudioConfig']['voice'],'expr-voice-2-f')
        b.update(language='Hindi',voiceAlias='english-main')
        with self.assertRaises(ValueError): validate(b,cfg)
        b['voiceAlias']='hindi-main'; self.assertEqual(validate(b,cfg)['voiceStudioConfig']['engine'],'omnivoice-gguf')
        cfg['voiceStudio']['profiles']['hindi-main']['engine']='kittentts'
        with self.assertRaises(ValueError): validate(b,cfg)
    def test_urls_remote_engines_alias_fallbacks_and_ambiguous_inputs_are_rejected(self):
        for url in ('https://example.com','http://169.254.169.254:80','http://localhost:3900','http://127.0.0.1:3900/v1',
                    'http://user:pass@127.0.0.1:3900','http://127.0.0.1:3900?key=secret'):
            with self.assertRaises(ValueError): base_url(url)
        self.assertEqual(base_url('http://127.0.0.1:3900/'),'http://127.0.0.1:3900')
        cfg=config(Path('/tmp')); b=body(); b['ttsProvider']='voicestudio'
        for field,value in [('engine','tts-1'),('engine','paid-provider'),('voice','alloy'),('speed',float('nan'))]:
            bad=config(Path('/tmp')); bad['voiceStudio']['profiles']['english-main'][field]=value
            with self.assertRaises(ValueError): validate(b,bad)
        b.update(audioFile='/voice.mp3',captionFile='/voice.srt')
        with self.assertRaises(ValueError): validate(b,cfg)
    def test_voice_failure_blocks_before_flow_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cfg=config(root); b=body(); b['ttsProvider']='voicestudio'
            pipe=Pipeline(Store(root/'jobs.db'),cfg,root); pipe.command=Mock()
            with patch('wondertales.voicestudio.Client.preflight',side_effect=StopJob('needs_setup','Install the local engine')):
                with self.assertRaises(StopJob): pipe.preflight(validate(b,cfg))
            pipe.command.assert_not_called()


class VoiceHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
        self.requests=[]; self.fail_asr=False; self.redirect=False; self.remote_asr=False; self.pinned=True
        test=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def respond(self,data,kind='application/json',status=200):
                self.send_response(status); self.send_header('Content-Type',kind); self.end_headers(); self.wfile.write(data)
            def do_GET(self):
                test.requests.append(('GET',self.path,dict(self.headers)))
                if test.redirect:
                    self.send_response(302); self.send_header('Location','http://example.com/stolen'); self.end_headers(); return
                if self.path=='/v1/audio/voices':
                    self.respond(json.dumps({'voices':[{'voice_id':'profile-one','type':'profile','name':'Narrator','language':'hi'}],
                      'engines':[{'id':engine,'available':True,'supports_cloning':True,'routing_status':'cpu_only'} for engine in ('kittentts','omnivoice-gguf')]}).encode())
                else:
                    self.respond(json.dumps({'active':'openai-compat-asr' if test.remote_asr else 'faster-whisper','env_override':test.pinned,
                                  'backends':[{'id':'faster-whisper','available':True}]}).encode())
            def do_POST(self):
                data=self.rfile.read(int(self.headers.get('Content-Length',0))); test.requests.append(('POST',self.path,data))
                if self.path.endswith('/speech'): self.respond(wav_bytes(),'audio/wav')
                elif test.fail_asr: self.respond(b'{"error":"private-server-token-must-not-leak"}',status=503)
                else: self.respond(b'1\n00:00:00,000 --> 00:00:00,400\nHello friends.\n','text/plain')
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        cfg=config(self.root); cfg['voiceStudio']['url']=f'http://127.0.0.1:{self.server.server_port}'
        self.client=Client(profile({'language':'English'},cfg),self.root)
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()
    def converter(self,args,**kwargs):
        Path(args[-1]).write_bytes(b'fixture mp3'); return Mock(returncode=0)
    def test_real_loopback_http_wav_caption_cache_and_no_duplicate_speech_after_asr_failure(self):
        prefix=self.root/'voice'; self.fail_asr=True
        with self.assertRaises(StopJob) as caught: self.client.unit('Hello friends.',prefix,self.converter)
        self.assertNotIn('private-server-token',caught.exception.detail)
        self.assertTrue(prefix.with_suffix('.wav').exists())
        self.fail_asr=False
        mp3,srt=self.client.unit('Hello friends.',prefix,self.converter)
        self.assertTrue(mp3.exists()); self.assertTrue(srt.exists())
        posts=[r[1] for r in self.requests if r[0]=='POST']
        self.assertEqual(posts.count('/v1/audio/speech'),1)
        speech=json.loads(next(r[2] for r in self.requests if r[:2]==('POST','/v1/audio/speech')))
        self.assertEqual((speech['model'],speech['voice']),('kittentts','expr-voice-2-f'))
        count=len(self.requests); self.client.unit('Hello friends.',prefix,self.converter)
        self.assertEqual(len(self.requests),count)
        with self.assertRaises(StopJob): self.client.unit('Different text.',prefix,self.converter)
    def test_preflight_rejects_remote_unpinned_asr_and_unknown_clone_profile(self):
        self.client.preflight(); self.remote_asr=True
        with self.assertRaises(StopJob): self.client.preflight()
        self.remote_asr=False; self.pinned=False
        with self.assertRaises(StopJob): self.client.preflight()
        self.pinned=True; self.client.config.update(engine='omnivoice-gguf',voice='unknown-profile')
        with self.assertRaises(StopJob): self.client.preflight()
    def test_loopback_token_is_private_and_redirects_are_never_followed(self):
        (self.root/'voicestudio-token').write_text('private-local-token')
        inventory=self.client.inventory()
        self.assertNotIn('private-local-token',json.dumps(inventory))
        self.assertEqual(self.requests[0][2].get('Authorization'),'Bearer private-local-token')
        self.redirect=True
        with self.assertRaises(StopJob) as caught: self.client.inventory()
        self.assertNotIn('private-local-token',caught.exception.detail)
        self.assertEqual(len(self.requests),2)

    def test_too_long_speech_stops_before_transcription_or_video(self):
        with self.assertRaises(StopJob) as caught:
            self.client.unit('Hello.',self.root/'long',self.converter,max_duration=0.2)
        self.assertEqual(caught.exception.state,'story_too_long')
        self.assertEqual([r[1] for r in self.requests if r[0]=='POST'],['/v1/audio/speech'])

    def test_actual_audio_prepare_uses_voicestudio_and_reuses_prepared_files(self):
        from wondertales.audio import prepare
        from wondertales.core import run, probe
        import shutil
        if not shutil.which('ffmpeg'): self.skipTest('FFmpeg required')
        work=self.root/'jobs'/'fixture'; work.mkdir(parents=True)
        b=body(); b.update(ttsProvider='voicestudio',voiceStudioConfig=self.client.config)
        def command(args,**kw):
            self.assertEqual(str(args[0]),'ffmpeg'); return run(args,**kw)
        prepare(b,config(self.root),work,command)
        self.assertTrue((work/'captions.srt').is_file())
        self.assertGreater(float(probe(work/'narration.mp3')['format']['duration']),0)
        count=len(self.requests); prepare(b,config(self.root),work,command)
        self.assertEqual(len(self.requests),count)


if __name__=='__main__': unittest.main()
