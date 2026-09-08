import os
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

youtube_tools = composio_toolset.get_tools(apps=[App.YOUTUBE])
pinterest_tools = composio_toolset.get_tools(apps=[App.PINTEREST])

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


def search_youtube_for_rap():
    try:
        print("Searching YouTube for underground rap...")
        search_queries = [
            "underground rap album cover 2024",
            "independent hip hop album 2024",
            "best underground rap albums 2024",
            "new underground hip hop album",
        ]
        query = random.choice(search_queries)
        response = composio_toolset.execute_tool_calls(
            tool_calls=[{
                "function": {
                    "name": "YOUTUBE_SEARCH",
                    "arguments": {
                        "query": query,
                        "maxResults": 10,
                        "type": "video",
                    },
                }
            }]
        )

        items = []
        if isinstance(response, dict):
            items = response.get("items") or []
        elif isinstance(response, list):
            for entry in response:
                if isinstance(entry, dict) and entry.get("items"):
                    items = entry["items"]
                    break

        for item in items:
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            if " - " not in title:
                continue
            artist, album = [part.strip() for part in title.split(" - ", 1)]
            for word in ["(Official)", "(Audio)", "(Lyric Video)", "FULL ALBUM"]:
                album = album.replace(word, "").strip()
            thumbnails = snippet.get("thumbnails", {})
            cover_url = (
                thumbnails.get("high", {}).get("url")
                or thumbnails.get("default", {}).get("url")
            )
            if cover_url:
                return {
                    "artist": artist[:50],
                    "album": album[:50],
                    "cover_url": cover_url,
                    "year": "2024",
                    "video_id": item.get("id", {}).get("videoId", ""),
                }

        print("YouTube search returned nothing, using backup list...")
        return random.choice(BACKUP_ALBUMS)
    except Exception as e:
        print(f"YouTube error: {e}")
        print("Using backup album...")
        return random.choice(BACKUP_ALBUMS)


def create_description(album):
    try:
        print("Writing description...")
        prompt = f"""Write a short, hype Pinterest description for this underground rap album:
Artist: {album['artist']}
Album: {album['album']}
Year: {album.get('year', '2024')}
Genre: {album.get('genre', 'Underground Rap')}

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
        if album["artist"] not in description:
            description = f"{album['artist']} - {album['album']} • {description}"
        return description[:200]
    except Exception as e:
        print(f"AI description failed: {e}")
        return f"{album['artist']} - {album['album']} • Underground heat. #808dystopia #undergroundrap"


def post_to_pinterest(album, description):
    try:
        print("Posting to Pinterest...")
        image_url = album.get("cover_url")
        if not image_url:
            print("No cover URL on this album. Skipping pin instead of posting a placeholder.")
            return None

        response = composio_toolset.execute_tool_calls(
            tool_calls=[{
                "function": {
                    "name": "PINTEREST_CREATE_PIN",
                    "arguments": {
                        "board_id": BOARD_ID,
                        "title": f"{album['artist']} - {album['album']}",
                        "description": description,
                        "image_url": image_url,
                        "link": SITE_URL,
                    },
                }
            }]
        )
        print(f"POSTED: {album['artist']} - {album['album']}")
        return response
    except Exception as e:
        print(f"Pinterest error: {e}")
        return None


def daily_post():
    print("=" * 50)
    print(f"808DYSTOPIA BOT ACTIVATED - {datetime.now()}")
    print("=" * 50)
    album = search_youtube_for_rap()
    print(f"Found: {album['artist']} - {album['album']}")
    description = create_description(album)
    print(f"Description: {description[:100]}...")
    result = post_to_pinterest(album, description)
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
