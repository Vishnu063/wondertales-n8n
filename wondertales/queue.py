"""Rule-based daily queue manager. No AI/API subscription, login automation, or notifications."""
from collections import Counter
from datetime import datetime
import time
from zoneinfo import ZoneInfo

ACTIVE = {'queued', 'preflight', 'narrating', 'generating', 'assembling', 'checking'}
HUMAN = {
    'blocked_balance': 'Check Flow balance access and CLI compatibility, then request Safe Resume. No generation was submitted.',
    'blocked_login': 'Stop the worker, sign into the dedicated Chrome profile, then request Safe Resume.',
    'needs_reconciliation': 'Check Flow and recover the existing clip; do not regenerate an uncertain scene.',
    'upload_uncertain': 'Check YouTube Studio and record the existing video ID; do not upload again.',
    'needs_setup': 'Run Setup Diagnostics and install the missing tool, then request Safe Resume.',
    'needs_references': 'Add the selected character reference files, then request Safe Resume.',
    'needs_attention': 'Read the job detail, fix the issue, then request Safe Resume or archive the job.',
    'story_too_long': 'Archive this job and submit a shorter story or select a longer duration.',
    'blocked_browser': 'Resolve the earlier browser/login problem, then request Safe Resume.',
}


class QueueManager:
    def __init__(self, service, timezone='Asia/Kolkata'):
        self.service = service
        self.store = service.store
        self.zone = ZoneInfo(timezone)

    def day(self, timestamp=None):
        return datetime.fromtimestamp(time.time() if timestamp is None else timestamp, self.zone).date().isoformat()

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.service.mutations:
            if self.store.is_paused():
                return {'dispatched': False, 'reason': 'paused', 'nextAction': 'Use Resume Everything in Queue Controls.'}
            jobs = self.store.list(limit=None)
            if any(j['state'] in ACTIVE for j in jobs):
                return {'dispatched': False, 'reason': 'already_working', 'nextAction': 'Wait; only one browser job runs at a time.'}
            blockers = [j for j in jobs if j['state'] in HUMAN]
            if blockers:
                job = min(blockers, key=lambda j: j['created'])
                return {'dispatched': False, 'reason': 'needs_you', 'jobId': job['id'], 'nextAction': HUMAN[job['state']]}
            if any(j['state'] in ('ready', 'uploading') for j in jobs):
                return {'dispatched': False, 'reason': 'awaiting_private_upload',
                        'nextAction': 'The private-upload workflow must finish the previous video before the next begins.'}
            candidates = sorted((j for j in jobs if j['state'] in ('waiting', 'paused', 'blocked_credit')), key=lambda j:j['created'])
            if not candidates:
                return {'dispatched': False, 'reason': 'empty_story_bank', 'nextAction': 'Add stories using Story Intake or Story Bank.'}
            job = candidates[0]
            if job['state'] == 'blocked_credit' and job['retry_after'] > now:
                return {'dispatched': False, 'reason': 'waiting_for_credit_check', 'jobId':job['id'],
                        'nextCheckAt':datetime.fromtimestamp(job['retry_after'],self.zone).isoformat(), 'nextAction':'Nothing needed. A later tick will recheck the balance without video generation.'}
            if not self.store.reserve_day(self.day(now), job['id']):
                return {'dispatched': False, 'reason': 'daily_limit', 'nextAction': 'Today’s video slot is used. The queue resumes on the next local calendar day.'}
            self.store.update(job['id'], 'queued', 'Daily queue selected this story; one managed job per local day.', retry_after=0)
            self.service.enqueue(job['id'])
            return {'dispatched': True, 'jobId': job['id'], 'localDate': self.day(now)}

    def summary(self, now=None):
        today = self.day(now)
        jobs = self.store.list(limit=None)
        events = lambda key: sum(bool(j.get(key)) and self.day(j[key]) == today for j in jobs)
        needs = [{'jobId':j['id'], 'title':j['body']['title'], 'state':j['state'],
                  'problem':j['detail'], 'nextAction':HUMAN[j['state']]} for j in jobs if j['state'] in HUMAN]
        return {'localDate': today, 'timezone':str(self.zone), 'paused':self.store.is_paused(),
                'dailyLimit':1, 'counts':dict(Counter(j['state'] for j in jobs)),
                'today':{'submitted':sum(self.day(j['created'])==today for j in jobs),
                         'videosCompleted':events('ready_at'), 'privateUploadsCompleted':events('uploaded_at')},
                'waiting':sum(j['state'] in ('waiting','paused','blocked_credit') for j in jobs),
                'attentionRequired':len(needs),
                'failedOrBlockedToday':sum(j['state'] in HUMAN and self.day(j['updated']) == today for j in jobs),
                'needsYou':needs, 'nextAction': 'Resume Everything when ready.' if self.store.is_paused() else
                    (needs[0]['nextAction'] if needs else 'Nothing needs your attention. Keep the worker, n8n queue workflow, and any SSH tunnel running.')}
