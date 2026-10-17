"""Private analytics snapshots and transparent editorial rules, without an AI service."""
from collections import defaultdict
from datetime import date
from difflib import SequenceMatcher
import json
import math
import re
import time
import unicodedata

METRICS = ('views', 'estimatedMinutesWatched', 'averageViewPercentage', 'subscribersGained')


def story_check(body, jobs, ident=None):
    normalize = lambda text: re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text).casefold()).strip()
    text = normalize(body['story'])
    current = next((j for j in jobs if j['id'] == ident), None)
    similar = []
    for job in jobs:
        if job['id'] == ident or job['state'] == 'archived':
            continue
        if current and job['created'] >= current['created']:
            continue
        previous = normalize(job['body']['story'])
        if text == previous:
            score = 1.0
        elif 2*min(len(text), len(previous))/max(1, len(text)+len(previous)) < 0.92:
            continue
        else:
            score = SequenceMatcher(None, text, previous, autojunk=True).ratio()
        if score >= 0.92:
            similar.append({'jobId': job['id'], 'title': job['body']['title'], 'textSimilarity': round(score, 3)})
    warnings = []
    if not body.get('learningGoal', '').strip():
        warnings.append('Add a concrete learning goal when relevant; this rule cannot judge educational value.')
    if not body.get('rightsNote', '').strip():
        warnings.append('Record your rights or licences for the story, characters, music and reference images.')
    if body.get('variant', '').strip() and similar:
        warnings.append('Intentional variant recorded. Review whether the new video adds meaningful creative value.')
    return {'similarJobs': similar[:5], 'warnings': warnings,
            'method': 'Text similarity only; not copyright clearance, visual review or monetization approval.'}


def cost_report(job):
    b = job['body']
    submitted = sum(s['state'] in ('done', 'generating', 'uncertain') for s in job['scenes'])
    uncertain = sum(s['state'] in ('generating', 'uncertain') for s in job['scenes'])
    return {'jobId': job['id'], 'title': b['title'], 'editor': b.get('editor', 'builtin'),
            'plannedCredits': b.get('estimatedCredits', b['plannedSceneCount'] * b['creditCostPerClip']),
            'submittedOrRecoveredScenes': submitted, 'uncertainScenes': uncertain,
            'submittedSceneCreditEstimate': round(submitted * b['creditCostPerClip'], 3),
            'reusableClips': sum(s['state'] == 'done' for s in job['scenes']),
            'note': 'Configured-rate estimate, not actual Google billing. Recovered clips may have been generated outside this worker.'}


class Growth:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analytics (destination TEXT PRIMARY KEY, payload TEXT NOT NULL, updated REAL NOT NULL)')

    def save(self, body):
        destination = body.get('destination')
        if destination not in self.settings['youtubeDestinations']:
            raise ValueError('Unknown YouTube destination alias')
        channel = body.get('channelId')
        if not isinstance(channel, str) or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', channel):
            raise ValueError('Enter the verified expected YouTube channel ID')
        start, end = body.get('startDate'), body.get('endDate')
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
        except (ValueError, TypeError):
            raise ValueError('Use ISO report dates')
        if first > last or (last-first).days > 90 or last > date.today():
            raise ValueError('Use a past report window of at most 91 days')
        rows, videos = body.get('rows', []), body.get('videos', [])
        if not isinstance(rows, list) or len(rows) > 200 or not isinstance(videos, list) or len(videos) > 50:
            raise ValueError('Snapshot exceeds the supported report size')
        clean, statuses = [], []
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(row.get('video', ''))):
                raise ValueError('Invalid analytics video ID')
            if row['video'] in seen:
                raise ValueError('Duplicate analytics video ID')
            seen.add(row['video'])
            item = {'video': row['video']}
            for key in METRICS:
                value = row.get(key)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError('Analytics metrics must be finite non-negative numbers')
                item[key] = value
            clean.append(item)
        for item in videos:
            if (not isinstance(item, dict) or item.get('channelId') != channel or
                not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(item.get('id', ''))) or
                item.get('privacyStatus') not in ('private', 'public', 'unlisted')):
                raise ValueError('Video status does not match the verified channel')
            statuses.append({k: item[k] for k in ('id', 'channelId', 'privacyStatus')})
        count = body.get('subscriberCount')
        if count is not None and (type(count) is not int or count < 0):
            raise ValueError('Subscriber count must be an integer or null when hidden')
        payload = {'destination': destination, 'channelId': channel, 'startDate': start, 'endDate': end,
                   'rows': clean, 'videos': statuses, 'subscriberCount': count}
        with self.store.connect() as db:
            previous = db.execute('SELECT payload FROM analytics WHERE destination=?', (destination,)).fetchone()
            if previous and json.loads(previous[0])['channelId'] != channel:
                raise ValueError('This alias already tracks another channel. Register a separate destination alias.')
            if previous and json.loads(previous[0])['endDate'] > end:
                raise ValueError('A newer report is already saved; an older execution cannot overwrite it')
            db.execute('INSERT INTO analytics VALUES(?,?,?) ON CONFLICT(destination) DO UPDATE SET payload=excluded.payload,updated=excluded.updated',
                       (destination, json.dumps(payload), time.time()))
        return {'saved': True, 'videosWithAnalytics': len(clean), 'destination': destination}

    def report(self, now=None):
        now = time.time() if now is None else now
        jobs = self.store.list(limit=None)
        by_video = {(j['body']['youtubeDestination'], j['youtube_id']): j for j in jobs if j.get('youtube_id')}
        with self.store.connect() as db:
            snapshots = [dict(row) for row in db.execute('SELECT * FROM analytics')]
        channels, results, visibility = [], [], {}
        for record in snapshots:
            data = json.loads(record['payload'])
            destination = data['destination']
            stale = (now - record['updated'] > 3 * 86400 or
                     (date.fromtimestamp(now) - date.fromisoformat(data['endDate'])).days > 7)
            channels.append({'destination': destination, 'channelId': data['channelId'],
                             'subscriberCount': data['subscriberCount'], 'startDate': data['startDate'],
                             'endDate': data['endDate'], 'snapshotAt': record['updated'], 'stale': stale})
            for v in data['videos']:
                visibility[(destination, v['id'])] = (v['privacyStatus'], stale)
            for row in data['rows']:
                job = by_video.get((destination, row['video']))
                state = visibility.get((destination, row['video']))
                # Compare only managed videos confirmed public in a fresh status snapshot.
                if not job or stale or state != ('public', False):
                    continue
                b = job['body']
                results.append({**row, 'jobId': job['id'], 'title': b['title'], 'destination': destination,
                                'language': b['language'], 'format': b['aspectRatio'], 'durationSeconds': b['durationSeconds'],
                                'characters': [c['name'] for c in b['selectedCharacters']],
                                'learningGoal': b.get('learningGoal', '')})
        reminders = []
        for job in jobs:
            if job['state'] == 'ready':
                reminders.append({'jobId': job['id'], 'action': 'Enable/configure the private-upload workflow for this destination.'})
            elif job['state'] == 'uploaded':
                state = visibility.get((job['body']['youtubeDestination'], job['youtube_id']))
                if state == ('private', False):
                    action = 'Review in YouTube Studio and make public when you choose. Automation never publishes.'
                elif state is None or state[1]:
                    action = 'Refresh analytics/status; publication status is unknown or stale.'
                else:
                    continue
                reminders.append({'jobId': job['id'], 'title': job['body']['title'], 'action': action})
        groups = defaultdict(list)
        for row in results:
            # Keep different channels, languages and formats separate.
            label = f"{row['destination']} / {row['language']} / {row['format']} / {row['durationSeconds']}s"
            groups[label].append(row)
        comparisons = []
        for label, rows in groups.items():
            views = sum(r['views'] for r in rows)
            comparisons.append({'group': label, 'videos': len(rows), 'views': views,
                                'viewWeightedAveragePercentage': round(sum(r['views']*r['averageViewPercentage'] for r in rows)/views, 2) if views else None,
                                'subscribersGained': sum(r['subscribersGained'] for r in rows),
                                'evidence': 'exploratory' if len(rows) >= 3 and views >= 100 else 'small sample; keep testing'})
        ranked = sorted(results, key=lambda r: r['estimatedMinutesWatched'], reverse=True)
        suggestions = ['Review opening, story clarity, pacing and ending on your best-performing videos; analytics is not a creative-quality judgment.']
        if not snapshots:
            suggestions.insert(0, 'Connect and run workflow 12 YouTube Analytics for each destination; no channel data has been collected yet.')
        if len(results) < 3:
            suggestions.insert(0, 'Not enough matched public videos yet. Publish reviewed originals and collect more data before choosing a winning format.')
        if ranked:
            suggestions.append(f"Review '{ranked[0]['title']}' first: it has the most watched minutes among the matched videos in this report. Test a fresh story, rather than duplicating it.")
        return {'channels': channels, 'matchedPublicVideos': len(results), 'topVideosByWatchedMinutes': ranked[:10],
                'formatComparisons': comparisons, 'recommendations': suggestions, 'needsYou': reminders,
                'costs': [cost_report(j) for j in jobs[:100]],
                'rightsRegister': [{'jobId': j['id'], 'title': j['body']['title'],
                                   'ownerNote': j['body'].get('rightsNote', ''), 'verifiedByAutomation': False} for j in jobs[:100]],
                'limits': ['Rolling-window snapshots are replaced, never added together.',
                           'Analytics covers up to 200 top channel videos; status covers 50 latest managed uploads per refresh. Other videos are excluded.',
                           'Character names are listed per video; this report cannot isolate which character caused a result.',
                           'Subscriber counts may be rounded or hidden. Check YouTube Studio Earn for official YPP eligibility; these analytics are not qualified watch hours or qualified Shorts views.',
                           'No automatic publishing, paid AI calls, or monetization guarantees.']}
