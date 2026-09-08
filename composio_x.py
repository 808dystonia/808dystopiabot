"""One Composio execute helper. Discord calls pin DT SERVER BOT."""
from __future__ import annotations

import os

import requests

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
COMPOSIO_USER_ID = os.getenv("COMPOSIO_USER_ID", "default")
COMPOSIO_DISCORD_ACCOUNT = os.getenv("COMPOSIO_DISCORD_ACCOUNT", "discordbot_qung-whiff")
COMPOSIO_BASE = os.getenv("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")


def execute_composio_tool(slug, arguments, user_id=None):
    if not COMPOSIO_API_KEY:
        raise RuntimeError("Missing COMPOSIO_API_KEY in Render Environment")
    payload = {
        "arguments": arguments or {},
        "user_id": user_id or COMPOSIO_USER_ID,
        "version": "latest",
    }
    if str(slug).upper().startswith("DISCORDBOT_"):
        payload["connected_account_id"] = COMPOSIO_DISCORD_ACCOUNT
    url = f"{COMPOSIO_BASE}/tools/execute/{slug}"
    print(f"Composio execute {slug}", flush=True)
    resp = requests.post(
        url,
        headers={"x-api-key": COMPOSIO_API_KEY, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if resp.status_code >= 400:
        print(f"Composio {slug} HTTP {resp.status_code}: {resp.text[:500]}", flush=True)
        resp.raise_for_status()
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}
