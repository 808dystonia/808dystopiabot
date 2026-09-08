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
from genius_pull import genius_brief
from carousel_slides import render_slide2_single, render_slide2_tracks
from carousel_outro import publish_with_outro
from carousel_tag import apply_at, resolve_handle


def _cover(q, a="", t=""):
    carousel.LAST_ARTIST = a or q
    carousel.LAST_HANDLE = resolve_handle(a or q)
    return pick_official_cover(a or q, t or a or q)


def _brief(item):
    brief = genius_brief(item)
    handle = resolve_handle(item.get("artist") or "")
    carousel.LAST_HANDLE = handle
    carousel.LAST_ARTIST = item.get("artist") or ""
    brief["caption"] = apply_at(brief.get("caption") or "", handle, item.get("artist") or "")
    return brief


def _publish(urls, text):
    handle = getattr(carousel, "LAST_HANDLE", "") or ""
    artist = getattr(carousel, "LAST_ARTIST", "") or ""
    text = apply_at(text, handle, artist)
    mid, outro = publish_with_outro(urls, text, handle=handle)
    print(f"outro slide3 {outro} @{handle} media={mid}", flush=True)
    return mid


carousel.lookup_artist_image = _cover
carousel.fetch_brief = _brief
carousel.render_slide2_single = render_slide2_single
carousel.render_slide2_tracks = render_slide2_tracks
carousel.publish_carousel = _publish
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
    print("808 bot up — carousel @tag + outro slide 3", flush=True)
    keepalive()
    while True:
        schedule.run_pending()
        time.sleep(30)
