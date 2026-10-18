"""Optional loopback-only VoiceStudio client. No SDK, model imports or cloud fallback."""
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import URLError, HTTPError

from .core import StopJob, probe

PRESETS = {f'expr-voice-{n}-{sex}' for n in range(2,6) for sex in ('m','f')}
TTS = {'kittentts','omnivoice-gguf'}
ASR = {'faster-whisper','whisperx'}


def base_url(value):
    if not isinstance(value,str): raise ValueError('Use a loopback VoiceStudio URL')
    p=urlsplit(value)
    try: port=p.port
    except ValueError: raise ValueError('Invalid VoiceStudio port')
    if p.scheme!='http' or p.hostname not in ('127.0.0.1','::1') or not port or not 1024<=port<=65535 or p.username or p.password or p.query or p.fragment or p.path not in ('','/'):
        raise ValueError('Use http://127.0.0.1:PORT (or [::1]) for VoiceStudio; tunnel remote workers to loopback')
    return value.rstrip('/')


def profile(body, settings):
    config=settings.get('voiceStudio',{})
    alias=body.get('voiceAlias') or ('english-main' if body['language']=='English' else 'hindi-main')
    if not isinstance(alias,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',alias):
        raise ValueError('Use a simple VoiceStudio voice alias')
    entry=config.get('profiles',{}).get(alias)
    if not isinstance(entry,dict) or entry.get('language')!=body['language']:
        raise ValueError('Configure this language/voice alias with workflow 19 VoiceStudio Settings first')
    engine,voice=entry.get('engine'),entry.get('voice')
    if engine not in TTS or not isinstance(voice,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',voice):
        raise ValueError('Choose an explicit supported VoiceStudio engine and voice ID')
    if engine=='kittentts' and (body['language']!='English' or voice not in PRESETS):
        raise ValueError('KittenTTS supports English preset voices only; use OmniVoice GGUF for Hindi/cloning')
    speed=entry.get('speed',1.0)
    if isinstance(speed,bool) or not isinstance(speed,(int,float)) or not math.isfinite(speed) or not 0.5<=speed<=1.5:
        raise ValueError('VoiceStudio speed must be between 0.5 and 1.5')
    asr=config.get('asrEngine','faster-whisper')
    if asr not in ASR: raise ValueError('Select a supported local ASR engine')
    return {'alias':alias,'url':base_url(config.get('url','http://127.0.0.1:3900')),
            'engine':engine,'voice':voice,'language':body['language'],'speed':speed,'asrEngine':asr}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


class Client:
    def __init__(self, config, root):
        self.config=config; self.root=Path(root)
        self.url=base_url(config.get('url','http://127.0.0.1:3900'))
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def request(self,path,data=None,content_type=None,limit=2_000_000,timeout=30):
        headers={}
        token=self.root/'voicestudio-token'
        if token.is_file():
            value=token.read_text().strip()
            if not value or '\n' in value or '\r' in value: raise StopJob('needs_setup','Repair the private VoiceStudio token file.')
            headers['Authorization']='Bearer '+value
        if content_type: headers['Content-Type']=content_type
        req=Request(self.url+path,data=data,headers=headers)
        try:
            with self.opener.open(req,timeout=timeout) as response:
                result=response.read(limit+1)
                if len(result)>limit: raise ValueError('Response too large')
                return result
        except HTTPError as exc:
            exc.close()
            raise StopJob('needs_attention','VoiceStudio rejected the request. Check the local service/models/token; saved audio is preserved and no fallback was attempted.')
        except (URLError,OSError,TimeoutError,ValueError):
            raise StopJob('needs_attention','VoiceStudio is unavailable, timed out, or returned an invalid response. Check the local service/models/token. No provider fallback or automatic audio retry; saved audio is preserved.')

    def get_json(self,path):
        try: return json.loads(self.request(path))
        except (ValueError,UnicodeError): raise StopJob('needs_attention','VoiceStudio returned invalid metadata. Check API compatibility before resuming.')

    def check_asr(self):
        data=self.get_json('/engines/asr')
        expected=self.config.get('asrEngine','faster-whisper')
        if expected not in ASR or data.get('active')!=expected or data.get('env_override') is not True or not any(b.get('id')==expected and b.get('available') is True for b in data.get('backends',[])):
            raise StopJob('needs_setup','Pin the configured local ASR engine with OMNIVOICE_ASR_BACKEND, install its multilingual model, then restart VoiceStudio. Remote or unpinned ASR is not accepted.')

    def inventory(self):
        data=self.get_json('/v1/audio/voices')
        return {'voices':[{k:v.get(k) for k in ('voice_id','name','type','language')} for v in data.get('voices',[]) if v.get('type')=='profile'],
                'engines':[{k:b.get(k) for k in ('id','available','supports_cloning','effective_device','routing_status')} for b in data.get('engines',[]) if b.get('id') in TTS],
                'englishPresets':sorted(PRESETS)}

    def preflight(self):
        inventory=self.inventory(); config=self.config
        engine=next((b for b in inventory['engines'] if b['id']==config['engine']),None)
        if not engine or engine['available'] is not True or engine.get('routing_status')=='unavailable':
            raise StopJob('needs_setup','Install the selected VoiceStudio TTS engine/model. GGUF source checkouts need a real compatible native binary, not the placeholder.')
        if config['engine']=='omnivoice-gguf' and (engine.get('supports_cloning') is not True or not any(v['voice_id']==config['voice'] for v in inventory['voices'])):
            raise StopJob('needs_setup','Choose an existing VoiceStudio voice-profile ID for OmniVoice GGUF. Unknown IDs/default aliases are rejected to avoid a silent voice change.')
        self.check_asr()
        return {'connected':True,'engine':config['engine'],'voiceAlias':config.get('alias'),
                'localASR':config['asrEngine'],'note':'Metadata check only; generate and listen to an audio sample before the first real video.'}

    def unit(self,text,prefix,command,*,max_duration=None):
        from .audio import parse_srt
        if len(text)>4096:
            raise StopJob('needs_attention','VoiceStudio accepts at most 4096 characters per speech request. Use a storyboard to split this narration into shorter scenes.')
        prefix=Path(prefix); wav=prefix.with_suffix('.wav'); mp3=prefix.with_suffix('.mp3'); srt=prefix.with_suffix('.srt'); record=prefix.with_suffix('.request.json')
        digest=hashlib.sha256(json.dumps([text,self.config],sort_keys=True).encode()).hexdigest()
        if not record.exists() and any(p.exists() for p in (wav,mp3,srt)):
            raise StopJob('needs_attention','Audio cache has no matching request record. Rebuild narration before reusing it.')
        if record.exists() and record.read_text()!=digest:
            raise StopJob('needs_attention','Cached VoiceStudio audio belongs to different settings. Use Rebuild Narration and Captions before Safe Resume.')
        record.write_text(digest)
        if not wav.is_file():
            body={'model':self.config['engine'],'voice':self.config['voice'],'language':'hi' if self.config['language']=='Hindi' else 'en',
                  'speed':self.config['speed'],'input':text,'response_format':'wav'}
            content=self.request('/v1/audio/speech',json.dumps(body).encode(),'application/json',limit=50_000_000,timeout=900)
            if len(content)<12 or content[:4]!=b'RIFF' or content[8:12]!=b'WAVE':
                raise StopJob('needs_attention','VoiceStudio speech was not a WAV file. No Flow generation was submitted.')
            temp=wav.with_suffix('.wav.tmp'); temp.write_bytes(content); temp.replace(wav)
        info=probe(wav)
        duration=float(info['format']['duration'])
        if not math.isfinite(duration) or duration<=0 or not any(s.get('codec_type')=='audio' for s in info.get('streams',[])):
            raise StopJob('needs_attention','The saved VoiceStudio audio is invalid; rebuild narration before resuming.')
        if max_duration is not None and duration > max_duration:
            raise StopJob('story_too_long','VoiceStudio narration is too long for its target scene/video. Submit shorter narration; captions and Flow generation were not requested for this segment.')
        if not srt.is_file():
            # The upstream transcription API uses its ACTIVE engine, not the model field.
            self.check_asr()
            boundary='WonderTales'+secrets.token_hex(16)
            lang='hi' if self.config['language']=='Hindi' else 'en'
            payload=b''
            for name,value in [('model',self.config['asrEngine']),('language',lang),('response_format','srt')]:
                payload+=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
            payload+=f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="speech.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()+wav.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            result=self.request('/v1/audio/transcriptions',payload,'multipart/form-data; boundary='+boundary,timeout=900)
            temp=srt.with_suffix('.srt.tmp'); temp.write_bytes(result)
            try: parse_srt(temp,duration)
            except (ValueError,OSError,UnicodeError):
                temp.unlink(missing_ok=True)
                raise StopJob('needs_attention','VoiceStudio returned invalid/empty timed captions. Saved speech is retained; fix local ASR and Safe Resume.')
            temp.replace(srt)
        try: parse_srt(srt,duration)
        except (ValueError,OSError,UnicodeError):
            raise StopJob('needs_attention','Cached VoiceStudio captions are invalid. Rebuild narration/captions before Safe Resume.')
        if not mp3.is_file():
            result=command(['ffmpeg','-v','error','-y','-i',wav,'-vn','-c:a','libmp3lame','-b:a','192k',mp3])
            if result.returncode:
                mp3.unlink(missing_ok=True)
                raise StopJob('needs_attention','VoiceStudio audio conversion failed; the original WAV and captions remain saved.')
        return mp3,srt
