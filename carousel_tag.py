"""Always @ the artist in the caption. Known handles first, then a public search."""
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
    "karrahbooo": "karrahbooo",
}


def resolve_handle(artist):
    key = re.sub(r"[^a-z0-9]+", " ", (artist or "").lower()).strip()
    if key in KNOWN:
        return KNOWN[key]
    for name, handle in KNOWN.items():
        if name in key or key in name:
            return handle
    try:
        raw = execute_composio_tool(
            "COMPOSIO_SEARCH_WEB",
            {"query": f"{artist} official Instagram handle"},
        )
        blob = json.dumps(raw).lower()
        hits = re.findall(r"instagram\.com/([a-z0-9._]{2,30})", blob)
        at = re.findall(r"@([a-z0-9._]{2,30})", blob)
        for cand in hits + at:
            if cand in ("p", "reel", "reels", "stories", "explore"):
                continue
            return cand
    except Exception as e:
        print(f"handle search: {e}", flush=True)
    slug = re.sub(r"[^a-z0-9]+", "", key)
    return slug or ""


def apply_at(caption, handle, artist=""):
    cap = (caption or "").strip()
    if handle:
        tag = f"@{handle}"
        if tag.lower() not in cap.lower():
            cap = f"{tag} {cap}".strip()
        cap = re.sub(rf"Credit\s+{re.escape(artist)}", f"Credit {tag}", cap, flags=re.I) if artist else cap
        if f"credit {tag.lower()}" not in cap.lower() and "credit @" not in cap.lower():
            cap += f"\nCredit {tag}"
    if "follow for more" not in cap.lower():
        cap += "\nFollow for more."
    return cap[:900]
