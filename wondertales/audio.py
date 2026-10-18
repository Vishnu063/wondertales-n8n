"""Existing owner audio or per-scene online speech, prepared before Flow spending."""
from pathlib import Path
import re
import shutil

from .core import StopJob, allowed_file, probe


def parse_srt(path, duration):
    file = Path(path)
    if file.stat().st_size > 2_000_000:
        raise ValueError('Caption file exceeds 2 MB')
    raw = file.read_text(encoding='utf-8-sig').strip()
    blocks = re.split(r'\r?\n\s*\r?\n', raw)
    cues = []
    def seconds(value):
        h,m,s,ms = map(int, re.split('[:,]', value))
        if m>59 or s>59: raise ValueError('Invalid SRT time')
        return 3600*h+60*m+s+ms/1000
    for block in blocks:
        lines = block.splitlines()
        if len(lines)<3 or not lines[0].isdigit():
            raise ValueError('Use numbered UTF-8 SRT cues')
        match = re.fullmatch(r'(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})',lines[1])
        if not match: raise ValueError('Use standard SRT timestamps')
        start,end = map(seconds,match.groups())
        if end<=start or end>duration+0.1 or (cues and start<cues[-1][1]):
            raise ValueError('Caption timings must be ordered, non-overlapping and fit the audio')
        caption='\n'.join(lines[2:]).strip()
        if not caption: raise ValueError('Caption text is blank')
        cues.append((start,end,caption))
    return cues


def write_srt(path, cues):
    def stamp(seconds):
        ms = round(seconds*1000); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000)
        return f'{h:02}:{m:02}:{s:02},{ms:03}'
    Path(path).write_text('\n\n'.join(f'{i}\n{stamp(start)} --> {stamp(end)}\n{caption}' for i,(start,end,caption) in enumerate(cues,1))+'\n',encoding='utf-8')


def owner_assets(body, settings):
    if not body.get('audioFile'):
        return None
    try:
        audio=allowed_file(body['audioFile'], settings['importsDir'])
        captions=allowed_file(body['captionFile'], settings['importsDir'])
        if audio.suffix.lower() not in ('.mp3','.wav','.m4a','.ogg','.flac') or captions.suffix.lower()!='.srt' or audio.stat().st_size>100_000_000:
            raise ValueError('Use audio up to 100 MB plus a UTF-8 .srt file')
        info=probe(audio)
        duration=float(info['format']['duration'])
        if not any(s.get('codec_type')=='audio' for s in info.get('streams',[])) or not 0<duration<=body['durationSeconds']+0.05:
            raise ValueError('Owner audio needs a readable audio stream fitting the target duration')
        parse_srt(captions, duration)
        return audio,captions
    except (ValueError, OSError, UnicodeError, KeyError, TypeError):
        raise StopJob('needs_attention','Check your owner audio and UTF-8 SRT: use files inside imports, valid ordered cue timings, and audio no longer than the target duration.')


def prepare(body, settings, work, command):
    work=Path(work)
    audio,captions=work/'narration.mp3',work/'captions.srt'
    if audio.is_file() and captions.is_file(): return
    if body.get('audioFile'):
        source,srt=owner_assets(body,settings)
        result=command(['ffmpeg','-v','error','-y','-i',source,'-vn','-c:a','libmp3lame','-b:a','192k',audio])
        if result.returncode:
            raise StopJob('needs_attention','Owner audio conversion failed before new Flow generations.')
        shutil.copyfile(srt,captions)
        return
    plan=body.get('storyboard')
    if not plan: return False
    voice=settings.get('voices',{}).get(body['language'],'hi-IN-SwaraNeural' if body['language']=='Hindi' else 'en-IN-NeerjaNeural')
    cues=[]
    for n,scene in enumerate(plan):
        slot=min(8,body['durationSeconds']-n*8)
        spoken,timed=work/f'scene-voice-{n:02}.mp3',work/f'scene-captions-{n:02}.srt'
        if not spoken.is_file() or not timed.is_file():
            result=command(['edge-tts','--voice',voice,'--text',scene['narration'],'--write-media',spoken,'--write-subtitles',timed])
            if result.returncode or not spoken.is_file() or not timed.is_file():
                raise StopJob('needs_attention',f'Scene {n+1} narration failed before new Flow spending. Safe Resume reuses the completed speech files.')
        duration=float(probe(spoken)['format']['duration'])
        if duration>slot-0.1:
            raise StopJob('story_too_long',f'Scene {n+1} narration must fit its {slot}-second slot. Submit shorter scene narration; no new Flow clips were generated.')
        try:
            cues.extend((start+n*8,end+n*8,caption) for start,end,caption in parse_srt(timed,duration))
        except (ValueError,OSError,UnicodeError):
            raise StopJob('needs_attention',f'Scene {n+1} captions are invalid. Rebuild narration/captions before Safe Resume.')
        result=command(['ffmpeg','-v','error','-y','-i',spoken,'-af','apad','-t',str(slot),'-ar','44100','-ac','1',work/f'scene-voice-{n:02}.wav'])
        if result.returncode: raise StopJob('needs_attention','Scene narration alignment failed before Flow generation.')
    (work/'voices.txt').write_text(''.join(f"file 'scene-voice-{n:02}.wav'\n" for n in range(len(plan))))
    result=command(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i','voices.txt','-c:a','libmp3lame','-b:a','192k','narration.mp3'],cwd=work)
    if result.returncode: raise StopJob('needs_attention','Aligned narration assembly failed before new Flow clips.')
    write_srt(captions,cues)
