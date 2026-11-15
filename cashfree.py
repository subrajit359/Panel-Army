import aiohttp
import asyncio
import hmac
import hashlib
import base64
import binascii
import uuid
from datetime import datetime, timedelta, timezone
from config import CASHFREE_APP_ID, CASHFREE_SECRET_KEY, CASHFREE_ENV, PUBLIC_BASE_URL

API_BASE = "https://sandbox.cashfree.com/pg" if CASHFREE_ENV == "sandbox" else "https://api.cashfree.com/pg"
API_VERSION = "2022-09-01"

# Reuse one keep-alive connection pool across checkout requests. Creating a new
# ClientSession for every customer adds DNS/TLS setup latency.
_http_session = None
_session_lock = asyncio.Lock()

def _timeout():
    return aiohttp.ClientTimeout(total=22, connect=8, sock_connect=8, sock_read=18)

async def _get_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        async with _session_lock:
            if _http_session is None or _http_session.closed:
                connector = aiohttp.TCPConnector(
                    limit=40, limit_per_host=30, ttl_dns_cache=600,
                    keepalive_timeout=45, enable_cleanup_closed=True,
                )
                _http_session = aiohttp.ClientSession(
                    timeout=_timeout(), connector=connector,
                    headers={"Accept": "application/json"},
                )
    return _http_session

async def close_cashfree_session():
    global _http_session
    if _http_session is not None and not _http_session.closed:
        await _http_session.close()
    _http_session = None

def _headers():
    return {"x-client-id": CASHFREE_APP_ID, "x-client-secret": CASHFREE_SECRET_KEY, "x-api-version": API_VERSION, "Content-Type": "application/json"}

async def create_payment_link(order_id: str, amount: float, telegram_user_id: int, customer_name: str, phone: str, payment_description: str = "Panel Army purchase"):
    """Create a unique Cashfree Payment Link for one Panel Army order.

    Payment Links use POST /links and do not call the restricted POST /orders/pay
    S2S QR-initiation endpoint. Partial payments and Cashfree SMS/email delivery
    are disabled; the bot shares the returned URL directly in Telegram.
    """
    if not PUBLIC_BASE_URL:
        raise RuntimeError("PUBLIC_BASE_URL is required for Cashfree payment notifications")
    link_expiry = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(timespec="seconds")
    payload = {
        "link_id": str(order_id)[:50],
        "link_amount": round(float(amount), 2),
        "link_currency": "INR",
        "link_purpose": (payment_description or f"Panel Army {order_id}")[:200],
        "link_partial_payments": False,
        "link_expiry_time": link_expiry,
        "customer_details": {
            "customer_name": (customer_name or "Telegram User")[:100],
            "customer_phone": str(phone).strip(),
        },
        "link_notify": {"send_email": False, "send_sms": False},
        "link_auto_reminders": False,
        "link_meta": {
            "notify_url": f"{PUBLIC_BASE_URL}/cashfree/webhook",
            "return_url": "https://t.me/",
            "payment_methods": "upi",
            "upi_intent": True,
        },
    }
    headers = _headers()
    # A deterministic idempotency key makes safe retries of this order less
    # likely to create multiple payment links after a network timeout.
    headers["x-idempotency-key"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"panel-army-cashfree-link:{order_id}"))
    session = await _get_session()
    async with session.post(f"{API_BASE}/links", headers=headers, json=payload) as resp:
        created = await resp.json(content_type=None)
        if resp.status not in (200, 201):
            code = created.get("code") if isinstance(created, dict) else None
            message = created.get("message") if isinstance(created, dict) else None
            raise RuntimeError(f"Cashfree Payment Link creation error {resp.status}: {code or 'provider_error'} {str(message or '')[:180]}")
    link_url = created.get("link_url") if isinstance(created, dict) else None
    returned_link_id = created.get("link_id") if isinstance(created, dict) else None
    if not link_url or not isinstance(link_url, str) or not link_url.startswith("https://"):
        raise RuntimeError("Cashfree accepted Payment Link request but returned no valid HTTPS link")
    if returned_link_id and returned_link_id != order_id:
        raise RuntimeError("Cashfree returned a Payment Link ID that does not match the order")
    return {
        "link_id": returned_link_id or order_id,
        "link_url": link_url,
        "link_status": created.get("link_status", "ACTIVE"),
        "link_expiry_time": created.get("link_expiry_time") or link_expiry,
    }


async def fetch_payment_link(link_id: str):
    """Fetch authoritative Payment Link state from Cashfree."""
    session = await _get_session()
    async with session.get(f"{API_BASE}/links/{link_id}", headers=_headers()) as response:
        body = await response.json(content_type=None)
        if response.status == 200:
            return body
        code = body.get("code") if isinstance(body, dict) else None
        raise RuntimeError(f"Cashfree fetch Payment Link error {response.status}: {code or 'provider_error'}")


def payment_link_is_paid(link: dict, expected_amount: float, expected_link_id: str | None = None) -> bool:
    """Require a fully paid, exact-amount link before fulfilling an order."""
    if not isinstance(link, dict):
        return False
    if expected_link_id and link.get("link_id") != expected_link_id:
        return False
    try:
        link_amount = round(float(link.get("link_amount") or 0), 2)
        amount_paid = round(float(link.get("link_amount_paid") or 0), 2)
    except (TypeError, ValueError):
        return False
    return (
        str(link.get("link_status", "")).upper() == "PAID"
        and abs(link_amount - round(float(expected_amount), 2)) < 0.005
        and abs(amount_paid - round(float(expected_amount), 2)) < 0.005
        and str(link.get("link_currency", "INR")).upper() == "INR"
    )


async def create_upi_qr_order(order_id: str, amount: float, telegram_user_id: int, customer_name: str, phone: str, payment_description: str = "Panel Army purchase"):
    """Create a Cashfree PG order, then initiate its UPI QR payment."""
    payload = {
        "order_id": order_id, "order_amount": round(float(amount), 2), "order_currency": "INR",
        "customer_details": {"customer_id": f"tg_{telegram_user_id}", "customer_name": (customer_name or "Telegram User")[:100], "customer_phone": phone},
        "order_meta": {"notify_url": f"{PUBLIC_BASE_URL}/cashfree/webhook", "return_url": "https://t.me/"},
        "order_expiry_time": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(timespec="seconds"),
        "order_note": (payment_description or f"Panel Army {order_id}")[:200],
    }
    session = await _get_session()
    async with session.post(f"{API_BASE}/orders",headers=_headers(),json=payload) as resp:
        created=await resp.json(content_type=None)
        if resp.status not in (200,201):
            code = created.get("code") if isinstance(created, dict) else None
            message = created.get("message") if isinstance(created, dict) else None
            raise RuntimeError(f"Cashfree create order error {resp.status}: {code or 'provider_error'} {str(message or '')[:180]}")
    session_id=created.get("payment_session_id")
    if not session_id: raise RuntimeError("Cashfree response missing payment_session_id")
    pay_payload={"payment_session_id":session_id,"payment_method":{"upi":{"channel":"qrcode"}}}
    async with session.post(f"{API_BASE}/orders/sessions",headers=_headers(),json=pay_payload) as resp:
        paid=await resp.json(content_type=None)
        if resp.status not in (200,201):
            code = paid.get("code") if isinstance(paid, dict) else None
            message = paid.get("message") if isinstance(paid, dict) else None
            raise RuntimeError(f"Cashfree QR initiation error {resp.status}: {code or 'provider_error'} {str(message or '')[:180]}")
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
    # GET is idempotent, so a single short retry is safe for transient gateway/network errors.
    session = await _get_session()
    for attempt in range(2):
        try:
            async with session.get(f"{API_BASE}/orders/{order_id}/payments",headers=_headers()) as response:
                body = await response.json(content_type=None)
                if response.status == 200:
                    return body
                if response.status not in (429, 500, 502, 503, 504) or attempt:
                    code = body.get("code") if isinstance(body, dict) else None
                    raise RuntimeError(f"Cashfree fetch payments error {response.status}: {code or 'provider_error'}")
        except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, asyncio.TimeoutError):
            if attempt:
                raise
        await asyncio.sleep(0.15)
    raise RuntimeError("Cashfree payment status temporarily unavailable")

def verify_webhook_signature(timestamp: str, raw_body: bytes, signature: str) -> bool:
    if not timestamp or not signature:return False
    digest=hmac.new(CASHFREE_SECRET_KEY.encode(),timestamp.encode()+raw_body,hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(),signature)
