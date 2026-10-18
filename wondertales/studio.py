"""Storyboards, immutable character libraries, explicit scene revisions and retention."""
import copy
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time

from .core import allowed_file, probe


def text(value, name, limit=2000, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f'{name} must be text up to {limit} characters'+(' and cannot be blank' if required else ''))
    return value.strip()


def validate_plan(body):
    body['visualStyle'] = text(body.get('visualStyle', 'Polished child-friendly 3D animation, warm light, expressive movement'), 'visualStyle', 500, True)
    body['characterLibraryVersion'] = text(body.get('characterLibraryVersion', ''), 'characterLibraryVersion', 100)
    for char in body['selectedCharacters']:
        char['continuityNotes'] = text(char.get('continuityNotes', ''), 'continuityNotes', 1000)
    plan = body.get('storyboard', [])
    if not isinstance(plan, list) or (plan and len(plan) != body['plannedSceneCount']):
        raise ValueError(f"Storyboard needs exactly {body['plannedSceneCount']} scenes for this duration, or leave it blank")
    clean = []
    names = {c['name'] for c in body['selectedCharacters']}
    for index, scene in enumerate(plan):
        if not isinstance(scene, dict):
            raise ValueError('Every storyboard scene must be an object')
        cast = scene.get('characters')
        if not isinstance(cast, list) or not cast or any(not isinstance(c, str) or c not in names for c in cast) or len(set(cast)) != len(cast):
            raise ValueError('Scene characters must be unique names from the selected cast')
        clean.append({**{k: text(scene.get(k), f'Scene {index+1} {k}', 1500, True) for k in ('action','setting','narration')}, 'characters':cast})
    if clean:
        narration = ' '.join(s['narration'] for s in clean)
        if len(narration) > 12000:
            raise ValueError('Combined storyboard narration exceeds 12000 characters')
        body['storyOutline'] = body['story']
        body['story'] = narration
    body['storyboard'] = clean


class Studio:
    def __init__(self, store, settings, root):
        self.store, self.settings, self.root = store, settings, Path(root)
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS character_library (version TEXT PRIMARY KEY, payload TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS character_active (id INTEGER PRIMARY KEY CHECK(id=1), version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scene_revisions (request_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, target TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS retention (destination TEXT NOT NULL, video TEXT NOT NULL, payload TEXT NOT NULL,
                  updated REAL NOT NULL, PRIMARY KEY(destination,video));
            ''')

    def library(self):
        with self.store.connect() as db:
            row = db.execute('SELECT l.version,l.payload FROM character_library l JOIN character_active a ON a.version=l.version WHERE a.id=1').fetchone()
        return {'version':row['version'], 'characters':json.loads(row['payload'])} if row else {'version':'', 'characters':[]}

    def save_library(self, body):
        version = text(body.get('version'), 'Library version', 64, True)
        if not re.fullmatch(r'[A-Za-z0-9_-]+', version):
            raise ValueError('Use letters, numbers, underscores or hyphens for the library version')
        chars = body.get('characters')
        if not isinstance(chars, list) or not 2 <= len(chars) <= 10:
            raise ValueError('Save between two and ten complete character definitions')
        clean = [{k:text(c.get(k, ''), k, 2000 if k != 'continuityNotes' else 1000, k in ('name','facePrompt','bodyPrompt'))
                  for k in ('name','facePrompt','bodyPrompt','referenceImage','continuityNotes')} for c in chars if isinstance(c,dict)]
        if len(clean) != len(chars) or len({c['name'] for c in clean}) != len(clean):
            raise ValueError('Use complete character objects with unique names')
        for char in clean:
            if char['referenceImage']:
                path = allowed_file(char['referenceImage'], self.settings['importsDir'])
                if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                    raise ValueError('Use PNG, JPEG or WebP character reference images')
                char['referenceSha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        payload = json.dumps(clean, sort_keys=True)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload FROM character_library WHERE version=?',(version,)).fetchone()
            if row and row[0] != payload:
                raise ValueError('This version is immutable. Use a new version name to change the characters')
            db.execute('INSERT OR IGNORE INTO character_library VALUES(?,?,?)',(version,payload,time.time()))
            db.execute('INSERT INTO character_active VALUES(1,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version',(version,))
        return {'saved': True, 'version':version, 'characters':clean, 'note':'Existing jobs retain their saved definitions. This version is now active for forms without a local registry.'}

    def replacement(self, source_id, request, *, create=False):
        job = self.store.get(source_id)
        number = request.get('sceneIndex')
        if type(number) is not int or not 0 <= number < len(job['scenes']):
            raise ValueError('Choose a valid zero-based scene index')
        rate, cap = request.get('creditCostPerClip'), request.get('additionalCreditCap')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v <= 0 for v in (rate, cap)) or rate > cap:
            raise ValueError('Enter the current per-clip credit cost and an additional cap covering that one clip')
        direction = text(request.get('direction', ''), 'Replacement direction', 1500, True)
        label = text(request.get('requestLabel', ''), 'Replacement label', 64, create)
        fingerprint = hashlib.sha256(json.dumps([source_id,number,rate,cap,direction,label],ensure_ascii=False).encode()).hexdigest()
        key = hashlib.sha256((source_id+'|'+label).encode()).hexdigest()
        if create:
            if request.get('confirmation') != 'REPLACE_ONE_SCENE':
                raise ValueError('Preview the estimate, then type REPLACE_ONE_SCENE to request one new paid clip')
            with self.store.connect() as db:
                old = db.execute('SELECT * FROM scene_revisions WHERE request_key=?',(key,)).fetchone()
            if old:
                if old['request_hash'] != fingerprint:
                    raise ValueError('This replacement label was already used with different settings. Use a new label for a new request')
                return {'jobId':old['target'], 'duplicate':True, 'estimatedNewCredits':rate}
        if job['state'] not in ('ready','uploaded') or any(s['state'] != 'done' for s in job['scenes']):
            raise ValueError('Replace a scene only after all scenes are complete and the job is ready or uploaded. Resolve active or uncertain work first')
        for scene in job['scenes']:
            file = Path(scene['path'] or '')
            if not file.is_file():
                raise ValueError('Restore every original clip before requesting a replacement')
        estimate = {'sourceJobId':source_id, 'sceneIndex':number, 'estimatedNewCredits':rate,
                    'additionalCreditCap':cap, 'reusedScenes':len(job['scenes'])-1,
                    'note':'One new generation through the daily queue. Original clips/video remain saved. This estimate uses the rate you entered; verify it in Flow.'}
        if not create:
            return {**estimate, 'previewOnly':True, 'confirmationRequired':'REPLACE_ONE_SCENE'}
        # Validate all reused media before accepting a new paid task.
        for scene in job['scenes']:
            info = probe(scene['path'])
            if float(info['format']['duration']) < 7.5 or not any(s.get('codec_type')=='video' for s in info.get('streams',[])):
                raise ValueError('Repair the original clips before creating a scene revision')
        target = fingerprint[:32]
        work = self.root/'jobs'/target
        work.mkdir(parents=True, exist_ok=True)
        scenes = []
        for scene in job['scenes']:
            n = scene['number']
            dest = work/f'clip-{n:02}.mp4'
            if n != number:
                shutil.copyfile(scene['path'], dest)
            scenes.append((target,n,'pending' if n==number else 'done',None if n==number else str(dest),None if n==number else scene['media_id']))
        source_work = self.root/'jobs'/source_id
        for name in ('narration.mp3','captions.srt'):
            if (source_work/name).is_file():
                shutil.copyfile(source_work/name,work/name)
        for file in source_work.glob('reference-*'):
            if file.is_file(): shutil.copyfile(file, work/file.name)
        body = copy.deepcopy(job['body'])
        body.update(variant='scene-revision-'+key, revisionOf=source_id, replacementScene=number,
                    replacementDirection=direction, creditCostPerClip=rate, replacementCreditCap=cap,
                    estimatedCredits=rate, reusedSceneCount=len(scenes)-1)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            state = db.execute('SELECT state FROM jobs WHERE id=?',(source_id,)).fetchone()[0]
            if state not in ('ready','uploaded'):
                raise ValueError('Source job changed while preparing the revision; no new generation was submitted')
            db.execute('INSERT INTO jobs(id,fingerprint,body,state,detail,created,updated) VALUES(?,?,?,?,?,?,?)',
                       (target,fingerprint,json.dumps(body),'waiting','Explicit single-scene revision queued. Existing clips are reused.',time.time(),time.time()))
            db.executemany('INSERT INTO scenes(job,number,state,path,media_id) VALUES(?,?,?,?,?)',scenes)
            db.execute('INSERT INTO scene_revisions VALUES(?,?,?)',(key,fingerprint,target))
            if state == 'ready':
                db.execute("UPDATE jobs SET state='superseded',detail=?,updated=? WHERE id=?",
                           ('Original preserved. Replacement revision: '+target,time.time(),source_id))
        return {**estimate, 'jobId':target, 'duplicate':False}

    def save_retention(self, body):
        job = self.store.get(body.get('jobId'))
        destination, video = job['body']['youtubeDestination'], job.get('youtube_id')
        if job['state'] != 'uploaded' or not video or body.get('video') != video or body.get('destination') != destination:
            raise ValueError('Retention must match an uploaded managed video and destination')
        with self.store.connect() as db:
            channel = db.execute('SELECT payload FROM analytics WHERE destination=?',(destination,)).fetchone()
        if not channel or json.loads(channel[0])['channelId'] != body.get('channelId'):
            raise ValueError('Run daily analytics for this verified channel before saving retention')
        try:
            start, end = date.fromisoformat(body.get('startDate')), date.fromisoformat(body.get('endDate'))
        except (ValueError, TypeError):
            raise ValueError('Use ISO retention report dates')
        if start > end or (end-start).days > 90 or end > date.today():
            raise ValueError('Use a past retention window of at most 91 days')
        points = body.get('points')
        if not isinstance(points,list) or len(points)>1000:
            raise ValueError('Retention points must be an array of at most 1000 entries')
        clean = []
        for p in points:
            if not isinstance(p,dict): raise ValueError('Invalid retention point')
            item = {}
            for name in ('elapsedVideoTimeRatio','audienceWatchRatio','relativeRetentionPerformance'):
                value = p.get(name)
                if name == 'relativeRetentionPerformance' and value is None:
                    item[name] = None
                    continue
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or (name!='audienceWatchRatio' and value>1):
                    raise ValueError('Invalid retention ratio')
                item[name] = value
            clean.append(item)
        clean.sort(key=lambda p:p['elapsedVideoTimeRatio'])
        if len({p['elapsedVideoTimeRatio'] for p in clean}) != len(clean):
            raise ValueError('Duplicate retention time positions')
        payload = {k:body[k] for k in ('jobId','destination','channelId','video','startDate','endDate')}
        payload['points'] = clean
        with self.store.connect() as db:
            old = db.execute('SELECT payload FROM retention WHERE destination=? AND video=?',(destination,video)).fetchone()
            if old and json.loads(old[0])['endDate'] > body['endDate']:
                raise ValueError('An older retention window cannot overwrite a newer one')
            db.execute('INSERT INTO retention VALUES(?,?,?,?) ON CONFLICT(destination,video) DO UPDATE SET payload=excluded.payload,updated=excluded.updated',
                       (destination,video,json.dumps(payload),time.time()))
        return {'saved':True, 'jobId':job['id'], 'points':len(clean)}

    def retention_report(self):
        with self.store.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM retention ORDER BY updated DESC LIMIT 50')]
        reports = []
        for row in rows:
            data = json.loads(row['payload']); job = self.store.get(data['jobId'])
            duration = job['report'].get('durationSeconds', job['body']['durationSeconds'])
            stale = time.time()-row['updated'] > 3*86400 or (date.today()-date.fromisoformat(data['endDate'])).days>7
            decreases = [{'fromSeconds':round(a['elapsedVideoTimeRatio']*duration,2),
                          'toSeconds':round(b['elapsedVideoTimeRatio']*duration,2),
                          'watchRatioDecrease':round(a['audienceWatchRatio']-b['audienceWatchRatio'],4)}
                         for a,b in zip(data['points'],data['points'][1:]) if a['audienceWatchRatio']>b['audienceWatchRatio']]
            reports.append({**data, 'title':job['body']['title'], 'stale':stale, 'snapshotAt':row['updated'],
                            'inspectIntervals':[] if stale else sorted(decreases,key=lambda x:x['watchRatioDecrease'],reverse=True)[:3],
                            'note':'Inspect these intervals for pacing, audio or story clarity. Ratios can include rewatching; decreases do not prove why viewers left. Empty or stale data gives no recommendation.'})
        return reports
