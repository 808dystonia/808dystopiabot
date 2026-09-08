import os
import threading
import time

import requests
import schedule

from pinterest_bot import daily_post, start_health_server
from briefing import send_brief

SITE = os.getenv("RENDER_EXTERNAL_URL", "https://eight08dystopiabot.onrender.com")


def keepalive():
    try:
        requests.get(SITE + "/", timeout=10)
    except Exception as e:
        print(f"keepalive: {e}", flush=True)


if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    time.sleep(0.3)
    schedule.every().day.at("09:00").do(daily_post)
    schedule.every().day.at("18:00").do(send_brief)
    schedule.every(5).minutes.do(keepalive)
    print("808 bot up — Pinterest 09:00 CT, admin brief 18:00 CT, ping every 5 min", flush=True)
    keepalive()
    while True:
        schedule.run_pending()
        time.sleep(30)
