# WonderTales n8n

A self-hosted workflow for turning **your own children’s stories, poems, or nursery rhymes** into videos, then uploading them to YouTube as **Private** for you to review.

## Agreed behavior

- You enter the story in an n8n form; story generation is not automatic.
- Choose Hindi or English, one language per submission.
- Choose 9:16 or 16:9 and a target duration of 30 seconds, 1 minute, 90 seconds, or 2 minutes.
- The workflow randomly uses 2–3 characters from a 10-slot registry you can edit in n8n.
- Create video with Google Flow using the signed-in account in one dedicated spare Chrome profile.
- Assemble clips and upload to the selected YouTube channel as **Private**. You decide if/when to make it public.
- Never store Google passwords, Flow cookies, or YouTube tokens in this repository.

## Current files

- `n8n/workflows/01-story-intake.json` — importable n8n intake workflow. It collects and validates a submission, selects 2–3 characters, and hands it to the local generator service.
- This first workflow is the intake layer. The local generation service and YouTube upload workflow are the next implementation steps; the endpoint in the workflow is a local placeholder until that service is added.

## Planned flow

1. Submit story and choose language, format, and duration in n8n.
2. Select 2–3 characters from the editable registry.
3. Turn the story into scenes and prompts while preserving the submitted story.
4. Generate scene clips through the local Google Flow browser session.
5. Assemble clips, voice, captions, and music into one video.
6. Upload to YouTube as Private, with title, description, and language metadata.
7. Show the job status and resulting YouTube link in n8n.

## Important setup notes

- Google Flow does not provide a supported public API for this workflow. The candidate integration is the community project [gflow-cli](https://github.com/ffroliva/gflow-cli), which drives a signed-in browser session and can break if Google changes Flow. It is unofficial and carries account/session risk.
- Keep the Flow browser profile dedicated to this project. You sign in yourself; do not send passwords or browser cookies to anyone.
- Run the Flow generation component on the computer that owns the spare Chrome profile. An EC2-only n8n instance cannot directly use a browser profile on your computer. A secure local-to-EC2 connection can be added later; do not expose the local generator service to the public internet.
- YouTube OAuth credentials belong in n8n's credential store, never in workflow JSON or GitHub.
- Video generation and YouTube upload are not wired up yet in this initial commit. This repository will add those in small, testable stages.

## Import the starter workflow

In n8n, choose **Workflows → Import from File** and import `n8n/workflows/01-story-intake.json`. The character registry is a visible **Edit Fields** node in the workflow. Fill its 10 character slots there after deciding the character details.

The local generator endpoint is currently `http://127.0.0.1:8099/v1/jobs`. It will work only after the companion service is implemented and running on the same host as n8n. If n8n runs in Docker, the URL must be changed to the host/container address appropriate to your setup.

## Cost and privacy

The workflow adds no paid story-writing model. It uses the story you submit. Video generations consume the Google Flow credits available to your account. Keep all generated videos Private until you review them.
