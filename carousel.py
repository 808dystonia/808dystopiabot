"""9:00 AM CT IG news carousel. v5 layout. Albums = tracklist. Singles = context slide."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

from pinterest_bot import execute_composio_tool, get_llm_client, lookup_artist_image
from reel_publish import announce_discord
from genius_pull import genius_tracklist

HEAT_CHANNEL = os.getenv("DISCORD_HEAT_CHANNEL_ID", "1545437232142360599")
IG_USER_ID = os.getenv("IG_USER_ID", "28902406756011804")
PUBLISH = os.getenv("CAROUSEL_PUBLISH", "0") == "1" or os.getenv("AUTO_PUBLISH", "0") == "1"
USED_FILE = Path(os.getenv("CAROUSEL_USED_FILE", "/tmp/808_carousel_used.json"))
USED_DRIVE_ID = os.getenv("CAROUSEL_USED_DRIVE_ID", "10fRHhw-MNlWcNKDWhyOIn0ZowmyBtRbk")
WORKDIR = Path("/tmp/808carousel")
CT = ZoneInfo("America/Chicago")
W, H = 1080, 1350
PHOTO_X, PHOTO_Y = 18, 12
PHOTO_W, PHOTO_H = W - 36, 708
TEXT_TOP, FOOTER_TOP = 720, 1188
USED_SEED = ["karrahbooo", "not da 2", "lazer dim 700", "ld7"]
NEWS_TMPL_ID = "1SmfujfYpPF20OX-hBoozPPPXQl8EZ3pl"
FONT_FILE_ID = os.getenv("CAROUSEL_FONT_ID", "1m7Ev0SCglKj70M87QnsOpcLubXNAppzN")
FONT_CACHE = WORKDIR / "Capture_it.ttf"
UGUU = "https://uguu.se/upload"
RED = "#E10600"
HASHTAGS = [
    "#808Dystopia #UndergroundRap #UndergroundHipHop #HipHopHistory",
    "#RapNews #UnsignedArtist #IndieHipHop #ProducerLife",
]


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _parse_used(raw):
    data = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(data, list):
        return {slugify(x) for x in data if x}
    if isinstance(data, dict):
        rows = data.get("slugs") or data.get("used") or data.get("ids") or []
        return {slugify(x) for x in rows if x}
    return set()


def load_used():
    """Union Drive + local. Never wipe memory just because one store is down."""
    local = None
    drive = None
    try:
        local = _parse_used(USED_FILE.read_text())
    except Exception:
        local = None
    if USED_DRIVE_ID:
        try:
            dest = WORKDIR / "_used_drive.json"
            download_drive(USED_DRIVE_ID, dest)
            drive = _parse_used(dest.read_text())
        except Exception as e:
            print(f"used drive load: {e}", flush=True)
            drive = None
    used = set()
    if local:
        used |= local
    if drive:
        used |= drive
    if not used:
        used = {slugify(s) for s in USED_SEED}
    return used


def save_used(used):
    payload = json.dumps(sorted(used))
    try:
        USED_FILE.parent.mkdir(parents=True, exist_ok=True)
        USED_FILE.write_text(payload)
    except Exception as e:
        print(f"used local save: {e}", flush=True)
    if not USED_DRIVE_ID:
        return
    try:
        execute_composio_tool(
            "GOOGLEDRIVE_EDIT_FILE",
            {"file_id": USED_DRIVE_ID, "content": payload, "mime_type": "application/json"},
        )
    except Exception as e:
        print(f"used drive save: {e}", flush=True)


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


def font(size):
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


def fill_width(draw, text, max_w, lo=48, hi=180):
    for size in range(hi, lo - 1, -2):
        f = font(size)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_w:
            return f
    return font(lo)


def wrap_text(draw, text, fnt, max_w):
    words = (text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        box = draw.textbbox((0, 0), trial, font=fnt)
        if box[2] - box[0] <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def template():
    path = WORKDIR / "news_template.png"
    if not path.exists():
        try:
            download_drive(NEWS_TMPL_ID, path)
        except Exception as e:
            print(f"template drive: {e}", flush=True)
            img = Image.new("RGB", (W, H), "black")
            img.save(path)
            return img.convert("RGB")
    return Image.open(path).convert("RGB").resize((W, H))


def fetch_photo(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGB")


def cover_fill(photo: Image.Image, tw, th):
    src = photo.copy()
    ratio = max(tw / src.width, th / src.height)
    nw, nh = int(src.width * ratio), int(src.height * ratio)
    src = src.resize((nw, nh), Image.Resampling.LANCZOS)
    x = max(0, min((nw - tw) // 2, nw - tw))
    y = max(0, min(int((nh - th) * 0.28), nh - th))
    return src.crop((x, y, x + tw, y + th))


def render_slide1(artist, hook, photo: Image.Image):
    base = template()
    base.paste(cover_fill(photo, PHOTO_W, PHOTO_H), (PHOTO_X, PHOTO_Y))
    draw = ImageDraw.Draw(base)
    badge = "NEWS"
    bf = font(28)
    bb = draw.textbbox((0, 0), badge, font=bf)
    nw, nh = bb[2] - bb[0] + 28, bb[3] - bb[1] + 16
    nx = (W - nw) // 2
    ny = PHOTO_Y + PHOTO_H - nh - 10
    draw.rectangle((nx, ny, nx + nw, ny + nh), fill="black", outline="white", width=3)
    draw.text((nx + 14, ny + 4), badge, font=bf, fill="white")
    draw.rectangle((0, TEXT_TOP, W, FOOTER_TOP), fill="black")
    name, hook_u = artist.upper(), hook.upper()
    fa = fill_width(draw, name, 1044, 80, 180)
    ba = draw.textbbox((0, 0), name, font=fa)
    fh = fill_width(draw, hook_u, 1032, 70, 140)
    bh = draw.textbbox((0, 0), hook_u, font=fh)
    ah, hh, gap = ba[3] - ba[1], bh[3] - bh[1], 10
    ty = TEXT_TOP + (FOOTER_TOP - TEXT_TOP - (ah + gap + hh)) // 2 - 8
    draw.text(((W - (ba[2] - ba[0])) // 2, ty), name, font=fa, fill="white")
    draw.text(((W - (bh[2] - bh[0])) // 2, ty + ah + gap), hook_u, font=fh, fill=RED)
    out = WORKDIR / "slide1.jpg"
    base.save(out, quality=93)
    return out


def render_slide2_tracks(title, tracks, photo: Image.Image, source=""):
    base = template()
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, W, FOOTER_TOP), fill="black")
    ttl = title.upper()
    ft = fill_width(draw, ttl, 1016, 50, 120)
    draw.text((36, 20), ttl, font=ft, fill="white")
    tb = draw.textbbox((0, 0), ttl, font=ft)
    draw.text((36, tb[3] + 28), f"TRACKLIST  -  {len(tracks)} TRACKS", font=font(30), fill="white")
    draw.rectangle((36, tb[3] + 66, 380, tb[3] + 72), fill=RED)
    body, featf = font(24), font(16)
    start_y = tb[3] + 90
    split = 9 if len(tracks) > 11 else max(len(tracks), 1)
    for i, track in enumerate(tracks[:18], 1):
        if isinstance(track, str):
            name, feat = track, ""
        else:
            name, feat = track.get("name") or "", track.get("feat") or ""
        col = 0 if i <= split else 1
        x = 36 if col == 0 else 556
        y = start_y + ((i - 1) % split) * 44
        draw.text((x, y), f"{i:02d}", font=body, fill=RED)
        draw.text((x + 50, y), name.upper()[:22], font=body, fill="white")
        if feat:
            nb = draw.textbbox((0, 0), name.upper()[:22], font=body)
            draw.text((x + 50 + nb[2] - nb[0] + 6, y + 3), f"FEAT. {feat.upper()[:16]}", font=featf, fill=RED)
    if source:
        draw.text((36, 1148), source.upper()[:48], font=font(18), fill="#888888")
    out = WORKDIR / "slide2.jpg"
    base.save(out, quality=93)
    return out


def render_slide2_single(title, brief, photo: Image.Image, source=""):
    base = template()
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, W, FOOTER_TOP), fill="black")
    ttl = title.upper()
    ft = fill_width(draw, ttl, 1016, 50, 110)
    draw.text((36, 20), ttl, font=ft, fill="white")
    tb = draw.textbbox((0, 0), ttl, font=ft)
    draw.text((36, tb[3] + 24), "SINGLE", font=font(28), fill=RED)
    draw.rectangle((36, tb[3] + 60, 220, tb[3] + 66), fill=RED)
    y = tb[3] + 90
    quote = (brief.get("quote") or "").strip()
    if quote:
        if not quote.startswith('"'):
            quote = f'"{quote.strip(chr(34))}"'
        qf = font(28)
        for line in wrap_text(draw, quote.upper(), qf, 1000):
            draw.text((36, y), line, font=qf, fill="white")
            y += 40
        y += 12
    body = font(26)
    for para in brief.get("lines") or []:
        for line in wrap_text(draw, str(para).upper(), body, 1000):
            draw.text((36, y), line, font=body, fill="#DDDDDD")
            y += 36
        y += 8
    if source:
        draw.text((36, 1148), source.upper()[:48], font=font(18), fill="#888888")
    out = WORKDIR / "slide2.jpg"
    base.save(out, quality=93)
    return out


def looks_single(item, tracks):
    blob = f"{item.get('line','')} {item.get('title','')}".lower()
    if any(w in blob for w in ("single", "diss", "video out", "surprise-dropped")):
        return True
    return len(tracks) <= 1


def fetch_tracks(artist, title):
    result = genius_tracklist(artist, title)
    tracks = result.get("tracks") or []
    if len(tracks) < 2:
        return {"tracks": [], "source": "", "verified": False}
    return result


def fetch_brief(item):
    llm = get_llm_client()
    fallback = {"quote": "", "lines": [item.get("line") or item["title"]], "caption": item.get("line") or ""}
    if not llm:
        return fallback
    try:
        resp = llm.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": '808 news. Return ONLY JSON {"quote":"short real lyric or empty","lines":["fact","fact"],"caption":"4-6 sentence caption"}. No fake lyrics. If diss/context is reported, say it. End caption with Credit ARTIST then Follow for more.',
                },
                {"role": "user", "content": f"{item['artist']} {item['title']}\n{item.get('line','')}"},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        data = json.loads(raw)
        lines = [str(x)[:80] for x in (data.get("lines") or [])][:6]
        cap = str(data.get("caption") or fallback["caption"])[:900]
        if "follow for more" not in cap.lower():
            cap += "\nFollow for more."
        if item["artist"].lower() not in cap.lower():
            cap += f"\nCredit {item['artist']}"
        return {"quote": str(data.get("quote") or "")[:80], "lines": lines or fallback["lines"], "caption": cap}
    except Exception as e:
        print(f"brief: {e}", flush=True)
        return fallback


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
            if e.get("description"):
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
        m = re.search(
            r"([A-Za-z0-9$][A-Za-z0-9$ .'xX]{1,40})\s+(?:dropped|dumped|out with|surprise-dropped)\s+\*?([^*—\-]+)",
            line,
            re.I,
        )
        if not m:
            m = re.search(r"([A-Za-z0-9$][A-Za-z0-9$ .'xX]{1,40})\s+\*([^*]+)\*", line)
        if not m:
            continue
        artist = m.group(1).strip(" -")
        title = re.split(r"\s+[—\-(]", m.group(2).strip(" *"))[0].strip(" .")
        if len(title) < 2 or len(artist) < 2:
            continue
        items.append({"artist": artist, "title": title, "line": line})
    return items


def pick_article():
    used = load_used()
    for it in parse_items(heat_text()):
        key = slugify(it["artist"] + it["title"])
        if any(s in key or s in slugify(it["line"]) for s in used):
            continue
        return it, key
    return None, None


def publish_carousel(urls, text):
    children = []
    for url in urls:
        created = execute_composio_tool(
            "INSTAGRAM_POST_IG_USER_MEDIA",
            {"ig_user_id": IG_USER_ID, "image_url": url, "is_carousel_item": True},
        )
        cid = (created.get("data") or {}).get("id")
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
    job = uuid.uuid4().hex[:6]
    now = datetime.now(CT).strftime("%a %b %d %Y %I:%M %p CT")
    WORKDIR.mkdir(parents=True, exist_ok=True)
    print(f"CAROUSEL job={job} {now}", flush=True)
    item, key = pick_article()
    if not item:
        announce_discord(f"808 carousel job={job} {now}\nNo unused Morning Heat album. Skip.")
        return None
    cover = lookup_artist_image(f"{item['artist']} {item['title']}", item["artist"], item["title"])
    if not cover.get("ok"):
        announce_discord(f"808 carousel job={job} skip {item['artist']} — no real photo.")
        return None
    photo = fetch_photo(cover["url"])
    tl = fetch_tracks(item["artist"], item["title"])
    tracks = tl.get("tracks") or []
    verified = bool(tl.get("verified"))
    hook = f'DROPS "{item["title"]}"'
    s1 = render_slide1(item["artist"], hook, photo)
    use_tracklist = verified and not looks_single(item, tracks)
    if use_tracklist:
        s2 = render_slide2_tracks(item["title"], tracks, photo, source=tl.get("source") or "SOURCE: GENIUS")
        cap = f"{item['line']}\n\nCredit {item['artist']}\nFollow for more."
    else:
        if not looks_single(item, tracks):
            announce_discord(
                f"808 carousel job={job}\n{item['artist']} — {item['title']}\n"
                "No verified Genius tracklist. Context slide, not a fake list."
            )
        brief = fetch_brief(item)
        s2 = render_slide2_single(item["title"], brief, photo, source="SOURCE: HEAT")
        cap = brief.get("caption") or item["line"]
    u1, u2 = host_image(s1), host_image(s2)
    announce_discord(
        f"808 carousel staged job={job} {now}\n{item['artist']} — {item['title']}\n"
        f"photo: {cover.get('source')} tracks={len(tracks)} verified={verified}\n"
        f"{u1}\n{u2}\n\n{cap}\n\npublish={'ON' if PUBLISH else 'OFF'}"
    )
    used = load_used()
    used.add(key)
    used.add(slugify(item["artist"]))
    save_used(used)
    if PUBLISH:
        mid = publish_carousel([u1, u2], cap[:900])
        announce_discord(f"808 carousel live job={job} media_id={mid}")
    return item


if __name__ == "__main__":
    run_carousel_job()
