"""GET /run/* kick endpoints. Return 202 fast so free crons (30s timeout) work."""
from __future__ import annotations

import json
import os
import threading
from http.server import HTTPServer
from urllib.parse import parse_qs, urlparse

from pinterest_bot import HealthHandler

TOKEN = os.getenv("RUN_TOKEN", "")


def authorized(qs):
    if not TOKEN:
        return True
    return (qs.get("token") or [""])[0] == TOKEN


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


JOBS = {
    "/run/carousel": run_carousel,
    "/run/pin": run_pin,
    "/run/brief": run_brief,
    "/run/reel": run_reel,
}


class KickHandler(HealthHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        if path in ("/wake",):
            body = b"awake"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in JOBS:
            if not authorized(qs):
                payload = json.dumps({"ok": False, "error": "bad token"}).encode()
                self.send_response(401)
            else:
                name = JOBS[path]()
                payload = json.dumps({"ok": True, "started": name}).encode()
                self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), KickHandler)
    print(f"Health+kick server on port {port}", flush=True)
    server.serve_forever()
