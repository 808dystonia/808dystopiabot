"""Publish an already-built 808 IG news carousel.

Grok (or you) only supplies public HTTPS media URLs + caption.
This script does the Instagram container + publish loop.
Does not design slides. Does not use Grok.

Env (Render):
  COMPOSIO_API_KEY
  COMPOSIO_USER_ID   (optional, default "default")
  IG_USER_ID         (default 28902406756011804)
"""
import os
import sys
import json
import time
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
IG_USER_ID = os.getenv("IG_USER_ID", "28902406756011804")
MAX_PUBLISH_ATTEMPTS = 2


def execute(slug, arguments):
    if not COMPOSIO_API_KEY:
        raise SystemExit("Missing COMPOSIO_API_KEY")
    url = f"{COMPOSIO_BASE}/tools/execute/{slug}"
    payload = {
        "arguments": arguments or {},
        "user_id": COMPOSIO_USER_ID,
        "version": "latest",
    }
    headers = {"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"}
    print(f"Composio {slug}", flush=True)
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code >= 400:
        print(resp.text[:500], flush=True)
        resp.raise_for_status()
    return resp.json()


def publish_carousel(image_urls, video_url, caption):
    last_err = None
    for attempt in range(1, MAX_PUBLISH_ATTEMPTS + 1):
        print(f"Publish attempt {attempt}/{MAX_PUBLISH_ATTEMPTS}", flush=True)
        try:
            args = {
                "ig_user_id": IG_USER_ID,
                "caption": caption,
                "child_image_urls": image_urls,
            }
            if video_url:
                args["child_video_urls"] = [video_url]
            created = execute("INSTAGRAM_CREATE_CAROUSEL_CONTAINER", args)
            data = created.get("data") or created
            creation_id = (
                data.get("id")
                or data.get("creation_id")
                or (data.get("data") or {}).get("id")
            )
            if not creation_id:
                raise RuntimeError(f"No creation_id: {json.dumps(created)[:400]}")
            published = execute(
                "INSTAGRAM_POST_IG_USER_MEDIA_PUBLISH",
                {
                    "ig_user_id": IG_USER_ID,
                    "creation_id": str(creation_id),
                    "max_wait_seconds": 180,
                },
            )
            pdata = published.get("data") or published
            media_id = pdata.get("id") or (pdata.get("data") or {}).get("id")
            if not media_id:
                raise RuntimeError(f"No media id: {json.dumps(published)[:400]}")
            meta = execute(
                "INSTAGRAM_GET_IG_MEDIA",
                {"ig_media_id": str(media_id), "fields": "id,permalink,caption"},
            )
            print(json.dumps({"ok": True, "media_id": media_id, "meta": meta}, default=str), flush=True)
            return meta
        except Exception as e:
            last_err = e
            print(f"Attempt {attempt} failed: {e}", flush=True)
            time.sleep(8)
    raise SystemExit(f"Publish failed after {MAX_PUBLISH_ATTEMPTS} attempts: {last_err}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--slide1", required=True, help="Public JPEG URL, 4:5")
    p.add_argument("--slide2", required=True, help="Public JPEG URL, 4:5")
    p.add_argument("--outro", default="", help="Public MP4 URL, 4:5 with audio")
    p.add_argument("--caption", required=True)
    args = p.parse_args()
    images = [args.slide1, args.slide2]
    publish_carousel(images, args.outro or None, args.caption)


if __name__ == "__main__":
    main()
