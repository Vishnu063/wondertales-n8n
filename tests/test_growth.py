import copy
from datetime import date, timedelta
from pathlib import Path
import tempfile
import time
import unittest

from wondertales.core import Store, validate
from wondertales.growth import Growth, cost_report, story_check
from test_core import body, settings

CHANNEL = 'UC' + 'a'*22
VIDEO = 'abcdefghijk'


def snapshot():
    end = date.today()-timedelta(days=2)
    return {'destination': 'channel-main', 'channelId': CHANNEL, 'subscriberCount': 42,
            'startDate': (end-timedelta(days=27)).isoformat(), 'endDate': end.isoformat(),
            'videos': [{'id': VIDEO, 'channelId': CHANNEL, 'privacyStatus': 'public'}],
            'rows': [{'video': VIDEO, 'views': 100, 'estimatedMinutesWatched': 25,
                      'averageViewPercentage': 65, 'subscribersGained': 2}]}


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.config = settings(self.root); self.store = Store(self.root/'jobs.db')
        self.growth = Growth(self.store, self.config)
    def tearDown(self):
        self.tmp.cleanup()
    def job(self):
        job, _ = self.store.submit(validate(body(), self.config))
        self.store.update(job['id'], 'ready')
        claim = self.store.claim_upload(job['id'], 'channel-main')
        self.store.complete_upload(job['id'], claim, VIDEO)
        return self.store.get(job['id'])
    def test_snapshots_replace_instead_of_double_counting(self):
        self.job()
        self.growth.save(snapshot()); self.growth.save(snapshot())
        report = self.growth.report()
        self.assertEqual(report['matchedPublicVideos'], 1)
        self.assertEqual(report['topVideosByWatchedMinutes'][0]['views'], 100)
        self.assertEqual(report['formatComparisons'][0]['evidence'], 'small sample; keep testing')
    def test_wrong_channel_metrics_and_destinations_fail_without_changing_snapshot(self):
        self.growth.save(snapshot())
        for mutate in (lambda b: b.update(channelId='UC'+'b'*22),
                       lambda b: b.update(destination='wrong'),
                       lambda b: b['rows'][0].update(views=float('nan')),
                       lambda b: b['videos'][0].update(channelId='UC'+'c'*22)):
            b = snapshot(); mutate(b)
            with self.assertRaises(ValueError): self.growth.save(b)
        self.assertEqual(self.growth.report()['channels'][0]['channelId'], CHANNEL)
    def test_private_unknown_and_stale_videos_are_not_performance_winners(self):
        self.job()
        b = snapshot(); b['videos'][0]['privacyStatus'] = 'private'
        self.growth.save(b)
        report = self.growth.report()
        self.assertEqual(report['matchedPublicVideos'], 0)
        self.assertIn('Review in YouTube Studio', report['needsYou'][0]['action'])
        b['videos'] = []; self.growth.save(b)
        self.assertEqual(self.growth.report()['matchedPublicVideos'], 0)
        self.growth.save(snapshot())
        report = self.growth.report(now=time.time()+4*86400)
        self.assertEqual(report['matchedPublicVideos'], 0)
        self.assertTrue(report['channels'][0]['stale'])
    def test_channel_identity_and_destination_both_match_before_joining(self):
        self.job(); self.config['youtubeDestinations'].append('channel-other')
        b = snapshot(); b['destination'] = 'channel-other'; self.growth.save(b)
        self.assertEqual(self.growth.report()['matchedPublicVideos'], 0)
    def test_older_report_cannot_replace_newer(self):
        self.growth.save(snapshot()); b = snapshot()
        b['endDate'] = (date.fromisoformat(b['endDate'])-timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError): self.growth.save(b)
    def test_duplicate_story_detection_ignores_title_and_whitespace(self):
        first, _ = self.store.submit(validate(body(), self.config))
        b = body(); b.update(title='Different title', story='  Two friends help a tiny bird.  ')
        check = story_check(b, self.store.list())
        self.assertEqual(check['similarJobs'][0]['jobId'], first['id'])
        self.assertTrue(check['warnings'])
        b['story'] = 'A moon explorer fixes her spaceship and learns to share water.'
        self.assertFalse(story_check(b, self.store.list())['similarJobs'])
    def test_story_check_excludes_self_and_future_queue_entries(self):
        first, _ = self.store.submit(validate(body(), self.config))
        b = body(); b['title'] = 'Later story'
        second, _ = self.store.submit(validate(b, self.config))
        self.assertFalse(story_check(first['body'], self.store.list(), first['id'])['similarJobs'])
        self.assertTrue(story_check(second['body'], self.store.list(), second['id'])['similarJobs'])
    def test_credit_report_labels_uncertainty_without_claiming_actual_billing(self):
        job, _ = self.store.submit(validate(body(), self.config))
        self.store.scene(job['id'], 0, 'uncertain')
        self.store.scene(job['id'], 1, 'done', self.root/'saved.mp4')
        report = cost_report(self.store.get(job['id']))
        self.assertEqual(report['uncertainScenes'], 1)
        self.assertEqual(report['reusableClips'], 1)
        self.assertEqual(report['submittedSceneCreditEstimate'], 2)
        self.assertIn('not actual', report['note'])


if __name__ == '__main__': unittest.main()
