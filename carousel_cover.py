"""Pick the artwork that ships with the song, not a random artist photo."""
from __future__ import annotations

from pinterest_bot import execute_composio_tool, lookup_artist_image

PREFERRED = ("scdn.co", "genius.com", "mzstatic.com", "i.ibb.co")


def _results(raw):
    data = raw.get("data") if isinstance(raw, dict) else {}
    if not isinstance(data, dict):
        return []
    inner = data.get("results") or data
    if isinstance(inner, dict):
        return inner.get("images_results") or []
    return []


def pick_official_cover(artist, title):
    query = f"{artist} {title} official cover art"
    try:
        raw = execute_composio_tool("COMPOSIO_SEARCH_IMAGE", {"query": query, "num": 10})
    except Exception as e:
        print(f"cover search: {e}", flush=True)
        raw = {}
    ranked = []
    for hit in _results(raw):
        if not isinstance(hit, dict):
            continue
        url = hit.get("original") or hit.get("thumbnail") or ""
        if not url.startswith("http"):
            continue
        host_score = 0
        low = url.lower()
        if "scdn.co" in low:
            host_score = 3
        elif "genius.com" in low or "mzstatic.com" in low:
            host_score = 2
        elif any(p in low for p in PREFERRED):
            host_score = 1
        title_l = (hit.get("title") or "").lower()
        if "cover" in title_l:
            host_score += 1
        ranked.append((host_score, url, hit.get("source") or "google"))
    ranked.sort(key=lambda x: -x[0])
    if ranked and ranked[0][0] >= 2:
        return {"ok": True, "url": ranked[0][1], "source": ranked[0][2]}
    fallback = lookup_artist_image(f"{artist} {title} cover", artist, title)
    if fallback.get("ok"):
        return fallback
    if ranked:
        return {"ok": True, "url": ranked[0][1], "source": ranked[0][2]}
    return {"ok": False, "url": "", "source": ""}
