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

UNDERGROUND_ARTISTS = [
    "MIKE", "Earl Sweatshirt", "Mick Jenkins", "Billy Woods", "JPEGMAFIA",
    "Armand Hammer", "Roc Marciano", "Boldy James", "Westside Gunn",
    "Conway the Machine", "Ka", "Lupe Fiasco", "Aesop Rock", "El-P",
    "Danny Brown", "Freddie Gibbs", "Vince Earl", "Navy Blue", "Pink Siifu",
    "Zelooperz", "MIKE", "The Alchemist", "Conductor Williams", "Nicholas Craven",
    "Rome Streetz", "Stove God Cooks", "Keefe", "Jay Electronica", "Yasiin Bey",
    "Guilty Simpson", "Guilty Simpson", "Guilty Simpson", "Guilty Simpson",
]

UNDERGROUND_GENRES = [
    "Abstract Hip-Hop", "Experimental Rap", "Conscious Hip-Hop", "East Coast Rap",
    "Detroit Rap", "Boom Bap", "Lo-Fi Hip-Hop", "Underground Rap", "Jazz Rap",
    "Hardcore Rap", "Alternative Hip-Hop", "G-Funk", "Southern Rap", "Midwest Rap",
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
    """DeepSeek picks a real underground hip-hop/rap artist and album to feature."""
    try:
        print("DeepSeek selecting underground hip-hop/rap album...")
        seed_artist = random.choice(UNDERGROUND_ARTISTS)
        seed_genre = random.choice(UNDERGROUND_GENRES)
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
- Focus on underground, independent, or cult-classic hip-hop/rap — not mainstream pop rap.
- Vary the style each time."""
        response = client.chat.completions.create(
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
        return random.choice([
            {"artist": "MIKE", "album": "Disco!", "year": "2023", "genre": "Abstract Hip-Hop", "vibe": "lo-fi dreamy", "cover_prompt": ""},
            {"artist": "Earl Sweatshirt", "album": "Some Rap Songs", "year": "2018", "genre": "Experimental Rap", "vibe": "raw and introspective", "cover_prompt": ""},
            {"artist": "Roc Marciano", "album": "The Elephant Man's Bones", "year": "2022", "genre": "East Coast Rap", "vibe": "gritty boom bap", "cover_prompt": ""},
        ])


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
    if "s=10" in low or "s=0" in low:
        return False
    return True


def find_cover_image(concept):
    """Search Google Images (via Composio) for a real underground rap album cover."""
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
        response = client.chat.completions.create(
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
        # Guarantee the artist is credited even if the model forgets.
        if concept["artist"].lower() not in description.lower():
            description = f"by {concept['artist']} — {description}"
        if concept["album"].lower() not in description.lower():
            description = f"{concept['album']} {description}"
        return description[:200]
    except Exception as e:
        print(f"AI description failed: {e}")
        return f"{concept['album']} by {concept['artist']} • Underground heat. #808dystopia #undergroundrap"


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

    # 808 Pinterest cadence: 9:00 AM daily. Set TZ=America/Chicago on Render.
    schedule.every().day.at("09:00").do(daily_post)

    print("808DYSTOPIA BOT IS RUNNING")
    print("Scheduled 09:00 daily (America/Chicago)")
    print("Running one test post now...")
    daily_post()

    while True:
        schedule.run_pending()
        time.sleep(30)
