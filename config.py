import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID", "").strip()
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY", "").strip()
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "sandbox").strip().lower()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
    raise RuntimeError("CASHFREE_APP_ID and CASHFREE_SECRET_KEY are required")
if not PUBLIC_BASE_URL:
    raise RuntimeError("PUBLIC_BASE_URL is required (Railway public domain)")
