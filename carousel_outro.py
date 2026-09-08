"""Slide 3: 808-Dystopia_Outro.mov (spinning logo + audio)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

from pinterest_bot import execute_composio_tool

OUTRO_ID = os.getenv("CAROUSEL_OUTRO_ID", "1RXsoQs4N8OnBfNSnMM0ZykADdwA-n3Us")
WORKDIR = Path("/tmp/808carousel")
UGUU = "https://uguu.se/upload"
IG_USER_ID = os.getenv("IG_USER_ID", "28902406756011804")
HASHTAGS = [
    "#808Dystopia #UndergroundRap #UndergroundHipHop #HipHopHistory",
    "#RapNews #UnsignedArtist #IndieHipHop #ProducerLife",
]


def download_outro():
    dest = WORKDIR / "808-Dystopia_Outro.mov"
    WORKDIR.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 10000:
        return dest
    raw = execute_composio_tool("GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": OUTRO_ID})
    data = raw.get("data") if isinstance(raw, dict) else {}
    content = data.get("downloaded_file_content") or {}
    s3 = content.get("s3url") or data.get("s3url")
    if not s3:
        raise RuntimeError(f"no outro download {raw}")
    dest.write_bytes(requests.get(s3, timeout=120).content)
    return dest


def host_outro():
    path = download_outro()
    with path.open("rb") as f:
        resp = requests.post(
            UGUU,
            files={"files[]": (path.name, f, "video/quicktime")},
            timeout=120,
        )
    data = resp.json()
    files = data.get("files") or []
    url = files[0].get("url") if files else data.get("url")
    if not url:
        raise RuntimeError(resp.text[:200])
    return url


def _child(url, video=False, handle=""):
    args = {"ig_user_id": IG_USER_ID, "is_carousel_item": True}
    if video:
        args["video_url"] = url
    else:
        args["image_url"] = url
        if handle:
            args["user_tags"] = [{"username": handle, "x": 0.5, "y": 0.82}]
    created = execute_composio_tool("INSTAGRAM_POST_IG_USER_MEDIA", args)
    cid = (created.get("data") or {}).get("id")
    if not cid:
        raise RuntimeError(f"no child id {created}")
    return cid


def _wait_finished(cid, tries=24):
    for _ in range(tries):
        st = execute_composio_tool("INSTAGRAM_GET_POST_STATUS", {"creation_id": cid})
        code = ((st.get("data") or {}).get("status_code") or "").upper()
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise RuntimeError(f"container error {cid} {st}")
        time.sleep(5)
    raise RuntimeError(f"container timeout {cid}")


def publish_with_outro(image_urls, text, handle=""):
    children = []
    for i, url in enumerate(image_urls):
        children.append(_child(url, video=False, handle=handle if i == 0 else ""))
    outro = host_outro()
    vid = _child(outro, video=True)
    _wait_finished(vid)
    children.append(vid)
    parent = execute_composio_tool(
        "INSTAGRAM_POST_IG_USER_MEDIA",
        {
            "ig_user_id": IG_USER_ID,
            "media_type": "CAROUSEL",
            "children": children,
            "caption": text,
        },
    )
    creation = (parent.get("data") or {}).get("id")
    published = execute_composio_tool(
        "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH",
        {"ig_user_id": IG_USER_ID, "creation_id": creation, "max_wait_seconds": 180},
    )
    media_id = (published.get("data") or {}).get("id")
    if media_id:
        for batch in HASHTAGS:
            try:
                execute_composio_tool(
                    "INSTAGRAM_POST_IG_MEDIA_COMMENTS",
                    {"ig_media_id": media_id, "message": batch},
                )
            except Exception as e:
                print(f"comment: {e}", flush=True)
    return media_id, outro
