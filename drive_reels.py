"""Pull mp4s you drop in Drive History Posts, watermark, caption, post.
Never processes the same file twice (Drive ledger + Posted folder + name).
Watermark lock: top-left monogram + 808 DYSTOPIA.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import requests
from openai import OpenAI

from reel_media import crop_to_916, host_mp4, probe
from reel_publish import announce_discord, publish_reel
from carousel_tag import apply_credits

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
DRIVE_HISTORY = os.getenv("DRIVE_HISTORY_FOLDER_ID", "1lKG3gWXAnvzVVlQdO89z4VrROjHhxMNP")
DRIVE_POSTED = os.getenv("DRIVE_POSTED_FOLDER_ID", "1E_6CoDH9wBBqt7XyVtwsulD-LGP8BC4k")
LEDGER_FILE_ID = os.getenv("DRIVE_REELS_LEDGER_ID", "1WVlwf9HxvGRB2z6nRu0bL_GCrnYLD38W")
LOGO_FILE_ID = os.getenv("DRIVE_LOGO_FILE_ID", "18p2f3hlWQhK2tpt8Ll46B55kD_behsXi")
LOGO_CACHE = Path(os.getenv("DRIVE_LOGO_CACHE", "/tmp/808reels/808-Dystopia_Monogram_White-on-Black.jpg"))
SEEN_FILE = Path(os.getenv("DRIVE_REELS_SEEN", "/tmp/808_drive_reels_seen.json"))
WORKDIR = Path("/tmp/808reels/drive")
VIDEO_MARKERS = (".mp4", ".mov", ".m4v", ".webm", "video/")
HASHTAG_BATCHES = [
    "#808Dystopia #UndergroundRap #UndergroundHipHop #HipHopHistory",
    "#RapNews #UnsignedArtist #IndieHipHop #ProducerLife",
]


def execute(slug, arguments):
    resp = requests.post(
        f"{COMPOSIO_BASE}/tools/execute/{slug}",
        headers={"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"},
        json={"arguments": arguments or {}, "user_id": COMPOSIO_USER_ID, "version": "latest"},
        timeout=180,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{slug} HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def norm_name(name):
    return " ".join((name or "").lower().replace("_", " ").replace("-", " ").split())


def empty_ledger():
    return {"ids": [], "names": []}


def load_ledger():
    ledger = empty_ledger()
    try:
        local = json.loads(SEEN_FILE.read_text())
        if isinstance(local, dict):
            ledger["ids"] = list(local.get("ids") or [])
            ledger["names"] = list(local.get("names") or [])
        elif isinstance(local, list):
            ledger["ids"] = [str(x) for x in local]
    except Exception:
        pass
    try:
        dest = WORKDIR / "_808_reels_posted.json"
        download_drive(LEDGER_FILE_ID, dest)
        data = json.loads(dest.read_text())
        ledger["ids"] = list({*ledger["ids"], *[str(x) for x in data.get("ids") or []]})
        ledger["names"] = list({*ledger["names"], *[norm_name(x) for x in data.get("names") or []]})
    except Exception as e:
        print(f"ledger drive: {e}", flush=True)
    return ledger


def save_ledger(ledger):
    payload = {
        "ids": sorted(set(str(x) for x in ledger.get("ids") or [])),
        "names": sorted(set(norm_name(x) for x in ledger.get("names") or [])),
    }
    WORKDIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(payload))
    try:
        execute(
            "GOOGLEDRIVE_EDIT_FILE",
            {"file_id": LEDGER_FILE_ID, "content": json.dumps(payload, indent=2), "mime_type": "application/json"},
        )
    except Exception as e:
        print(f"ledger save: {e}", flush=True)


def already_done(fid, name, ledger):
    if fid and fid in set(ledger.get("ids") or []):
        return True
    return norm_name(name) in set(ledger.get("names") or [])


def mark_done(fid, name, ledger):
    ledger.setdefault("ids", []).append(str(fid))
    ledger.setdefault("names", []).append(norm_name(name))
    save_ledger(ledger)
    try:
        execute(
            "GOOGLEDRIVE_MOVE_FILE",
            {"file_id": fid, "add_parents": DRIVE_POSTED, "remove_parents": DRIVE_HISTORY},
        )
    except Exception as e:
        print(f"move posted: {e}", flush=True)


def list_drive_videos():
    raw = execute(
        "GOOGLEDRIVE_FIND_FILE",
        {
            "folder_id": DRIVE_HISTORY,
            "q": "trashed = false",
            "pageSize": 50,
            "orderBy": "modifiedTime desc",
        },
    )
    data = raw.get("data") if isinstance(raw, dict) else {}
    files = data.get("files") or data.get("items") or []
    out = []
    for f in files:
        if not isinstance(f, dict):
            continue
        name = f.get("name") or ""
        mime = (f.get("mimeType") or "").lower()
        if name.startswith("_808_"):
            continue
        if mime.startswith("application/vnd.google-apps"):
            continue
        parents = f.get("parents") or []
        if DRIVE_POSTED in parents:
            continue
        blob = f"{name} {mime}".lower()
        if not any(m in blob for m in VIDEO_MARKERS):
            continue
        out.append(f)
    return out


def download_drive(file_id, dest: Path):
    raw = execute("GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": file_id})
    data = raw.get("data") if isinstance(raw, dict) else {}
    content = data.get("downloaded_file_content") or {}
    s3 = content.get("s3url") or content.get("s3_url") or data.get("s3url")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if s3:
        r = requests.get(s3, timeout=180)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return dest
    raise RuntimeError(f"no s3url in download: {str(data)[:200]}")


def logo_path():
    if LOGO_CACHE.exists() and LOGO_CACHE.stat().st_size > 1000:
        return LOGO_CACHE
    download_drive(LOGO_FILE_ID, LOGO_CACHE)
    return LOGO_CACHE


def watermark(src: Path, dest: Path):
    """Top-left monogram + 808 DYSTOPIA. Clear of IG Reels chrome."""
    tmp = dest.with_name(dest.stem + ".wm.tmp.mp4")
    if tmp.exists():
        tmp.unlink()
    logo = logo_path()
    cmd = [
        "ffmpeg", "-y", "-i", str(src), "-i", str(logo),
        "-filter_complex",
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base];"
        "[1:v]colorkey=0x000000:0.35:0.15,scale=160:160[lg];"
        "[base][lg]overlay=48:72,"
        "drawtext=text='808 DYSTOPIA':fontcolor=white@0.9:fontsize=34:"
        "x=48+160+20:y=72+(160-th)/2:borderw=2:bordercolor=black@0.55",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(tmp),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-300])
    probe(tmp)
    tmp.replace(dest)
    return dest


def caption_for(name):
    artist = name.split("_")[0].split("-")[0].rsplit(".", 1)[0]
    producer = ""
    fallback = apply_credits(f"{artist}\nSource: 808 archive", artist=artist, producer=producer)
    if not OPENAI_API_KEY:
        return fallback, artist
    try:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.deepseek.com/v1")
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "808 Dystopia Reel caption. Return ONLY JSON "
                        '{"caption":"","artist":"","producer":""}. '
                        "Artist from the filename. Producer only if the name/context names one. "
                        "No fake facts. No @ handles — code adds those. No hashtag dump."
                    ),
                },
                {"role": "user", "content": name},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        data = json.loads(raw) if raw.startswith("{") else {"caption": raw}
        artist = str(data.get("artist") or artist)
        producer = str(data.get("producer") or "")
        text = apply_credits(str(data.get("caption") or fallback), artist=artist, producer=producer)
        return text[:900], artist
    except Exception as e:
        print(f"caption: {e}", flush=True)
        return fallback, artist


def comment_hashtags(media_id):
    for batch in HASHTAG_BATCHES:
        try:
            execute("INSTAGRAM_POST_IG_MEDIA_COMMENTS", {"ig_media_id": media_id, "message": batch})
        except Exception as e:
            print(f"hashtag comment: {e}", flush=True)


def process_drive_reels():
    if not COMPOSIO_API_KEY:
        print("drive reels: no key", flush=True)
        return []
    ledger = load_ledger()
    posted = []
    for f in list_drive_videos():
        fid = str(f.get("id") or "")
        name = f.get("name") or fid
        if not fid or already_done(fid, name, ledger):
            print(f"skip used {name}", flush=True)
            continue
        print(f"drive reel {name}", flush=True)
        try:
            raw = download_drive(fid, WORKDIR / name)
            cropped, _ = crop_to_916(raw, WORKDIR / f"{Path(name).stem}_916.mp4")
            marked = watermark(cropped, WORKDIR / f"{Path(name).stem}_wm.mp4")
            hosted = host_mp4(marked)
            caption, _artist = caption_for(name)
            result = publish_reel(hosted, caption)
            media_id = (result or {}).get("media_id")
            if media_id:
                comment_hashtags(media_id)
            mark_done(fid, name, ledger)
            posted.append(name)
            announce_discord(f"808 Drive Reel processed: {name}\nhosted {hosted}\nmoved to Posted")
        except Exception as e:
            announce_discord(f"808 Drive Reel failed {name}: {e}")
            print(f"drive reel fail {name}: {e}", flush=True)
    return posted


if __name__ == "__main__":
    print(process_drive_reels())
