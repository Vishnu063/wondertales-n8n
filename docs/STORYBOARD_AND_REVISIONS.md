# Storyboards, continuity, audio and scene revisions

All features use the existing private worker and n8n. They add no paid AI model. Flow generation still uses credits, and a requested scene replacement is an additional generation. All workflow exports remain inactive until configured. Your publishing decision stays in YouTube Studio.

## Shared character continuity sheet (workflow 16)

Open **Character Continuity Sheet (edit here)** in workflow 16. Enter a library version, such as `v1`, and fill between two and ten characters. Each needs a name, face description and body/clothing description. Optional fields hold a local reference image and continuity notes such as personality, movement, proportions and permanent accessories. Leave unused slots fully blank.

Select the local worker Header Auth credential on **Save Immutable Library Version**, then run the workflow. The saved version becomes active. Changing any definition requires a new version name; saving the same version with exactly the same definitions reactivates it. Existing jobs retain their saved character data and library version, rather than changing with the library.

For reference mode, put images in the worker's imports folder before saving the library. Images must be PNG, JPEG or WebP. The library records their content hashes; changing an image without a new version stops preflight. Once a job begins, reference images are copied into its private job folder and reused on resumes/revisions. Hash/version checks improve continuity but cannot guarantee the model's visual output.

In workflows 01, 02, 08 and 14, select the worker Header Auth credential on the new **Read Shared Character Library** node. Leave their local Character Registry slots blank to use the shared library. If any local name is filled, that workflow uses its local definitions instead and needs at least two complete characters. Local overrides keep older setups compatible, but are not centrally versioned.

The form can choose 2–3 names from your pool automatically, or accept **Cast names**. A storyboard uses the characters named in its scenes; their union must contain exactly two or three defined characters. An individual scene may show a subset. Only that scene's selected reference images are passed to Flow. The **Visual style** field applies consistently across the job.

## Scene-plan form format

In Story Intake, the optional **Scene plan** has one block per scene:

```text
Characters: A, B
Setting: A sunny garden
Action: A notices a bird beside a fallen nest. B points toward the tree.
Narration: Two friends discover a bird that needs help.
---
Characters: A, B
Setting: Beneath the same tree
Action: They carefully bring an adult gardener to help.
Narration: They ask a trusted adult for help.
```

This shows two blocks for illustration. Submit exactly **4 scenes for 30 seconds, 8 for 60, 12 for 90, or 15 for 120**. Every block needs Characters, Setting, Action and Narration. Use short narration: slots are eight seconds each, except the final slot may be shorter (for example six seconds in a 30-second video).

When a plan is supplied, its joined narration is the voice-over script; the main story field is saved as an outline. The worker prepares and caches speech per scene, checks each spoken segment fits its slot, pads it to that slot, then joins the audio and shifts its caption timestamps. These steps complete before any new Flow clip is requested. Too-long scene narration stops with a scene-specific message, so submit a shorter plan or a longer target duration. Safe Resume reuses completed speech files. Rebuild Narration and Captions clears those speech caches when explicitly requested on a stopped job.

Without a scene plan, the existing story segmentation and single-narrator path remain available. Free Story Review checks text similarity and metadata; it does not synthesize speech or certify that narration will fit. Preflight verifies connections/assets but does not render scene narration. Actual speech duration is checked when the queued job runs, before Flow generation.

For different custom plans or audio, use separate single-story submissions. Story Bank rejects a shared custom plan/audio when multiple stories are submitted together, preventing accidental repetition.

## Your own narration or song

Copy your audio and matching UTF-8 `.srt` file into the worker's private imports folder. Enter their full paths in **Your audio path** and **Your captions SRT path**. Both are required together. Supported audio: MP3, WAV, M4A, OGG and FLAC, up to 100 MB. The audio must have a readable audio stream and fit the selected target duration.

The worker validates numbered SRT cues with ordered, non-overlapping timestamps that fit the audio. It converts the supplied audio into the working narrator track and uses your captions; it does not call TTS or a transcription service. Existing prepared audio/captions are reused on resume and scene replacement. Your audio may include singing, but this does not provide an automatic song generator or clear music/voice rights.

With a storyboard plus owner audio, **your audio and SRT determine timing**. Per-scene TTS alignment is skipped; make your recording follow the eight-second scene boundaries yourself. The worker cannot judge whether lyrics, narration, captions and visuals match in meaning. Preview the first private result, including Hindi text shaping and pronunciation.

## Replace exactly one scene (workflow 17)

1. Copy the source Job ID and choose its zero-based scene index. The source must have every clip complete and be `ready` or `uploaded`; active or uncertain jobs must be resolved first.
2. Enter the current credits per clip shown by Flow, an additional credit cap, and clear visual replacement directions. Narration, character definitions and all other scenes stay the same.
3. Select **Preview credit estimate**. This reads saved state and shows one new clip's estimated cost; it neither generates nor queues a video.
4. To proceed, use a stable **Replacement label**, select **Request one scene replacement**, and type `REPLACE_ONE_SCENE`. Reuse the same label and identical settings when retrying the same request. Changed settings with a used label are rejected; a new intentional replacement needs a new label.

A request validates the source clips and creates a separate revision job. It copies/reuses every other clip, plus prepared narration/captions and reference snapshots. Only the chosen scene starts pending. The original files remain saved. A ready original becomes `superseded` and cannot be automatically uploaded; an already uploaded original and its YouTube ID remain unchanged. Completed originals stay previewable through their API URLs. The revised video gets its own private upload; no existing YouTube video is edited or deleted.

The revision enters the ordinary daily queue, respecting global pause, the one-job-per-day reservation, current balance and the additional cap. If the source used today's slot, the revision waits for a later eligible day. This form does not bypass the daily limit or start generation immediately. Its request label makes retries idempotent across restarts. After the revision is ready/uploaded, use its Job ID as the source for another edit.

No generation occurs before the usual persisted billing boundary. An uncertain replacement stops for reconciliation; it is never retried automatically. Missing reused clips stop before new spending. Editing or quality failures preserve the paid replacement clip as well as the originals. Job Status distinguishes clips reused from the source from new scene credit estimates. Costs remain estimates based on the rate you entered, not Google billing records.

## Audience retention review (workflow 18)

First configure and run workflow 12 Analytics for the destination. Retention snapshots bind to that verified channel. In workflow 18 set **Retention Destination (configure)** to the same destination alias and actual expected channel ID.

Connect:

- Worker Header Auth on the local growth report, managed-job, save-snapshot and updated-report HTTP nodes.
- The channel's YouTube OAuth2 credential on **Verify Retention Channel** and **Verify Video Is Public**.
- The same read-only generic OAuth2 credential used for analytics on **Read Retention (read-only OAuth)**, with `yt-analytics.readonly` scope.

Use the form with an uploaded Job ID, or leave it blank to pick one eligible public video from the growth report's top ten. Automatic selection prioritizes videos not previously checked, then those with the oldest saved retention snapshot. It operates on one video per run, limiting API calls. After manual verification, you may activate its Monday 9:30 AM Asia/Kolkata schedule; daily analytics runs at 9 AM and the weekly growth report at 10 AM. For multiple channels, duplicate and configure separately.

The workflow checks the OAuth channel, the managed destination and the video's current channel/public status. It explicitly requests one video's `elapsedVideoTimeRatio`, `audienceWatchRatio` and `relativeRetentionPerformance` for the same rolling 28-day window ending two days earlier. Google may return no retention data, especially for new videos; that produces no recommendation. Unavailable relative performance is recorded as unknown. API failures do not replace an earlier successful snapshot.

The result shows up to three measured intervals with the largest decreases in watch ratio, converted to video timestamps. These are places to inspect for pacing, unclear audio or confusing action, **not proof of why viewers left**. Watch ratios can exceed 1 due to rewatching; this is not an error or a direct count of people leaving. Sparse data is not reliable evidence of a creative cause. Stale reports (over three days since collection, or windows ending over seven days ago) produce no inspection recommendation.

Workflow 13 includes saved retention reviews. No video is automatically rewritten, regenerated, published or retitled from this data. Counts, watch time and retention do not establish YPP eligibility; use YouTube Studio Earn for that.

## Verification status

Offline tests validate plans/casting, immutable libraries/reference hashes, explicit revision requests and retries, original preservation, new-credit estimates, audio/SRT validation, real audio alignment, authenticated endpoints and retention account isolation. Synthetic-media tests exercise a full single-scene revision with a mocked Flow provider and real FFmpeg assembly. Workflow JavaScript and shell syntax are checked in CI.

Actual Flow scene generation, online Edge speech, upstream MoneyPrinterTurbo rendering, imported n8n execution and authenticated Google APIs still need the owner's live environment. No provider credits are used by these tests.
