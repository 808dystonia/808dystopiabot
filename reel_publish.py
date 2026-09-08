"""Discord first, Instagram second.

Never pass a YouTube page URL to IG. Only a direct mp4.
"""
from __future__ import annotations

import os

import requests

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
IG_USER_ID = os.getenv("IG_USER_ID", "28902406756011804")
ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "1542355862079807509")
PUBLISH_TO_IG = os.getenv("REELS_PUBLISH_TO_IG", "0") == "1"


def execute(slug, arguments):
    resp = requests.post(
        f"{COMPOSIO_BASE}/tools/execute/{slug}",
        headers={"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"},
        json={"arguments": arguments or {}, "user_id": COMPOSIO_USER_ID, "version": "latest"},
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{slug} HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def announce_discord(text):
    execute("DISCORDBOT_CREATE_MESSAGE", {"channel_id": ADMIN_CHANNEL_ID, "content": text[:1900]})


def publish_reel(video_url, caption):
    """Stage on Discord, then publish to IG if the flag is on."""
    announce_discord(
        f"808 clip staged for IG (not a YouTube link):\n{video_url}\n\nCaption:\n{caption[:400]}"
    )
    if not PUBLISH_TO_IG:
        announce_discord("IG publish is OFF. Set REELS_PUBLISH_TO_IG=1 on Render after you like the staged clip.")
        return {"staged": True, "published": False, "video_url": video_url}

    created = execute(
        "INSTAGRAM_POST_IG_USER_MEDIA",
        {
            "ig_user_id": IG_USER_ID,
            "video_url": video_url,
            "caption": caption,
            "media_type": "REELS",
            "share_to_feed": True,
        },
    )
    data = created.get("data") if isinstance(created, dict) else {}
    creation_id = data.get("id")
    if not creation_id:
        raise RuntimeError(f"no creation_id: {created}")
    published = execute(
        "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH",
        {
            "ig_user_id": IG_USER_ID,
            "creation_id": creation_id,
            "max_wait_seconds": 180,
        },
    )
    pdata = published.get("data") if isinstance(published, dict) else {}
    media_id = pdata.get("id")
    announce_discord(f"808 Reel published to IG. media_id={media_id}")
    return {"staged": True, "published": True, "media_id": media_id, "video_url": video_url}
