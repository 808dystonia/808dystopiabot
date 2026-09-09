"""Watch #admin-general for video attachments.

Someone attaches the mp4 → crop/host → post hosted clip in Discord → IG if flag on.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from reel_media import crop_to_916, host_mp4
from reel_publish import publish_reel

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "1542355862079807509")
SEEN_FILE = Path(os.getenv("DISCORD_INGEST_SEEN", "/tmp/808_discord_ingest_seen.json"))
WORKDIR = Path("/tmp/808reels/discord")
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/webm"}


def execute(slug, arguments):
    resp = requests.post(
        f"{COMPOSIO_BASE}/tools/execute/{slug}",
        headers={"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"},
        json={"arguments": arguments or {}, "user_id": COMPOSIO_USER_ID, "version": "latest"},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{slug} HTTP {resp.status_code}: {resp.text[:240]}")
    return resp.json()


def load_seen():
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen)[-200:]))


def ingest_admin_videos():
    if not COMPOSIO_API_KEY:
        print("ingest: no COMPOSIO_API_KEY", flush=True)
        return []
    seen = load_seen()
    raw = execute("DISCORDBOT_LIST_MESSAGES", {"channel_id": ADMIN_CHANNEL_ID, "limit": 25})
    data = raw.get("data") if isinstance(raw, dict) else {}
    messages = data.get("messages") or data.get("data") or data.get("items") or []
    if isinstance(data, list):
        messages = data
    saved = []
    WORKDIR.mkdir(parents=True, exist_ok=True)
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        mid = str(msg.get("id") or "")
        caption = (msg.get("content") or "Follow for more.")[:900]
        for att in msg.get("attachments") or []:
            if not isinstance(att, dict):
                continue
            aid = str(att.get("id") or mid)
            if aid in seen:
                continue
            name = att.get("filename") or att.get("name") or f"{aid}.mp4"
            url = att.get("url") or att.get("proxy_url")
            mime = (att.get("content_type") or "").lower()
            ext = Path(name).suffix.lower()
            if ext not in VIDEO_EXTS and mime not in VIDEO_MIMES:
                continue
            if not url:
                continue
            dest = WORKDIR / name
            print(f"ingest download {name}", flush=True)
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            dest.write_bytes(r.content)
            cropped, _info = crop_to_916(dest, WORKDIR / f"{dest.stem}_916.mp4")
            hosted = host_mp4(cropped)
            publish_reel(hosted, caption if caption.strip() else f"{name}\nFollow for more.")
            seen.add(aid)
            saved.append(hosted)
    save_seen(seen)
    return saved


if __name__ == "__main__":
    print(ingest_admin_videos())
