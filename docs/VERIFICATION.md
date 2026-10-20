# Verification · v2

Verified in the development session:

- Python offline tests for planning, structured AI fixture/fallback, immutable cast snapshots, approval limits, durable reservations, cross-job daily cap, timeout uncertainty, revision reuse, path containment and a real FFmpeg decode fixture.
- Four generated inactive n8n exports: graph/JavaScript validation and regeneration consistency.
- Studio JavaScript syntax and shell-script syntax.
- Hypit **0.3.1** installed and version queried.
- Hypit `check` accepted the generated SVML/SVS/Run project targeting `final.video`.

The local rendering browser's explicit preparation was attempted. Its Chrome Headless Shell download/install failed in this environment. A complete encoded Hypit render has **not** been verified here; no substitute compositor is reported as a Hypit render. Run `scripts/prepare-renderer.sh` on your own worker, or choose an existing compatible local Chrome executable in Settings and prepare again.

Not performed: live Flow login, model discovery/generation/billing, actual local Ollama inference, real n8n import/form execution, an owner-account end-to-end video, EC2 deployment or uploads. Tests do not consume Flow credits and do not prove visual quality, speech correctness or browser compatibility.

To finish live validation: stop the old worker/schedules, install and prepare the new worker, connect its dedicated Flow profile, verify current model/rate, configure conservative caps, import the new n8n exports with Header Auth, then approve one short scene. Verify original downloaded media, Hypit output, captions and final audio before scheduling larger jobs.

Upload-details update: offline tests additionally cover metadata extraction, UTF-8 description limits, explicit audience, Private-only validation, channel mismatch, durable single-use claims, metadata read-back validation, idempotent completion, opt-in automatic approval and old-settings compatibility. The actual YouTube OAuth/upload has not been executed. No video was sent to YouTube during development.

Story-profile update: 29 offline/API tests pass, including six new cases for Hindi/English repetition, structured planner input, model-timeout fallback, saved-profile snapshots, old-settings/jobs compatibility and invalid-profile persistence. Studio/workflow JavaScript syntax checks pass. Model responses in these tests are fixtures; actual Ollama/Flow creative quality, narrator-tone adherence and end-to-end rendering/upload remain unverified.
