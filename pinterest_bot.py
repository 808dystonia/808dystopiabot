import os
import json
import threading
import time
import random
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
import schedule
from composio import ComposioToolSet, App
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "1099230290240885517")
SITE_URL = os.getenv("SITE_URL", "https://808dystopia.win")

if not COMPOSIO_API_KEY:
    raise SystemExit("Missing COMPOSIO_API_KEY. Set it in Render Environment, not in the repo.")

composio_toolset = ComposioToolSet(api_key=COMPOSIO_API_KEY)
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.deepseek.com/v1",
)

BACKUP_ALBUMS = [
    {"artist": "MIKE", "album": "Disco!", "year": "2023", "genre": "Abstract Hip-Hop"},
    {"artist": "Earl Sweatshirt", "album": "Some Rap Songs", "year": "2018", "genre": "Experimental Rap"},
    {"artist": "Mick Jenkins", "album": "The Waters", "year": "2014", "genre": "Conscious Hip-Hop"},
    {"artist": "Billy Woods", "album": "Maps", "year": "2023", "genre": "Experimental Rap"},
    {"artist": "JPEGMAFIA", "album": "SCARING THE HOES", "year": "2023", "genre": "Industrial Rap"},
    {"artist": "Armand Hammer", "album": "We Buy Diabetic Test Strips", "year": "2023", "genre": "Experimental Rap"},
    {"artist": "Roc Marciano", "album": "The Elephant Man's Bones", "year": "2022", "genre": "East Coast Rap"},
    {"artist": "Boldy James", "album": "The Price of Tea in China", "year": "2020", "genre": "Detroit Rap"},
    {"artist": "Westside Gunn", "album": "Pray for Paris", "year": "2020", "genre": "East Coast Rap"},
    {"artist": "Conway the Machine", "album": "God Don't Make Mistakes", "year": "2022", "genre": "East Coast Rap"},
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


def generate_album_concept():
    """DeepSeek invents a fresh underground rap album concept."""
    try:
        print("DeepSeek generating album concept...")
        prompt = """Invent one brand-new, fictional underground rap album that does NOT exist in real life.
Return ONLY valid JSON, no markdown fences, no commentary, with these exact keys:
- artist: a made-up artist name (string)
- album: a made-up album title (string)
- year: a plausible release year as a string, e.g. "2025"
- genre: a short genre tag, e.g. "Abstract Hip-Hop"
- vibe: one short sentence describing the sound/mood
- cover_prompt: a short text prompt describing an album cover image suitable for an AI image generator

Make it sound like real underground hip-hop: gritty, specific, interesting. Vary the style each time."""
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You are a creative director for an underground rap brand. You output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=1.0,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").lstrip("json").strip()
        concept = json.loads(raw)
        concept["artist"] = str(concept.get("artist", "Unknown"))[:50]
        concept["album"] = str(concept.get("album", "Untitled"))[:50]
        concept["year"] = str(concept.get("year", "2025"))[:4]
        concept["genre"] = str(concept.get("genre", "Underground Rap"))[:40]
        concept["vibe"] = str(concept.get("vibe", ""))[:120]
        concept["cover_prompt"] = str(concept.get("cover_prompt", ""))[:200]
        print(f"Concept: {concept['artist']} - {concept['album']}")
        return concept
    except Exception as e:
        print(f"DeepSeek concept generation failed: {e}")
        print("Falling back to backup album...")
        return random.choice(BACKUP_ALBUMS)


def is_usable_cover(url, title=""):
    """Filter out junk: tiny thumbs, logos, non-image pages, obvious non-covers."""
    if not url or not isinstance(url, str):
        return False
    low = url.lower()
    if not low.startswith("http"):
        return False
    bad_ext = (".svg", ".gif", "logo", "icon", "sprite", "button", "avatar")
    if any(b in low for b in bad_ext):
        return False
    # Prefer square-ish or large images; skip obvious tiny thumbs
    if "s=10" in low or "s=0" in low:
        return False
    return True


def find_cover_image(concept):
    """Search Google Images (via Composio) for a real underground rap album cover."""
    try:
        print("Searching Google Images for a real album cover...")
        queries = [
            f"{concept.get('artist', '')} {concept.get('album', '')} album cover art",
            f"{concept.get('genre', 'underground rap')} album cover art underground hip hop",
            f"underground rap mixtape cover art {concept.get('vibe', '')[:30]}",
            "underground hip hop album cover art real",
        ]
        seen = set()
        for q in queries:
            q = q.strip()
            if not q or q in seen:
                continue
            seen.add(q)
            try:
                response = composio_toolset.execute_tool_calls(
                    tool_calls=[{
                        "function": {
                            "name": "COMPOSIO_SEARCH_IMAGE",
                            "arguments": {"query": q, "num": 10},
                        }
                    }]
                )
            except Exception as e:
                print(f"Image search error for '{q}': {e}")
                continue

            images = []
            if isinstance(response, dict):
                data = response.get("data") or response
                images = (data.get("images_results")
                          or data.get("results", {}).get("images_results")
                          or [])
            elif isinstance(response, list):
                for entry in response:
                    if isinstance(entry, dict):
                        data = entry.get("data") or entry
                        images = (data.get("images_results")
                                  or data.get("results", {}).get("images_results")
                                  or [])
                        if images:
                            break

            for img in images:
                url = img.get("original") or img.get("thumbnail")
                title = img.get("title", "")
                if is_usable_cover(url, title):
                    print(f"Found cover: {url} (from: {title[:60]})")
                    return url

        print("No usable cover found in Google Images.")
        return None
    except Exception as e:
        print(f"Cover search error: {e}")
        return None


def create_description(concept):
    try:
        print("Writing description...")
        prompt = f"""Write a short, hype Pinterest description for this underground rap album:
Artist: {concept['artist']}
Album: {concept['album']}
Year: {concept.get('year', '2025')}
Genre: {concept.get('genre', 'Underground Rap')}
Vibe: {concept.get('vibe', '')}

Requirements:
- Mention the artist and album
- 1 sentence why it's dope
- Add #808dystopia and #undergroundrap
- Keep under 150 characters
"""
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "You write hype descriptions for underground rap on Pinterest. Keep it short and catchy.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        description = response.choices[0].message.content or ""
        if concept["artist"] not in description:
            description = f"{concept['artist']} - {concept['album']} • {description}"
        return description[:200]
    except Exception as e:
        print(f"AI description failed: {e}")
        return f"{concept['artist']} - {concept['album']} • Underground heat. #808dystopia #undergroundrap"


def post_to_pinterest(concept, description, cover_url):
    try:
        print("Posting to Pinterest...")
        if not cover_url:
            print("No cover URL. Skipping pin instead of posting a placeholder.")
            return None

        response = composio_toolset.execute_tool_calls(
            tool_calls=[{
                "function": {
                    "name": "PINTEREST_CREATE_PIN",
                    "arguments": {
                        "board_id": BOARD_ID,
                        "title": f"{concept['artist']} - {concept['album']}",
                        "description": description,
                        "link": SITE_URL,
                        "media_source": {
                            "source_type": "image_url",
                            "url": cover_url,
                        },
                    },
                }
            }]
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
    print("-" * 50)


if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()

    # 808 Pinterest cadence: 10am / 2pm / 7pm. Set TZ=America/Chicago on Render.
    schedule.every().day.at("10:00").do(daily_post)
    schedule.every().day.at("14:00").do(daily_post)
    schedule.every().day.at("19:00").do(daily_post)

    print("808DYSTOPIA BOT IS RUNNING")
    print("Scheduled 10:00 / 14:00 / 19:00")
    print("Running one test post now...")
    daily_post()

    while True:
        schedule.run_pending()
        time.sleep(30)
