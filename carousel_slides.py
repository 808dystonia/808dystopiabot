"""Larger slide-2 type. Fill the black field. Tracklist slide: no cover art."""
from __future__ import annotations

from PIL import ImageDraw

import carousel as c

RED = c.RED
W, H = c.W, c.H
FOOTER_TOP = c.FOOTER_TOP


def render_slide2_tracks(title, tracks, photo, source=""):
    base = c.template()
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, W, FOOTER_TOP), fill="black")
    ttl = title.upper()
    ft = c.fill_width(draw, ttl, 1016, 64, 150)
    draw.text((32, 16), ttl, font=ft, fill="white")
    tb = draw.textbbox((0, 0), ttl, font=ft)
    meta = c.font(36)
    draw.text((32, tb[3] + 20), f"TRACKLIST  -  {len(tracks)} TRACKS", font=meta, fill="white")
    draw.rectangle((32, tb[3] + 64, 420, tb[3] + 72), fill=RED)
    body, featf = c.font(30), c.font(20)
    start_y = tb[3] + 96
    split = 9 if len(tracks) > 11 else max(len(tracks), 1)
    row_h = 48 if len(tracks) <= 12 else 40
    for i, track in enumerate(tracks[:18], 1):
        if isinstance(track, str):
            name, feat = track, ""
        else:
            name, feat = track.get("name") or "", track.get("feat") or ""
        col = 0 if i <= split else 1
        x = 32 if col == 0 else 556
        y = start_y + ((i - 1) % split) * row_h
        draw.text((x, y), f"{i:02d}", font=body, fill=RED)
        draw.text((x + 58, y), name.upper()[:22], font=body, fill="white")
        if feat:
            nb = draw.textbbox((0, 0), name.upper()[:22], font=body)
            draw.text((x + 58 + nb[2] - nb[0] + 8, y + 4), f"FEAT. {feat.upper()[:16]}", font=featf, fill=RED)
    if source:
        draw.text((32, 1144), source.upper()[:48], font=c.font(18), fill="#888888")
    out = c.WORKDIR / "slide2.jpg"
    base.save(out, quality=93)
    return out


def render_slide2_single(title, brief, photo, source=""):
    base = c.template()
    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, W, FOOTER_TOP), fill="black")
    ttl = title.upper()
    ft = c.fill_width(draw, ttl, 1016, 64, 140)
    draw.text((32, 12), ttl, font=ft, fill="white")
    tb = draw.textbbox((0, 0), ttl, font=ft)
    draw.text((32, tb[3] + 12), "SINGLE", font=c.font(36), fill=RED)
    draw.rectangle((32, tb[3] + 56, 260, tb[3] + 64), fill=RED)
    y = tb[3] + 84
    quote = (brief.get("quote") or "").strip()
    if quote:
        if not quote.startswith('"'):
            quote = f'"{quote.strip(chr(34))}"'
        qf = c.font(40)
        for line in c.wrap_text(draw, quote.upper(), qf, 1016):
            draw.text((32, y), line, font=qf, fill="white")
            y += 50
        y += 18
    body = c.font(32)
    for para in brief.get("lines") or []:
        for line in c.wrap_text(draw, str(para).upper(), body, 1016):
            draw.text((32, y), line, font=body, fill="#E8E8E8")
            y += 42
        y += 10
    src = source or brief.get("source") or "SOURCE: GENIUS"
    draw.text((32, 1144), src.upper()[:48], font=c.font(18), fill="#888888")
    out = c.WORKDIR / "slide2.jpg"
    c.WORKDIR.mkdir(parents=True, exist_ok=True)
    base.save(out, quality=93)
    return out
