"""Optional local MoneyPrinterTurbo renderer; never invokes its task/provider pipeline."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from .core import StopJob, allowed_file, probe

REPO = Path(__file__).resolve().parents[1]
VERSION = '1.3.8'
REVISION = '9e7d8b7efa6b912058156943906542b53b945f0a'


def interpreter(settings):
    return Path(settings.get('mptPython', REPO/'.mpt-venv/bin/python')).expanduser().resolve()


def environment(root):
    home = Path(root).resolve()/'mpt'
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Do not pass provider keys, browser sessions, proxy settings or user configs.
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(home),
            'MPT_HOME': str(home), 'XDG_CONFIG_HOME': str(home/'config'),
            'LANG': 'C.UTF-8', 'PYTHONIOENCODING': 'utf-8',
            'IMAGEIO_FFMPEG_EXE': shutil.which('ffmpeg') or 'ffmpeg'}


def status(settings, root):
    python = interpreter(settings)
    if not python.is_file():
        return {'available': False, 'version': VERSION, 'action': 'Run bash scripts/setup-mpt.sh on the worker computer.'}
    try:
        result = subprocess.run([str(python), str(REPO/'scripts/mpt_render.py'), '--check'],
                                capture_output=True, text=True, timeout=90, env=environment(root))
        if result.returncode == 0:
            return {'available': True, 'version': VERSION, 'network': 'disabled in renderer'}
    except (OSError, subprocess.TimeoutExpired):
        pass
    return {'available': False, 'version': VERSION, 'action': 'Re-run setup-mpt.sh; the pinned renderer/dependencies did not pass import checks.'}


def assets(body, settings):
    custom = settings.get('mptFonts', {}).get(body['language'])
    candidates = [custom] if custom else (
        ['/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf'] if body['language'] == 'Hindi' else
        ['/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'])
    font = next((Path(p).expanduser().resolve() for p in candidates if p and Path(p).expanduser().is_file()), None)
    if not font:
        raise StopJob('needs_setup', 'Install fonts-noto-core, or configure mptFonts for this language in private settings.json.')
    music = None
    if body.get('musicFile'):
        try:
            music = allowed_file(body['musicFile'], settings['importsDir'])
        except ValueError:
            raise StopJob('needs_setup', 'Copy your licensed music file into imports and use its full worker path.')
        if music.suffix.lower() not in ('.wav', '.mp3', '.m4a', '.ogg', '.flac'):
            raise StopJob('needs_setup', 'Use a WAV, MP3, M4A, OGG or FLAC music file.')
        info = probe(music)
        if not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
            raise StopJob('needs_setup', 'The selected music file has no readable audio stream.')
    return font, music


def preflight(body, settings, root):
    if body.get('editor', 'builtin') != 'moneyprinterturbo':
        return
    available = status(settings, root)
    if not available['available']:
        raise StopJob('needs_setup', available['action'])
    assets(body, settings)


def render(body, settings, root, work, command):
    """Only local preprocessing and rendering. Failures preserve original paid clips."""
    work = Path(work).resolve()
    font, music = assets(body, settings)
    env = environment(root)
    fonts = Path(env['MPT_HOME'])/'resource/fonts'
    fonts.mkdir(parents=True, exist_ok=True)
    font_name = hashlib.sha256(font.read_bytes()).hexdigest()+font.suffix
    shutil.copyfile(font, fonts/font_name)
    duration = str(body['durationSeconds'])
    w, h = (1080, 1920) if body['aspectRatio'] == '9:16' else (1920, 1080)
    steps = [
        ['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', 'concat.txt',
         '-an', '-vf', f'scale={w}:{h},setsar=1', '-t', duration, '-c:v', 'libx264',
         '-pix_fmt', 'yuv420p', 'mpt-picture.mp4'],
        ['ffmpeg', '-v', 'error', '-y', '-i', 'narration.mp3', '-af',
         'apad,loudnorm=I=-16:TP=-1.5:LRA=11', '-t', duration, '-ar', '44100', 'mpt-voice.wav']]
    if music:
        steps.append(['ffmpeg', '-v', 'error', '-y', '-stream_loop', '-1', '-i', music,
                      '-vn', '-t', duration, '-ar', '44100', 'mpt-music.wav'])
    for args in steps:
        if command(args, cwd=work, timeout=900).returncode:
            raise StopJob('needs_attention', 'MoneyPrinterTurbo media preparation failed. Saved Flow clips are preserved; Safe Resume retries editing only when all clips are complete.')
    manifest = {'video': str(work/'mpt-picture.mp4'), 'audio': str(work/'mpt-voice.wav'),
                'subtitles': str(work/'captions.srt'), 'output': str(work/'mpt-output.mp4'),
                'aspect': body['aspectRatio'], 'font': font_name,
                'style': body.get('subtitleStyle', 'clean'),
                'music': str(work/'mpt-music.wav') if music else None,
                'musicVolume': body.get('musicVolume', 0.12)}
    (work/'mpt-render.json').write_text(json.dumps(manifest))
    try:
        result = command([interpreter(settings), REPO/'scripts/mpt_render.py', work/'mpt-render.json'],
                         cwd=work, timeout=1800, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise StopJob('needs_attention', 'MoneyPrinterTurbo stopped or timed out. Completed Flow clips remain saved; use Safe Resume after fixing the editor.')
    output = work/'mpt-output.mp4'
    if result.returncode or not output.is_file() or not output.stat().st_size:
        raise StopJob('needs_attention', 'MoneyPrinterTurbo rendering failed, including any requested music mix. No automatic provider fallback; saved clips remain available for Safe Resume.')
    # Final local normalization preserves the same validation/upload boundary as the built-in editor.
    result = command(['ffmpeg', '-v', 'error', '-y', '-i', output, '-map', '0:v:0', '-map', '0:a:0',
                      '-t', duration, '-c', 'copy', '-movflags', '+faststart', 'final.mp4'], cwd=work, timeout=300)
    if result.returncode:
        raise StopJob('needs_attention', 'Edited output could not be finalized. Original Flow clips are preserved.')
