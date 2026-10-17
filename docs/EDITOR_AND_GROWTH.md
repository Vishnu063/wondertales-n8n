# Editor and growth automation setup

These additions support an original children's channel while controlling production costs. They do not determine YouTube Partner Program eligibility or replace your creative review. Uploads stay **Private** until you choose to publish in YouTube Studio. No messages are sent to other people.

## 1. Optional MoneyPrinterTurbo editing

The normal installation already uses FFmpeg. To enable the optional editor, run this from the checkout **on the computer running the worker**:

```bash
bash scripts/setup-mpt.sh
```

This installs the official [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) package (`mpt`, version 1.3.8) at inspected source commit `9e7d8b7efa6b912058156943906542b53b945f0a` into `.mpt-venv`. MoneyPrinterTurbo is MIT-licensed; its upstream dependencies retain their own licences. The source is pinned because this adapter calls its internal local renderer, which can change between versions. Do not upgrade it without rechecking the adapter.

The optional full package is significantly larger than our standard worker. It installs upstream dependencies even though this adapter only uses the local renderer. No GPU or paid provider key is required for this editing path, but rendering uses CPU, disk and memory. Prefer the default built-in editor if your machine struggles. A 1080-pixel canvas does not restore detail missing from original clips.

On Linux install `ffmpeg` and `fonts-noto-core`. The editor requires Pillow RAQM support for Hindi shaping. Setup Diagnostics tests imports, the source revision and shaping support. On other systems, or to choose another font, set private `settings.json` entries such as:

```json
{"mptFonts":{"English":"/full/path/to/NotoSans-Regular.ttf","Hindi":"/full/path/to/NotoSansDevanagari-Regular.ttf"}}
```

Merge these keys with the existing settings; do not replace account mappings. Restart the worker after manual settings edits. An alternative isolated interpreter can be set with `mptPython` by the machine owner; it is not accepted from story forms.

In workflows 01, 02, 08 and 14:

- Select **MoneyPrinterTurbo** as Editor. Blank defaults to built-in FFmpeg.
- Choose `clean` or `kids` captions. Both use timed sentence captions, without animation. Preview Hindi shaping on the first live result.
- Optionally supply the full path of your licensed music file inside the worker's `imports` folder. The background level is 0.12; the API accepts values greater than 0 and at most 0.3. The form intentionally keeps this control simple.
- Add a learning goal and rights/licence notes when relevant. These are owner records, not automated clearance.
- Run workflow 02 Preflight before the first paid generation. Missing editor/font/music stops before new Flow submissions.

The sequence is: existing ordered Flow clips → local FFmpeg preparation → MoneyPrinterTurbo captions/music render → common audio/video/decode checks → Private upload. Source clip audio is removed, and our existing narration/SRT are reused. Only `generate_video` is called; upstream script writing, stock downloads, voice generation and publishing are not invoked. The render process receives a private `MPT_HOME`, a minimal environment without provider keys/proxies, and blocked Python socket connections. It starts no web server or browser.

If editing fails or times out, the job stops with instructions. No other video provider is tried. Safe Resume reuses completed clips; if every scene is complete, it performs no new Flow generation. If earlier scene generation was incomplete, normal balance/cap checks still apply before those pending scenes. Requested music failures are reported rather than silently treated as success.

## 2. Free story checks and production records

Workflow **14 Story Review** performs a local text-similarity check and displays missing learning-goal/rights-note reminders. It does not open Chrome, call a language model, save a new job or spend Flow credits. It cannot judge whether a story is engaging, safe, original in meaning, correctly licensed or suitable for monetization.

Before production, the worker checks similarity against earlier non-archived jobs. A normalized text match or similarity of at least 0.92 stops a repeated story before new clips, unless you supplied an explicit **Variant label** for an intentional version. A legitimate translation or substantial rewrite may not match; this is not a copyright detector. For a stopped duplicate, archive the job and submit a different story, or use a deliberate Variant label. Existing completed clips remain saved.

Use your own characters or characters you have permission to use. Keep story, image, voice and music rights information in **Rights / licence notes**. Workflow 13 displays these notes as an owner-maintained register. It does not certify them. Form guidance suggests an engaging opening, a clear problem and a satisfying ending; you still supply the story.

Job Status includes submitted/recovered scene counts, uncertain scenes, reusable clips and credit estimates at your configured rate. These are **not actual Google billing records**. Recovered clips may have been generated elsewhere. Different jobs may use different configured rates; review individual entries rather than treating a sum as an account balance.

## 3. Connect YouTube Analytics once per channel

You do not need a paid AI subscription for these reports. Google APIs use OAuth and quotas; Google OAuth client setup is still required. Keep credentials in n8n, never in exported workflows, forms or GitHub.

1. Enable **YouTube Analytics API** alongside **YouTube Data API v3** in your Google Cloud project.
2. Import **12 YouTube Analytics**. In **Analytics Destination (configure)** set its private destination alias and actual expected YouTube channel ID. Use a distinct alias for each channel.
3. On **Verify Analytics Channel** and **Read Publication Status**, select the matching existing **YouTube OAuth2** credential.
4. On **Read YouTube Analytics (read-only OAuth)**, create a generic **OAuth2 API** credential with Authorization Code grant, authorization URL `https://accounts.google.com/o/oauth2/v2/auth`, token URL `https://oauth2.googleapis.com/token`, and scope `https://www.googleapis.com/auth/yt-analytics.readonly`. Use your Google OAuth client ID/secret, register the exact n8n callback URL, and use Google's offline-access authorization parameters when needed. Follow [n8n Google OAuth setup](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-generic/) and [Google Analytics authorization](https://developers.google.com/youtube/analytics/guides/authorization).
5. Sign into the account that owns the configured channel. Analytics explicitly requests `channel==EXPECTED_CHANNEL_ID`; the Data API nodes also verify channel ownership/identity. Mismatches stop the workflow; there is no default-account fallback.
6. Select your **WonderTales Local Worker** Header Auth credential on both local API nodes. Do not select that credential on Google nodes.
7. Run workflow 12 manually once. Check the saved snapshot and only then activate the daily 9 AM Asia/Kolkata schedule. For another channel, duplicate it and configure separate aliases/credentials.

No revenue or monetary scope is requested, so the channel need not already be monetized to collect ordinary analytics. An empty/lagged report is valid; permission/API errors fail without overwriting the previous snapshot. An older report cannot replace a newer window. The destination alias is pinned to its first saved analytics channel; create a new alias if switching to a different channel.

Collection uses a rolling 28-day window ending two days before execution to allow for reporting delay. It retrieves up to 200 top channel videos by watched minutes and checks publication status for the latest 50 managed uploads per destination. It stores one normalized snapshot per destination in private SQLite state, replacing the prior snapshot instead of adding overlapping windows. Videos outside this coverage are excluded, not treated as zero views. The 50-video status request and Analytics requests use Google API quota. OAuth tokens can expire or require reconnection.

## 4. Weekly improvement report

Import **13 Weekly Growth Review** and select the worker Header Auth credential. Run **Review Performance Now** for an immediate report; activate it for Monday 10 AM Asia/Kolkata. It reads saved snapshots and performs no paid AI calls. Results stay in n8n execution output; it sends no email or chat messages.

The report includes:

- Fresh, matched public videos ranked by watched minutes, with average view percentage and subscribers gained.
- Comparisons separated by channel, language, format and target duration. Each includes a sample-size label; the rules are exploratory, not a statistical test.
- Character names and learning goals on each matched video. It does not infer that a particular character caused performance.
- A suggestion to review the strongest measured video's storytelling and test a fresh story.
- Publication reminders when a recent API response confirms a video is still private; otherwise it says status is unknown/stale.
- Production credit estimates, reusable clips and owner rights notes for the latest 100 jobs.

Snapshots older than three days, or reporting windows ending more than seven days ago, are marked stale and excluded from performance rankings. Subscriber counts may be rounded or hidden. API watch time and total views are **not** an official calculation of YPP qualified watch hours or qualified Shorts views. Check YouTube Studio **Earn** for official eligibility and review current [YPP requirements](https://support.google.com/youtube/answer/72851).

No automatic creative rewrites, public publishing or viral predictions are included. Your story submissions and publishing decision remain under your control. For children's videos, review YouTube's [monetization policies](https://support.google.com/youtube/answer/1311392) and [made-for-kids feature restrictions](https://support.google.com/youtube/answer/9527654).

## 5. Title and thumbnail preparation

After successful assembly, Job Status shows your original title plus an optional title using your supplied learning goal. These are simple owner-text suggestions, not generated SEO claims; no title is changed on YouTube automatically.

The worker extracts three JPEG frame candidates from 20%, 50% and 80% of the video. Workflow **15 Thumbnail Preview** downloads the selected frame into n8n binary execution data. Choose a suitable clear frame yourself. Extraction is best-effort; a missing candidate does not waste completed video generation. No thumbnail is uploaded automatically, and Shorts thumbnail selection depends on YouTube's supported app controls.

## Verification and first live run

Offline checks cover validation, authentication, duplicate protection, account/destination isolation, snapshot replacement, stale-data exclusions, no-network environment settings, editor contract/failure behavior, and real FFmpeg preparation plus built-in assembly/thumbnail extraction using synthetic media. The actual upstream MoneyPrinterTurbo render, imported n8n runtime, authenticated Flow generation, online narration, YouTube Analytics and private upload remain **pending owner installation and account sign-in**.

On an existing installation: update the checkout, restart the worker, import the new/updated workflows, restore your configured character/credit nodes and credential selections, then run Diagnostics and Preflight. Reimports can create duplicate n8n workflows; keep the previous schedules inactive and activate only one configured copy. Run the first real video privately and inspect its voice, captions, character consistency and music before publishing.

All scheduled exports start inactive. Repository completion is not live EC2 deployment: the worker/n8n/tunnel must actually be installed and running, with the owner's credentials connected.
