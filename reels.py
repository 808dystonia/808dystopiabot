"""7:00 PM CT history Reel job. Pick + download + Discord stage + optional IG."""
from __future__ import annotations

import json
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from openai import OpenAI

from reel_media import process_url
from reel_publish import publish_reel

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "1542355862079807509")
USED_FILE = os.getenv("REELS_USED_FILE", "/tmp/808_reels_used.json")
CT = ZoneInfo("America/Chicago")

IG_REEL_MAX_SEC = int(os.getenv("IG_REEL_MAX_SEC", "90"))
IG_REEL_MIN_SEC = 5
PUBLISH_TO_IG = os.getenv("REELS_PUBLISH_TO_IG", "0") == "1"

LANE = [
    "OsamaSon", "Nettspend", "xaviersobased", "Che", "Glokk40Spaz",
    "Nine Vicious", "Bleood", "Prettifun", "fakemink", "Feng",
    "EsDeeKid", "Nemzzz", "Fimiguerrero", "Yhapojj", "Ohsxnta",
]
QUERY_SHAPES = [
    "{artist} interview underground rap",
    "{artist} studio session",
    "{artist} live performance",
    "{artist} song breakdown",
    "{artist} documentary",
    "{artist} making of",
]

CAPTION_SYSTEM = """You write 808 Dystopia IG Reel captions.
Voice: underground media, specific, not corporate, not generic hype.
Required shape (5-8 short lines): hook, real details, optional transcript quote, why it matters, Artist, Source URL, Follow for more.
Only facts in the payload. Never invent lore. No hashtag dump.
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
        with open(USED_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_used(used):
    try:
        with open(USED_FILE, "w") as f:
            json.dump(sorted(used), f)
    except Exception as e:
        print(f"used-file: {e}", flush=True)


def parse_iso_duration(s):
    if not s or not isinstance(s, str):
        return None
    s = s.replace("PT", "")
    hours = mins = secs = 0
    num = ""
    for ch in s:
        if ch.isdigit():
            num += ch
        elif ch == "H":
            hours = int(num or 0)
            num = ""
        elif ch == "M":
            mins = int(num or 0)
            num = ""
        elif ch == "S":
            secs = int(num or 0)
            num = ""
    return hours * 3600 + mins * 60 + secs


def fetch_transcript(video_id):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        segs = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        text = " ".join((s.get("text") or "").strip() for s in segs if s.get("text"))
        return " ".join(text.split())[:1500]
    except Exception as e:
        print(f"transcript {video_id}: {e}", flush=True)
        return ""


def search_youtube(artist):
    q = random.choice(QUERY_SHAPES).format(artist=artist)
    raw = execute(
        "YOUTUBE_SEARCH_YOU_TUBE",
        {"q": q, "type": "video", "maxResults": 8, "order": "relevance", "regionCode": "US"},
    )
    data = raw.get("data") if isinstance(raw, dict) else {}
    items = data.get("items") or data.get("data", {}).get("items") or []
    ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        vid = (it.get("id") or {})
        if isinstance(vid, dict):
            vid = vid.get("videoId")
        if vid:
            ids.append(str(vid))
    return q, ids


def video_details(ids):
    if not ids:
        return []
    raw = execute(
        "YOUTUBE_GET_VIDEO_DETAILS_BATCH",
        {"id": ids[:15], "parts": ["snippet", "contentDetails", "statistics", "status"]},
    )
    data = raw.get("data") if isinstance(raw, dict) else {}
    return data.get("items") or data.get("videos") or []


def pick_clip():
    used = load_used()
    artists = LANE[:]
    random.shuffle(artists)
    for artist in artists[:6]:
        q, ids = search_youtube(artist)
        fresh = [i for i in ids if i not in used]
        details = video_details(fresh or ids)
        for item in details:
            if not isinstance(item, dict):
                continue
            vid = item.get("id")
            if not vid or vid in used:
                continue
            sn = item.get("snippet") or {}
            cd = item.get("contentDetails") or {}
            st = item.get("status") or {}
            stats = item.get("statistics") or {}
            if st.get("privacyStatus") and st.get("privacyStatus") != "public":
                continue
            seconds = parse_iso_duration(cd.get("duration"))
            if seconds is not None and seconds < IG_REEL_MIN_SEC:
                continue
            title = sn.get("title") or ""
            low = title.lower()
            if any(bad in low for bad in ("full album", "hour mix", "3 hour", "playlist")):
                continue
            return {
                "artist": artist,
                "query": q,
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": title,
                "channel": sn.get("channelTitle") or "",
                "description": (sn.get("description") or "")[:800],
                "published_at": sn.get("publishedAt") or "",
                "tags": (sn.get("tags") or [])[:12],
                "views": stats.get("viewCount"),
                "seconds": seconds,
                "trim": bool(seconds and seconds > IG_REEL_MAX_SEC),
                "transcript": fetch_transcript(vid),
            }
    return None


def draft_caption(pick):
    fallback = (
        f"{pick['title']}\n"
        f"Artist: {pick['artist']}\n"
        f"Source: {pick['channel']} — {pick['url']}\n"
        f"Follow for more."
    )
    if not OPENAI_API_KEY:
        return fallback
    try:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.deepseek.com/v1")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": CAPTION_SYSTEM},
                {"role": "user", "content": json.dumps(pick, default=str)},
            ],
            temperature=0.7,
        )
        text = (resp.choices[0].message.content or "").strip()
        if pick["artist"].lower() not in text.lower():
            text = f"Artist: {pick['artist']}\n{text}"
        if "follow for more" not in text.lower():
            text = text + "\nFollow for more."
        return text[:900]
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
    print(f"REEL JOB {now}", flush=True)
    try:
        pick = pick_clip()
        if not pick:
            execute("DISCORDBOT_CREATE_MESSAGE", {"channel_id": ADMIN_CHANNEL_ID, "content": f"808 Reel {now}\nNo unused clip. Skip."})
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
                    f"808 Reel pick {now}\n"
                    f"{pick['artist']} — {pick['title']}\n"
                    f"{pick['url']}\n\n"
                    f"Caption:\n{caption}\n\n"
                    f"First comment:\n{hashtags()}\n\n"
                    f"Grabbing mp4..."
                )[:1900],
            },
        )
        try:
            media = process_url(pick["url"], pick["video_id"])
        except Exception as e:
            execute(
                "DISCORDBOT_CREATE_MESSAGE",
                {
                    "channel_id": ADMIN_CHANNEL_ID,
                    "content": f"808 mp4 grab failed: {e}\nAttach the file here and ingest will take it.",
                },
            )
            return pick
        publish_reel(media["url"], caption)
        return pick
    except Exception as e:
        print(f"reel job: {e}", flush=True)
        try:
            execute("DISCORDBOT_CREATE_MESSAGE", {"channel_id": ADMIN_CHANNEL_ID, "content": f"808 Reel failed: {e}"})
        except Exception:
            pass
        return None


if __name__ == "__main__":
    run_reel_job()
