import os
import json
import threading
import time
import random
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
import schedule
import requests
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "1099230290240885517")
SITE_URL = os.getenv("SITE_URL", "https://808dystopia.win")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")

_llm_client = None

BACKUP_ALBUMS = [
    {"artist": "OsamaSon", "album": "Flex Musix", "year": "2023", "genre": "Rage Rap", "vibe": "maximalist rage, woozy and layered", "cover_prompt": ""},
    {"artist": "Nettspend", "album": "Him", "year": "2024", "genre": "Jerk", "vibe": "deep-fried, slurry auto-tune", "cover_prompt": ""},
    {"artist": "xaviersobased", "album": "115 & LSD", "year": "2021", "genre": "Digicore", "vibe": "chaotic, blown-out 808s", "cover_prompt": ""},
    {"artist": "Che", "album": "REST IN BASS", "year": "2025", "genre": "Rage Rap", "vibe": "blown-out bass", "cover_prompt": ""},
    {"artist": "Glokk40Spaz", "album": "3vil Reflection", "year": "2024", "genre": "Rage Trap", "vibe": "dark Atlanta rage", "cover_prompt": ""},
]

UNDERGROUND_ARTISTS = [
    "OsamaSon", "Nettspend", "xaviersobased", "Che", "Glokk40Spaz",
    "Nine Vicious", "Bleood", "Pradabagshawty", "Slayr", "Molly Santana",
    "Tezzus", "Protect", "Pz'", "ApolloRed1", "1oneam", "Ohsxnta",
    "Okaymar", "Boolymon", "tdf", "Yhapojj", "phreshboyswag", "ksuuvi",
    "Prettifun", "fakemink", "Feng", "EsDeeKid", "Nemzzz", "Fimiguerrero",
]

UNDERGROUND_GENRES = [
    "Rage Rap", "SoundCloud Rap", "Plugg", "Pluggnb", "Jerk", "Digicore",
    "Sigilkore", "HexD", "Krushclub", "Cloud Rap", "Underground Trap", "Rage Trap",
    "Experimental Rap", "Underground Hip-Hop", "Opium Rap", "Mumble Rap",
]


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"808dystopiabot ok")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server on port {port}")
    server.serve_forever()


def get_llm_client():
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    if not OPENAI_API_KEY:
        return None
    _llm_client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url="https://api.deepseek.com/v1",
    )
    return _llm_client


def execute_composio_tool(slug, arguments, user_id=None):
    """Call Composio REST v3.1. Avoids the dead composio-core SDK (HTTP 410)."""
    if not COMPOSIO_API_KEY:
        raise RuntimeError("Missing COMPOSIO_API_KEY in Render Environment")
    url = f"{COMPOSIO_BASE}/tools/execute/{slug}"
    payload = {
        "arguments": arguments or {},
        "user_id": user_id or COMPOSIO_USER_ID,
        "version": "latest",
    }
    headers = {
        "x-api-key": COMPOSIO_API_KEY,
        "Content-Type": "application/json",
    }
    print(f"Composio execute {slug}")
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code >= 400:
        print(f"Composio {slug} HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def generate_album_concept():
    """Pick a real underground hip-hop/rap artist and album to feature."""
    seed_artist = random.choice(UNDERGROUND_ARTISTS)
    seed_genre = random.choice(UNDERGROUND_GENRES)
    llm = get_llm_client()
    if llm is None:
        print("No OPENAI_API_KEY / DEEPSEEK_API_KEY. Using backup album.")
        return random.choice(BACKUP_ALBUMS)
    try:
        print("DeepSeek selecting underground hip-hop/rap album...")
        prompt = f"""You are curating an underground hip-hop and rap Pinterest board.
Pick ONE real, existing underground hip-hop or rap artist and ONE of their real albums or mixtapes.
Seed artist hint: {seed_artist}
Seed genre hint: {seed_genre}

Return ONLY valid JSON, no markdown fences, no commentary, with these exact keys:
- artist: the real artist name (string)
- album: the real album or mixtape title (string)
- year: release year as a string, e.g. "2023"
- genre: short genre tag, must be underground hip-hop or rap related
- vibe: one short sentence describing the sound/mood
- cover_prompt: a short text prompt describing the album's cover art style

Rules:
- Artist and album MUST be real and verifiable.
- Focus on the OsamaSon / Nettspend underground lane: rage, jerk, plugg, digicore, SoundCloud rap.
- Vary the style each time."""
        response = llm.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a curator of underground hip-hop and rap. You output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        concept = json.loads(raw)
        concept["artist"] = str(concept.get("artist", seed_artist))[:50]
        concept["album"] = str(concept.get("album", "Untitled"))[:50]
        concept["year"] = str(concept.get("year", "2023"))[:4]
        concept["genre"] = str(concept.get("genre", seed_genre))[:40]
        concept["vibe"] = str(concept.get("vibe", ""))[:120]
        concept["cover_prompt"] = str(concept.get("cover_prompt", ""))[:200]
        print(f"Concept: {concept['artist']} - {concept['album']}")
        return concept
    except Exception as e:
        print(f"DeepSeek concept generation failed: {e}")
        print("Falling back to backup album...")
        return random.choice(BACKUP_ALBUMS)


def is_usable_cover(url, title=""):
    if not url or not isinstance(url, str):
        return False
    low = url.lower()
    if not low.startswith("http"):
        return False
    bad_ext = (".svg", ".gif", "logo", "icon", "sprite", "button", "avatar")
    if any(b in low for b in bad_ext):
        return False
    if "s=10" in low or "s=0" in low:
        return False
    return True


def extract_images(payload):
    if not payload:
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    if data is None and isinstance(payload, dict):
        data = payload
    if not isinstance(data, dict):
        return []
    images = (
        data.get("images_results")
        or data.get("results", {}).get("images_results")
        or data.get("results")
        or []
    )
    if isinstance(images, dict):
        images = images.get("images_results") or []
    return images if isinstance(images, list) else []


def find_cover_image(concept):
    try:
        print("Searching Google Images for a real album cover...")
        artist = concept.get("artist", "")
        album = concept.get("album", "")
        queries = [
            f"{artist} {album} album cover art",
            f"{artist} {album} cover underground hip hop",
            f"{concept.get('genre', 'underground rap')} album cover art {artist}",
            f"{artist} mixtape cover art hip hop",
        ]
        seen = set()
        for q in queries:
            q = q.strip()
            if not q or q in seen:
                continue
            seen.add(q)
            try:
                response = execute_composio_tool(
                    "COMPOSIO_SEARCH_IMAGE",
                    {"query": q, "num": 10},
                )
            except Exception as e:
                print(f"Image search error for '{q}': {e}")
                continue

            for img in extract_images(response):
                if not isinstance(img, dict):
                    continue
                url = img.get("original") or img.get("thumbnail") or img.get("url")
                title = img.get("title", "")
                if is_usable_cover(url, title):
                    print(f"Found cover: {url} (from: {str(title)[:60]})")
                    return url

        print("No usable cover found in Google Images.")
        return None
    except Exception as e:
        print(f"Cover search error: {e}")
        return None


def create_description(concept):
    fallback = f"{concept['album']} by {concept['artist']} • Underground heat. #808dystopia #undergroundrap"
    llm = get_llm_client()
    if llm is None:
        return fallback
    try:
        print("Writing description...")
        prompt = f"""Write a short, hype Pinterest description for this underground rap album:
Artist: {concept['artist']}
Album: {concept['album']}
Year: {concept.get('year', '2023')}
Genre: {concept.get('genre', 'Underground Rap')}
Vibe: {concept.get('vibe', '')}

Requirements:
- MUST credit the artist by name, e.g. "by {concept['artist']}" or "Artist: {concept['artist']}"
- Mention the album title
- 1 sentence why it's dope
- Add #808dystopia and #undergroundrap
- Keep under 200 characters
"""
        response = llm.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You write hype descriptions for underground rap on Pinterest. Always credit the artist by name. Keep it short and catchy.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        description = (response.choices[0].message.content or "").strip()
        if concept["artist"].lower() not in description.lower():
            description = f"by {concept['artist']} — {description}"
        if concept["album"].lower() not in description.lower():
            description = f"{concept['album']} {description}"
        return description[:200]
    except Exception as e:
        print(f"AI description failed: {e}")
        return fallback


def post_to_pinterest(concept, description, cover_url):
    try:
        print("Posting to Pinterest...")
        if not cover_url:
            print("No cover URL. Skipping pin instead of posting a placeholder.")
            return None

        response = execute_composio_tool(
            "PINTEREST_CREATE_PIN",
            {
                "board_id": BOARD_ID,
                "title": f"{concept['artist']} - {concept['album']}",
                "description": description,
                "link": SITE_URL,
                "media_source": {
                    "source_type": "image_url",
                    "url": cover_url,
                },
            },
        )
        print(f"POSTED: {concept['artist']} - {concept['album']}")
        return response
    except Exception as e:
        print(f"Pinterest error: {e}")
        return None


def daily_post():
    print("=" * 50)
    print(f"808DYSTOPIA BOT ACTIVATED - {datetime.now()}")
    print("=" * 50)
    try:
        concept = generate_album_concept()
        print(f"Concept: {concept['artist']} - {concept['album']} ({concept.get('genre', '')})")
        cover_url = find_cover_image(concept)
        description = create_description(concept)
        print(f"Description: {description[:100]}...")
        result = post_to_pinterest(concept, description, cover_url)
        if result:
            print("SUCCESS")
        else:
            print("Failed to post")
    except Exception as e:
        print(f"daily_post crashed: {e}")
    print("-" * 50)


if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    time.sleep(0.3)

    if not COMPOSIO_API_KEY:
        print("WARNING: COMPOSIO_API_KEY is not set in Render Environment")
    if not OPENAI_API_KEY:
        print("WARNING: OPENAI_API_KEY / DEEPSEEK_API_KEY is not set. Descriptions will use the fallback template.")

    schedule.every().day.at("09:00").do(daily_post)

    print("808DYSTOPIA BOT IS RUNNING")
    print("Scheduled 09:00 daily (America/Chicago)")
    print("Running one test post now...")
    daily_post()

    while True:
        schedule.run_pending()
        time.sleep(30)
