"""Durable jobs and credit-conscious Flow orchestration. No account secrets in logs."""
from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import time
import uuid


class StopJob(Exception):
    def __init__(self, state, detail):
        self.state, self.detail = state, detail
        super().__init__(detail)


def validate(body, settings):
    keys = {"title", "story", "language", "aspectRatio", "flowAccount", "youtubeDestination",
            "durationSeconds", "selectedCharacters", "consistencyMode", "creditCostPerClip", "maxCreditsPerJob", "variant"}
    b = {k: v for k, v in body.items() if k in keys}
    for key in ('title', 'story', 'language', 'aspectRatio', 'flowAccount', 'youtubeDestination'):
        if not isinstance(b.get(key), str) or not b[key].strip():
            raise ValueError(f'{key} is required')
        b[key] = b[key].strip()
    if len(b['title']) > 100 or len(b['story']) > 12000:
        raise ValueError('Use a title up to 100 characters and a story up to 12000 characters')
    if b['language'] not in ('English', 'Hindi') or b['aspectRatio'] not in ('9:16', '16:9'):
        raise ValueError('Unsupported language or aspect ratio')
    if type(b.get('durationSeconds')) is not int or b['durationSeconds'] not in (30, 60, 90, 120):
        raise ValueError('Duration must be 30, 60, 90, or 120 seconds')
    if b['flowAccount'] not in settings['accounts']:
        raise ValueError('Flow account alias is not configured locally')
    account = settings['accounts'][b['flowAccount']]
    if not isinstance(account, dict) or not re.fullmatch(r'[A-Za-z0-9_-]+', str(account.get('profile', ''))):
        raise ValueError('Configure a dedicated Chrome profile for this Flow account alias')
    b['flowProfile'] = account['profile']
    b['flowProject'] = account.get('project', '')
    if b['youtubeDestination'] not in settings['youtubeDestinations']:
        raise ValueError('YouTube destination alias is not configured locally')
    chars = b.get('selectedCharacters', [])
    if not isinstance(chars, list) or len(chars) not in (2, 3):
        raise ValueError('Choose exactly two or three characters')
    for char in chars:
        if not isinstance(char, dict) or any(not isinstance(char.get(k), str) or not char[k].strip()
                                            for k in ('name', 'facePrompt', 'bodyPrompt')):
            raise ValueError('Each character needs name, facePrompt, and bodyPrompt')
    if len({c['name'] for c in chars}) != len(chars):
        raise ValueError('Character names must be unique')
    if b.get('consistencyMode', 'reference') not in ('reference', 'text'):
        raise ValueError('Unsupported consistency mode')
    for key in ('creditCostPerClip', 'maxCreditsPerJob'):
        value = b.get(key)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'Configure a positive {key} in n8n first')
    b.update(model='veo-lite', uploadVisibility='private', madeForKids=True,
             plannedSceneCount=math.ceil(b['durationSeconds'] / 8))
    b['estimatedCredits'] = b['plannedSceneCount'] * b['creditCostPerClip']
    if b['estimatedCredits'] > b['maxCreditsPerJob']:
        raise ValueError('Estimated credits exceed the per-job cap. Change duration or the cap in n8n.')
    b.pop('requestId', None)
    return b


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL, body TEXT NOT NULL,
                  state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', progress INTEGER DEFAULT 0,
                  report TEXT NOT NULL DEFAULT '{}', claim TEXT, youtube_id TEXT,
                  created REAL NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS scenes (
                  job TEXT NOT NULL, number INTEGER NOT NULL, state TEXT NOT NULL,
                  path TEXT, media_id TEXT, PRIMARY KEY(job, number));
                CREATE TABLE IF NOT EXISTS controls (id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER NOT NULL DEFAULT 0);
                INSERT OR IGNORE INTO controls(id,paused) VALUES(1,0);
                CREATE TABLE IF NOT EXISTS daily_dispatches (day TEXT PRIMARY KEY, job TEXT NOT NULL);
            ''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(jobs)')}
            for name, definition in [('retry_after','REAL NOT NULL DEFAULT 0'), ('ready_at','REAL'), ('uploaded_at','REAL')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {name} {definition}')

    def is_paused(self):
        with self.connect() as db:
            return bool(db.execute('SELECT paused FROM controls WHERE id=1').fetchone()[0])

    def set_paused(self, paused):
        with self.connect() as db:
            db.execute('UPDATE controls SET paused=? WHERE id=1', (int(paused),))

    def reserve_day(self, day, ident):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT job FROM daily_dispatches WHERE day=?', (day,)).fetchone()
            if row:
                return row[0] == ident
            db.execute('INSERT INTO daily_dispatches(day,job) VALUES(?,?)', (day,ident))
            return True

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (ident,)).fetchone()
            if row is None:
                raise KeyError(ident)
            job = dict(row)
            job['body'] = json.loads(job['body'])
            job['report'] = json.loads(job['report'])
            job['scenes'] = [dict(x) for x in db.execute(
                'SELECT number,state,path,media_id FROM scenes WHERE job=? ORDER BY number', (ident,))]
        return job

    def list(self, limit=100):
        with self.connect() as db:
            query = 'SELECT id FROM jobs ORDER BY created DESC'
            ids = [x[0] for x in db.execute(query if limit is None else query+' LIMIT ?', () if limit is None else (limit,))]
        return [self.get(x) for x in ids]

    def submit(self, body):
        return self.submit_many([body])[0]

    def submit_many(self, bodies):
        results = []
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for body in bodies:
                fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                previous = db.execute('SELECT id FROM jobs WHERE fingerprint=?', (fingerprint,)).fetchone()
                if previous:
                    results.append((previous[0], False))
                    continue
                ident = uuid.uuid4().hex
                db.execute('INSERT INTO jobs(id,fingerprint,body,state,detail,created,updated) VALUES(?,?,?,?,?,?,?)',
                           (ident, fingerprint, json.dumps(body), 'waiting', 'Saved in the story bank; waiting for the daily queue.', time.time(), time.time()))
                db.executemany('INSERT INTO scenes(job,number,state) VALUES(?,?,?)',
                               [(ident, n, 'pending') for n in range(body['plannedSceneCount'])])
                results.append((ident, True))
        return [(self.get(ident),created) for ident,created in results]

    def update(self, ident, state, detail='', **extra):
        allowed = {'progress', 'report', 'retry_after'}
        if set(extra) - allowed:
            raise ValueError('Unsupported job fields')
        values = {'state': state, 'detail': detail, 'updated': time.time(), **extra}
        if 'report' in values:
            values['report'] = json.dumps(values['report'])
        with self.connect() as db:
            clause = ',ready_at=COALESCE(ready_at,?)' if state == 'ready' else ''
            args = [*values.values()] + ([time.time()] if state == 'ready' else []) + [ident]
            db.execute('UPDATE jobs SET '+','.join(f'{k}=?' for k in values)+clause+' WHERE id=?', args)

    def scene(self, ident, number, state, path=None, media_id=None):
        with self.connect() as db:
            db.execute('UPDATE scenes SET state=?,path=?,media_id=? WHERE job=? AND number=?',
                       (state, str(path) if path else None, media_id, ident, number))

    def recover_after_restart(self):
        with self.connect() as db:
            db.execute("UPDATE scenes SET state='uncertain' WHERE state='generating'")
            db.execute("UPDATE jobs SET state='upload_uncertain',detail='Check YouTube and record the existing video ID; do not upload again.' WHERE state='uploading'")
            db.execute("UPDATE jobs SET state='queued' WHERE state IN ('preflight','narrating','generating','assembling','checking')")
            db.execute("UPDATE jobs SET state='needs_reconciliation',detail='A scene may already have been billed. Recover the existing clip before resuming.' WHERE id IN (SELECT job FROM scenes WHERE state='uncertain') AND state!='uploaded'")
            db.execute("UPDATE jobs SET state='waiting' WHERE state='queued'")
        return []  # Scheduling always goes through the durable daily queue after a restart.

    def claim_upload(self, ident, destination):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT paused FROM controls WHERE id=1').fetchone()[0]:
                raise ValueError('Global pause is active; new uploads are paused too')
            row = db.execute('SELECT state,body FROM jobs WHERE id=?', (ident,)).fetchone()
            if not row:
                raise KeyError(ident)
            if json.loads(row['body'])['youtubeDestination'] != destination:
                raise ValueError('Wrong upload destination')
            if row['state'] != 'ready':
                raise ValueError('Job is not ready or its upload is already claimed')
            day = datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
            reserved = db.execute('SELECT job FROM daily_dispatches WHERE day=?',(day,)).fetchone()
            if reserved and reserved[0] != ident:
                raise ValueError('Another video owns today’s daily slot; this private upload waits for the next day')
            db.execute('INSERT OR IGNORE INTO daily_dispatches(day,job) VALUES(?,?)',(day,ident))
            claim = uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='uploading',claim=?,updated=? WHERE id=?",
                       (claim, time.time(), ident))
        return claim

    def complete_upload(self, ident, claim, video_id, reconcile=False):
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            raise ValueError('Enter a valid 11-character YouTube video ID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT state,claim FROM jobs WHERE id=?', (ident,)).fetchone()
            if not row:
                raise KeyError(ident)
            if row['state'] == 'uploaded':
                previous = db.execute('SELECT youtube_id FROM jobs WHERE id=?', (ident,)).fetchone()[0]
                if previous != video_id:
                    raise ValueError('This job is already linked to another video')
                return
            if row['state'] not in ('uploading', 'upload_uncertain') or (not reconcile and row['claim'] != claim):
                raise ValueError('Invalid upload claim or state')
            day = datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
            db.execute('INSERT OR IGNORE INTO daily_dispatches(day,job) VALUES(?,?)',(day,ident))
            db.execute("UPDATE jobs SET state='uploaded',youtube_id=?,detail='',progress=100,uploaded_at=?,updated=? WHERE id=?",
                       (video_id, time.time(), time.time(), ident))


def run(args, *, cwd=None, timeout=180):
    """Never use shell=True; never include raw provider output in persistent job logs."""
    return subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True,
                          text=True, timeout=timeout, check=False)


def probe(path):
    result = run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path])
    if result.returncode:
        raise StopJob('needs_attention', 'A media file could not be read. Replace or repair it before resuming.')
    return json.loads(result.stdout)


def quality(path, aspect, duration, *, audio=True):
    info = probe(path)
    videos = [s for s in info.get('streams', []) if s.get('codec_type') == 'video']
    if not videos:
        raise StopJob('needs_attention', 'Missing video stream.')
    v = videos[0]
    expected = 9/16 if aspect == '9:16' else 16/9
    if abs(v['width']/v['height'] - expected) > 0.025 or min(v['width'], v['height']) < 720:
        raise StopJob('needs_attention', 'Video dimensions or resolution do not match the selected format.')
    actual = float(info['format']['duration'])
    if abs(actual - duration) > 0.6:
        raise StopJob('needs_attention', 'Video length does not match the requested duration.')
    if audio and not any(s.get('codec_type') == 'audio' for s in info.get('streams', [])):
        raise StopJob('needs_attention', 'Missing narration audio.')
    return {'durationSeconds': actual, 'width': v['width'], 'height': v['height'], 'hasAudio': audio}


def allowed_file(path, root):
    resolved, base = Path(path).expanduser().resolve(), Path(root).expanduser().resolve()
    if not resolved.is_relative_to(base) or not resolved.is_file():
        raise ValueError('Use an existing media file inside the configured imports directory')
    return resolved


class Pipeline:
    def __init__(self, store, settings, state_dir):
        self.store, self.settings, self.state_dir = store, settings, Path(state_dir)

    def command(self, args, **kw):
        return run(args, **kw)

    def balance(self, profile):
        result = self.command(['gflow', 'credits', 'user', '--profile', profile, '--json'])
        if result.returncode:
            raise StopJob('blocked_login', 'Flow balance or login could not be verified. Check the spare Chrome session and CLI compatibility. Some accounts cannot expose a balance; repeated login may not help. No generation or automatic retry.')
        try:
            data = json.loads(result.stdout)
            credits = data['credits']
            if not data.get('authenticated', True) or isinstance(credits, bool) or not isinstance(credits, (int, float)) or not math.isfinite(credits):
                raise ValueError()
            return credits
        except (ValueError, KeyError, TypeError):
            raise StopJob('blocked_balance', 'Flow did not return a verifiable balance. Check account/CLI compatibility before Safe Resume; no generation was submitted.')

    def preflight(self, body, remaining=None):
        account = {'profile': body.get('flowProfile') or self.settings['accounts'][body['flowAccount']]['profile'],
                   'project': body.get('flowProject', '')}
        if not isinstance(account.get('profile'), str) or not re.fullmatch(r'[A-Za-z0-9_-]+', account['profile']):
            raise StopJob('needs_attention', 'Configure a dedicated Flow profile in the local accounts file.')
        refs = []
        if body.get('consistencyMode', 'reference') == 'reference':
            for c in body['selectedCharacters']:
                try:
                    path = allowed_file(c.get('referenceImage', ''), self.settings['importsDir'])
                except ValueError:
                    raise StopJob('needs_references', 'Add one local reference image per selected character, or explicitly select text-only consistency.')
                if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                    raise StopJob('needs_references', 'Use PNG, JPEG, or WebP character references.')
                refs.append(path)
        needed = (remaining if remaining is not None else body['plannedSceneCount']) * body['creditCostPerClip']
        balance = self.balance(account['profile'])
        if needed > balance:
            raise StopJob('blocked_credit', 'The estimated remaining scene cost exceeds the current Flow balance. Wait for credits or shorten the video.')
        return account, refs

    def execute(self, ident):
        if self.store.is_paused():
            raise StopJob('paused', 'Global pause is active. Saved clips are preserved; Resume Everything will restart safe work.')
        job = self.store.get(ident)
        body = job['body']
        if any(s['state'] in ('generating', 'uncertain') for s in job['scenes']):
            raise StopJob('needs_reconciliation', 'A scene may already be billed. Recover its downloaded clip before resuming.')
        work = self.state_dir / 'jobs' / ident
        work.mkdir(parents=True, exist_ok=True)
        self.store.update(ident, 'preflight', 'Checking tools, references, and Flow balance.')
        pending = [s for s in job['scenes'] if s['state'] != 'done']
        required = ['ffmpeg', 'ffprobe']
        if pending:
            required.append('gflow')
        if not (work/'narration.mp3').exists() or not (work/'captions.srt').exists():
            required.append('edge-tts')
        for binary in required:
            if not shutil.which(binary):
                raise StopJob('needs_setup', f'Install the missing tool: {binary}')
        pending = [s for s in job['scenes'] if s['state'] != 'done']
        account, refs = self.preflight(body, len(pending)) if pending else (self.settings['accounts'][body['flowAccount']], [])
        self.store.update(ident, 'narrating', 'Preparing one consistent narration and timed captions before spending Flow credits.')
        audio, captions = work/'narration.mp3', work/'captions.srt'
        if not audio.exists() or not captions.exists():
            voice = self.settings.get('voices', {}).get(body['language'],
                       'hi-IN-SwaraNeural' if body['language'] == 'Hindi' else 'en-IN-NeerjaNeural')
            result = self.command(['edge-tts', '--voice', voice, '--text', body['story'],
                                   '--write-media', audio, '--write-subtitles', captions])
            if result.returncode or not audio.exists() or not captions.exists() or not captions.stat().st_size:
                raise StopJob('needs_attention', 'Narration/caption service failed. No additional Flow credits will be spent; resume when it is available.')
        if float(probe(audio)['format']['duration']) > body['durationSeconds'] - 0.2:
            raise StopJob('story_too_long', 'The spoken story is too long for this duration. Submit a shorter story or select a longer duration; no new Flow clips were generated.')
        if 'subtitles' not in self.command(['ffmpeg', '-hide_banner', '-filters']).stdout:
            raise StopJob('needs_setup', 'Install an FFmpeg build with the subtitles/libass filter before generation.')
        words = body['story'].split()
        total = body['plannedSceneCount']
        normalized = []
        for scene in job['scenes']:
            n = scene['number']
            clip = Path(scene['path']) if scene['path'] else work/f'clip-{n:02}.mp4'
            if scene['state'] == 'done' and not clip.is_file():
                raise StopJob('needs_reconciliation', 'A completed clip is missing. Restore that file; it will not be regenerated automatically.')
            if scene['state'] != 'done':
                if self.store.is_paused():
                    raise StopJob('paused', 'Paused at a safe scene boundary. Completed clips are preserved.')
                self.preflight(body, sum(s['state'] != 'done' for s in self.store.get(ident)['scenes']))
                segment = ' '.join(words[len(words)*n//total:len(words)*(n+1)//total])
                identities = '\n'.join(f"{c['name']}: {c['facePrompt']}; {c['bodyPrompt']}" for c in body['selectedCharacters'])
                prompt = (f'Child-friendly polished 3D animation for ages 8 to 10. Scene {n+1} of {total}. '
                          f'Only these characters may appear; keep their identity and clothing unchanged:\n{identities}\n'
                          f'Story moment: {segment}\nClear visual storytelling, expressive movement, warm light. '
                          'No written text, no dialogue or singing; narration will be added separately.')
                args = ['gflow', 'video', 'r2v' if refs else 't2v', prompt, '--model', 'veo-lite',
                        '--duration', '8', '--count', '1', '--aspect', body['aspectRatio'],
                        '--profile', account['profile'], '--out-dir', work, '--json']
                if account.get('project'):
                    args += ['--project', account['project']]
                for ref in refs:
                    args += ['--ref', ref]
                if self.store.is_paused():
                    raise StopJob('paused', 'Paused before submitting the next paid scene.')
                # Commit the billing boundary BEFORE calling the provider.
                self.store.scene(ident, n, 'generating')
                self.store.update(ident, 'generating', f'Generating scene {n+1}/{total}. Keep the spare Chrome window open.', progress=int(n/total*75))
                try:
                    result = self.command(args, timeout=900)
                    data = json.loads(result.stdout)
                    if result.returncode or not data.get('succeeded') or not data.get('local_path'):
                        raise ValueError()
                    source = Path(data['local_path']).resolve()
                    if not source.is_relative_to(work.resolve()) or not source.is_file():
                        raise ValueError()
                    if source != clip.resolve():
                        shutil.copyfile(source, clip)
                    self.store.scene(ident, n, 'done', clip, data.get('media_id'))
                except (ValueError, OSError, subprocess.TimeoutExpired):
                    self.store.scene(ident, n, 'uncertain')
                    raise StopJob('needs_reconciliation', 'Generation stopped, timed out, or returned an unverifiable result. Check Flow for a billed clip, login, or CAPTCHA. This scene will not be submitted again automatically.')
            info = probe(clip)
            if float(info['format']['duration']) < 7.5:
                raise StopJob('needs_attention', 'A saved scene is shorter than expected. Recover a complete clip before assembly.')
            target = work/f'normalized-{n:02}.mp4'
            w, h = (720, 1280) if body['aspectRatio'] == '9:16' else (1280, 720)
            result = self.command(['ffmpeg', '-v', 'error', '-y', '-i', clip, '-an', '-vf',
                                   f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1',
                                   '-t', '8', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', target])
            if result.returncode:
                raise StopJob('needs_attention', 'Clip normalization failed; the original completed scenes are preserved.')
            normalized.append(target)
        self.store.update(ident, 'assembling', 'Assembling saved clips, narration, and timed captions.', progress=80)
        (work/'concat.txt').write_text(''.join(f"file '{p.name}'\n" for p in normalized))
        final = work/'final.mp4'
        result = self.command(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '1', '-i', 'concat.txt',
                               '-i', 'narration.mp3', '-map', '0:v', '-map', '1:a', '-vf', 'subtitles=captions.srt',
                               '-af', 'apad,loudnorm=I=-16:TP=-1.5:LRA=11', '-t', str(body['durationSeconds']),
                               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart',
                               'final.mp4'], cwd=work, timeout=600)
        if result.returncode:
            raise StopJob('needs_attention', 'Final assembly failed. Completed Flow scenes are preserved for safe resume.')
        self.store.update(ident, 'checking', 'Checking final video, duration, audio, captions, and decode errors.', progress=90)
        report = quality(final, body['aspectRatio'], body['durationSeconds'])
        result = self.command(['ffmpeg', '-v', 'error', '-i', final, '-f', 'null', '-'], timeout=300)
        if result.returncode or result.stderr.strip():
            raise StopJob('needs_attention', 'Final video did not pass the full decode check.')
        levels = self.command(['ffmpeg', '-hide_banner', '-i', final, '-vn', '-af', 'volumedetect', '-f', 'null', '-'], timeout=300)
        level = re.search(r'max_volume:\s*(-?\d+(?:\.\d+)?|-inf) dB', levels.stderr)
        if levels.returncode or not level or level.group(1) == '-inf' or float(level.group(1)) < -50:
            raise StopJob('needs_attention', 'Narration appears silent or could not be measured. Review audio before uploading.')
        report.update(captions='timed and burned in', consistency=body.get('consistencyMode', 'reference'),
                      narration='spoken, not sung', finalFile='final.mp4')
        self.store.update(ident, 'ready', 'Quality checks passed. Ready for private YouTube upload.', progress=95, report=report)
