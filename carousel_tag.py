"""Always @ the artist and producer. Known handles first, then a public search."""
from __future__ import annotations

import json
import re

from pinterest_bot import execute_composio_tool

KNOWN = {
    "nemzzz": "nemzzz_",
    "yeat": "yeat",
    "che": "praiseche",
    "nettspend": "nettspend_",
    "osamason": "osamason",
    "lazer dim 700": "lazerdim700",
    "lazerdim700": "lazerdim700",
    "karrahbooo": "karrahbooo",
    "xaviersobased": "xaviersobased",
    "glokk40spaz": "glokk40spaz",
    "nine vicious": "ninevicious",
    "prettifun": "prettifun",
    "fakemink": "fakemink",
    "feng": "4eversick",
    "bleood": "bleood",
    "lil yachty": "lilyachty",
    "travis scott": "travisscott",
    "latto": "latto",
    "cash cobain": "cashcobain",
    "tunde": "tunde",
}


def resolve_handle(name):
    key = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()
    if not key:
        return ""
    if key in KNOWN:
        return KNOWN[key]
    compact = key.replace(" ", "")
    if compact in KNOWN:
        return KNOWN[compact]
    for known, handle in KNOWN.items():
        if known in key or key in known:
            return handle
    try:
        raw = execute_composio_tool(
            "COMPOSIO_SEARCH_WEB",
            {"query": f"{name} official Instagram handle"},
        )
        blob = json.dumps(raw).lower()
        hits = re.findall(r"instagram\.com/([a-z0-9._]{2,30})", blob)
        at = re.findall(r"@([a-z0-9._]{2,30})", blob)
        skip = {"p", "reel", "reels", "stories", "explore", "tv", "accounts"}
        for cand in hits + at:
            if cand in skip:
                continue
            return cand
    except Exception as e:
        print(f"handle search: {e}", flush=True)
    return re.sub(r"[^a-z0-9]+", "", key)


def apply_at(caption, handle, artist=""):
    return apply_credits(caption, artist=artist or handle, producer="")


def apply_credits(caption, artist="", producer=""):
    cap = (caption or "").strip()
    a_tag = f"@{resolve_handle(artist)}" if artist else ""
    p_tag = f"@{resolve_handle(producer)}" if producer else ""
    if a_tag.endswith("@"):
        a_tag = ""
    if p_tag.endswith("@"):
        p_tag = ""
    if a_tag and a_tag.lower() not in cap.lower():
        cap = f"{a_tag} {cap}".strip()
    if artist:
        cap = re.sub(rf"Credit\s+{re.escape(artist)}", f"Credit {a_tag or artist}", cap, flags=re.I)
    if a_tag and f"artist: {a_tag.lower()}" not in cap.lower():
        cap += f"\nArtist: {a_tag}"
    if p_tag and f"producer: {p_tag.lower()}" not in cap.lower():
        cap += f"\nProducer: {p_tag}"
    if a_tag and "credit @" not in cap.lower():
        cap += f"\nCredit {a_tag}"
        if p_tag:
            cap += f" / {p_tag}"
    if "follow for more" not in cap.lower():
        cap += "\nFollow for more."
    return cap[:900]
