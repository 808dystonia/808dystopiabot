"""Genius-only lyrics + annotation for 808 single slides.
Tracklists come from Genius search dumps, never invented by the LLM.
"""
from __future__ import annotations

import json
import re

from pinterest_bot import execute_composio_tool, get_llm_client


def _blob(raw):
    return json.dumps(raw, ensure_ascii=True)[:8000]


def _search(query):
    try:
        return execute_composio_tool("COMPOSIO_SEARCH_WEB", {"query": query})
    except Exception as e:
        print(f"genius search: {e}", flush=True)
        return {}


def _split_feat(name):
    name = re.sub(r"\s+", " ", (name or "").strip())
    name = re.sub(r"^\d{1,2}\s*[.)-]?\s*", "", name)
    m = re.search(
        r"^(.*?)(?:\s*[\(\[]\s*(?:feat\.?|ft\.?|featuring)\s+([^\)\]]+)[\)\]]|\s+feat\.?\s+(.+))$",
        name,
        re.I,
    )
    if not m:
        return name[:40], ""
    feat = (m.group(2) or m.group(3) or "").strip(" -")
    return m.group(1).strip(" -")[:40], feat[:24]


def _parse_tracks_from_text(blob):
    tracks = []
    seen = set()
    for line in (blob or "").splitlines():
        line = line.strip().strip("-•*")
        m = re.match(r"^(?:track\s*)?(\d{1,2})\s*[.)\-:]\s+(.+)$", line, re.I)
        if not m:
            m = re.match(r"^(\d{1,2})\s{2,}(.+)$", line)
        if not m:
            continue
        raw_name = m.group(2).strip()
        if len(raw_name) < 2:
            continue
        low = raw_name.lower()
        if any(b in low for b in ("lyrics", "annotation", "about this", "read more", "contributors")):
            continue
        name, feat = _split_feat(raw_name)
        key = re.sub(r"[^a-z0-9]+", "", name.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        tracks.append({"name": name, "feat": feat})
        if len(tracks) >= 18:
            break
    return tracks


def genius_tracklist(artist, title):
    """Return verified tracks only. Empty list if Genius dump has no numbered list."""
    empty = {"tracks": [], "source": "", "verified": False}
    artist = artist or ""
    title = title or ""
    if not artist or not title:
        return empty
    lyrics_raw = _search(f"site:genius.com {artist} {title} lyrics")
    album_raw = _search(f"site:genius.com {artist} {title} album tracklist")
    packed = (
        f"ARTIST: {artist}\nTITLE: {title}\n\n"
        f"GENIUS LYRICS SEARCH:\n{_blob(lyrics_raw)}\n\n"
        f"GENIUS ALBUM SEARCH:\n{_blob(album_raw)}"
    )
    tracks = _parse_tracks_from_text(packed)
    if len(tracks) >= 2:
        return {"tracks": tracks, "source": "SOURCE: GENIUS", "verified": True}

    llm = get_llm_client()
    if not llm:
        return empty
    try:
        resp = llm.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract a tracklist ONLY if the dump contains a real numbered Genius track list. "
                        'Return ONLY JSON: {"tracks":[{"name":"","feat":""}]}. '
                        "Copy titles as written. feat is empty unless the dump names a feature. "
                        "If there is no numbered list, return {\"tracks\":[]}. "
                        "Never invent songs. Never guess a single as a fake album list."
                    ),
                },
                {"role": "user", "content": packed[:7000]},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        data = json.loads(raw)
        out = []
        seen = set()
        for row in data.get("tracks") or []:
            if isinstance(row, str):
                name, feat = _split_feat(row)
            elif isinstance(row, dict) and row.get("name"):
                name, feat = _split_feat(str(row.get("name") or ""))
                feat = str(row.get("feat") or feat or "")[:24]
            else:
                continue
            key = re.sub(r"[^a-z0-9]+", "", name.lower())
            if not key or key in seen:
                continue
            seen.add(key)
            out.append({"name": name[:40], "feat": feat[:24]})
        if len(out) >= 2:
            return {"tracks": out[:18], "source": "SOURCE: GENIUS", "verified": True}
    except Exception as e:
        print(f"genius tracklist: {e}", flush=True)
    return empty


def genius_brief(item):
    artist = item.get("artist") or ""
    title = item.get("title") or ""
    heat = item.get("line") or ""
    fallback = {
        "quote": "",
        "lines": [heat or title],
        "caption": f"{heat}\n\nCredit {artist}\nFollow for more.",
        "source": "SOURCE: HEAT",
    }
    lyrics_raw = _search(f"site:genius.com {artist} {title} lyrics")
    annot_raw = _search(f"site:genius.com {artist} {title} annotation diss meaning")
    packed = (
        f"ARTIST: {artist}\nTITLE: {title}\nHEAT: {heat}\n\n"
        f"GENIUS SEARCH:\n{_blob(lyrics_raw)}\n\n"
        f"ANNOTATION SEARCH:\n{_blob(annot_raw)}"
    )
    llm = get_llm_client()
    if not llm:
        return fallback
    try:
        resp = llm.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "808 Dystopia single card. Use ONLY facts in the dump. "
                        'Return ONLY JSON: {"quote":"","lines":["",""],"caption":""}. '
                        "quote = one short lyric copied EXACTLY as Genius spells it. "
                        "If no verified Genius lyric exists, quote MUST be empty. "
                        "NEVER write that Genius is missing, that there is no page, or that there is no quote. "
                        "Do not put those notes in lines or caption either. Just skip the quote. "
                        "lines = 4-6 short facts (who, when, producer, why it matters). "
                        "caption = 4-6 sentences of that depth, then Credit ARTIST, Follow for more. "
                        "Only add Lyrics/context: Genius if a real quote was used."
                    ),
                },
                {"role": "user", "content": packed[:7000]},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        data = json.loads(raw)
        quote = str(data.get("quote") or "").strip()
        banned = ("no genius", "genius page", "no quote", "no lyrics page", "not on genius")
        if quote and not re.search(r"[A-Za-z]", quote):
            quote = ""
        if any(b in quote.lower() for b in banned):
            quote = ""
        lines = []
        for x in data.get("lines") or []:
            t = str(x).strip()
            if not t or any(b in t.lower() for b in banned):
                continue
            lines.append(t[:90])
        cap = str(data.get("caption") or fallback["caption"])[:900]
        if any(b in cap.lower() for b in banned):
            cap = fallback["caption"]
        if "follow for more" not in cap.lower():
            cap += "\nFollow for more."
        if artist.lower() not in cap.lower():
            cap += f"\nCredit {artist}"
        src = "SOURCE: GENIUS" if quote else "SOURCE: HEAT"
        if quote and "genius" not in cap.lower():
            cap += "\nLyrics/context: Genius."
        return {"quote": quote[:90], "lines": lines or fallback["lines"], "caption": cap, "source": src}
    except Exception as e:
        print(f"genius brief: {e}", flush=True)
        return fallback
