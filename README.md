# WonderTales n8n

Turn your own children's stories, poems, and spoken nursery rhymes into animated videos, then upload them to YouTube as **Private**. Manage submissions, character profiles, credit caps, job status, recovery, and destination selection through n8n.

**Status:** local worker and seven n8n workflow exports are implemented. Offline tests cover recovery, duplicate protection, and real FFmpeg assembly using synthetic clips. **A real Google Flow session, Edge narration, and YouTube OAuth/upload have not been tested with an owner's accounts yet.** Do not treat this as a live-verified production service.

## What it does

- Hindi or English per submission; 9:16 or 16:9; 30, 60, 90, or 120 seconds.
- Ten editable character slots in n8n. Selects two or three per story; identical submissions keep the same pseudorandom cast to prevent paid duplicates. Change the optional variant label only for an intentional new version.
- Uses Veo 3.1 Lite, explicitly requests one output per scene, and serializes all managed Flow operations. Saved Google sessions can belong to different accounts, but only one dedicated Chrome profile is operated at a time.
- Reference-image mode reuses one supplied image per selected character. Text-only mode is available explicitly and is less consistent. Visual identity remains best-effort from the video model.
- Creates a single narrator track with timed captions before generating clips. Stops before generation if the spoken story is too long. Original model audio is removed, and final narration/captions are added consistently.
- Saves each clip, checks the final file, and claims an upload once before sending it to the selected YouTube channel. Uploads are Private, made for kids, and have subscriber notifications off.
- Stops on unverified login/balance, CAPTCHA/provider failures, uncertain billing, and uncertain uploads. Never automatically resubmits an uncertain scene or reclaims an uncertain upload.

See [all 11 improvements and their verification status](docs/FEATURES.md).

## Local setup: computer with the spare Chrome browser

This is the recommended first setup. macOS and Linux are supported; Windows can use a suitable Linux desktop environment, but its GUI/browser integration is not tested here. Keep the computer awake and Chrome open while generation is running.

1. Install Python 3.11+, Google Chrome, an [n8n-supported Node.js version](https://docs.n8n.io/hosting/installation/npm/), and FFmpeg/ffprobe with the subtitles/libass filter. Install fonts supporting Hindi, for example Noto Sans Devanagari. On Ubuntu, FFmpeg and fonts can be installed with `sudo apt-get install ffmpeg fonts-noto-core`; on macOS, a Homebrew FFmpeg build needs libass support.
2. Clone this repository, then run:

   ```bash
   bash scripts/setup.sh
   ```

   This installs a dedicated Python environment, pinned gflow-cli, online TTS support, and a local n8n installation. It does not sign into accounts or generate videos.

3. Sign into the dedicated Google account yourself:

   ```bash
   bash scripts/login.sh wondertales
   ```

   Stop the local worker before logging in; the login helper shares its process lock. The named profile is separate from your normal Chrome profile. Do not run other gflow processes against it during a job.

4. Start the worker in one terminal, and n8n in another:

   ```bash
   bash scripts/start.sh
   ```

   ```bash
   bash scripts/start-n8n.sh
   ```

5. Open `http://localhost:5678`, create your local n8n owner login, and import the JSON files under `n8n/workflows/`.
6. Configure the local header credential, character registry, credit settings, and YouTube destination as described below. Run Setup Diagnostics and Preflight before enabling private uploads.

## One-time n8n connections

**Local worker credential:** create an n8n **Header Auth** credential named `WonderTales Local Worker`. Header name: `X-WonderTales-Key`. Copy the value from `~/.local/share/wondertales/api-token` on your own computer into the credential. Select it on every HTTP Request node that calls `127.0.0.1:8099`. Never paste the token into workflow parameters, GitHub, a form, or a shared screenshot.

**Characters:** in `01-story-intake`, open the visible `Character Registry` Edit Fields node. Each of ten slots has a name, face description, body/clothing description, and optional local reference image path. Fill at least two slots. For reference-image mode, copy the images into the worker's `imports` directory and enter their full local paths. All selected characters need an image. Character reference paths point to the worker computer, not EC2.

**Credit settings:** in the visible `Credit Settings` node, enter the current per-clip cost shown in your Flow account and your maximum credits per job. These values deliberately have no account-specific defaults in this public repository. The server calculates the clip count and estimate itself, checks the cap, and checks the current Flow balance before each new scene. These are estimates based on your configured rate, not a binding Google price quote. If Google's balance API cannot read your account, the job stops rather than spending blindly. Longer videos use multiple generations. No unlimited generation is promised.

**YouTube:** create your own Google OAuth client, enable YouTube Data API v3, and create a YouTube OAuth2 credential in n8n. Follow [n8n's Google credential setup](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-single-service/) and use the exact callback URL n8n displays. Connect the same credential on BOTH `Verify Connected YouTube Account` and `Upload Private to YouTube`. Set the destination alias and actual expected channel ID in `YouTube Destination (configure)`. Keep the upload workflow inactive until these match. No password or OAuth token belongs in this repository.

**Preflight:** copy the configured registry and credit fields into `02-preflight`, select the local header credential, and submit its form. It makes read-only Flow checks and submits no video generations. A successful preflight does not establish that video generation, reference binding, narration quality, or YouTube upload work on your account. The first complete live video remains a separate test.

## All controls in n8n

| Workflow | Purpose |
| --- | --- |
| 01 Story Intake | Story, language, format, duration, account aliases, cast, credit cap; queues a video job |
| 02 Preflight | Check references, account/balance access, and estimated credits without generating video |
| 03 Job Status | Enter a job ID, or leave blank to see recent jobs, progress, errors, and private YouTube links |
| 04 Job Recovery | Resume safe steps, attach a recovered scene clip, or record the ID of an already-uploaded YouTube video |
| 05 Private YouTube Upload | Once enabled, checks for one ready job each minute and uploads it privately to its configured channel |
| 06 Setup Diagnostics | Checks installed tools and configured account aliases without generating media |
| 07 Manage Account Aliases | Registers private Flow profile mappings and YouTube destination aliases without editing files |

Use the n8n execution data view to see outputs and detailed errors. These are workflow forms and execution results, not a separate custom dashboard. Save the returned job ID after submission.

**Multiple accounts:** use workflow 07 to map aliases to dedicated gflow profiles and optional existing Flow project IDs. The mappings are saved in private local `~/.local/share/wondertales/settings.json`. Sign into each profile separately with `scripts/login.sh PROFILE` while the worker is stopped. Saved sessions coexist; managed browser operations remain serialized. The form chooses the alias. For each YouTube channel, register a destination alias with workflow 07, duplicate workflow 05, set its destination/expected channel ID, and connect the matching n8n OAuth credential on both Google nodes. Never make a default-channel fallback. Account mappings saved through workflow 07 apply immediately; already-submitted jobs retain their original Flow profile. Restart after manually editing the settings file.

The local worker's token, account mappings, SQLite jobs, clips, narration, captions, and browser sessions remain outside the repository. Do not export n8n credentials. Back up the private state and n8n credential encryption configuration securely if you need recovery after disk loss.

## Failures and recovery

- A completed clip is never regenerated automatically. Safe Resume reuses existing completed clips and rebuilds remaining work.
- A provider call is marked `generating` in SQLite **before** launch. If the result or download is uncertain, the scene becomes `uncertain`; a restart cannot silently charge for it again.
- If a scene is uncertain, check Flow yourself. Download the existing clip into `imports`, then use Job Recovery with its zero-based scene index and file path. Resume after recovery. A lost or unfindable billed result may require manual investigation; there is no automatic paid retry.
- If Flow proves that an uncertain scene was **never submitted**, Job Recovery has an explicit operator-only confirmation action. Wait for any in-flight operation to finish, check Flow carefully, then type `NOT_SUBMITTED` for that scene. This merely unlocks a later Safe Resume; it does not generate automatically. Never use it for a billed or still-running scene.
- A failed login or uncertain scene pauses subsequent browser jobs. Close any leftover spare Chrome window and resolve the original problem first. Resume affected jobs in n8n.
- If upload completion is uncertain, check YouTube Studio and enter the existing video ID in Job Recovery. Do not retry the YouTube upload node directly from cached n8n data: that bypasses the workflow's claim boundary. A normal full-workflow rerun cannot claim the same job twice.
- `story_too_long` requires a new submission with a shorter script or longer duration. A variant label creates an intentional new version; do not change it as a retry mechanism.
- For missing/corrupt narration, use Rebuild narration and captions in Job Recovery, then Safe Resume. Saved Flow clips remain intact.

## Using your existing EC2 for n8n

Keep the browser worker on the computer that owns the dedicated Chrome sessions. n8n may run natively on your existing EC2. From that computer, an SSH tunnel can link the loopback-only worker to EC2 without opening an internet-facing worker port:

```bash
ssh -N -L 5678:127.0.0.1:5678 -R 127.0.0.1:8099:127.0.0.1:8099 ubuntu@YOUR_EC2_HOST
```

Use your own SSH key/configuration. The workflow URLs stay `http://127.0.0.1:8099` because EC2's loopback port is forwarded to the local worker. EC2's native n8n stays bound to loopback. The tunnel and local computer must remain running. This deployment arrangement is documented but has not been tested on an owner's EC2. Docker n8n has a separate network namespace and needs additional routing; the default scripts target native n8n. This repository does not provision or start AWS resources.

## Limits and quality

- [gflow-cli](https://github.com/ffroliva/gflow-cli) is an unofficial, reverse-engineered alpha. Google can change the UI, model controls, or account access. A dedicated browser reduces exposure; it does not eliminate session theft or account-enforcement risk. The worker does not implement CAPTCHA solving, stealth patches, proxy rotation, or a public Flow API.
- [edge-tts](https://github.com/rany2/edge-tts) uses Microsoft's online speech service without a paid API key. Submitted story text is sent to that service. Availability, voice quality, and continued free access are not guaranteed. The default output is **spoken narration, not sung rhymes**. This version uses one narrator voice per language, rather than separate voices for each character.
- The scene planner splits your supplied script in order without a paid writing model. It does not invent a sophisticated screenplay, guarantee virality, or semantically review the story. Use explicit visual descriptions in your script for better scenes, and review the private result.
- Automated checks cover files, decode errors, dimensions, duration, audio presence/level, and captions. They do not guarantee character fidelity, perfect Hindi pronunciation, readable font shaping on every computer, or absence of visual artifacts. Music is not added by default.
- The budget guard uses the configured per-clip estimate; Google ultimately controls billing. This application makes no generation retries, but cannot guarantee the behavior of the upstream CLI or Google. No paid provider fallback is enabled.

## Development checks

```bash
python3 -m unittest discover -s tests -v
node tests/check_workflows.js
```

The tests use dummy account aliases and synthetic media; they never sign in, call Google, run online TTS, or consume Flow credits. FFmpeg is required for the real media-assembly test. CI installs it and runs these checks. JSON/logic validation is not a live n8n import/execution test.
