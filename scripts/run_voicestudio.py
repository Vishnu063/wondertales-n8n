"""Launch the owner's separate VoiceStudio checkout on loopback, with local-only ASR."""
import json
import os
from pathlib import Path
import secrets
import shutil

repo=Path(__file__).resolve().parents[1]
source=repo/'.voicestudio'
if not (source/'backend/main.py').is_file():
    raise SystemExit('Run bash scripts/setup-voicestudio.sh first, or use your existing VoiceStudio server.')
uv=shutil.which('uv')
if not uv: raise SystemExit('Install uv first; see the VoiceStudio setup guide.')
root=Path(os.environ.get('WONDERTALES_HOME','~/.local/share/wondertales')).expanduser().resolve()
root.mkdir(parents=True,exist_ok=True,mode=0o700); os.chmod(root,0o700)
settings=json.loads((root/'settings.json').read_text()) if (root/'settings.json').is_file() else {}
config=settings.get('voiceStudio',{})
asr=config.get('asrEngine','faster-whisper')
if asr not in ('faster-whisper','whisperx'): raise SystemExit('Select a supported local ASR engine.')
from urllib.parse import urlsplit
endpoint=urlsplit(config.get('url','http://127.0.0.1:3900'))
if endpoint.hostname!='127.0.0.1' or endpoint.scheme!='http' or not endpoint.port:
    raise SystemExit('The supplied launcher supports a 127.0.0.1 VoiceStudio endpoint.')
token=root/'voicestudio-token'
if not token.exists():
    fd=os.open(token,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as out: out.write(secrets.token_urlsafe(40))
os.chmod(token,0o600)
env=os.environ.copy()
env.update(OMNIVOICE_BIND_HOST='127.0.0.1',OMNIVOICE_PORT=str(endpoint.port),
           OMNIVOICE_API_KEY=token.read_text().strip(),OMNIVOICE_ASR_BACKEND=asr,
           OMNIVOICE_TTS_BACKEND='kittentts',OMNIVOICE_GPU_WORKERS='1',OMNIVOICE_SINGLE_ENGINE_RESIDENT='1')
env.setdefault('OMNIVOICE_DEVICE','cpu'); env.setdefault('ASR_COMPUTE_TYPE','int8')
os.chdir(source)
os.execvpe(uv,[uv,'run','--locked','--no-dev','--python','3.12','python','backend/main.py'],env)
