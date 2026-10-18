# VoiceStudio narration and captions

WonderTales can call the local HTTP API from [Vishnu063/VoiceStudio](https://github.com/Vishnu063/VoiceStudio). VoiceStudio runs separately; its Torch, speech models and ASR packages are **not** added to the main WonderTales Python environment. Our adapter imports only Python's standard library and existing media helpers.

This is an optional provider. Existing jobs continue using their saved provider/settings. In new story forms, choose **Current online narrator**, **VoiceStudio local**, or **My audio + SRT**. Supplying owner audio remains supported; it cannot be combined with VoiceStudio generation in the same submission.

## What is supported

| Choice | Use | Limits |
| --- | --- | --- |
| `kittentts` | Lightweight English preset narrator | English only; no cloning or emotional voice design |
| `omnivoice-gguf` | Multilingual speech, including Hindi, using an existing voice profile | Needs model weights and a working platform-specific binary; quality/speed require a real sample |
| Local ASR | Create timed SRT from the generated speech | Pin `faster-whisper` or `whisperx` on the VoiceStudio server; install its multilingual model |

Use actual engine IDs and saved profile IDs. OpenAI aliases like `tts-1`, `alloy` and `default` are not accepted by this integration. The upstream speech API routes some aliases to the active/default engine; explicit IDs avoid that ambiguity. KittenTTS accepts only its eight known preset IDs. GGUF checks that the selected profile exists and its engine reports cloning support.

Voice selection is **one narrator/profile per video**, reused for every storyboard scene. This update does not implement a different acting voice for each character, automatic singing, emotional acting guarantees, or automatic voice cloning from a story form. Create/manage reference profiles in VoiceStudio using your own voice or a speaker who permits the use, and review each engine/model's commercial-use terms.

## Install or use an existing server

If VoiceStudio already runs on the worker computer, use that service and skip installation. Its API should be reachable at `http://127.0.0.1:3900`. A different port can be configured in workflow 19. Remote machines must be securely tunneled to a loopback port on the worker; story forms cannot supply remote URLs. The adapter disables environment proxies and does not follow redirects.

For a new source installation, install [uv](https://docs.astral.sh/uv/getting-started/installation/) and upstream OS prerequisites, then from the WonderTales checkout run:

```bash
bash scripts/setup-voicestudio.sh
```

The optional helper clones **your VoiceStudio repository** at inspected commit `4e61c2782d51df5488b390699d2faa98be677090`, then uses its lockfile and a separate Python 3.12 environment under `.voicestudio`. It preserves a pre-existing checkout at another revision by stopping rather than overwriting it. Dependency installation is substantial; models/binaries may require separate setup. No models are installed into WonderTales's `.venv`.

Start the separate service in another terminal:

```bash
bash scripts/start-voicestudio.sh
```

The supplied launcher binds to `127.0.0.1`, uses CPU by default, pins local ASR, permits one generation worker, and starts with the lighter KittenTTS engine. Requests can explicitly select GGUF once it is installed. It creates a private `voicestudio-token` under `WONDERTALES_HOME` (default `~/.local/share/wondertales`) and passes it to the local service. This is a **local authentication secret, not a paid provider API key**. Never paste it into a story, workflow export or GitHub. The adapter reads that file itself. An existing Docker/keyed server must use the matching private token file; a normal native loopback server can run without it.

The launcher uses `OMNIVOICE_ASR_BACKEND` set to workflow 19's configured local ASR engine. The adapter checks that the engine is available **and environment-pinned**. Upstream `/v1/audio/transcriptions` uses its active ASR engine, not necessarily the request's `model` field; an unpinned or remote engine is therefore rejected. Set the same environment variable and restart if using your own launcher. We never change the server's active engine or install a model through an n8n form.

The full VoiceStudio application lists 8 GB RAM minimum and 16 GB recommended for its default workflow. A small engine does not make the full app stack equally small. Start with English KittenTTS and check your actual memory/speed before sharing a machine with Chrome, n8n and video encoding. CPU-only Hindi/GGUF and ASR still need benchmarking. No GPU service or paid voice subscription is required by this adapter; your compute/storage usage remains your responsibility.

**GGUF from source:** the upstream source checkout contains placeholder binaries. Follow its [GGUF engine guide](https://github.com/Vishnu063/VoiceStudio/blob/main/docs/engines/omnivoice-gguf.md) to obtain/build a compatible real binary and install the weights. A successful Python dependency install does not establish that GGUF works. The adapter fails before Flow spending if its availability check fails.

## Configure in n8n

Import workflows 19, 20 and 21. Assign the **WonderTales Local Worker** Header Auth credential to their HTTP nodes; tokens do not belong in workflow JSON.

1. Open workflow **19 VoiceStudio Settings**. For a first English test use alias `english-main`, language English, engine `kittentts`, voice ID `expr-voice-2-f`, speed 1, port 3900, local ASR `faster-whisper`.
2. Start/restart VoiceStudio with that pinned local ASR. In its model catalogue install a multilingual recognition model suitable for your hardware. English-only recognition models are unsuitable for Hindi.
3. Run workflow **20 Connection Check**. It shows available supported TTS engines, saved voice-profile IDs, English preset IDs and configured mappings. It is an inventory request; no synthesis or transcription is performed.
4. For Hindi, create an appropriate voice profile in VoiceStudio and copy its profile ID. Save alias `hindi-main`, language Hindi, engine `omnivoice-gguf`, that ID and your chosen speed through workflow 19. A profile name alone is not its ID.
5. Run workflow **21 Audio Sample** with a short script in the chosen language. It checks metadata, synthesizes speech and obtains local SRT, but never creates a Flow video job or uploads to YouTube. The first model load can take minutes. View/download the sample through n8n's execution binary data and compare it with your current narration.
6. Choose **VoiceStudio local** in Story Intake, Story Bank or Preflight. Blank voice alias uses `english-main` or `hindi-main` according to the selected language. The profile must be configured first. Preflight makes metadata checks; actual generation/ASR and listening are separate validations.

A voice mapping change affects future submissions only. Every new job saves the URL, explicit engine, voice ID, speed, language and ASR choice; no credential is stored in that job snapshot. Keep the old server/profile available if resuming an existing job. If intentionally changing a video’s voice, submit a deliberate new version rather than assuming a settings edit changes already-paid work.

Pinning a profile ID does not freeze changes made inside VoiceStudio itself. Keep that profile's reference/audio unchanged for queued work, use its locking controls where appropriate, and create a new profile ID for a changed voice. Once speech has been generated, our saved WAV/MP3 protects that job from subsequent profile changes during normal resume.

## Generation, timing and recovery

Without a storyboard, one request generates the narration, then ASR supplies timed captions. The speech endpoint accepts up to 4096 characters; longer scripts need a storyboard. Storyboards use one speech/caption pair per scene and the existing slot-alignment logic, so narration remains synchronized with the planned visuals. Generated speech that exceeds its time allowance stops **before transcription for that segment and before new Flow generation**. Shorten it and submit a corrected story/plan.

Each audio unit has a request digest, original WAV, timed SRT and converted MP3. A failed caption request retains the WAV. Safe Resume can finish captions/conversion without synthesizing that speech again. Caption times must fit the audio; malformed/empty responses stop the job. ASR text can still be wrong, particularly with names and Hindi; compare the captions to the script during private review. No automated recognition result is treated as proof of accuracy.

Once final narration/SRT exist, video generation can proceed through the existing balance, cap and scene-billing checks. Editing resumes and scene revisions reuse those files and do not require VoiceStudio to be running. No silent switch to another narrator, cloud ASR or paid provider is implemented. Engine/profile metadata checks reduce fallback ambiguity, but actual speaker identity/quality still needs listening.

On an audio failure use Job Status, fix the local service/model, then Safe Resume. **Rebuild Narration and Captions** deliberately deletes the voice caches and will synthesize again; use it only when you want a rebuild. In workflow 21, keep the returned Sample ID to resume a partial sample with identical text/settings. Sample files remain private under the worker state’s `samples` folder; its audio/caption URLs require worker authentication. A sample creates no paid video or upload.

## Licences and verification

VoiceStudio's application is AGPL-3.0; its underlying OmniVoice model and optional engines have separate licences. This integration calls the unmodified local API and links to its source rather than copying the application into this repository. Retain upstream notices and review [its licence notice](https://github.com/Vishnu063/VoiceStudio/blob/main/LICENSE-NOTICE.md) plus the chosen engine/model terms before commercial deployment. Software availability does not grant rights to imitate a particular speaker.

Offline tests use a small loopback HTTP fixture serving synthetic WAV/SRT. They verify profile pinning, explicit engine/language checks, rejection of remote/unpinned ASR, proxy/redirect boundaries, private token handling, preservation of speech after caption errors, time-limit checks and real FFmpeg conversion into our audio path. They do **not** load a VoiceStudio model or benchmark its real output.

The actual VoiceStudio application, optional installer/native GGUF binary, real speech/ASR quality, n8n runtime and owner-account video/upload chain remain pending installation and live testing. No Flow credits are spent by these checks.
