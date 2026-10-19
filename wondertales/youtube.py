"""Story-derived upload details and a durable, single-use n8n upload handoff."""
import copy
import re
import secrets


CHANNEL_DEFAULTS = {"channel_id": "", "category_id": "1", "region": "IN",
                    "made_for_kids": None, "auto_upload": False,
                    "description_footer": "", "tags": [], "hashtags": []}


def channel_settings(value):
    if not isinstance(value, dict) or set(value) - set(CHANNEL_DEFAULTS):
        raise ValueError("Invalid YouTube channel settings")
    result = {**copy.deepcopy(CHANNEL_DEFAULTS), **value}
    if result["channel_id"] and not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", result["channel_id"]):
        raise ValueError("Use your YouTube channel ID beginning with UC")
    if not re.fullmatch(r"[0-9]{1,2}", str(result["category_id"])):
        raise ValueError("Category must be a YouTube category ID")
    if not isinstance(result["region"], str) or not re.fullmatch(r"[A-Z]{2}", result["region"]):
        raise ValueError("Region must be a two-letter country code")
    if result["made_for_kids"] is not None and type(result["made_for_kids"]) is not bool:
        raise ValueError("Choose made for kids explicitly")
    if type(result["auto_upload"]) is not bool:
        raise ValueError("Auto upload must be true or false")
    footer = result["description_footer"]
    if not isinstance(footer, str) or len(footer.encode()) > 1000 or any(c in footer for c in "<>"):
        raise ValueError("Description footer must be at most 1000 UTF-8 bytes with no angle brackets")
    for key in ("tags", "hashtags"):
        values = result[key]
        if not isinstance(values, list) or len(values) > (15 if key == "tags" else 3):
            raise ValueError("Save up to 15 tags and three hashtags")
        for v in values:
            if not isinstance(v, str) or not v.strip() or len(v) > 60 or any(c in v for c in "<>,"):
                raise ValueError("Use short nonempty tags without commas or angle brackets")
            if key == "hashtags" and (not v.startswith("#") or not v[1:].replace("_", "").isalnum()):
                raise ValueError("Hashtags must begin with # and contain letters/numbers/underscores")
        if len(','.join(values)) > 350:
            raise ValueError("Channel tags are too long")
    if result["auto_upload"] and (not result["channel_id"] or result["made_for_kids"] is None):
        raise ValueError("Set channel and audience before enabling automatic Private upload")
    return result


def clean(text):
    return ' '.join(str(text).replace('<', '').replace('>', '').split())


def validate_metadata(meta):
    if not isinstance(meta, dict) or set(meta) != {"title", "description", "tags", "language", "category_id", "made_for_kids", "privacy"}:
        raise ValueError("Upload details contain missing or unknown fields")
    if not isinstance(meta["title"], str) or not meta["title"].strip() or len(meta["title"]) > 100 or any(c in meta["title"] for c in "<>\r\n"):
        raise ValueError("Title needs 1–100 characters, without angle brackets or line breaks")
    if not isinstance(meta["description"], str) or not meta["description"].strip() or len(meta["description"].encode()) > 5000 or any(c in meta["description"] for c in "<>"):
        raise ValueError("Description needs 1–5000 UTF-8 bytes with no angle brackets")
    if meta["language"] not in ("en", "hi") or meta["privacy"] != "private" or type(meta["made_for_kids"]) is not bool:
        raise ValueError("Choose English/Hindi, explicit audience, and Private visibility")
    if not re.fullmatch(r"[0-9]{1,2}", str(meta["category_id"])):
        raise ValueError("Invalid category ID")
    tags = meta["tags"]
    if not isinstance(tags, list) or len(tags) > 15 or any(not isinstance(t, str) or not t.strip() or len(t) > 60 or any(c in t for c in "<>,") for t in tags):
        raise ValueError("Use up to 15 short tags without commas/angle brackets")
    # Conservative bound allows for YouTube's extra quotation accounting for spaced tags.
    if sum(len(t) + 3 for t in tags) > 450:
        raise ValueError("Tags exceed the supported length")
    return copy.deepcopy(meta)


def metadata(job, defaults):
    config = channel_settings(defaults)
    if not config["channel_id"] or config["made_for_kids"] is None:
        raise ValueError("Save your YouTube channel and explicit audience setting first")
    title = clean(job["title"])[:100].strip()
    # Deliberately extract from the real script instead of inventing promises, morals or SEO claims.
    sentences = re.split(r"(?<=[.!?।])\s+", clean(job["story"]))
    summary = ' '.join(sentences[:2])
    if len(summary) > 600:
        summary = summary[:600].rsplit(' ', 1)[0] + '…'
    description = '\n\n'.join(p for p in (summary, config["description_footer"].strip(), ' '.join(config["hashtags"])) if p)
    return validate_metadata({"title": title, "description": description, "tags": config["tags"],
        "language": "hi" if job["language"] == "Hindi" else "en", "category_id": str(config["category_id"]),
        "made_for_kids": config["made_for_kids"], "privacy": "private"})


class Uploads:
    def __init__(self, store):
        self.store = store

    def prepare(self, ident):
        config = channel_settings(self.store.settings()["youtube"])
        with self.store.transaction() as db:
            job = self.store._read(db, ident)
            if job["status"] != "complete" or job.get("upload", {}).get("state") in ("claimed", "uploaded"):
                raise ValueError("Use a completed video with no active/completed upload")
            job["upload"] = {"metadata": metadata(job, config), "channel_id": config["channel_id"],
                             "region": config["region"], "state": "ready" if config["auto_upload"] else "review"}
            return self.store._write(db, job, "Upload details prepared from the script. Review is recommended; visibility is Private.")

    def approve(self, ident, details):
        details = validate_metadata(details)
        with self.store.transaction() as db:
            job = self.store._read(db, ident)
            if job["status"] != "complete" or job.get("upload", {}).get("state") not in ("review", "ready"):
                raise ValueError("Prepare upload details before approving; claimed uploads cannot change")
            job["upload"].update(metadata=details, state="ready")
            return self.store._write(db, job, "Upload details approved for Private upload.")

    def next(self):
        for job in reversed(self.store.list()):
            if job["status"] == "complete" and job.get("upload", {}).get("state") == "ready":
                return {"id": job["id"], **job["upload"]}
        return None

    def claim(self, ident, channel_id):
        with self.store.transaction() as db:
            job = self.store._read(db, ident)
            upload = job.get("upload", {})
            if job["status"] != "complete" or upload.get("state") != "ready" or upload.get("channel_id") != channel_id:
                raise ValueError("Upload is not ready or connected channel does not match")
            validate_metadata(upload["metadata"])
            upload.update(state="claimed", claim=secrets.token_urlsafe(24))
            self.store._write(db, job, "YouTube upload claimed. If interrupted, check YouTube Studio; automatic re-upload is blocked.")
            return {"id": ident, **upload}

    def complete(self, ident, claim, video):
        with self.store.transaction() as db:
            job = self.store._read(db, ident)
            upload = job.get("upload", {})
            if upload.get("state") == "uploaded" and upload.get("video_id") == video.get("id"):
                return job
            if upload.get("state") != "claimed" or not secrets.compare_digest(str(upload.get("claim", "")), str(claim)):
                raise ValueError("Upload claim does not match")
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", str(video.get("id", ""))) or video.get("snippet", {}).get("channelId") != upload["channel_id"] or video.get("status", {}).get("privacyStatus") != "private":
                raise ValueError("Verify the uploaded video ID, channel and Private status before recording completion")
            wanted = upload["metadata"]
            snippet, status = video["snippet"], video["status"]
            if any(snippet.get(k) != wanted[v] for k, v in (("title", "title"), ("description", "description"), ("categoryId", "category_id"), ("defaultLanguage", "language"))) or status.get("selfDeclaredMadeForKids") is not wanted["made_for_kids"] or set(snippet.get("tags", [])) != set(wanted["tags"]):
                raise ValueError("YouTube details differ from the approved metadata. Inspect the existing video; do not re-upload")
            upload.update(state="uploaded", video_id=video["id"])
            return self.store._write(db, job, "Video uploaded to YouTube as Private. Watch it in YouTube Studio before publishing.")
