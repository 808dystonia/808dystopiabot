"""Official song cover only. Spotify/Genius first. No random artist photos."""
from __future__ import annotations

from pinterest_bot import execute_composio_tool, lookup_artist_image


def _results(raw):
    data = raw.get("data") if isinstance(raw, dict) else {}
    if not isinstance(data, dict):
        return []
    inner = data.get("results") or data
    if isinstance(inner, dict):
        return inner.get("images_results") or []
    return []


def _score(hit):
    url = (hit.get("original") or hit.get("thumbnail") or "").lower()
    title = (hit.get("title") or "").lower()
    source = (hit.get("source") or "").lower()
    if not url.startswith("http"):
        return -1
    score = 0
    if "scdn.co" in url:
        score += 8
    if "genius.com" in url or "images.genius.com" in url:
        score += 7
    if "mzstatic.com" in url:
        score += 6
    if "spotify" in source or "genius" in source:
        score += 3
    if "cover" in title or "single" in title:
        score += 2
    if any(bad in title for bad in ("pfp", "wallpaper", "concert", "live", "selfie")):
        score -= 5
    if "ytimg.com" in url or "tiktok" in url:
        score -= 4
    return score


def pick_official_cover(artist, title):
    queries = [
        f"{artist} {title} official single cover art spotify",
        f"{artist} {title} cover site:open.spotify.com",
        f"{artist} {title} official cover art",
    ]
    ranked = []
    for q in queries:
        try:
            raw = execute_composio_tool("COMPOSIO_SEARCH_IMAGE", {"query": q, "num": 10})
        except Exception as e:
            print(f"cover search: {e}", flush=True)
            continue
        for hit in _results(raw):
            if not isinstance(hit, dict):
                continue
            url = hit.get("original") or hit.get("thumbnail") or ""
            s = _score(hit)
            if s >= 6 and url.startswith("http"):
                ranked.append((s, url, hit.get("source") or "spotify"))
        if ranked:
            break
    ranked.sort(key=lambda x: -x[0])
    if ranked:
        return {"ok": True, "url": ranked[0][1], "source": ranked[0][2]}
    fallback = lookup_artist_image(f"{artist} {title} official cover", artist, title)
    return fallback if fallback.get("ok") else {"ok": False, "url": "", "source": ""}
