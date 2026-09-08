"""Download YouTube or Instagram clips with optional cookies, make Reel-safe, host MP4.
Does not publish to Instagram.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import requests

WORKDIR = Path(os.getenv("REEL_WORKDIR", "/tmp/808reels"))
UGUU = os.getenv("REEL_HOST_UPLOAD", "https://uguu.se/upload")
COOKIE_CANDIDATES = [
    os.getenv("YTDLP_COOKIES_FILE"),
    "/etc/secrets/youtube_cookies.txt",
    "/etc/secrets/cookies.txt",
    "/tmp/yt_cookies.txt",
]


def cookies_file():
    raw = os.getenv("YTDLP_COOKIES")
    if raw and "# Netscape" in raw or (raw and "youtube.com" in raw):
        path = Path("/tmp/yt_cookies.txt")
        path.write_text(raw)
        return str(path)
    for cand in COOKIE_CANDIDATES:
        if cand and Path(cand).is_file() and Path(cand).stat().st_size > 20:
            return cand
    return None


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
        "vcodec": vs.get("codec_name"),
        "acodec": aus.get("codec_name"),
    }


def ytdlp_base():
    cmd = ["yt-dlp"]
    ck = cookies_file()
    if ck:
        cmd += ["--cookies", ck]
        print(f"yt-dlp cookies: {ck}", flush=True)
    else:
        print("yt-dlp cookies: NONE — expect 403 on many videos", flush=True)
    return cmd


def download_url(url, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    out = dest.with_suffix(".%(ext)s")
    base = ytdlp_base()
    cmd = base + [
        "--extractor-args", "youtube:player_client=android,ios,web",
        "-f", "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4][height<=1080]/18/best",
        "--merge-output-format", "mp4",
        "-o", str(out),
        url,
    ]
    try:
        run(cmd)
    except Exception:
        run(base + ["-f", "18/best", "-o", str(out), url])
    found = list(dest.parent.glob(dest.stem + ".*"))
    if not found:
        raise RuntimeError("yt-dlp produced no file")
    return found[0]


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
    data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
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
    raw = download_url(url, WORKDIR / f"{slug}_raw.mp4")
    out = WORKDIR / f"{slug}_916.mp4"
    final, info = crop_to_916(raw, out)
    hosted = host_mp4(final)
    return {"file": str(final), "url": hosted, "probe": info, "source": url}


def process_youtube(url, slug):
    return process_url(url, slug)
