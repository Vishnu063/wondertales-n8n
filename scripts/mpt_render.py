"""Run only the pinned upstream local renderer, inside the optional isolated venv."""
import importlib.metadata
import json
import os
from pathlib import Path
import socket
import sys

VERSION = '1.3.8'
REVISION = '9e7d8b7efa6b912058156943906542b53b945f0a'


def deny_network(*args, **kwargs):
    raise RuntimeError('Networking is disabled in the WonderTales editor')


def load_renderer():
    socket.create_connection = deny_network
    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.socket.sendto = deny_network
    dist = importlib.metadata.distribution('mpt')
    direct = json.loads(dist.read_text('direct_url.json') or '{}')
    if dist.version != VERSION or direct.get('vcs_info', {}).get('commit_id') != REVISION:
        raise RuntimeError('Install the exact MoneyPrinterTurbo revision from requirements-mpt.txt')
    from app.models.schema import VideoParams
    from app.services.video import generate_video
    from PIL import features
    if not features.check_feature('raqm'):
        raise RuntimeError('Pillow RAQM support is required for Hindi caption shaping')
    return VideoParams, generate_video


def render_manifest(data, params_type, renderer):
    music = data.get('music')
    params = params_type(video_subject='Local WonderTales edit', video_aspect=data['aspect'],
                         video_source='local', video_concat_mode='sequential',
                         voice_volume=1.0, subtitle_enabled=True, font_name=data['font'],
                         subtitle_position='two_thirds_bottom', subtitle_display_mode='sentence',
                         subtitle_animation='none', font_size=60,
                         text_fore_color='#FFE66D' if data['style'] == 'kids' else '#FFFFFF',
                         text_background_color='#181818', rounded_subtitle_background=True,
                         stroke_color='#000000', stroke_width=1.5, n_threads=2,
                         bgm_type='custom' if music else '', bgm_file=music or '',
                         bgm_volume=data['musicVolume'] if music else 0.0)
    mixed = renderer(video_path=data['video'], audio_path=data['audio'],
                     subtitle_path=data['subtitles'], output_file=data['output'],
                     params=params, bgm_file_override=music)
    if music and not mixed:
        raise RuntimeError('Requested background music was not mixed successfully')


def main():
    if not os.environ.get('MPT_HOME'):
        raise RuntimeError('A private MPT_HOME is required')
    params_type, renderer = load_renderer()
    if sys.argv[1:] == ['--check']:
        print(json.dumps({'available': True, 'version': VERSION}))
        return
    data = json.loads(Path(sys.argv[1]).read_text())
    render_manifest(data, params_type, renderer)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Upstream exception text can contain paths/config values. Return a stable private-worker error.
        print('Local MoneyPrinterTurbo renderer failed; no provider fallback.', file=sys.stderr)
        sys.exit(1)
