# WonderTales Agent · v2

**Your story → a scene plan → Google Flow clips → Hypit film → your review.**

A simpler replacement for the previous 21-workflow studio. Four n8n exports coordinate a local worker and optional Private YouTube uploads. The worker keeps character descriptions, optionally asks a small local Ollama model for visual direction, checks credit limits, generates scenes through your signed-in Flow browser, and uses **Hypit 0.3.1 to compose and render the picture and sound**. FFmpeg burns the planned captions and checks the final file.

**Code is implemented; your Google account, EC2 deployment and real Flow generation are not connected or live-tested.** This is not unlimited free AI video. Flow uses your account's credits. No Google generation API key or paid script-writing API is required by this integration.

## What changed

| Component | Responsibility |
| --- | --- |
| Local studio | Story form, plan review, upload-details review, progress, download, recovery and Settings |
| n8n | Story intake and queue/status reports; no AI reasoning or rendering inside n8n |
| Planner | Exact supplied narration, scene breakdown, character/style memory; optional local AI visual descriptions |
| Google Flow | Eight-second clips with requested narration, through pinned unofficial `gflow-cli` |
| Hypit | Local SVML composition, audio placement and final video rendering |
| Recovery | Durable scene checkpoints, reuse completed clips, explicit recovery after uncertain generation |

The v1 editor, VoiceStudio, MoneyPrinterTurbo and analytics workflows have been removed from the current version. **A new Private-only upload workflow replaces the old uploader. Public publishing is not included.** Prior code remains in Git history. Private v1 data is not migrated or deleted; v2 uses a separate state directory.

## 1. Install the worker on your browser computer

**Recommended command path: Ubuntu desktop, x86_64/amd64, Python 3.11+, Node.js 24 and Google Chrome.** Run steps A–E on the computer with a graphical desktop. A plain EC2 SSH terminal cannot complete the interactive Google login. n8n itself may run on EC2 using the separate instructions below.

| Machine | Install here |
| --- | --- |
| Ubuntu desktop / browser computer | Python worker, Node/Hypit, Chrome, FFmpeg; optional Ollama |
| EC2, if used | Existing n8n or a new Docker n8n installation; SSH tunnel |

macOS/Windows installation has not been live-tested. These `apt-get`/`.deb` commands are Ubuntu-only; do not run them on a Mac. Linux ARM machines cannot use this amd64 Chrome package. Use an appropriate supported graphical browser machine rather than installing the wrong architecture.

**Updating an old installation?** Use [Update an existing checkout](#update-an-existing-checkout) below. Deactivate old generation/upload schedules and stop the old worker before updating. Preserve your private state and n8n credentials. Do not start a second worker or n8n installation alongside an existing one.

### A. Install Ubuntu tools

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 python3-venv ffmpeg fonts-noto-core
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
```

This installs Git, download certificates, Python environments, media tools and Hindi-capable fonts. If `venv` later fails, install the package matching your Python version, such as `python3.14-venv` for Python 3.14; do not blindly install a different Python version.

### B. Install Node.js 24

Skip installation if `node --version` already reports v24. Run this block in Bash. The pinned nvm installer installs Node for your user; do not use `sudo npm` for this project.

```bash
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh -o /tmp/wondertales-nvm-install.sh
bash /tmp/wondertales-nvm-install.sh
export NVM_DIR="$HOME/.nvm"
. "$NVM_DIR/nvm.sh"
nvm install 24
nvm alias default 24
nvm use 24
node --version
npm --version
```

In a new terminal, load nvm again if Node is missing: `export NVM_DIR="$HOME/.nvm"` then `. "$NVM_DIR/nvm.sh"`. Sources: [Node.js downloads](https://nodejs.org/en/download), [nvm](https://github.com/nvm-sh/nvm).

### C. Install Google Chrome (Ubuntu amd64 only)

Skip this block if Google Chrome already opens on your desktop.

```bash
test "$(dpkg --print-architecture)" = amd64
curl -fL https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb -o /tmp/wondertales-google-chrome.deb
sudo apt-get install -y /tmp/wondertales-google-chrome.deb
google-chrome --version
```

Open Chrome normally from the desktop once. Do not run Chrome as root or use a headless EC2 terminal as a substitute for the Google sign-in window. Hypit uses a separate local rendering browser prepared in step E.

### D. Clone and install the project (fresh installation)

```bash
cd ~
git clone https://github.com/Vishnu063/wondertales-n8n.git
cd ~/wondertales-n8n
bash scripts/setup.sh
```

The script creates `.venv`, installs `gflow-cli==0.85.0`, installs lockfile-selected Hypit dependencies with `npm ci`, and checks tool presence. It does not install n8n, Ollama or Google Chrome, connect accounts, or spend Flow credits. Do not clone again if this directory already contains your project.

### E. Prepare rendering and sign into Flow

```bash
cd ~/wondertales-n8n
bash scripts/prepare-renderer.sh
bash scripts/login.sh
```

Run one command at a time and resolve any error before continuing. Renderer preparation downloads Hypit's rendering browser if needed, not an AI video model. The login helper opens the dedicated `wondertales` Chrome profile; sign in yourself, finish any verification, then close the login session before starting the worker. Profile changes belong in Settings and require signing into that selected profile again.

**If the renderer download fails:** repair its network/download access and rerun `prepare-renderer.sh`. Alternatively start the studio, enter a compatible existing Chrome executable's absolute path in Settings, save, stop the worker and rerun renderer preparation. A successful tools check alone does not mean rendering or Google login is ready. The renderer download failed in this development environment, so a full rendered video remains unverified here.

## 2. Open the studio

```bash
cd ~/wondertales-n8n
bash scripts/start.sh
```

Open **http://127.0.0.1:8099** on the worker computer. The terminal prints the private token-file location. Read that file and paste the token into **Connect your local worker**. Default:

```bash
cat "${WONDERTALES_HOME:-$HOME/.local/share/wondertales-v2}/api-token"
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

Skip this section for the lowest-memory Templates mode. For the optional local model, run on the **Ubuntu browser computer**, not a remote n8n-only host:

```bash
curl -fsSL https://ollama.com/install.sh -o /tmp/wondertales-ollama-install.sh
sh /tmp/wondertales-ollama-install.sh
ollama --version
curl --fail http://127.0.0.1:11434/api/tags
ollama pull qwen2.5:1.5b
```

The installer may request sudo and installs a service on supported Linux systems. If the local API is not running, start `ollama serve` in a separate terminal and leave it open; do not start another copy if the service already listens on port 11434. Model weights need download space and RAM. Sources: [official Linux installer](https://ollama.com/download/linux), [Ollama quickstart](https://docs.ollama.com/quickstart).

Select **Local AI** in Settings. The default model is only a starting choice; performance depends on RAM, CPU and competing processes. No GPU is required by our planner API, but low-memory machines can be slow. A 4K context and 60-second keep-alive limit retained model memory. Hypit uses one rendering browser at a time.

The model improves visual descriptions, while the supplied script remains unchanged. If Ollama is missing or returns invalid JSON, the plan is explicitly labelled **template fallback**. This is not silent AI success. Only a localhost Ollama endpoint is accepted; no external AI account is configured. A model can still produce poor visual direction: review it before spending credits.

## 3. Install or reuse n8n

**Already using n8n? Skip the fresh-install block.** Keep its existing data and credentials, then import the new exports. Do not run a second container on port 5678.

### Fresh n8n on Ubuntu desktop or EC2 (Linux Docker)

Run this only on the machine that will host n8n. On EC2 this installs **n8n only**; the graphical Flow worker stays on the browser computer.

```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo docker volume create wondertales_n8n_data
sudo docker run -d \
  --name wondertales-n8n \
  --restart unless-stopped \
  --network host \
  -e N8N_LISTEN_ADDRESS=127.0.0.1 \
  -e N8N_HOST=localhost \
  -e N8N_PROTOCOL=http \
  -e N8N_SECURE_COOKIE=false \
  -e N8N_PORT=5678 \
  -e N8N_EDITOR_BASE_URL=http://localhost:5678 \
  -e WEBHOOK_URL=http://localhost:5678/ \
  -e N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true \
  -e GENERIC_TIMEZONE=Asia/Kolkata \
  -e TZ=Asia/Kolkata \
  -v wondertales_n8n_data:/home/node/.n8n \
  docker.n8n.io/n8nio/n8n:2.43.7
sudo docker logs --tail 30 wondertales-n8n
```

This fresh-install example pins n8n to the stable version listed in its official Docker guide when these instructions were updated. The image and exported workflows have not been executed together here. Keep existing installations on their chosen version until you deliberately test an upgrade. Source: [n8n Docker guide](https://docs.n8n.io/hosting/installation/docker/).

Linux host networking allows n8n to reach the worker or SSH reverse tunnel on `127.0.0.1:8099`; n8n itself listens only on host loopback. The named volume preserves workflows, credentials and encryption configuration. Do not delete it. Do not apply this Linux host-network recipe to Docker Desktop without adapting its networking.

Open **http://localhost:5678** locally, or use the EC2 SSH tunnel below, and create the n8n owner account. Keep localhost access local; these commands do not configure a public HTTPS domain.

### Import and connect the workflows

Import these **inactive** exports from `n8n/workflows`:

| Export | Purpose |
| --- | --- |
| `01-story-plan.json` | Story form → save plan; no credit approval/generation |
| `02-job-status.json` | Manual progress, completed jobs and recovery guidance |
| `03-queue-monitor.json` | Hourly report of the already-approved queue |
| `04-private-youtube-upload.json` | Check every ten minutes for approved video details, verify channel, upload Private, read back and record result |

For each **local worker** HTTP Request node, select a **Header Auth** credential:

- Header name: `X-Wondertales-Token`
- Header value: the private v2 `api-token` file's contents

Default worker URL: `http://127.0.0.1:8099`. Native n8n on the same host, or Linux Docker n8n using host networking, can use it directly. A bridge-network container needs deliberate host routing; its own `127.0.0.1` is not the worker. Do not expose worker or Google browser ports publicly.

The n8n form saves a plan. **Approve spending in the local studio.** The worker polls approved jobs every two seconds; n8n's hourly monitor does not start another worker or approve credits. Character selection, recovery and revisions are available in the studio. The exports contain no embedded secrets or active schedules. The Google/YouTube nodes in workflow 04 use the same **YouTube OAuth2** credential, not the worker Header Auth credential. See [YouTube setup and review](docs/YOUTUBE.md).

### Access EC2 n8n from the browser computer

Run this from the **browser computer**, replacing the SSH host and key path with your actual values. Keep the terminal open:

```bash
ssh -i "$HOME/.ssh/YOUR_EC2_KEY.pem" -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 5678:127.0.0.1:5678 \
  -R 127.0.0.1:8099:127.0.0.1:8099 ubuntu@YOUR_EC2_HOST
```

Then open local port 5678 for EC2 n8n. Keep the tunnel and worker running. This setup assumes native or host-network n8n on EC2; it has not been tested against your instance.

## 4. Connect YouTube and run the first video

These account setup steps need the actual account owner; a shell command cannot replace Google consent.

1. In studio Settings, save your expected YouTube channel ID, category, explicit audience, tags/hashtags and optional description footer. Leave automatic upload approval off for the first test.
2. In n8n, connect an existing YouTube OAuth2 credential, or create a Google OAuth web client with the exact redirect URL displayed by n8n and enable YouTube Data API v3. Select that same credential on every Google/YouTube node in workflow 04. An OAuth client ID/secret is required; a paid AI API key is not.
3. Create one short story plan in the studio. Review the displayed Flow rate/cap and approve generation only when your account/model are ready.
4. After the video completes, inspect it, review its upload details, and approve a Private upload. Run workflow 04 from its first node once; check the recorded video in YouTube Studio.
5. Activate the uploader's ten-minute schedule only after the test works. Optional automatic Private approval applies to future completed videos; it does not approve Flow spending or public publishing.

Full account setup and recovery: [YouTube guide](docs/YOUTUBE.md). First real Flow generation, Hypit render and YouTube upload still need live validation.

## Update an existing checkout

First deactivate old schedules, let current operations finish and stop the worker with `Ctrl+C`. Back up worker state and n8n data/credentials. Then, on the **browser computer**:

```bash
cd ~/wondertales-n8n
git status --short
git pull --ff-only
bash scripts/setup.sh
bash scripts/prepare-renderer.sh
```

If `git status` shows local edits, preserve/review them before pulling; do not overwrite them. Project dependency updates do not upgrade your existing n8n instance or erase private state. Reimport changed workflow JSON, select the v2 credentials and deactivate duplicate schedules. Sign in again with `bash scripts/login.sh` only if needed, while the worker is stopped. Restart with `bash scripts/start.sh`.

The current defaults use `~/.local/share/wondertales-v2`. To use a different **absolute** state location, set `WONDERTALES_HOME` consistently in every setup, preparation, login and startup terminal before running commands. Never point two concurrent workers at the same Google profile.

## Everyday start and stop

Browser computer:

```bash
cd ~/wondertales-n8n
bash scripts/start.sh
```

Leave it running. Stop with `Ctrl+C` and wait for the active scene/render. Check tools without starting production:

```bash
cd ~/wondertales-n8n
bash scripts/start.sh --doctor
```

If you created the Docker container above, manage it on its **n8n host**:

```bash
sudo docker stop wondertales-n8n
sudo docker start wondertales-n8n
sudo docker logs --tail 30 wondertales-n8n
```

These are separate stop/start/diagnostic operations, not commands you need to run in sequence every day. Reconnect the SSH tunnel whenever EC2 n8n needs the browser computer's worker.

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

**Remaining limits:** Flow automation is unofficial and can break when Google changes its UI. Login, CAPTCHA and account restrictions may require you. Native Flow narration may vary in voice, pronunciation or accuracy; an audio stream does not prove correct speech. Caption timing is per scene, not word-level ASR. Identity descriptions are not reference-image conditioning. Video checks cover stream presence, duration, aspect, resolution and decoding, not semantic quality. Real n8n import/form execution, Flow generation and first complete owner-account video remain live validation steps. No scheduled story invention, external messaging, public publishing, monetization promise or unlimited-generation claim is included. Private upload code still needs owner-account validation.

Private state: `~/.local/share/wondertales-v2`, or a consistently set absolute `WONDERTALES_HOME`. Back up the whole folder while the worker is stopped. Browser profiles and n8n data need their own private backups. Never commit state, cookies or tokens.

Further detail: [API & architecture](docs/API.md).
