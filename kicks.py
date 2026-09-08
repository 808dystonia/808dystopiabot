"""Background kick runners used by GET /run/* on the health server."""
from __future__ import annotations

import os
import threading

TOKEN = os.getenv("RUN_TOKEN", "")


def authorized(qs):
    if not TOKEN:
        return True
    got = (qs.get("token") or [""])[0]
    return got == TOKEN


def start(name, fn):
    def runner():
        print(f"KICK start {name}", flush=True)
        try:
            fn()
            print(f"KICK done {name}", flush=True)
        except Exception as e:
            print(f"KICK fail {name}: {e}", flush=True)

    threading.Thread(target=runner, daemon=True, name=f"kick-{name}").start()
    return name


def run_carousel():
    from carousel import run_carousel_job
    return start("carousel", run_carousel_job)


def run_pin():
    from pinterest_bot import daily_post
    return start("pin", daily_post)


def run_brief():
    from briefing import send_brief
    return start("brief", send_brief)


def run_reel():
    from reels import run_reel_job
    from drive_reels import process_drive_reels

    def both():
        run_reel_job()
        process_drive_reels()

    return start("reel", both)
