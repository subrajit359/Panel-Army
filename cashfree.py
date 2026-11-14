import aiohttp
import hmac
import hashlib
import base64
import binascii
from datetime import datetime, timedelta, timezone
from config import CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV, PUBLIC_BASE_URL

API_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "sandbox" else "https://api.cashfree.com/pg"
API_VERSION = "2022-09-01"

def _headers():
    return {"x-client-id": CASHFREE_APP_ID, "x-client-secret": CASHFREE_SECRET_KEY, "x-api-version": API_VERSION, "Content-Type": "application/json"}

async def create_upi_qr_order(order_id: str, amount: float, telegram_user_id: int, customer_name: str, phone: str):
    """Create a Cashfree PG order, then initiate its UPI QR payment."""
    payload = {
        "order_id": order_id, "order_amount": round(float(amount), 2), "order_currency": "INR",
        "customer_details": {"customer_id": f"tg_{telegram_user_id}", "customer_name": (customer_name or "Telegram User")[:100], "customer_phone": phone},
        "order_meta": {"notify_url": f"{PUBLIC_BASE_URL}/cashfree/webhook", "return_url": "https://t.me/"},
        "order_expiry_time": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds"),
        "order_note": f"Panel Army {order_id}",
    }
    timeout=aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(f"{API_BASE}/orders",headers=_headers(),json=payload) as resp:
            created=await resp.json(content_type=None)
            if resp.status not in (200,201): raise RuntimeError(f"Cashfree create order error {resp.status}: {created}")
        session_id=created.get("payment_session_id")
        if not session_id: raise RuntimeError(f"Cashfree response missing payment_session_id: {created}")
        pay_payload={"payment_session_id":session_id,"payment_method":{"upi":{"channel":"qrcode"}}}
        async with session.post(f"{API_BASE}/orders/sessions",headers=_headers(),json=pay_payload) as resp:
            paid=await resp.json(content_type=None)
            if resp.status not in (200,201): raise RuntimeError(f"Cashfree QR initiation error {resp.status}: {paid}")
    # Cashfree can return either a UPI string or an image data URI. In the
    # response shape used by QR initiation, the image is at
    # data.payload.qrcode (for example: data:image/png;base64,...).
    def find_qr(obj):
        if isinstance(obj, dict):
            payload = obj.get("payload")
            if isinstance(payload, dict):
                value = payload.get("qrcode")
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for key in ("qr_code", "qrCode", "qr_code_url", "qr_url", "qrcode", "code"):
                value = obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            for value in obj.values():
                found = find_qr(value)
                if found:
                    return found
        elif isinstance(obj, list):
            for value in obj:
                found = find_qr(value)
                if found:
                    return found
        return None

    qr_value = find_qr(paid)
    if not qr_value:
        # Do not dump the response body: it may contain a large QR image.
        raise RuntimeError(f"Cashfree accepted QR request but returned no QR payload (keys={list(paid) if isinstance(paid, dict) else type(paid).__name__})")

    result = {"qr_value": qr_value, "cashfree_order_id": created.get("order_id", order_id)}
    if qr_value.startswith("data:image/"):
        try:
            header, encoded = qr_value.split(",", 1)
            if ";base64" not in header.lower():
                raise ValueError("QR image data URI is not base64 encoded")
            image_bytes = base64.b64decode(encoded, validate=True)
            if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and not image_bytes.startswith(b"\xff\xd8"):
                raise ValueError("QR image data is not a valid PNG or JPEG")
            result["qr_image_bytes"] = image_bytes
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError(f"Cashfree returned an invalid base64 QR image: {exc}") from exc
    return result

async def fetch_order_payments(order_id: str):
    timeout=aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{API_BASE}/orders/{order_id}/payments",headers=_headers()) as response:
            body=await response.json(content_type=None)
            if response.status!=200: raise RuntimeError(f"Cashfree fetch payments error {response.status}: {body}")
            return body

def verify_webhook_signature(timestamp: str, raw_body: bytes, signature: str) -> bool:
    if not timestamp or not signature:return False
    digest=hmac.new(CASHFREE_SECRET_KEY.encode(),timestamp.encode()+raw_body,hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(),signature)
