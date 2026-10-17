"""Loopback-only, authenticated service for n8n. Start with python -m wondertales.app."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
from urllib.parse import urlsplit

from .core import Pipeline, StopJob, Store, allowed_file, probe, validate
from .queue import QueueManager
from .growth import Growth, story_check, cost_report


def load_settings(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    token_file = root/'api-token'
    if not token_file.exists():
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_urlsafe(40))
    os.chmod(token_file, 0o600)
    config = root/'settings.json'
    if not config.exists():
        data = {'accounts': {'flow-main': {'profile': 'wondertales'}},
                'youtubeDestinations': ['channel-main'], 'importsDir': str(root/'imports'),
                'voices': {'English': 'en-IN-NeerjaNeural', 'Hindi': 'hi-IN-SwaraNeural'}}
        fd = os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
    settings = json.loads(config.read_text())
    if not isinstance(settings.get('accounts'), dict) or not isinstance(settings.get('youtubeDestinations'), list):
        raise ValueError('Invalid local settings.json')
    Path(settings['importsDir']).expanduser().mkdir(parents=True, exist_ok=True)
    return root, settings, token_file.read_text().strip()


class Service:
    def __init__(self, root, settings):
        self.root, self.settings = root, settings
        self.store = Store(root/'jobs.sqlite3')
        self.pipeline = Pipeline(self.store, settings, root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='wondertales')
        self.mutations = threading.Lock()
        self.browser = threading.Lock()
        self.manager = QueueManager(self)
        self.growth = Growth(self.store, settings)

    def configure_accounts(self, body):
        if not self.browser.acquire(blocking=False):
            raise ValueError('Wait for the active browser job to finish before changing account mappings')
        try:
            with self.mutations:
                alias = str(body.get('flowAlias', '')).strip()
                profile = str(body.get('profile', '')).strip()
                destination = str(body.get('destination', '')).strip()
                project = str(body.get('project', '')).strip()
                safe = lambda value: bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value))
                if not alias and not destination:
                    raise ValueError('Provide a Flow account mapping or a YouTube destination alias')
                if alias and (not safe(alias) or not safe(profile)):
                    raise ValueError('Flow alias and profile name must use letters, numbers, hyphens, or underscores')
                if destination and not safe(destination):
                    raise ValueError('Use a simple YouTube destination alias')
                if project and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', project):
                    raise ValueError('Enter a valid existing Flow project ID')
                updated = json.loads(json.dumps(self.settings))
                if alias:
                    updated['accounts'][alias] = {'profile': profile, 'project': project}
                if destination and destination not in updated['youtubeDestinations']:
                    updated['youtubeDestinations'].append(destination)
                path = self.root/'settings.tmp'
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as f:
                    json.dump(updated, f, indent=2)
                os.replace(path, self.root/'settings.json')
                self.settings.clear()
                self.settings.update(updated)
                return {'configured': True, 'flowAccounts': list(updated['accounts']),
                        'youtubeDestinations': updated['youtubeDestinations'],
                        'note': 'Sign into the named dedicated Chrome profile yourself before submitting jobs. Existing jobs retain their pinned Flow profile.'}
        finally:
            self.browser.release()

    def enqueue(self, ident):
        self.executor.submit(self.work, ident)

    def work(self, ident):
        with self.browser:
            try:
                blockers = [j for j in self.store.list() if j['id'] != ident and j['state'] in ('needs_reconciliation', 'blocked_login')]
                if blockers:
                    raise StopJob('blocked_browser', 'Resolve the earlier Flow login or uncertain scene first. Close any leftover spare Chrome window before resuming jobs.')
                self.pipeline.execute(ident)
                if self.store.get(ident)['state'] == 'ready':
                    self.store.reserve_day(self.manager.day(), ident)
            except StopJob as exc:
                self.store.update(ident, exc.state, exc.detail, retry_after=time.time()+3600 if exc.state == 'blocked_credit' else 0)
            except Exception:
                # A provider may have accepted a scene before failing locally.
                job = self.store.get(ident)
                uncertain = False
                for scene in job['scenes']:
                    if scene['state'] == 'generating':
                        self.store.scene(ident, scene['number'], 'uncertain')
                        uncertain = True
                self.store.update(ident, 'needs_reconciliation' if uncertain else 'needs_attention',
                                  'The job stopped safely. Inspect saved clips and resume only after resolving the cause.')

    def public(self, ident):
        job = self.store.get(ident)
        job.pop('fingerprint', None)
        job.pop('claim', None)
        with self.store.connect() as db:
            slot = db.execute('SELECT job FROM daily_dispatches WHERE day=?',(self.manager.day(),)).fetchone()
        job['canClaimUpload'] = job['state']=='ready' and not self.store.is_paused() and (slot is None or slot[0]==ident)
        job['videoUrl'] = f'/v1/jobs/{ident}/video' if job['state'] in ('ready', 'uploading', 'uploaded', 'upload_uncertain') else None
        from .queue import HUMAN
        job['nextAction'] = HUMAN.get(job['state'], 'Wait for the next balance check.' if job['state']=='blocked_credit' else 'Use Resume Everything in Queue Controls.' if job['state']=='paused' else 'No action needed.')
        job['youtubeUrl'] = f"https://www.youtube.com/watch?v={job['youtube_id']}" if job.get('youtube_id') else None
        job['creditReport'] = cost_report(job)
        return job

    def action(self, ident, action, body):
        with self.mutations:
            job = self.store.get(ident)
            if action == 'resume':
                if job['state'] not in ('needs_setup', 'blocked_login', 'blocked_balance', 'blocked_credit', 'blocked_browser', 'needs_references', 'needs_attention'):
                    raise ValueError('This job cannot safely resume. Reconcile uncertain generations/uploads first.')
                if any(s['state'] in ('uncertain', 'generating') for s in job['scenes']):
                    raise ValueError('Recover the uncertain clip before resuming')
                self.store.update(ident, 'waiting', 'Safe resume requested; the daily queue and global pause still apply.', retry_after=0)
            elif action == 'archive':
                from .queue import ACTIVE
                if job['state'] in ACTIVE or job['state'] in ('uploading','upload_uncertain'):
                    raise ValueError('Wait for active work or reconcile the uncertain upload before archiving')
                self.store.update(ident, 'cancelled', 'Archived by owner. Saved clips are preserved; no further generation will run.')
            elif action == 'reset-narration':
                if job['state'] not in ('needs_attention', 'story_too_long'):
                    raise ValueError('Narration can only be rebuilt on a stopped job')
                for name in ('narration.mp3', 'captions.srt', 'final.mp4'):
                    (self.root/'jobs'/ident/name).unlink(missing_ok=True)
                self.store.update(ident, 'needs_attention', 'Narration cleared. Safe Resume will rebuild audio/captions and reuse completed scenes.')
            elif action == 'confirm-unsubmitted':
                number = body.get('sceneIndex')
                if job['state'] != 'needs_reconciliation' or type(number) is not int or not 0 <= number < len(job['scenes']):
                    raise ValueError('Choose an uncertain scene on a stopped job')
                if job['scenes'][number]['state'] != 'uncertain' or body.get('confirmation') != 'NOT_SUBMITTED':
                    raise ValueError('Only clear this after checking Flow and typing NOT_SUBMITTED. Never clear a still-running or billed scene.')
                self.store.scene(ident, number, 'pending')
                if not any(s['state'] in ('uncertain', 'generating') for s in self.store.get(ident)['scenes']):
                    self.store.update(ident, 'needs_attention', 'Operator confirmed no submission. Safe Resume may now submit this scene once.')
            elif action == 'recover':
                if job['state'] not in ('needs_reconciliation', 'needs_attention'):
                    raise ValueError('Stop the job before recovering a clip')
                number = body.get('sceneIndex')
                if type(number) is not int or not 0 <= number < len(job['scenes']):
                    raise ValueError('Enter a valid zero-based scene index')
                path = allowed_file(body.get('filePath', ''), self.settings['importsDir'])
                info = probe(path)
                if not any(s.get('codec_type') == 'video' for s in info.get('streams', [])) or float(info['format']['duration']) < 7.5:
                    raise ValueError('Recover a complete video clip of at least 7.5 seconds')
                dest = self.root/'jobs'/ident/f'clip-{number:02}.mp4'
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
                self.store.scene(ident, number, 'done', dest)
                if not any(s['state'] in ('uncertain', 'generating') for s in self.store.get(ident)['scenes']):
                    self.store.update(ident, 'needs_attention', 'Clip recovered. Resume to continue with the remaining safe steps.')
            elif action == 'claim-upload':
                claim = self.store.claim_upload(ident, body.get('destination'))
                return {**self.public(ident), 'uploadClaim': claim}
            elif action == 'complete-upload':
                self.store.complete_upload(ident, body.get('uploadClaim'), body.get('youtubeId', ''))
            elif action == 'reconcile-upload':
                self.store.complete_upload(ident, None, body.get('youtubeId', ''), reconcile=True)
            else:
                raise KeyError(action)
        return self.public(ident)


def make_handler(service, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Avoid logging paths, story text, provider responses, or tokens.

        def send_json(self, status, data):
            raw = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def authorized(self):
            return hmac.compare_digest(self.headers.get('X-WonderTales-Key', ''), token)

        def dispatch(self, method):
            path = urlsplit(self.path).path
            if path == '/health' and method == 'GET':
                return self.send_json(200, {'service': 'wondertales', 'status': 'running'})
            if not self.authorized():
                return self.send_json(401, {'error': 'Configure the WonderTales header credential in n8n.'})
            body = {}
            if method == 'POST':
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    raise ValueError('Invalid Content-Length')
                if size < 0 or size > 200000:
                    return self.send_json(413, {'error': 'Request body too large'})
                body = json.loads(self.rfile.read(size) or b'{}')
                if not isinstance(body, dict):
                    raise ValueError('Send a JSON object')
            if method == 'GET' and path == '/v1/setup':
                from .editor import status as editor_status
                return self.send_json(200, {'tools': {x: bool(shutil.which(x)) for x in ('gflow', 'edge-tts', 'ffmpeg', 'ffprobe')},
                    'flowAccounts': list(service.settings['accounts']),
                    'youtubeDestinations': service.settings['youtubeDestinations'],
                    'browserConcurrency': 1, 'generationModel': 'veo-lite',
                    'optionalEditor': editor_status(service.settings, service.root)})
            if method == 'POST' and path == '/v1/analytics/snapshot':
                return self.send_json(200, service.growth.save(body))
            if method == 'GET' and path == '/v1/analytics/jobs':
                return self.send_json(200, {'jobs': [{'id': j['id'], 'destination': j['body']['youtubeDestination'],
                    'youtubeId': j['youtube_id']} for j in service.store.list(limit=None) if j.get('youtube_id')]})
            if method == 'GET' and path == '/v1/growth/report':
                return self.send_json(200, service.growth.report())
            if method == 'POST' and path == '/v1/stories/check':
                data = validate(body, service.settings)
                return self.send_json(200, story_check(data, service.store.list(limit=None)))
            if path == '/v1/queue/command' and method == 'POST':
                action = body.get('action')
                if action not in ('pause','resume','tick','summary'):
                    raise ValueError('Choose a supported queue command')
                if action in ('pause','resume'):
                    service.store.set_paused(action == 'pause')
                result = service.manager.tick() if action in ('resume','tick') else None
                return self.send_json(200, {**service.manager.summary(), 'queueCheck':result})
            if path == '/v1/queue/tick' and method == 'POST':
                return self.send_json(200, service.manager.tick())
            if path == '/v1/queue/summary' and method == 'GET':
                return self.send_json(200, service.manager.summary())
            if path == '/v1/queue/control' and method == 'POST':
                if type(body.get('paused')) is not bool:
                    raise ValueError('Choose Pause Everything or Resume Everything')
                service.store.set_paused(body['paused'])
                return self.send_json(200, service.manager.summary())
            if path == '/v1/stories' and method == 'POST':
                stories = body.get('stories')
                if not isinstance(stories,list) or not 1 <= len(stories) <= 30:
                    raise ValueError('Submit between one and thirty stories in a batch')
                with service.mutations:
                    validated = [validate(story,service.settings) for story in stories]
                    saved = service.store.submit_many(validated)
                return self.send_json(202, {'jobs':[{**service.public(j['id']), 'duplicate':not created} for j,created in saved]})
            if path == '/v1/setup/accounts' and method == 'POST':
                return self.send_json(200, service.configure_accounts(body))
            if path == '/v1/jobs':
                if method == 'GET':
                    return self.send_json(200, {'jobs': [service.public(j['id']) for j in service.store.list()]})
                with service.mutations:
                    data = validate(body, service.settings)
                    job, created = service.store.submit(data)
                return self.send_json(202 if created else 200, {**service.public(job['id']), 'duplicate': not created})
            if method == 'POST' and path == '/v1/preflight':
                data = validate(body, service.settings)
                if not service.browser.acquire(blocking=False):
                    return self.send_json(409, {'error': 'The single browser is busy. Try preflight after the active job finishes.'})
                try:
                    service.pipeline.preflight(data)
                finally:
                    service.browser.release()
                return self.send_json(200, {'checked': True, 'plannedSceneCount': data['plannedSceneCount'],
                                            'estimatedCredits': data['estimatedCredits'], 'spentCredits': 0,
                                            'storyReview': story_check(data, service.store.list(limit=None))})
            match = re.fullmatch(r'/v1/jobs/([a-f0-9]{32})(?:/([a-z-]+|thumbnail-[123]))?', path)
            if not match:
                return self.send_json(404, {'error': 'Unknown endpoint'})
            ident, action = match.groups()
            if method == 'POST' and action:
                return self.send_json(200, service.action(ident, action, body))
            job = service.store.get(ident)
            if method == 'GET' and action in ('video', 'captions', 'thumbnail-1', 'thumbnail-2', 'thumbnail-3'):
                if job['state'] not in ('ready', 'uploading', 'uploaded', 'upload_uncertain'):
                    raise ValueError('The final video is not ready')
                filename = 'final.mp4' if action == 'video' else 'captions.srt' if action == 'captions' else action+'.jpg'
                file = service.root/'jobs'/ident/filename
                if not file.is_file():
                    raise KeyError('Missing output file')
                self.send_response(200)
                self.send_header('Content-Type', 'video/mp4' if action == 'video' else 'application/x-subrip' if action == 'captions' else 'image/jpeg')
                self.send_header('Content-Length', str(file.stat().st_size))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                with file.open('rb') as reader:
                    shutil.copyfileobj(reader, self.wfile)
                return
            if method == 'GET' and action is None:
                return self.send_json(200, service.public(ident))
            return self.send_json(404, {'error': 'Unknown endpoint'})

        def handle_method(self, method):
            try:
                self.dispatch(method)
            except ValueError as exc:
                self.send_json(400, {'error': str(exc)[:300]})
            except TypeError:
                self.send_json(400, {'error': 'Check the submitted field types.'})
            except KeyError:
                self.send_json(404, {'error': 'Job or resource not found'})
            except StopJob as exc:
                self.send_json(409, {'state': exc.state, 'detail': exc.detail})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send_json(500, {'error': 'Local worker error. Saved job state has been preserved.'})

        def do_GET(self):
            self.handle_method('GET')

        def do_POST(self):
            self.handle_method('POST')
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', default=os.environ.get('WONDERTALES_HOME', '~/.local/share/wondertales'))
    parser.add_argument('--port', type=int, default=8099)
    parser.add_argument('--doctor', action='store_true')
    args = parser.parse_args()
    root, settings, token = load_settings(args.state_dir)
    if args.doctor:
        tools = {x: bool(shutil.which(x)) for x in ('gflow', 'edge-tts', 'ffmpeg', 'ffprobe')}
        print(json.dumps({'tools': tools, 'accounts': list(settings['accounts']),
                          'settingsFile': str(root/'settings.json'), 'tokenFile': str(root/'api-token'),
                          'note': 'No Google login or generation performed.'}, indent=2))
        return 0 if all(tools.values()) else 1
    # macOS/Linux: one runner process, one serialized Chrome session across all accounts.
    import fcntl
    lock = (root/'worker.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Another WonderTales worker already owns this browser runner.')
    service = Service(root, settings)
    service.store.recover_after_restart()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(service, token))
    print(f'WonderTales is listening on http://127.0.0.1:{args.port}; use n8n for submissions and status.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.executor.shutdown(wait=True)
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
