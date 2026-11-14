import aiohttp
import hmac
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from config import CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV, PUBLIC_BASE_URL

API_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "sandbox" else "https://api.cashfree.com/pg"
API_VERSION = "2022-09-01"

def _headers():
    return {
        "x-client-id": CASHFREE_APP_ID,
        "x-client-secret": CASHFREE_SECRET_KEY,
        "x-api-version": API_VERSION,
        "Content-Type": "application/json",
    }

async def create_payment_link(order_id: str, amount: float, telegram_user_id: int, customer_name: str, phone: str):
    payload = {
        "link_id": order_id,
        "link_amount": round(float(amount), 2),
        "link_currency": "INR",
        "link_purpose": f"Panel Army order {order_id}",
        "customer_details": {
            "customer_name": (customer_name or "Telegram User")[:100],
            "customer_phone": phone,
        },
        "link_partial_payments": False,
        "link_expiry_time": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="seconds"),
        "link_notify": {"send_sms": False, "send_email": False},
        "link_auto_reminders": False,
        "link_meta": {
            "notify_url": f"{PUBLIC_BASE_URL}/cashfree/webhook",
            "return_url": "https://t.me/",
        },
        "link_notes": {"telegram_user_id": str(telegram_user_id), "order_id": order_id},
    }
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{API_BASE}/links", headers=_headers(), json=payload) as response:
            body = await response.json(content_type=None)
            if response.status not in (200, 201):
                raise RuntimeError(f"Cashfree API error {response.status}: {body}")
            link_url = body.get("link_url")
            if not link_url:
                raise RuntimeError(f"Cashfree response missing link_url: {body}")
            return {"payment_link": link_url, "cashfree_link_id": body.get("link_id", order_id)}

async def fetch_payment_link(link_id: str):
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{API_BASE}/links/{link_id}", headers=_headers()) as response:
            body = await response.json(content_type=None)
            if response.status != 200:
                raise RuntimeError(f"Cashfree fetch link error {response.status}: {body}")
            return body

def verify_webhook_signature(timestamp: str, raw_body: bytes, signature: str) -> bool:
    if not timestamp or not signature:
        return False
    digest = hmac.new(CASHFREE_SECRET_KEY.encode("utf-8"), timestamp.encode("utf-8") + raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)
