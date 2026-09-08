import threading
import time

import schedule

from pinterest_bot import daily_post, start_health_server
from briefing import send_brief


if __name__ == "__main__":
    threading.Thread(target=start_health_server, daemon=True).start()
    time.sleep(0.3)
    schedule.every().day.at("09:00").do(daily_post)
    schedule.every().day.at("18:00").do(send_brief)
    print("808 bot up — Pinterest 09:00 CT, admin brief 18:00 CT", flush=True)
    while True:
        schedule.run_pending()
        time.sleep(30)
