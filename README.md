# WonderTales Agent · v2

**Your story → a scene plan → Google Flow clips → Hypit film → your review.**

A simpler replacement for the previous 21-workflow studio. Three n8n exports coordinate a local worker. The worker keeps character descriptions, optionally asks a small local Ollama model for visual direction, checks credit limits, generates scenes through your signed-in Flow browser, and uses **Hypit 0.3.1 to compose and render the picture and sound**. FFmpeg burns the planned captions and checks the final file.

**Code is implemented; your Google account, EC2 deployment and real Flow generation are not connected or live-tested.** This is not unlimited free AI video. Flow uses your account's credits. No Google generation API key or paid script-writing API is required by this integration.

## What changed

| Component | Responsibility |
| --- | --- |
| Local studio | One story form, plan review, progress, download, scene recovery and Settings |
| n8n | Story intake and queue/status reports; no AI reasoning or rendering inside n8n |
| Planner | Exact supplied narration, scene breakdown, character/style memory; optional local AI visual descriptions |
| Google Flow | Eight-second clips with requested narration, through pinned unofficial `gflow-cli` |
| Hypit | Local SVML composition, audio placement and final video rendering |
| Recovery | Durable scene checkpoints, reuse completed clips, explicit recovery after uncertain generation |

The v1 editor, VoiceStudio, MoneyPrinterTurbo, analytics and YouTube upload workflows have been removed from the current version. **There is no automatic upload or publishing in v2.** Prior code remains in Git history. Private v1 data is not migrated or deleted; v2 uses a separate state directory.

## 1. Prepare your computer

Use an **Ubuntu desktop with Google Chrome**, Python 3.11+, Node.js 24, FFmpeg/ffprobe with libass, and Noto fonts. A headless EC2 shell does not provide the interactive Google login session. n8n may run on your existing EC2; the Flow worker needs a usable graphical browser machine. Windows and macOS have not been tested.

On Ubuntu, with Node 24 and Google Chrome already installed:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv ffmpeg fonts-noto-core
cd ~/wondertales-n8n
bash scripts/setup.sh
bash scripts/prepare-renderer.sh
bash scripts/login.sh
```

The setup script installs the Python Flow CLI and the lockfile-selected Hypit package. Renderer preparation downloads Hypit's local rendering browser when needed, **not an AI video model**. The login script opens a dedicated Flow Chrome profile; sign in yourself and finish any verification. It does not generate a video. Profile default: `wondertales`.

Stop any v1 worker and **deactivate its scheduled generation/upload workflows before updating**. Do not run two workers against the same Google profile. Back up old private state and n8n credentials first. If you already run n8n, keep that installation; no replacement n8n server is required.

For a fresh clone:

```bash
git clone https://github.com/Vishnu063/wondertales-n8n.git
cd wondertales-n8n
```

For an existing clean checkout, use `git pull --ff-only` before the setup commands. Preserve local changes first. Missing `venv` support requires the package matching your Python version.

## 2. Open the studio

```bash
bash scripts/start.sh
```

Open **http://127.0.0.1:8099** on the worker computer. The terminal prints the private token-file location. Read that file and paste the token into **Connect your local worker**. Default:

```bash
cat ~/.local/share/wondertales-v2/api-token
```

The token stays in the current browser tab's session storage. Keep it out of Git, screenshots and shared workflow exports. The worker only binds to loopback. Keep its terminal open while producing videos; `Ctrl+C` waits for the active scene/render to finish. A forced kill can leave an uncertain provider submission.

In **Settings**:

1. Set the Flow profile and a model ID supported by the installed gflow CLI/account. `veo-lite` is a configurable starter, not a promise of availability.
2. Check Flow's actual displayed rate. Enter **credits per eight-second clip** and a **daily credit cap**. Both start at zero, so generation is blocked until configured.
3. Save up to ten characters as `[{"name":"Milo","description":"A small orange fox wearing a blue scarf"}]`. Choose up to three per story.
4. Choose Templates for lowest memory, or Ollama for AI visual planning. Settings apply to **new** plans. Each job retains its original account, model, price, cast and style.

Write the spoken story in Hindi or English. Choose vertical or landscape and 16, 32, 64 or 120 seconds. The API also accepts other multiples of eight, from 8 to 120. Longer videos require more clips. The planner rejects narration that exceeds a conservative speech budget instead of silently truncating it.

Click **Create scene plan**, review its scenes and estimated credits, then **Approve & create video**. Once approved, the local worker completes generation and assembly automatically while tools and login remain available. If a step needs you, the status explains why. Download the finished MP4 and watch/listen before sharing it.

### Optional small local AI

Install [Ollama](https://docs.ollama.com/quickstart) separately and run it on the worker computer. Then:

```bash
ollama pull qwen2.5:1.5b
```

Select **Local AI** in Settings. The default model is only a starting choice; performance depends on RAM, CPU and competing processes. No GPU is required by our planner API, but low-memory machines can be slow. A 4K context and 60-second keep-alive limit retained model memory. Hypit uses one rendering browser at a time.

The model improves visual descriptions, while the supplied script remains unchanged. If Ollama is missing or returns invalid JSON, the plan is explicitly labelled **template fallback**. This is not silent AI success. Only a localhost Ollama endpoint is accepted; no external AI account is configured. A model can still produce poor visual direction: review it before spending credits.

## 3. Connect your existing n8n

Import these **inactive** exports from `n8n/workflows`:

| Export | Purpose |
| --- | --- |
| `01-story-plan.json` | Story form → save plan; no credit approval/generation |
| `02-job-status.json` | Manual progress, completed jobs and recovery guidance |
| `03-queue-monitor.json` | Hourly report of the already-approved queue |

For each HTTP Request node, select a **Header Auth** credential:

- Header name: `X-Wondertales-Token`
- Header value: the private v2 `api-token` file's contents

Default worker URL: `http://127.0.0.1:8099`. Native n8n on the same host, or Linux Docker n8n using host networking, can use it directly. A bridge-network container needs deliberate host routing; its own `127.0.0.1` is not the worker. Do not expose worker or Google browser ports publicly.

The n8n form saves a plan. **Approve spending in the local studio.** The worker polls approved jobs every two seconds; n8n's hourly monitor does not start another worker or approve credits. Character selection, recovery and revisions are available in the studio. The exports contain no embedded secrets or active schedules.

For n8n on EC2, run this from the browser computer, using your actual SSH host alias:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 5678:127.0.0.1:5678 \
  -R 127.0.0.1:8099:127.0.0.1:8099 ubuntu@YOUR_EC2_HOST
```

Then open local port 5678 for EC2 n8n. Keep the tunnel and worker running. This setup assumes native or host-network n8n on EC2; it has not been tested against your instance.

## Recovery and revisions

- **Known completed clip:** reused on Safe resume; it is never regenerated just because rendering failed.
- **Submission timeout/unknown response:** the scene is marked uncertain and automatic generation stops. Check Flow for the existing result. Download it into `~/.local/share/wondertales-v2/imports`, use **Recover an existing clip**, then **Safe resume**.
- **Confirmed no clip:** do not reset the job or blindly retry generation. v2 intentionally has no one-click uncertain-scene resubmission. Reconcile your Flow history and budget first; a fresh production is a separate decision.
- **Change one scene:** on a completed video, choose its scene number and new visual direction. A new plan reuses the other clips and shows the extra estimated cost. Review and approve it separately. The spoken script remains the same.
- **Hypit interruption:** the Build ID is saved and Safe resume reattaches it. Local rendering failure may need renderer repair and the explicit retry endpoint described in the API guide; never clear paid scene checkpoints.
- **Low balance/cap:** no next scene is submitted. A queued or failed job does not automatically obtain a higher budget. Increase the daily cap only intentionally, then Safe resume. Job caps cannot be increased after approval in this version.

Daily limits use **Asia/Kolkata** and count reservations before each submission, including uncertain attempts. These are conservative estimates, **not an actual Google billing ledger**. Entering the wrong per-clip rate can invalidate your estimates; Flow remains the authority. No provider/account switching or automatic paid retry is configured.

## What the checks establish

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_workflows.py
node tests/check_workflows.js
for script in scripts/*.sh; do bash -n "$script"; done
```

Offline tests cover credit boundaries, duplicate approval/claim prevention, restart uncertainty, daily caps, planner fallback, character snapshots, path containment, revision reuse and real synthetic-video decoding. They use no Google generation, online TTS or YouTube upload. CI runs them automatically.

Hypit source uses its actual `check`, `plan`, `build`, `status` and `get` commands. Only local media/rendering endpoints are configured; there is no hosted generation credential in Hypit. See [verification notes](docs/VERIFICATION.md) for exactly what was exercised.

**Remaining limits:** Flow automation is unofficial and can break when Google changes its UI. Login, CAPTCHA and account restrictions may require you. Native Flow narration may vary in voice, pronunciation or accuracy; an audio stream does not prove correct speech. Caption timing is per scene, not word-level ASR. Identity descriptions are not reference-image conditioning. Video checks cover stream presence, duration, aspect, resolution and decoding, not semantic quality. Real n8n import/form execution, Flow generation and first complete owner-account video remain live validation steps. No scheduled story invention, notifications to external accounts, YouTube upload, monetization promise or unlimited-generation claim is included.

Private state: `~/.local/share/wondertales-v2`, or a consistently set absolute `WONDERTALES_HOME`. Back up the whole folder while the worker is stopped. Browser profiles and n8n data need their own private backups. Never commit state, cookies or tokens.

Further detail: [API & architecture](docs/API.md).
