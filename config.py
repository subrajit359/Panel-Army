import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
FAMGATEWAY_API_KEY = os.getenv("FAMGATEWAY_API_KEY", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not FAMGATEWAY_API_KEY:
    raise RuntimeError("FAMGATEWAY_API_KEY is required")
if not PUBLIC_BASE_URL or not PUBLIC_BASE_URL.startswith("https://"):
    raise RuntimeError("PUBLIC_BASE_URL is required (public HTTPS Railway domain)")
