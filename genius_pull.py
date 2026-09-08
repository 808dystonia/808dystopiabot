"""Genius-only lyrics + annotation for 808 single slides."""
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
                        "Return ONLY JSON: {\"quote\":\"\",\"lines\":[\"\",\"\"],\"caption\":\"\"}. "
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
