# Local API and architecture

The Python standard-library server binds to `127.0.0.1:8099`. Every `/api/*` request needs `X-Wondertales-Token`; the HTML shell alone is public on that loopback address. POST bodies must be JSON objects up to 64 KB. No CORS is enabled. Private jobs, ledger, token and media live outside the checkout.

| Method/path | Body / result |
| --- | --- |
| `GET /api/settings` | Current settings, no Google credentials |
| `POST /api/settings` | Full settings object; validation and local persistence |
| `GET /api/doctor` | Tool presence only, not account readiness |
| `POST /api/plan` | `title`, `story`, `language`, `aspect`, `duration`, optional `characters` names |
| `GET /api/jobs` | Plans, status, events and guidance |
| `GET /api/jobs/ID` | One job |
| `POST /api/approve` | `id`, `cap`; approval queues exactly that immutable plan |
| `POST /api/resume` | `id`; only a stopped approved job with no uncertain scenes |
| `POST /api/recover` | `id`, 1-based `scene`, `filename` relative to private imports |
| `POST /api/revise` | `id`, 1-based `scene`, `direction`; creates a new unapproved plan |
| `POST /api/retry-render` | `id`; confirms the existing Hypit Result failed/cancelled before clearing only its Build ID and queuing a local retry |
| `POST /api/tick` | `{}`; approved queue summary; worker already processes jobs automatically |
| `GET /api/video/ID` | Finished MP4 attachment |

## Execution boundaries

Jobs move `planned → queued → running → complete`, or `running → attention`. A single worker claims queued jobs using an immediate SQLite transaction. A process lock prevents duplicate worker/login processes in one state directory. Do not create separate state directories for simultaneous workers using the same Google account/profile: caps and locks are local to that state directory.

Scenes move `pending → submitting → done`, or `submitting → uncertain`. A credit reservation and `submitting` checkpoint commit **before** Flow is invoked. A crash after reservation conservatively counts the estimated cost even if the upstream request never reached Google. Restart converts in-flight scenes to uncertain and running jobs to attention. Recovery never refunds estimates or silently submits again.

The current Flow integration uses `gflow-cli==0.85.0` subprocess arguments, never shell interpolation. It is **not** the Google Flow MCP connector discussed as another option. It retains the existing repository's CLI integration to avoid two independent Google session owners. The adapter uses balance JSON and `video t2v` with profile, model, duration, aspect, one output and a job-specific download directory. It fails closed if the CLI response/download is unrecognised. Google UI/model changes require real-account compatibility checks.

Ollama receives the story and selected character descriptions locally, with a structured response schema. Only visual descriptions are accepted; script, cast list, account, model and spending permissions come from validated application data. A failed AI call produces a labelled template plan. There are no model-generated shell commands or tools.

Each job has an editable Hypit project under private `jobs/ID`: `film.svml`, `film.svs`, `film.svrun`, `hypit.runtime.json`, `BRIEF.md`, `plan.json`, downloaded assets, Hypit Results, planned `captions.srt` and final media. The Profile contains only local media and HTML renderer endpoints and no credential stores. Hypit consumes the actual downloaded video streams and places picture/audio on one finite Timeline. FFmpeg adds per-scene captions afterward. `hypit_build` is checkpointed and resumed by ID. A failed render retry never clears a completed Flow clip or credit ledger entry.

Planning and input validation are independent of Google login. Approving zero/unset rates is prohibited. Current Flow balance is checked before each new submission. Estimated per-job and global daily credit limits are enforced transactionally. These cannot verify Google's actual tariff or consumption; the owner must keep the configured per-clip price accurate.

## n8n use

The story export is intentionally a plan-only form. No POST endpoint implicitly approves new spending, except the explicit `approve` endpoint with a supplied cap. Only connect that endpoint to automation if you deliberately want preauthorised recurring production and have defined the source, budget and frequency. The shipped hourly workflow reports status; it is not a daily generation schedule.

Fresh production needs an approval in the studio. After approval, scene production and assembly run without a user click between successful stages. Reconciliation, Google login/verification, plan revisions and higher budgets need an operator. External messaging and public publishing are absent. Optional Private uploads use the separately configured n8n workflow.

## Model and dependency references

- [Hypit agent quickstart](https://github.com/hypit-ai/hypit/blob/main/docs/quickstart.md)
- [Hypit local rendering provider](https://github.com/hypit-ai/hypit/tree/main/packages/provider-html-local)
- [gflow-cli](https://github.com/ffroliva/gflow-cli)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [n8n workflow import/export](https://docs.n8n.io/workflows/export-import/)

Google accounts/browser sessions are never bundled in this repository. Using an existing Google subscription does not supply API credits or unlimited generation.

## Private upload API

All routes require the same worker token. `settings.youtube` stores the expected channel, category/region, explicit audience, tags, hashtags, footer and opt-in automatic Private approval. Existing settings gain these defaults without overwriting other values.

| Method/path | Purpose |
| --- | --- |
| `POST /api/upload/prepare` | `{id}`: derive details from a completed job; defaults snapshot into the job |
| `POST /api/upload/approve` | `{id, metadata}`: validate edited details and queue Private upload |
| `GET /api/upload/next` | Returns `{jobs: []}` or one ready candidate; read-only |
| `POST /api/upload/claim` | `{id, channel_id}`: atomic single-use handoff; returns metadata and claim receipt |
| `POST /api/upload/complete` | `{id, claim, video}`: record a read-back YouTube resource only after ID, channel, Private visibility and metadata checks |

Upload state: `review → ready → claimed → uploaded`. A claimed job stays claimed across restarts and never reappears in the ready queue. An interrupted upload requires YouTube/n8n reconciliation. There is no automatic claim reset or upload retry. Normal full-workflow reruns cannot claim it twice; manually reexecuting a cached upload node can bypass orchestration, so never do that. A revision gets its own upload state rather than inheriting the original video's ID.

Metadata generation uses the supplied title and up to two script sentences plus saved footer/hashtags. It does not call another model, invent SEO metrics or guarantee content accuracy. Audience is never inferred. All stored and mapped upload visibility is Private. Thumbnail and playlist assignment remain manual in YouTube Studio.

## Story profile

`settings.story_profile` contains `audience`, `tone` and `boundaries`, each a nonblank string of up to 600 characters. Unknown fields and invalid values are rejected before changing saved settings. Older settings receive defaults. Creating a plan snapshots the profile; changes to settings do not rewrite an existing job or its budget approval.

Ollama receives this profile with the narration and per-scene direction as structured input. It still supplies visual descriptions only. The template fallback and Flow prompt retain the preferences. The application preserves the supplied story and narration, including intentional repeated Hindi/English lines. No title/hook score, automatic transcript cutting or retention inference was added. The creative audience is independent of the explicit YouTube Made for kids setting.

## Optional ArcReel handoff

These endpoints require the existing `X-Wondertales-Token` header. Configure `ARCREEL_URL` and the separate `ARCREEL_TOKEN` server-side, then restart the worker.

| Method/path | Purpose |
| --- | --- |
| `GET /api/arcreel` | Returns `{configured, url}`; presence of configuration only, not live readiness; never the token |
| `POST /api/arcreel` | `{id}`: manually transfer a saved plan to a separate ArcReel storyboard workspace; returns a durable receipt |

Job list/detail responses include `arcreel` (receipt or null). This transfer creates a project and uploads source text only. No generation, budget approval, media import or publishing is triggered. Source overview generation is explicitly disabled. Receipts live separately from job/ledger state; an uncertain mutation blocks automatic retry. See README for inspection and manual recovery.
