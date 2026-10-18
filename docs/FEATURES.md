# The 11 improvements

“Implemented” below means code and offline tests are present. It does not mean an owner's accounts have been connected or the integration has been proved live.

| # | Improvement | Implementation | Verification / remaining work |
| --- | --- | --- | --- |
| 1 | Credit protection | Configured cost estimate, server-calculated scene count, per-job cap, current balance check, explicit model/count, identical-job deduplication | Offline failures/caps tested; account balance and displayed Google pricing need live confirmation |
| 2 | Resume failed jobs | SQLite checkpoints, clip reuse, safe-stage resume, explicit recovery of uncertain scenes | Restart, missing-reference, uncertain-scene, and clip-reuse tests pass |
| 3 | Consistent characters | Ten editable profiles, stable two/three-character casting, shared reference images, fixed descriptions, one narrator voice per language | Casting tested; actual reference fidelity, voices, and Hindi output require owner review |
| 4 | Account selection | Account-management form, private local profile allowlist, one serialized browser runner, per-channel OAuth workflows, channel-ID guard | Offline routing/claim tests pass; multiple signed-in accounts not live-tested |
| 5 | Clear n8n status | Separate status/recovery/setup forms/workflows, progress, errors, media report, private YouTube link | Worker API tested; actual n8n import/activation and UI experience need live testing |
| 6 | Video quality checks | Narration fit before paid clips, scene completeness, aspect/resolution/duration checks, burned timed captions, audio level, complete decode | Synthetic FFmpeg end-to-end passes; semantic/visual quality and Hindi font shaping still need review |
| 7 | Simple setup | Setup/start/login helpers, local tool diagnostics, loopback-only service, protected token, local/EC2 instructions | Scripts checked; clean install, Node compatibility, and owner's EC2 tunnel not live-tested |
| 8 | Children's settings | Private upload, selfDeclaredMadeForKids=true, no subscriber notifications, no automatic public publication | Workflow fields verified against upstream n8n node source; no real YouTube upload yet |
| 9 | Actual Flow connection check | Read-only n8n preflight plus setup diagnostics, before a paid end-to-end test | **Pending owner's spare Chrome sign-in. No live Flow test has been performed.** |
| 10 | Stop on login/CAPTCHA errors | Fail closed on unverifiable login/balance; uncertain generation stops the queue; no automated challenge solving or paid retries | Failed-login/uncertain-job tests pass; provider-specific live errors need testing |
| 11 | Preserve work / avoid duplicates | Durable scene records, billing boundary before launch, saved files, atomic upload claim, uncertain-upload reconciliation | Concurrent-claim, restart, deduplication, and repeated-assembly tests pass |

## Live acceptance checklist

1. Install the tools, import the workflows, and select the local header credential.
2. Sign into one dedicated Chrome profile; run Setup Diagnostics and the zero-video-credit Preflight.
3. Fill character definitions/references and verify the Flow model, per-clip estimate, and cap.
4. Submit one short story, check actual billing and saved scenes, and inspect narration/captions.
5. Connect one YouTube OAuth credential, set its expected channel ID, and enable its private-upload workflow.
6. Confirm the real uploaded video is Private and made for kids; inspect it in YouTube Studio.
7. Test a safe assembly resume without making another Flow generation. Configure further accounts/channels only after the first complete run works.

Do not claim the project is production-ready until these owner-account checks have passed. No additional questions are required to finish the code; account sign-in and real output review require the owner.


## Added queue and stress-reduction controls

- **Story bank:** single submissions and up to 30-story batches wait durably; batch validation finishes before any rows are inserted.
- **Rule-based queue manager:** one managed job per local calendar day, default Asia/Kolkata; durable daily reservations, no catch-up bursts, no paid AI dependency.
- **Automatic waiting:** insufficient-credit jobs get a new balance check after at least one hour; login, CAPTCHA, and uncertain billing still need manual resolution.
- **Needs You:** each blocking state has a clear next action in job status and the daily summary.
- **Daily summary:** on-demand and scheduled at 8 PM in n8n; completed, uploaded, waiting, and failure counts. No messages are sent to anyone.
- **Pause/resume everything:** durable global pause holds new scenes and upload claims, preserving completed clips and allowing an in-flight operation to finish. All resumes still obey the daily queue.
- **Archive:** stopped stories can be archived without deleting paid clips/history; uncertain uploads must be reconciled first.

The added workflows are 08 Story Bank, 09 Daily Queue Manager, 10 Queue Controls, and 11 Daily Summary. All exports remain inactive by default. Enable 09 for automatic dispatch; the worker alone does not release new jobs. Owner-account live validation is still pending.

## Optional editing and growth additions

- Optional MoneyPrinterTurbo local rendering with pinned source, separate environment, explicit local assets, clean/kids captions and optional licensed background music. No extra provider/browser pipeline.
- Pre-generation text-similarity check, explicit intentional variants, learning-goal and rights-note fields.
- Credit estimates and saved-clip counts in Job Status; figures are labelled as estimates rather than actual bills.
- Daily read-only YouTube Analytics snapshots with explicit channel/destination checks, window replacement, stale-data detection and public-video matching.
- Weekly rule-based performance and publication reminders, with owner rights notes and sample-size labels. No paid AI or outbound messaging.
- Owner-text title suggestions and three saved video-frame candidates, previewable through n8n.

See [setup, limitations and first live run](EDITOR_AND_GROWTH.md). Offline fixtures test contracts, failure recovery, FFmpeg preparation and workflow JavaScript. Actual upstream rendering, OAuth APIs and imported n8n execution still require live owner-account validation.

## Storyboard and scene-editing additions

- Explicit scene plans with actions/settings/cast, scene-aligned narration/captions, and voice-length checks before new Flow spending.
- Shared immutable character library versions, continuity notes, reference hashes and per-job reference snapshots; legacy local registries remain available.
- Owner audio/song plus matching SRT input, without paid transcription or song-generation services.
- Explicit one-scene revision requests: preview additional credits, type confirmation, reuse other clips, preserve originals and deduplicate retried requests.
- Public-video retention analysis, one video per run, account guards, rolling-window snapshots and labelled intervals to inspect; no automatic creative changes.

Workflows 16–18 are inactive until configured. See the [storyboard/revision guide](STORYBOARD_AND_REVISIONS.md) for operation and live-test limitations.
