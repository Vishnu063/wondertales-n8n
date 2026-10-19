# Private YouTube upload

The agent prepares details from the real script and your saved defaults. n8n uploads the completed video, then reads its YouTube resource back to verify the channel, visibility, title, description, tags, language, category and audience setting. **This implementation has offline tests; a real owner-account upload is still pending.**

## Set up once

1. In the studio's Settings, enter your intended YouTube **channel ID** (`UC…`), category ID (starter `1` = Film & Animation), region, relevant tags/hashtags and optional description footer.
2. Choose the audience yourself: Made for kids or Not made for kids. It starts unset, blocking metadata approval. For a children's channel, choose according to your actual content; the agent does not decide this.
3. Leave **Automatically approve Private uploads** off for the first videos. Save Settings.
4. Import `04-private-youtube-upload.json` into your existing n8n. Keep it inactive while configuring/testing.
5. Select the v2 worker's Header Auth credential on every local worker HTTP node.
6. Select **one identical YouTube OAuth2 credential** on `Check connected channel`, `Upload Private video` and `Verify uploaded video`. A channel is chosen by the OAuth connection, not by a title, email string or the Flow account. Check that its authorized channel matches your saved channel ID.

Reuse your existing YouTube OAuth credential if suitable. Otherwise enable YouTube Data API v3 in a Google Cloud project, configure OAuth consent, create a web OAuth client with the exact redirect URL shown by n8n, and connect your account in n8n. Google OAuth client ID/secret and consent are required; this is distinct from a paid AI API key. Keep all secrets in n8n credentials, not exported JSON. The credential needs read access for channel/video verification as well as upload access.

## Review the first video

After production completes, the studio shows upload details. If the video predates this update, click **Prepare upload details** first. Expand **Review upload details**, check/edit title, description and tags, check the saved audience/category/language, then click **Save & approve Private upload**.

The title starts from your supplied title, capped at YouTube's supported length. The description extracts the first two script sentences, then appends your saved footer and up to three relevant hashtags. This avoids introducing unsupported morals, promises or popularity claims. Metadata cannot prove the generated footage/narration matches the script: watch the actual video.

Run the uploader once from its first node. It stops with no upload if nothing is ready or the connected channel differs. On success, the studio records a video ID and a YouTube Studio link. Read-back success means the saved details match, not that YouTube has finished processing or approved the video for distribution.

Watch the Private video in YouTube Studio. Correct any content errors before publishing. Thumbnail and playlist selection are currently manual; no automatic public publication or scheduled release is configured.

## Automatic operation after testing

Enable the configured uploader workflow to check every ten minutes. If you also deliberately enable **Automatically approve Private uploads** in studio Settings, future completed videos will enter its ready queue without per-video metadata approval. Changing this setting does not retroactively approve older review jobs or authorize new Flow spending. It never changes visibility to Public.

The pipeline still requires a supplied story and generation approval. This update handles metadata and Private delivery; it is not yet a fully tested unattended channel.

## Failed or interrupted uploads

A durable claim is recorded before n8n downloads/submits the file. Only one normal workflow execution can claim a video. A restart, timeout or lost response never automatically resets that claim. The studio shows `claimed` until completion is confirmed; this can mean an upload is still running **or** its outcome is unknown.

**Do not retry the YouTube upload node from cached execution data.** Check YouTube Studio and the original n8n execution first. A video may already exist even if n8n reported an error. If it exists, use a read-only `videos.list` request with the same OAuth account, then record its verified resource through `/api/upload/complete` using the saved job ID/claim. Repeating completion with the same recorded video is safe; uploading again is not.

If failure occurred before actual submission, reconcile that evidence before any new upload decision. This version intentionally has no automatic claim reset. No claim mechanism can guarantee exactly-once behavior if an operator manually bypasses the workflow or an upstream tool retries internally.

Official references: [YouTube upload resource fields](https://developers.google.com/youtube/v3/docs/videos/insert), [n8n YouTube credentials](https://docs.n8n.io/integrations/builtin/credentials/google/oauth-single-service/), [n8n YouTube node](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.youtube/).
