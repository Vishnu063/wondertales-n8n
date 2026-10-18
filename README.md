# WonderTales n8n

Create animated children's stories, poems and rhymes from your own scripts, then upload them to YouTube as **Private**. Use n8n for story forms, characters, accounts, credit limits, progress, recovery and channel reports. You review the result and choose when to make it public.

**Implemented:** a local worker, 21 inactive n8n workflow exports and optional VoiceStudio/MoneyPrinterTurbo integrations. **Verified:** 81 offline tests, workflow JavaScript/structure and shell checks. Tests use synthetic media and local API fixtures, spending no Flow credits. **Pending:** installation and end-to-end testing with the owner's actual n8n, Google Flow, speech models, EC2 and YouTube accounts. This repository is not a live-deployed service.

## Contents

- [Features and costs](#features-and-costs)
- [Choose where to run it](#choose-where-to-run-it)
- [Install on your browser computer](#install-on-your-browser-computer)
- [Start n8n](#start-n8n)
- [Connect n8n, Google and YouTube](#connect-n8n-google-and-youtube)
- [All 21 workflows](#all-21-workflows)
- [Configure characters and submit a story](#configure-characters-and-submit-a-story)
- [Optional VoiceStudio audio](#optional-voicestudio-audio)
- [Optional MoneyPrinterTurbo editing](#optional-moneyprinterturbo-editing)
- [Analytics and retention](#analytics-and-retention)
- [Run n8n on EC2](#run-n8n-on-ec2)
- [Daily operation and scheduling](#daily-operation-and-scheduling)
- [Troubleshooting and recovery](#troubleshooting-and-recovery)
- [Update, stop and back up](#update-stop-and-back-up)
- [Limitations and development checks](#limitations-and-development-checks)

## Features and costs

| Capability | Included |
| --- | --- |
| Video settings | Hindi or English; 9:16 or 16:9; 30, 60, 90 or 120 seconds |
| Cast | Ten character slots; two or three selected per video; optional explicit cast |
| Continuity | Versioned character library, appearance/clothing notes, reference hashes and saved reference images |
| Storyboards | Scene actions, settings, cast and narration; speech/captions aligned to scene slots |
| Flow | Dedicated Google sessions, selectable account aliases, one managed browser operation at a time |
| Credit protection | Current-balance checks, owner-set per-clip rate/cap, saved clips, no automatic uncertain-generation retry |
| Audio | Existing Edge speech, optional local VoiceStudio, or your own audio/song plus SRT |
| Editing | Built-in FFmpeg; optional MoneyPrinterTurbo captions/background music from your licensed local files |
| Revisions | Preview the additional cost, then explicitly request one replacement scene; reuse the others |
| YouTube | Destination checks, one upload claim, Private and made-for-kids defaults; manual publishing |
| Reports | Credit estimates, story similarity, rights notes, publication reminders, analytics and retention |
| Automation | Story bank, durable daily queue, pause/resume, summaries and needs-you guidance |

| Component | Cost model |
| --- | --- |
| Google Flow | Your subscription/credits; longer videos need multiple scenes; no unlimited-generation promise |
| EC2 | Your compute, storage and transfer charges, if used |
| Self-hosted n8n | No n8n Cloud subscription required for this personal setup; its licence still applies |
| FFmpeg / optional editors | Free software; local CPU, memory and disk required |
| VoiceStudio | No paid audio provider required by our adapter; model downloads and local compute required |
| YouTube APIs | OAuth setup and API quotas; no additional paid AI model is used |

No paid script-writing AI, stock subscription, GPU rental or paid fallback provider is configured. You supply the stories. Software/model licences and permission to use voices, characters, music and images still matter. Analytics helps assess videos; it does not determine monetization approval. Use YouTube Studio **Earn** for official eligibility.

## Choose where to run it

| Service | Recommended location |
| --- | --- |
| WonderTales worker + dedicated Chrome | Your Linux/macOS computer with a graphical desktop |
| n8n | The same computer, or your existing EC2 through an SSH tunnel |
| VoiceStudio, if selected | A machine with enough resources, reachable through a worker-side loopback port |
| MoneyPrinterTurbo, if selected | The worker computer in its separate optional environment |

**Start with the worker and n8n on one computer.** After one successful private video, move n8n to EC2 if wanted. A headless EC2 shell alone does not supply the signed-in graphical Chrome session. Windows/WSL desktop/browser integration is not live-tested here.

Default endpoints:

| Endpoint | Purpose |
| --- | --- |
| `http://127.0.0.1:5678` | n8n editor/forms |
| `http://127.0.0.1:8099` | Authenticated WonderTales worker |
| `http://127.0.0.1:3900` | Optional VoiceStudio API/UI |

Use SSH forwarding for remote access; do not open these service ports to the public internet. Keep the browser computer awake, the worker running and any tunnel connected during production.

## Install on your browser computer

Run these commands on the computer that will operate the spare Chrome profiles. Commands below assume Bash and a checkout at `~/wondertales-n8n`; substitute your actual path if different.

### 1. System prerequisites

Install Python **3.11+**, Git, Google Chrome, FFmpeg/ffprobe with subtitles/libass, and Hindi-capable fonts. The native n8n route also needs Node.js/npm. Node 24 LTS falls within the range listed in [n8n's npm requirements](https://docs.n8n.io/hosting/installation/npm/); use the [official Node download/install guide](https://nodejs.org/en/download) rather than assuming your OS package is recent enough.

On Ubuntu/Debian, install the basic worker packages:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv ffmpeg fonts-noto-core
```

Install [Google Chrome](https://www.google.com/chrome/) separately and confirm it opens on the graphical desktop. If Python is newer than 3.11, its matching venv package may be needed, for example `python3.12-venv` when using Python 3.12. Optional packages may have their own Python/platform limits.

Check the tools:

```bash
python3 --version
git --version
ffmpeg -version
ffprobe -version
```

For native n8n also check:

```bash
node --version
npm --version
```

On macOS, use the official Python/Node/Chrome installers and an FFmpeg build with libass. Install Noto Sans Devanagari or another suitable Hindi font. Linux package commands above are not macOS commands.

### 2. Clone the project

```bash
cd ~
git clone https://github.com/Vishnu063/wondertales-n8n.git
cd wondertales-n8n
```

Already cloned? Use the [update instructions](#update-stop-and-back-up), not another clone into the same directory.

### 3. Install the worker and choose an n8n route

**Native n8n route:** with Node/npm installed, our existing helper installs the worker plus a local n8n runtime:

```bash
bash scripts/setup.sh
```

It creates `.venv`, installs the pinned Flow CLI and Edge speech dependency, installs Playwright Chromium, and records n8n's resolved npm version under `.runtime`. It does not sign in or generate video. Google Chrome is still needed by the login helper.

**Linux Docker n8n route / worker-only computer:** avoid installing a second n8n runtime; install just the worker:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/playwright install chromium
```

Then use [Start n8n](#start-n8n). Optional audio/editor packages are separate and are not needed for the first basic test.

### 4. Initialize private state and inspect tools

```bash
bash scripts/start.sh --doctor
```

This initializes `~/.local/share/wondertales`, including private settings, imports and a worker authentication token. It makes no Google login or generation call. Resolve missing tools before proceeding. The base setup helper's doctor can report executables absent from its PATH; this command uses the actual worker PATH.

To use another state directory, set `WONDERTALES_HOME` to an **absolute path** consistently in every worker, login, n8n and VoiceStudio terminal before running the scripts:

```bash
export WONDERTALES_HOME="$HOME/.local/share/wondertales"
```

### 5. Sign into the dedicated Google browser profile

With the worker stopped:

```bash
bash scripts/login.sh wondertales
```

Sign into your Flow account yourself in the spare Chrome profile, finish any verification, and close the login session when complete. The default local mapping is `flow-main` → Chrome profile `wondertales`. Do not run a second gflow process against that profile during a job. The login helper shares the worker's process lock, so stop the worker before subsequent sign-ins too.

### 6. Start the worker

In terminal A:

```bash
cd ~/wondertales-n8n
bash scripts/start.sh
```

Keep this terminal running. A separate terminal can check its non-sensitive health endpoint:

```bash
curl --fail http://127.0.0.1:8099/health
```

Health means the service is running, not that Flow, narration or upload has been validated.

## Start n8n

Use **one** route. Do not run native and Docker n8n on port 5678 together.

### Native route: existing helper

In terminal B:

```bash
cd ~/wondertales-n8n
bash scripts/start-n8n.sh
```

Open `http://localhost:5678` and create the n8n owner login. This script binds n8n to loopback and stores its data under the worker state directory's `n8n` subdirectory.

**Current n8n guidance:** [npm installation](https://docs.n8n.io/hosting/installation/npm/) is documented as deprecated from n8n 3.0. These repository helpers currently target native npm n8n; compatibility must be checked against the installed version. n8n recommends Docker for self-hosting. Do not assume an untested major-version upgrade is compatible with the exports.

### Linux Docker route: same host network as the worker/tunnel

Install [Docker Engine](https://docs.docker.com/engine/install/ubuntu/) if needed and confirm `docker version` works. The following Linux-only recipe uses [host networking](https://docs.docker.com/engine/network/drivers/host/), so exported workflow URLs at `127.0.0.1:8099` can reach the worker or EC2 reverse tunnel without edits:

```bash
docker volume create wondertales_n8n_data
docker run -d \
  --name wondertales-n8n \
  --restart unless-stopped \
  --network host \
  -e N8N_LISTEN_ADDRESS=127.0.0.1 \
  -e N8N_HOST=localhost \
  -e N8N_PORT=5678 \
  -e N8N_PROTOCOL=http \
  -e GENERIC_TIMEZONE=Asia/Kolkata \
  -e TZ=Asia/Kolkata \
  -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
  -v wondertales_n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n
```

Inspect/start/stop this existing container with:

```bash
docker logs --tail 100 wondertales-n8n
docker stop wondertales-n8n
docker start wondertales-n8n
```

Open `http://localhost:5678` and create the owner login. The named volume retains n8n workflows, credentials and encryption configuration across container restarts. Do not delete it during an update.

This is a documented Linux host-network recipe, not a live-tested deployment. A bridge-network container's `127.0.0.1` points to the container itself, so the default workflow URLs will not reach the host worker. Docker Desktop/macOS/Windows require a different routing arrangement; use the native route for the initial desktop test or adapt networking deliberately. See [n8n's current deployment guidance](https://docs.n8n.io/hosting/installation/docker/) before a production deployment. Record/pin your working n8n version or image digest after testing; this initial Docker command resolves the current default image.

## Connect n8n, Google and YouTube

### Import the workflows

In the n8n editor, import the JSON files from `n8n/workflows/` using its import-from-file control. All exports are **inactive** and contain no credential IDs or secrets. Reimporting may create duplicates: keep old copies/schedules inactive and activate only one configured copy of each automation.

### Worker Header Auth credential

Create a Header Auth credential named **WonderTales Local Worker**:

| Field | Value |
| --- | --- |
| Header name | `X-WonderTales-Key` |
| Header value | Value of your private worker `api-token` file |

Open the token file locally on the browser computer and copy its value into the credential. Default path: `~/.local/share/wondertales/api-token`; a custom state directory changes that path. Never paste it into a story, workflow parameter, GitHub, shared screenshot or chat.

Select this credential on **every HTTP Request node calling the WonderTales worker**, including the new shared-library, analytics, retention and VoiceStudio-control nodes. Do not select it on Google's API nodes. For EC2 n8n, enter the same local worker token because the SSH tunnel reaches that worker.

### Characters and credit settings

Run workflow **16 Character Continuity Library** with at least two complete characters. Use a version such as `v1`; each character needs name, face description and body/clothing description. References and continuity notes are optional in text mode. Save a new version when definitions change. All ten slots can remain visible, with unused slots fully blank.

Leave local registries blank in workflows 01/02/08/14 to use the shared library. A populated local registry overrides it and needs at least two complete characters. Select the worker credential on **Read Shared Character Library**.

In those workflows' **Credit Settings** nodes, enter:

- `creditCostPerClip`: the current cost shown by your Flow account for the requested model/output.
- `maxCreditsPerJob`: your own per-video cap.

There are no account-specific defaults in the public repository. Clip counts are derived from the target duration; balance/cap checks occur before new scenes. These are configured-rate estimates, not a Google billing quote. If balance cannot be verified, the worker stops instead of spending blindly.

### YouTube OAuth and destination

1. In your Google Cloud project, enable **YouTube Data API v3** and create an OAuth client/consent configuration.
2. Follow [n8n's Google OAuth instructions](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-single-service/). Register the exact callback URL n8n displays; do not guess it from an example.
3. Create/connect a **YouTube OAuth2** credential in n8n using the desired channel owner's account.
4. In workflow 05, set `destination` to your registered alias, initially `channel-main`, and `expectedChannelId` to the actual channel ID.
5. Select the matching YouTube credential on **Verify Connected YouTube Account** and **Upload Private to YouTube**. Both must match. Select worker Header Auth on its local API nodes.

If n8n is reached through SSH, keep its port-forwarded editor URL and OAuth callback URL consistent. Follow Google's consent/testing requirements for your account; OAuth tokens may expire or require reconnection. No Google password or OAuth token belongs in GitHub.

### Multiple accounts

Use workflow **07** to register another Flow alias → dedicated Chrome profile and/or YouTube destination alias. Stop the worker and sign into each browser profile separately, for example:

```bash
bash scripts/login.sh spare-two
```

Then restart the worker. Sessions can coexist, but managed browser operations are serialized. Select the desired aliases in the story form; existing jobs retain their pinned Flow profile.

For each YouTube channel, duplicate workflow 05, configure its destination/expected channel ID and connect that channel's credential on both Google nodes. Configure separate analytics/retention copies for each destination too. There is no default-channel fallback. Do not use account switching to bypass service limits or change where an existing job uploads.

### First private video

1. Run **06 Setup Diagnostics** and resolve missing tools.
2. If using VoiceStudio, configure 19, inspect 20 and listen to 21 first.
3. Run **02 Preflight** with configured credit fields and the desired settings. It performs read-only metadata/balance/reference checks, with no video generation. It does not prove real generation or upload works.
4. Submit one original story using **01 Story Intake**, initially with the built-in editor and a short target. Keep its Job ID.
5. When ready for the first real paid generation, enable **09 Daily Queue Manager** or use workflow 10 **Check queue now**. This releases eligible work through the daily limit.
6. Watch **03 Job Status**. Once ready, enable the correctly configured **05 Private YouTube Upload**.
7. Inspect the private YouTube result: story clarity, characters, narration, Hindi pronunciation/shaping, captions, music, timing and thumbnail choice. Publish yourself in Studio only when satisfied.

No separate public-publishing approval gate is implemented: the upload is automatically Private, and publication remains your manual action.

## All 21 workflows

| File | Purpose / schedule when activated |
| --- | --- |
| [01 Story Intake](n8n/workflows/01-story-intake.json) | Single story form: language, format, duration, accounts, cast, plan, audio and editor |
| [02 Preflight](n8n/workflows/02-preflight.json) | Read-only assets/provider/balance checks; no video generation |
| [03 Job Status](n8n/workflows/03-job-status.json) | One Job ID or recent jobs, progress, errors, credits and private links |
| [04 Job Recovery](n8n/workflows/04-job-recovery.json) | Safe Resume, clip recovery, upload reconciliation, narration rebuild or archive |
| [05 Private YouTube Upload](n8n/workflows/05-private-youtube-upload.json) | Checks each minute for an eligible job for one configured channel |
| [06 Setup Diagnostics](n8n/workflows/06-setup-diagnostics.json) | Base tools, optional editor and account aliases |
| [07 Account Aliases](n8n/workflows/07-account-aliases.json) | Save private browser/destination mappings |
| [08 Story Bank](n8n/workflows/08-story-bank.json) | Save up to 30 stories for later daily processing |
| [09 Daily Queue Manager](n8n/workflows/09-daily-queue-manager.json) | Checks every five minutes; one managed job/day across accounts |
| [10 Queue Controls](n8n/workflows/10-queue-controls.json) | Pause, resume, check now or summary |
| [11 Daily Summary](n8n/workflows/11-daily-summary.json) | 8 PM Asia/Kolkata, results in n8n; no outgoing messages |
| [12 YouTube Analytics](n8n/workflows/12-youtube-analytics.json) | 9 AM daily; read-only rolling-window snapshots |
| [13 Weekly Growth Review](n8n/workflows/13-weekly-growth-review.json) | Monday 10 AM or manual; performance, costs, rights notes and reminders |
| [14 Story Review](n8n/workflows/14-story-review.json) | Local text similarity and metadata reminders; no browser or paid generation |
| [15 Thumbnail Preview](n8n/workflows/15-thumbnail-preview.json) | Download one of three extracted frame candidates |
| [16 Character Library](n8n/workflows/16-character-library.json) | Save/activate immutable character definitions and continuity notes |
| [17 Scene Replacement](n8n/workflows/17-scene-replacement.json) | Preview credits, explicitly request one new clip, reuse the rest |
| [18 Retention Review](n8n/workflows/18-audience-retention.json) | Public-video review form or Monday 9:30 AM, one video per run |
| [19 VoiceStudio Settings](n8n/workflows/19-voicestudio-settings.json) | Save voice alias, language, engine, voice ID, speed and local ASR mapping |
| [20 VoiceStudio Check](n8n/workflows/20-voicestudio-check.json) | List supported engine availability, profiles and English presets |
| [21 VoiceStudio Sample](n8n/workflows/21-voicestudio-sample.json) | Generate/download an audio sample and captions; no Flow/upload |

Forms and n8n execution results are the management interface; this is not a separate custom dashboard. Keep returned job/sample IDs. Scheduled workflows only run after you configure and activate them.

## Configure characters and submit a story

The worker's default imports folder is `~/.local/share/wondertales/imports`. Put character references, your audio/SRT and licensed music there. Enter **full worker-computer paths** in forms. Paths cannot escape this folder through symlinks. On an EC2 n8n installation, these paths still refer to the browser worker computer.

For references, use PNG/JPEG/WebP. Workflow 16 records hashes; changing an image requires a new library version or restoring the original. A running job snapshots reference files for recovery. Text-only mode is explicit and generally less consistent. Actual character fidelity remains model-dependent.

### Storyboard example

Each block needs Characters, Setting, Action and Narration:

```text
Characters: A, B
Setting: A sunny garden
Action: The friends notice a bird beside a fallen nest.
Narration: Two friends discover a bird that needs help.
---
Characters: A, B
Setting: Beneath the same tree
Action: They bring a trusted adult to help the bird.
Narration: They ask an adult for help.
```

This illustrates two blocks; submit exactly **4 / 8 / 12 / 15 scenes** for **30 / 60 / 90 / 120 seconds**. Slots are eight seconds except a shorter final slot. Keep narration short enough for its slot. Storyboard narration becomes the spoken script; the main story is retained as an outline. Automatic speech timing is checked before Flow spending.

Choose two or three cast names yourself, or leave casting automatic. A storyboard's combined cast must match two or three defined characters. Individual scenes can show a subset. Use the Visual style field for a consistent job-wide look.

### Story-bank example

```text
A little star
Two friends find a fallen star and help it return home.
---
The missing kite
Two friends follow a colourful kite and help its owner.
```

Language, format, credit cap, editor and narrator settings apply to a batch. Submit Hindi/English separately. Multiple stories cannot share one custom storyboard or owner-audio file; use single-story submissions for those. Validation is all-or-nothing before batch saving.

### Your own narration/song

Choose owner audio and provide both its audio path and matching UTF-8 SRT path. Supported audio: MP3, WAV, M4A, OGG or FLAC, up to 100 MB, fitting the target duration. Captions need ordered, non-overlapping timings. No transcription or paid singing service is called on this path. With your own audio plus a storyboard, you supply timing that follows the scene boundaries.

### Replace one scene

In workflow 17, select a ready/uploaded source Job ID, a zero-based scene index, replacement directions, current per-clip rate and an additional cap. Preview the estimate first. To request the extra generation, enter a stable replacement label and type `REPLACE_ONE_SCENE`.

A separate revision queues one pending clip and reuses the others. Original files remain saved. A ready original is withheld from upload as `superseded`; an uploaded original and its YouTube ID remain unchanged. Retries with identical settings/label reuse the same revision. Changed settings need a new intentional label. Normal pause, balance and daily-limit rules apply, so a revision may wait until another day. See the [full storyboard/revision guide](docs/STORYBOARD_AND_REVISIONS.md).

## Optional VoiceStudio audio

VoiceStudio runs separately and is not needed for the basic Edge/owner-audio paths. If already installed, use its local API. Otherwise install [uv](https://docs.astral.sh/uv/getting-started/installation/) and upstream OS prerequisites, then run from this checkout:

```bash
bash scripts/setup-voicestudio.sh
```

Start it in another terminal:

```bash
cd ~/wondertales-n8n
bash scripts/start-voicestudio.sh
```

The helper uses your [VoiceStudio repository](https://github.com/Vishnu063/VoiceStudio), an inspected source commit, its lockfile and separate Python 3.12 environment. The launcher binds to loopback, defaults to CPU/KittenTTS, pins local ASR and uses a private local authentication token. It does not install its models into WonderTales's environment.

Configure workflow 19, run 20 and listen to 21 before choosing **VoiceStudio local** in stories:

| Language/use | Engine | Voice alias / ID |
| --- | --- | --- |
| First English test | `kittentts` | Alias `english-main`, preset `expr-voice-2-f` |
| Hindi / cloned narrator | `omnivoice-gguf` | Alias `hindi-main`, an existing VoiceStudio profile ID |

Default speed is 1; supported mapping range is 0.5–1.5. KittenTTS is English-only. GGUF requires a real native binary and model weights; source checkouts contain placeholders until installed/built. The full app's default workflow lists 8 GB RAM minimum/16 GB recommended, so benchmark your own machine. It does not provide an automatic singing generator or per-character acting voices in this integration.

Install a local multilingual ASR model and pin `faster-whisper` or `whisperx` with `OMNIVOICE_ASR_BACKEND`; the supplied launcher does this from your mapping. Remote/unpinned ASR and generic engine/default-voice aliases are rejected. Speech is saved before captioning, allowing caption recovery without duplicate synthesis. One voice is selected per video; use a new profile ID when changing the reference voice for queued work. See [VoiceStudio setup, licences and recovery](docs/VOICESTUDIO.md).

## Optional MoneyPrinterTurbo editing

Install on the worker computer only:

```bash
cd ~/wondertales-n8n
bash scripts/setup-mpt.sh
```

Then select **MoneyPrinterTurbo** in the story form and run Preflight. Choose clean/kids captions and optionally a licensed music file inside imports. Music is off by default. The adapter uses saved, ordered Flow clips and existing narration/SRT; it does not invoke upstream writing, stock search, speech generation or publishing. Networking is disabled in its render process.

This editor has a separate `.mpt-venv`, pinned upstream source and language-font checks. It needs substantial CPU/RAM/dependencies; use built-in FFmpeg on a smaller machine if needed. A 1080 canvas does not recover detail missing from the source clips. Failures retain paid clips for Safe Resume. See [editor setup and limitations](docs/EDITOR_AND_GROWTH.md).

## Analytics and retention

Enable **YouTube Analytics API** in the same Google project. In workflows 12 and 18, set the destination and actual expected channel ID. Use the channel's YouTube OAuth credential on Data API nodes, worker Header Auth on local nodes, and a separate generic OAuth2 credential on Analytics API nodes:

| OAuth field | Value |
| --- | --- |
| Grant | Authorization Code |
| Authorization URL | `https://accounts.google.com/o/oauth2/v2/auth` |
| Token URL | `https://oauth2.googleapis.com/token` |
| Scope | `https://www.googleapis.com/auth/yt-analytics.readonly` |
| Callback | Exact redirect URL shown by n8n, registered in Google Cloud |

Follow [n8n Google OAuth setup](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-generic/) and [Google Analytics authorization](https://developers.google.com/youtube/analytics/guides/authorization), including offline access when needed. No monetary scope or paid model is requested. Test manually before enabling schedules.

Analytics stores a rolling 28-day snapshot ending two days before collection, replacing overlapping windows rather than adding them. Coverage is up to 200 top videos and publication status for the latest 50 managed uploads. Rankings require fresh, matched public videos; stale/missing data is excluded. Subscriber counts may be rounded/hidden, and API totals are not official YPP qualifying counts.

Retention queries one public managed video per run, highlights measured intervals to inspect, and can rotate among the growth report's eligible top videos. A decrease does not prove why viewers left; rewatching can produce ratios above 1. Empty/stale data produces no recommendation. Nothing automatically rewrites, regenerates or publishes a video based on analytics.

Reports include owner rights notes, learning goals, credit estimates and publication reminders. Title suggestions use your supplied text; three thumbnail candidates are extracted at 20%, 50% and 80% of the finished video. Choose/upload a thumbnail yourself using YouTube's supported controls. Detailed guides: [growth/editor](docs/EDITOR_AND_GROWTH.md) and [retention](docs/STORYBOARD_AND_REVISIONS.md).

## Run n8n on EC2

Keep the Chrome/Flow worker on your graphical browser computer. On your existing Linux EC2, run n8n using the Linux Docker recipe above, or install only the native n8n runtime if choosing that route:

```bash
cd ~
git clone https://github.com/Vishnu063/wondertales-n8n.git
cd wondertales-n8n
npm install --prefix .runtime --save-exact n8n
bash scripts/start-n8n.sh
```

The native block requires an n8n-compatible Node/npm already installed; its deprecation/version caveat applies. Do not install or start a second n8n if one already runs on the instance. No AWS resources, security groups or charges are created by this repository itself.

On the **browser computer**, with the worker running, connect SSH. Replace the host and key path with your own values, or use an existing SSH config alias:

```bash
ssh -i "$HOME/.ssh/YOUR_EC2_KEY.pem" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -N \
  -L 5678:127.0.0.1:5678 \
  -R 127.0.0.1:8099:127.0.0.1:8099 \
  ubuntu@YOUR_EC2_HOST
```

The local `5678` forward opens EC2 n8n at `http://localhost:5678`. The reverse `8099` forward lets EC2 n8n reach the browser computer's worker through EC2 loopback. Do not run local n8n on that same forwarded port. Keep SSH running; reconnect it after interruption. The EC2 SSH server must permit forwarding.

Default workflow URLs remain unchanged for native EC2 n8n or Linux Docker **host-network** n8n. A bridge-network container requires deliberate routing changes. No public worker port or public browser session is required. This EC2/tunnel arrangement still needs a live test with your instance.

## Daily operation and scheduling

- Add stories through 01 or 08. Submissions are saved, not generated immediately.
- Keep the worker, n8n, browser computer and any tunnel running.
- Enable only configured copies of 09 and 05 for daily generation/private upload. Reports are optional.
- Use 03 for progress and 10 for pause/resume/summary. A pause survives restarts and stops new scene submissions/uploads; it does not cancel an already-running provider operation.
- Review private uploads and publish manually in YouTube Studio. Private views/watch time do not build the public qualifying totals; check current [YPP requirements](https://support.google.com/youtube/answer/72851).

There is **one managed job per Asia/Kolkata calendar day across all accounts**, including explicit scene revisions. The durable daily reservation survives restarts. Same-job safe resumes can use its slot; missed days do not trigger catch-up bursts. A failed attempt may consume the day's slot. An earlier job awaiting private upload holds new production. Completing yesterday's ready upload may reserve today's slot too.

Low credits wait at least an hour before another read-only balance check. Unknown login/balance errors, CAPTCHA, uncertain billing/uploads and other needs-you states stop automatic retries. The queue manager and recommendations are rules, not paid AI agents. Summaries stay in n8n; no email/chat messages are sent.

## Troubleshooting and recovery

| Problem | Action |
| --- | --- |
| `python3 -m venv` fails | Install the venv package matching your Python, then rerun the chosen fresh-install step |
| Unsupported Node/npm | Install a supported Node version or use the Linux Docker route |
| Worker connection refused | Start `scripts/start.sh`; check the SSH tunnel and Docker networking if applicable |
| Worker HTTP 401 | Select the correct Header Auth credential; match the current private `api-token` file |
| Google channel mismatch | Connect the correct OAuth account and expected channel ID on every relevant Google node |
| Missing character/ref | Save a valid library or local registry; use worker imports paths and matching reference hashes |
| Flow login/balance failure | Stop the worker for manual profile sign-in, check CLI compatibility, then Safe Resume |
| Low Flow credits | Wait for credits/next hourly check, or submit a shorter future job; no automatic provider switch |
| `story_too_long` | Shorten the script/scene or choose a longer duration in a new submission |
| VoiceStudio unavailable | Start the local service; check explicit TTS/profile, pinned local ASR, model and token setup |
| GGUF unavailable | Install/build its real binary and weights; the source placeholder cannot synthesize |
| MPT/font/music failure | Run Diagnostics/Preflight, repair optional dependencies/assets, then Safe Resume |
| Retention/analytics empty | Confirm public status, API/OAuth/channel setup and reporting delay; no data is not zero performance |
| Empty queue | Add stories; check that the intended queue workflow is active and global pause is off |

**Paid-generation recovery:** a scene is marked generating in SQLite before calling Flow. If acceptance/download is uncertain, it becomes uncertain. Check Flow and recover the existing clip through workflow 04; do not rerun that generation node blindly. Completed clips are never automatically regenerated. If Flow proves a scene was never submitted and nothing remains in flight, the operator can type `NOT_SUBMITTED` in recovery, then request Safe Resume. Never use that for a billed/still-running scene.

**Upload recovery:** check YouTube Studio and record the already-uploaded video ID in workflow 04. Do not retry the upload node directly from cached execution data: that bypasses the normal claim boundary. Full workflow reruns cannot normally claim an uploaded/uncertain job again.

**Narration recovery:** Safe Resume reuses cached speech, captions and clips. Rebuild Narration and Captions deliberately clears voice caches and will synthesize again. An intentional version needs a new variant label; do not change it merely to retry a failure. Archive a stopped unusable job to release human blockers while preserving its history/files.

## Update, stop and back up

### Stop safely

Use workflow 10 **Pause everything** first and let any active scene/upload finish. Then stop the worker, native n8n and optional VoiceStudio with `Ctrl+C` in their terminals. For Docker n8n:

```bash
docker stop wondertales-n8n
```

The worker waits for its active task during normal shutdown. Force-killing a process during provider submission can leave uncertain work requiring reconciliation. A spare browser profile sign-in needs the worker stopped.

### Update repository code

Back up private state, stop services, then:

```bash
cd ~/wondertales-n8n
git status --short
git pull --ff-only
```

If there are local changes, preserve/review them rather than overwriting them. If worker requirements changed, update that environment explicitly:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Restart the worker and your chosen n8n route. Reimport only the changed/new workflows, restore your credential selections and edited registry/credit nodes, and leave duplicate schedules inactive. Run Diagnostics and Preflight again. Do not rerun the full base setup as an unreviewed n8n upgrade: it resolves an npm version again. Upgrade n8n and optional apps separately after checking compatibility/release notes and preserving their data. Do not blindly downgrade an n8n database after a migration.

### Private backups

With services stopped, back up the complete worker state:

```bash
umask 077
backup_root="$HOME/wondertales-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_root"
tar -czf "$backup_root/worker-state.tgz" \
  -C "${WONDERTALES_HOME:-$HOME/.local/share/wondertales}" .
```

This includes the native n8n subdirectory if you used that script on the same host. For Docker n8n, run on the Docker host, with the same `backup_root` variable defined there:

```bash
docker run --rm \
  -v wondertales_n8n_data:/data:ro \
  -v "$backup_root":/backup \
  alpine tar -czf /backup/n8n-data.tgz -C /data .
```

Keep these archives private: state and n8n data contain credentials/encryption configuration. Back up n8n's data **and encryption key/configuration together**, including any externally supplied key. Back up gflow's actual browser/session storage separately according to its configuration; it is not necessarily under the worker state folder. Also preserve VoiceStudio's configured profiles/reference audio/settings, and any source audio/references you need. Model downloads alone are not a voice-profile backup.

Restore only while services are stopped, using the matching state directory/n8n volume and encryption configuration. Do not commit state, sessions, private archives or exported credentials to GitHub. If n8n is on EC2 and the worker elsewhere, back up both hosts.

## Limitations and development checks

- [gflow-cli](https://github.com/ffroliva/gflow-cli) is unofficial and reverse-engineered. Google changes can break login, model access, references or balance checks. Dedicated Chrome profiles reduce exposure but do not remove account/session risks. No CAPTCHA solving, stealth or proxy/account-limit bypass is included.
- Edge speech sends submitted text to Microsoft's online speech service. VoiceStudio uses local models through the configured loopback API. Default TTS is spoken narration; singing requires your supplied audio. This integration uses one narrator per video, not an acting voice per character.
- Story checks are lexical similarity, not copyright clearance or semantic quality review. Repeated templates with different words can still be low quality. Use original, understandable stories with real creative/educational value, consistent with [YouTube's children's-content principles](https://support.google.com/youtube/answer/10774223) and [monetization policies](https://support.google.com/youtube/answer/1311392).
- Checks cover files, decode errors, dimensions, duration, audio and caption timing. They cannot guarantee character fidelity, Hindi pronunciation/shaping, accurate ASR, musical quality or absence of visual artifacts. Always inspect the first private result and intentional revisions.
- Cost reports use your configured rate and labelled submission/reuse counts, not actual Google bills. The worker avoids retries of uncertain operations but cannot guarantee upstream CLI/provider billing behavior. Analytics is incomplete/lagged, and monetization is not guaranteed.
- System fonts, Chrome sessions, models/binaries and imported n8n node behavior need real-machine validation. The installation recipes and source helpers have not been executed on the owner's environment here.

Run offline checks from the checkout after installing FFmpeg and Node for the JavaScript check:

```bash
python3 -m unittest discover -s tests -v
node tests/check_workflows.js
for script in scripts/*.sh; do bash -n "$script"; done
```

These checks make no Google login, real Flow generation, online TTS or YouTube upload. Local VoiceStudio fixtures serve synthetic WAV/SRT, not real models. CI runs the checks automatically; JSON/logic validation is not an actual n8n import/execution test.

Further detail: [feature status](docs/FEATURES.md), [VoiceStudio](docs/VOICESTUDIO.md), [storyboards/revisions/retention](docs/STORYBOARD_AND_REVISIONS.md), [MoneyPrinterTurbo/analytics](docs/EDITOR_AND_GROWTH.md).
