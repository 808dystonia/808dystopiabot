"""Get a Reel-safe MP4.

Order:
1. COBALT_API_URL if set (this is the reliable YouTube grab)
2. yt-dlp
3. Invidious
4. Fallback: 9:16 card built from the official YouTube thumbnail
   so Discord/IG still get a real mp4 when YouTube blocks the file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import requests

WORKDIR = Path(os.getenv("REEL_WORKDIR", "/tmp/808reels"))
UGUU = os.getenv("REEL_HOST_UPLOAD", "https://uguu.se/upload")
COBALT_API_URL = (os.getenv("COBALT_API_URL") or "").rstrip("/")
COBALT_API_KEY = os.getenv("COBALT_API_KEY") or ""
INVIDIOUS = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
]


def video_id_from(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{6,})", url or "")
    return m.group(1) if m else None


def run(cmd):
    print(" ".join(cmd), flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "cmd failed")[-400])
    return p.stdout


def probe(path):
    raw = run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)
    ])
    data = json.loads(raw)
    vs = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    aus = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "width": int(vs.get("width") or 0),
        "height": int(vs.get("height") or 0),
        "duration": float(data.get("format", {}).get("duration") or 0),
        "has_audio": bool(aus),
    }


def download_cobalt(url, dest: Path):
    if not COBALT_API_URL:
        raise RuntimeError("no COBALT_API_URL")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if COBALT_API_KEY:
        headers["Authorization"] = f"Bearer {COBALT_API_KEY}"
        headers["Api-Key"] = COBALT_API_KEY
    r = requests.post(
        COBALT_API_URL,
        headers=headers,
        json={"url": url, "videoQuality": "720", "youtubeVideoCodec": "h264"},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    media = data.get("url") or data.get("tunnel") or (data.get("picker") or [{}])[0].get("url")
    if not media:
        raise RuntimeError(f"cobalt no url: {str(data)[:200]}")
    g = requests.get(media, timeout=120)
    g.raise_for_status()
    dest.write_bytes(g.content)
    if dest.stat().st_size < 20000:
        raise RuntimeError("cobalt file too small")
    return dest


def download_ytdlp(url, dest: Path):
    out = dest.with_suffix(".%(ext)s")
    cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=android,ios,web",
        "-f", "b[ext=mp4][height<=720]/18/best",
        "--merge-output-format", "mp4",
        "-o", str(out),
        url,
    ]
    run(cmd)
    found = list(dest.parent.glob(dest.stem + ".*"))
    if not found:
        raise RuntimeError("yt-dlp no file")
    return found[0]


def download_invidious(url, dest: Path):
    vid = video_id_from(url)
    if not vid:
        raise RuntimeError("no video id")
    last = None
    for base in INVIDIOUS:
        try:
            r = requests.get(f"{base}/latest_version", params={"id": vid, "itag": "18"}, timeout=40)
            if r.status_code >= 400 or len(r.content) < 80000:
                last = f"{base} {r.status_code} {len(r.content)}"
                continue
            dest.write_bytes(r.content)
            return dest
        except Exception as e:
            last = str(e)
    raise RuntimeError(last or "invidious failed")


def download_thumb(video_id, dest: Path):
    last = None
    for name in ("maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg"):
        u = f"https://i.ytimg.com/vi/{video_id}/{name}"
        try:
            r = requests.get(u, timeout=20)
            if r.status_code == 200 and len(r.content) > 4000:
                dest.write_bytes(r.content)
                return dest
            last = f"{name} {r.status_code}"
        except Exception as e:
            last = str(e)
    raise RuntimeError(last or "no thumb")


def make_card_reel(thumb: Path, dest: Path, seconds=12):
    tmp = dest.with_name(dest.stem + ".tmp.mp4")
    if tmp.exists():
        tmp.unlink()
    run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(seconds), "-i", str(thumb),
        "-f", "lavfi", "-t", str(seconds), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-shortest",
        "-movflags", "+faststart",
        str(tmp),
    ])
    probe(tmp)
    tmp.replace(dest)
    return dest


def crop_to_916(src: Path, dest: Path):
    info = probe(src)
    w, h = info["width"], info["height"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + ".tmp.mp4")
    if tmp.exists():
        tmp.unlink()
    if w <= 0 or h <= 0:
        raise RuntimeError("bad video size")
    ratio = w / h
    target = 9 / 16
    if abs(ratio - target) < 0.03:
        vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    elif ratio > target:
        vf = "crop=ih*9/16:ih,scale=1080:1920"
    else:
        vf = "crop=iw:iw*16/9,scale=1080:1920"
    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(tmp),
    ])
    probe(tmp)
    tmp.replace(dest)
    return dest, probe(dest)


def host_mp4(path: Path):
    with path.open("rb") as f:
        resp = requests.post(UGUU, files={"files[]": (path.name, f, "video/mp4")}, timeout=120)
    resp.raise_for_status()
    data = {}
    try:
        data = resp.json()
    except Exception:
        pass
    url = None
    if isinstance(data, dict):
        files = data.get("files") or data.get("data") or []
        if files and isinstance(files, list):
            url = files[0].get("url") or files[0].get("hash")
        url = url or data.get("url")
    if not url:
        text = resp.text.strip()
        if text.startswith("http"):
            url = text.split()[0]
    if not url:
        raise RuntimeError(f"host upload failed: {resp.text[:200]}")
    return url


def process_url(url, slug):
    WORKDIR.mkdir(parents=True, exist_ok=True)
    raw = WORKDIR / f"{slug}_raw.mp4"
    kind = "source"
    errors = []
    for name, fn in (
        ("cobalt", lambda: download_cobalt(url, raw)),
        ("yt-dlp", lambda: download_ytdlp(url, raw)),
        ("invidious", lambda: download_invidious(url, raw)),
    ):
        try:
            got = fn()
            raw = Path(got)
            kind = name
            break
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"grab {name} fail: {e}", flush=True)
    else:
        vid = video_id_from(url) or slug
        thumb = WORKDIR / f"{slug}_thumb.jpg"
        download_thumb(vid, thumb)
        raw = WORKDIR / f"{slug}_card.mp4"
        make_card_reel(thumb, raw)
        kind = "thumb-card"
    out = WORKDIR / f"{slug}_916.mp4"
    if kind == "thumb-card":
        final, info = raw, probe(raw)
    else:
        final, info = crop_to_916(raw, out)
    hosted = host_mp4(final)
    return {
        "file": str(final),
        "url": hosted,
        "probe": info,
        "source": url,
        "kind": kind,
        "errors": errors,
    }
