"""6:00 PM CT briefing for FRZA + STOKELY in #admin-general.

Pulls whatever 808 pages are live on Composio. Missing platforms
show as not up instead of crashing the job.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
ADMIN_CHANNEL_ID = os.getenv("DISCORD_ADMIN_CHANNEL_ID", "1542355862079807509")
IG_USER_ID = os.getenv("IG_USER_ID", "28902406756011804")
YT_CHANNEL_ID = os.getenv("YT_CHANNEL_ID", "UCmi4MXIi5-M584F3-3dqxvg")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "1326786480516977")
BOARD_ID = os.getenv("PINTEREST_BOARD_ID", "1099230290240885517")
CT = ZoneInfo("America/Chicago")


def execute(slug, arguments):
    if not COMPOSIO_API_KEY:
        raise RuntimeError("Missing COMPOSIO_API_KEY")
    resp = requests.post(
        f"{COMPOSIO_BASE}/tools/execute/{slug}",
        headers={"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"},
        json={"arguments": arguments or {}, "user_id": COMPOSIO_USER_ID, "version": "latest"},
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{slug} HTTP {resp.status_code}: {resp.text[:240]}")
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def unwrap(payload):
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict):
            return inner
        return data
    return payload


def safe(slug, arguments):
    try:
        return unwrap(execute(slug, arguments)), None
    except Exception as e:
        return {}, str(e)


def metric_value(m):
    if not isinstance(m, dict):
        return None
    tv = m.get("total_value")
    if isinstance(tv, dict):
        return tv.get("value")
    if tv is not None:
        return tv
    vals = m.get("values") or []
    if vals and isinstance(vals[-1], dict):
        return vals[-1].get("value")
    return m.get("value")


def ig_section():
    info, err = safe(
        "INSTAGRAM_GET_USER_INFO",
        {"ig_user_id": IG_USER_ID},
    )
    media, merr = safe(
        "INSTAGRAM_GET_IG_USER_MEDIA",
        {
            "ig_user_id": IG_USER_ID,
            "limit": 5,
            "fields": "id,caption,permalink,timestamp,like_count,comments_count,media_type",
        },
    )
    insights, ierr = safe(
        "INSTAGRAM_GET_USER_INSIGHTS",
        {
            "ig_user_id": IG_USER_ID,
            "metric": ["reach", "profile_views", "total_interactions", "views"],
            "period": "day",
            "metric_type": "total_value",
        },
    )
    if err and merr and ierr:
        return f"IG @808dystopia — not up ({err})"
    followers = info.get("followers_count") or info.get("follower_count") or "n/a"
    media_count = info.get("media_count") or "n/a"
    lines = [f"IG @808dystopia — followers {followers} · posts {media_count}"]
    rows = insights.get("data") if isinstance(insights.get("data"), list) else []
    bits = []
    for m in rows:
        if isinstance(m, dict) and m.get("name"):
            bits.append(f"{m['name']} {metric_value(m)}")
    if bits:
        lines.append("  today: " + " · ".join(bits))
    items = media.get("data") if isinstance(media.get("data"), list) else []
    if items:
        top = items[0]
        cap = (top.get("caption") or "")[:60].replace("\n", " ")
        lines.append(
            f"  latest: {top.get('like_count', '?')} likes / {top.get('comments_count', '?')} comments — {cap}"
        )
        if top.get("permalink"):
            lines.append(f"  {top['permalink']}")
    return "\n".join(lines)


def pin_section():
    today = datetime.now(timezone.utc).date()
    start = (today - timedelta(days=7)).isoformat()
    end = today.isoformat()
    acct, err = safe(
        "PINTEREST_GET_ACCOUNT_ANALYTICS",
        {
            "start_date": start,
            "end_date": end,
            "metric_types": ["IMPRESSION", "PIN_CLICK", "SAVE", "OUTBOUND_CLICK", "ENGAGEMENT"],
            "content_type": "ORGANIC",
        },
    )
    pins, perr = safe(
        "PINTEREST_LIST_PINS",
        {"board_id": BOARD_ID, "page_size": 3},
    )
    if err and perr:
        return f"Pinterest — not up ({err})"
    lines = ["Pinterest @808dystopia — last 7 days"]
    all_metrics = acct.get("all") or acct.get("summary_metrics") or acct
    if isinstance(all_metrics, dict):
        keep = ["IMPRESSION", "PIN_CLICK", "SAVE", "OUTBOUND_CLICK", "ENGAGEMENT"]
        bits = [f"{k.lower()} {all_metrics.get(k)}" for k in keep if k in all_metrics]
        if bits:
            lines.append("  " + " · ".join(bits))
    items = pins.get("items") if isinstance(pins.get("items"), list) else pins.get("data")
    if isinstance(items, list) and items:
        latest = items[0]
        lines.append(f"  latest pin: {latest.get('title') or latest.get('id')}")
    return "\n".join(lines)


def fb_section():
    pages, err = safe("FACEBOOK_LIST_MANAGED_PAGES", {"limit": 10, "fields": "id,name,fan_count,link"})
    rows = pages.get("data") if isinstance(pages.get("data"), list) else []
    if err and not rows:
        return f"Facebook — not up ({err})"
    if not rows:
        return "Facebook — connected, no Page insights yet"
    lines = ["Facebook"]
    for p in rows[:3]:
        if not isinstance(p, dict):
            continue
        lines.append(
            f"  {p.get('name')} ({p.get('id')}) fans {p.get('fan_count', 'n/a')}"
        )
    return "\n".join(lines)


def yt_section():
    data, err = safe(
        "YOUTUBE_GET_CHANNEL_STATISTICS",
        {"id": YT_CHANNEL_ID, "part": "snippet,statistics"},
    )
    if err:
        return f"YouTube @808dystopia — not up ({err})"
    items = data.get("items") if isinstance(data.get("items"), list) else []
    ch = items[0] if items else data
    stats = ch.get("statistics") if isinstance(ch, dict) else {}
    snippet = ch.get("snippet") if isinstance(ch, dict) else {}
    title = snippet.get("title") if isinstance(snippet, dict) else "808 Dystopia"
    if not stats:
        return "YouTube @808dystopia — connected, no public stats yet"
    return (
        f"YouTube {title} — subs {stats.get('subscriberCount', 'n/a')} · "
        f"views {stats.get('viewCount', 'n/a')} · videos {stats.get('videoCount', 'n/a')}"
    )


def build_brief():
    now = datetime.now(CT)
    parts = [
        f"808 EOD · {now.strftime('%a %b %d %Y')} · 6:00 PM CT",
        "FRZA + STOKELY — numbers only. Platforms that are not live say so.",
        "",
        ig_section(),
        "",
        pin_section(),
        "",
        fb_section(),
        "",
        yt_section(),
        "",
        "X / TikTok — not posting yet",
    ]
    return "\n".join(parts)[:1900]


def send_brief():
    text = build_brief()
    print(text, flush=True)
    execute(
        "DISCORDBOT_CREATE_MESSAGE",
        {"channel_id": ADMIN_CHANNEL_ID, "content": text},
    )
    return text


if __name__ == "__main__":
    send_brief()
