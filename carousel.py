"""9:00 AM CT IG news carousel on Render. No Grok.
Type lock: Capture It (Phonto face) from Drive Fonts.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

from pinterest_bot import execute_composio_tool, lookup_artist_image
from reel_publish import announce_discord

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
HEAT_CHANNEL = os.getenv("DISCORD_HEAT_CHANNEL_ID", "1545437232142360599")
IG_USER_ID = os.getenv("IG_USER_ID", "28902406756011804")
PUBLISH = os.getenv("CAROUSEL_PUBLISH", "0") == "1"
USED_FILE = Path(os.getenv("CAROUSEL_USED_FILE", "/tmp/808_carousel_used.json"))
WORKDIR = Path("/tmp/808carousel")
CT = ZoneInfo("America/Chicago")
W, H = 1080, 1350
USED_SEED = ["karrahbooo", "not da 2", "lazer dim 700", "ld7"]
NEWS_TMPL_ID = "1SmfujfYpPF20OX-hBoozPPPXQl8EZ3pl"
FONT_FILE_ID = os.getenv("CAROUSEL_FONT_ID", "1m7Ev0SCglKj70M87QnsOpcLubXNAppzN")
FONT_CACHE = WORKDIR / "Capture_it.ttf"
UGUU = "https://uguu.se/upload"
HASHTAGS = [
    "#808Dystopia #UndergroundRap #UndergroundHipHop #HipHopHistory",
    "#RapNews #UnsignedArtist #IndieHipHop #ProducerLife",
]


def load_used():
    try:
        return set(json.loads(USED_FILE.read_text()))
    except Exception:
        return set(USED_SEED)


def save_used(used):
    USED_FILE.write_text(json.dumps(sorted(used)))


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def download_drive(file_id, dest: Path):
    raw = execute_composio_tool("GOOGLEDRIVE_DOWNLOAD_FILE", {"fileId": file_id})
    data = raw.get("data") if isinstance(raw, dict) else {}
    content = data.get("downloaded_file_content") or {}
    s3 = content.get("s3url") or data.get("s3url")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not s3:
        raise RuntimeError("no drive download")
    dest.write_bytes(requests.get(s3, timeout=60).content)
    return dest


def font_path():
    WORKDIR.mkdir(parents=True, exist_ok=True)
    if FONT_CACHE.exists() and FONT_CACHE.stat().st_size > 10000:
        return FONT_CACHE
    try:
        download_drive(FONT_FILE_ID, FONT_CACHE)
        return FONT_CACHE
    except Exception as e:
        print(f"font drive: {e}", flush=True)
        return None


def font(size, bold=True):
    p = font_path()
    if p:
        return ImageFont.truetype(str(p), size)
    for fallback in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(fallback).exists():
            return ImageFont.truetype(fallback, size)
    return ImageFont.load_default()


def fit_text(draw, text, max_w, start, min_size=36):
    size = start
    while size >= min_size:
        f = font(size)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_w:
            return f
        size -= 4
    return font(min_size)


def stroke_text(draw, xy, text, fnt, fill="white", stroke="black", width=3):
    draw.text(xy, text, font=fnt, fill=fill, stroke_width=width, stroke_fill=stroke)


def template():
    path = WORKDIR / "news_template.png"
    if not path.exists():
        try:
            download_drive(NEWS_TMPL_ID, path)
        except Exception as e:
            print(f"template drive: {e}", flush=True)
            img = Image.new("RGB", (W, H), "black")
            img.save(path)
            return img
    im = Image.open(path).convert("RGBA").resize((W, H))
    return im


def fetch_photo(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGB")


def cover_box(photo: Image.Image, box=(36, 36, 1044, 690)):
    x0, y0, x1, y1 = box
    tw, th = x1 - x0, y1 - y0
    src = photo.copy()
    src.thumbnail((tw, th), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (tw, th), (10, 10, 10))
    canvas.paste(src, ((tw - src.width) // 2, (th - src.height) // 2))
    return canvas


def render_slide1(artist, hook, photo: Image.Image):
    base = template().convert("RGB")
    framed = cover_box(photo)
    base.paste(framed, (36, 36))
    draw = ImageDraw.Draw(base)
    name_f = fit_text(draw, artist.upper(), 1000, 118)
    nb = draw.textbbox((0, 0), artist.upper(), font=name_f)
    nx = (W - (nb[2] - nb[0])) // 2
    stroke_text(draw, (nx, 760), artist.upper(), name_f, "white", "black", 4)
    hook_f = fit_text(draw, hook.upper(), 980, 72)
    hb = draw.textbbox((0, 0), hook.upper(), font=hook_f)
    hx = (W - (hb[2] - hb[0])) // 2
    fill = "#E10600" if '"' in hook or "\u201c" in hook else "white"
    stroke_text(draw, (hx, 900), hook.upper(), hook_f, fill, "black", 3)
    out = WORKDIR / "slide1.jpg"
    base.save(out, quality=92)
    return out


def render_slide2(title, tracks, photo: Image.Image):
    img = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(img)
    title_f = fit_text(draw, title.upper(), 700, 70)
    stroke_text(draw, (40, 36), title.upper(), title_f)
    meta_f = font(28)
    draw.text((40, 120), f"TRACKLIST  •  {len(tracks)} TRACKS", font=meta_f, fill="white")
    draw.rectangle((40, 158, 280, 162), fill="#E10600")
    y = 190
    body = font(28)
    for i, track in enumerate(tracks[:16], 1):
        draw.text((40, y), f"{i:02d}", font=body, fill="#E10600")
        draw.text((110, y), track.upper()[:28], font=body, fill="white")
        y += 42
    thumb = cover_box(photo, (0, 0, 360, 360))
    img.paste(thumb, (680, 40))
    draw.text((40, 1260), "SWIPE", font=font(22), fill="white")
    out = WORKDIR / "slide2.jpg"
    img.save(out, quality=92)
    return out


def host_image(path: Path):
    with path.open("rb") as f:
        resp = requests.post(UGUU, files={"files[]": (path.name, f, "image/jpeg")}, timeout=60)
    data = resp.json()
    files = data.get("files") or []
    url = files[0].get("url") if files else data.get("url")
    if not url:
        raise RuntimeError(resp.text[:200])
    return url


def heat_text():
    raw = execute_composio_tool("DISCORDBOT_LIST_MESSAGES", {"channel_id": HEAT_CHANNEL, "limit": 15})
    data = raw.get("data") if isinstance(raw, dict) else {}
    msgs = data.get("messages") or []
    blobs = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        for e in m.get("embeds") or []:
            if (e.get("title") or "").lower().find("heat") >= 0 or e.get("description"):
                blobs.append(e.get("description") or "")
    return "\n".join(blobs)


def parse_items(blob):
    items = []
    for line in blob.splitlines():
        line = line.strip(" •-*")
        if len(line) < 12:
            continue
        low = line.lower()
        if any(s in low for s in ("history note", "emerging", "keep eyes")):
            continue
        m = re.search(r"([A-Za-z0-9$][A-Za-z0-9$ .'xX]{1,40})\s+(?:dropped|dumped|out with|surprise-dropped)\s+\*?([^*\u2014\-]+)", line, re.I)
        if not m:
            m = re.search(r"([A-Za-z0-9$][A-Za-z0-9$ .'xX]{1,40})\s+\*([^*]+)\*", line)
        if not m:
            continue
        artist = m.group(1).strip(" -")
        title = re.split(r"\s+[\u2014\-(]", m.group(2).strip(" *"))[0].strip(" .")
        if len(title) < 2 or len(artist) < 2:
            continue
        items.append({"artist": artist, "title": title, "line": line})
    return items


def pick_article():
    used = load_used()
    items = parse_items(heat_text())
    for it in items:
        key = slugify(it["artist"] + it["title"])
        if any(s in key or s in slugify(it["line"]) for s in used):
            continue
        return it, key
    return None, None


def caption(item):
    return f"{item['line']}\n\nCredit {item['artist']}\nFollow for more."[:900]


def publish_carousel(urls, text):
    children = []
    for url in urls:
        created = execute_composio_tool(
            "INSTAGRAM_POST_IG_USER_MEDIA",
            {"ig_user_id": IG_USER_ID, "image_url": url, "is_carousel_item": True},
        )
        data = created.get("data") if isinstance(created, dict) else {}
        cid = data.get("id")
        if not cid:
            raise RuntimeError(f"no child id {created}")
        children.append(cid)
    parent = execute_composio_tool(
        "INSTAGRAM_POST_IG_USER_MEDIA",
        {"ig_user_id": IG_USER_ID, "media_type": "CAROUSEL", "children": children, "caption": text},
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
                execute_composio_tool("INSTAGRAM_POST_IG_MEDIA_COMMENTS", {"ig_media_id": media_id, "message": batch})
            except Exception as e:
                print(f"comment: {e}", flush=True)
    return media_id


def run_carousel_job():
    now = datetime.now(CT).strftime("%a %b %d %Y %I:%M %p CT")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    print(f"CAROUSEL {now}", flush=True)
    item, key = pick_article()
    if not item:
        announce_discord(f"808 carousel {now}\nNo unused Morning Heat album. Skip.")
        return None
    cover = lookup_artist_image(f"{item['artist']} {item['title']}", item["artist"], item["title"])
    if not cover.get("ok"):
        announce_discord(f"808 carousel skip {item['artist']} — no real photo.")
        return None
    photo = fetch_photo(cover["url"])
    hook = f'DROPS "{item["title"]}"'
    s1 = render_slide1(item["artist"], hook, photo)
    s2 = render_slide2(item["title"], [item["title"], "MORE INFO ON SLIDE 1"], photo)
    u1, u2 = host_image(s1), host_image(s2)
    cap = caption(item)
    announce_discord(
        f"808 carousel staged {now}\n{item['artist']} — {item['title']}\n"
        f"photo: {cover.get('source')}\n{u1}\n{u2}\n\n{cap}\n\npublish={'ON' if PUBLISH else 'OFF'}"
    )
    used = load_used()
    used.add(key)
    used.add(slugify(item["artist"]))
    save_used(used)
    if PUBLISH:
        mid = publish_carousel([u1, u2], cap)
        announce_discord(f"808 carousel live media_id={mid}")
    return item


if __name__ == "__main__":
    run_carousel_job()
