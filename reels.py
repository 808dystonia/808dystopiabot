"""7:00 PM CT history Reel job. Instagram-first picks."""
from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from openai import OpenAI

from carousel_tag import apply_credits

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "1542355862079807509")
USED_FILE = os.getenv("REELS_USED_FILE", "/tmp/808_reels_used.json")
CT = ZoneInfo("America/Chicago")

LANE = [
    "OsamaSon", "Nettspend", "xaviersobased", "Che", "Glokk40Spaz",
    "Nine Vicious", "Bleood", "Prettifun", "fakemink", "Feng",
]
IG_QUERY = [
    "{artist} interview site:instagram.com/reel",
    "{artist} studio site:instagram.com/reel",
    "{artist} live site:instagram.com/reel",
    "{artist} underground rap site:instagram.com/reel",
]
REEL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/reel/([A-Za-z0-9_-]+)/?")

CAPTION_SYSTEM = """You write 808 Dystopia IG Reel captions.
Voice: underground media, specific. Only facts in the payload.
Return ONLY JSON {"caption":"", "artist":"", "producer":""}.
producer is the beatmaker if named in the clip context, else empty.
No invented lore. No hashtag dump. No @ handles — we add those in code.
"""


def execute(slug, arguments):
    if not COMPOSIO_API_KEY:
        raise RuntimeError("Missing COMPOSIO_API_KEY")
    resp = requests.post(
        f"{COMPOSIO_BASE}/tools/execute/{slug}",
        headers={"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"},
        json={"arguments": arguments or {}, "user_id": COMPOSIO_USER_ID, "version": "latest"},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{slug} HTTP {resp.status_code}: {resp.text[:240]}")
    return resp.json()


def load_used():
    try:
        return set(json.load(open(USED_FILE)))
    except Exception:
        return set()


def save_used(used):
    try:
        json.dump(sorted(used), open(USED_FILE, "w"))
    except Exception as e:
        print(f"used-file: {e}", flush=True)


def dump_text(obj):
    try:
        return json.dumps(obj)
    except Exception:
        return str(obj)


def search_ig_reels(artist):
    q = random.choice(IG_QUERY).format(artist=artist)
    links = []
    for slug, args in (
        ("COMPOSIO_SEARCH", {"query": q}),
        ("COMPOSIO_SEARCH_WEB", {"query": q}),
        ("COMPOSIO_SEARCH_IMAGE", {"query": q, "num": 8}),
    ):
        try:
            raw = execute(slug, args)
        except Exception as e:
            print(f"{slug}: {e}", flush=True)
            continue
        for m in REEL_RE.finditer(dump_text(raw)):
            url = f"https://www.instagram.com/reel/{m.group(1)}/"
            if url not in links:
                links.append(url)
        if links:
            break
    return q, links


def pick_clip():
    used = load_used()
    artists = LANE[:]
    random.shuffle(artists)
    for artist in artists[:8]:
        q, links = search_ig_reels(artist)
        for url in links:
            code = REEL_RE.search(url).group(1)
            if code in used:
                continue
            return {
                "artist": artist,
                "query": q,
                "video_id": code,
                "url": url,
                "title": f"{artist} IG Reel",
                "channel": "Instagram",
                "description": "",
                "source": "instagram",
            }
    return None


def draft_caption(pick):
    artist = pick.get("artist") or ""
    producer = pick.get("producer") or ""
    fallback = apply_credits(
        f"{artist} — underground clip.\nSource: {pick.get('url') or '808 archive'}",
        artist=artist,
        producer=producer,
    )
    if not OPENAI_API_KEY:
        return fallback
    try:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.deepseek.com/v1")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": CAPTION_SYSTEM},
                {"role": "user", "content": json.dumps(pick)},
            ],
            temperature=0.7,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        data = json.loads(raw) if raw.startswith("{") else {"caption": raw}
        text = str(data.get("caption") or fallback)
        artist = str(data.get("artist") or artist)
        producer = str(data.get("producer") or producer)
        return apply_credits(text, artist=artist, producer=producer)
    except Exception as e:
        print(f"caption: {e}", flush=True)
        return fallback


def hashtags():
    return (
        "#808Dystopia #UndergroundRap #UndergroundHipHop #HipHopHistory\n"
        "#RapNews #UnsignedArtist #IndieHipHop #ProducerLife"
    )


def run_reel_job():
    now = datetime.now(CT).strftime("%a %b %d %Y %I:%M %p CT")
    print(f"REEL JOB IG {now}", flush=True)
    try:
        pick = pick_clip()
        if not pick:
            execute(
                "DISCORDBOT_CREATE_MESSAGE",
                {"channel_id": ADMIN_CHANNEL_ID, "content": f"808 Reel {now}\nNo unused IG Reel link. Skip."},
            )
            return None
        caption = draft_caption(pick)
        used = load_used()
        used.add(pick["video_id"])
        save_used(used)
        execute(
            "DISCORDBOT_CREATE_MESSAGE",
            {
                "channel_id": ADMIN_CHANNEL_ID,
                "content": (
                    f"808 IG Reel pick {now}\n"
                    f"Already 9:16 on Instagram.\n"
                    f"{pick['artist']}\n"
                    f"{pick['url']}\n\n"
                    f"Caption draft:\n{caption}\n\n"
                    f"First comment:\n{hashtags()}\n\n"
                    f"Graph API cannot download another account's file.\n"
                    f"Remix/share in the IG app, or attach the mp4 here."
                )[:1900],
            },
        )
        return pick
    except Exception as e:
        print(f"reel job: {e}", flush=True)
        try:
            execute(
                "DISCORDBOT_CREATE_MESSAGE",
                {"channel_id": ADMIN_CHANNEL_ID, "content": f"808 Reel failed: {e}"},
            )
        except Exception:
            pass
        return None


if __name__ == "__main__":
    run_reel_job()
