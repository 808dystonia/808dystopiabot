import os
import threading
import time

import requests
import schedule

from pinterest_bot import daily_post, start_health_server
from briefing import send_brief
from reels import run_reel_job
from discord_ingest import ingest_admin_videos
from drive_reels import process_drive_reels
import carousel
from carousel_cover import pick_official_cover

carousel.lookup_artist_image = lambda q, a="", t="": pick_official_cover(a or q, t or a or q)
from carousel import run_carousel_job

SITE = os.getenv("RENDER_EXTERNAL_URL", "https://eight08dystopiabot.onrender.com")


def keepalive():
    try:
        requests.get(SITE + "/", timeout=10)
    except Exception as e:
        print(f"keepalive: {e}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    time.sleep(0.3)
    schedule.every().day.at("09:00").do(run_carousel_job)
    schedule.every().day.at("09:10").do(daily_post)
    schedule.every().day.at("18:00").do(send_brief)
    schedule.every().day.at("19:00").do(run_reel_job)
    schedule.every(10).minutes.do(ingest_admin_videos)
    schedule.every(10).minutes.do(process_drive_reels)
    schedule.every(5).minutes.do(keepalive)
    print("808 bot up — carousel 09:00 official covers, pins 09:10, brief 18:00, reel 19:00", flush=True)
    keepalive()
    while True:
        schedule.run_pending()
        time.sleep(30)
