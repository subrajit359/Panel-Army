"""FamGateway dynamic UPI QR client for Panel Army Store."""
import asyncio
import aiohttp
from config import FAMGATEWAY_API_KEY, PUBLIC_BASE_URL

BASE_URL = "https://famgateway.in"
_session = None
_session_lock = asyncio.Lock()


def _timeout():
    return aiohttp.ClientTimeout(total=18, connect=5, sock_connect=5, sock_read=12)


async def _get_session():
    global _session
    if _session is None or _session.closed:
        async with _session_lock:
            if _session is None or _session.closed:
                connector = aiohttp.TCPConnector(limit=30, limit_per_host=20, ttl_dns_cache=600, keepalive_timeout=45)
                _session = aiohttp.ClientSession(timeout=_timeout(), connector=connector, headers={"Accept": "application/json"})
    return _session


async def close_famgateway_session():
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def _require_key():
    if not FAMGATEWAY_API_KEY:
        raise RuntimeError("FAMGATEWAY_API_KEY is not configured in Railway Variables")


async def create_qr(amount: float, customer_name: str = "Customer", customer_phone: str = "", note: str = "Panel Army purchase"):
    """Create a unique FamGateway dynamic QR for one local order."""
    _require_key()
    amount = round(float(amount), 2)
    payload = {
        "api_key": FAMGATEWAY_API_KEY,
        "amount": amount,
        "customer_name": (customer_name or "Customer")[:80],
        "customer_phone": str(customer_phone or "")[:20],
        "webhook_url": f"{PUBLIC_BASE_URL}/famgateway/webhook",
    }
    session = await _get_session()
    async with session.post(f"{BASE_URL}/api/create-order", json=payload, headers={"X-Api-Key": FAMGATEWAY_API_KEY, "Content-Type": "application/json"}) as response:
        try:
            body = await response.json(content_type=None)
        except Exception as exc:
            raise RuntimeError("FamGateway returned invalid JSON while creating the QR") from exc
        if response.status != 200 or not isinstance(body, dict):
            message = body.get("message") if isinstance(body, dict) else "provider error"
            raise RuntimeError(f"FamGateway create-order HTTP {response.status}: {str(message or 'provider error')[:180]}")
    if str(body.get("status", "")).lower() != "success":
        raise RuntimeError(str(body.get("message") or "FamGateway could not create the payment QR")[:180])
    data = body.get("data") or {}
    order_id = str(data.get("order_id") or "")
    qr_url = str(data.get("qr_url") or "")
    try:
        returned_amount = round(float(data.get("payable_amount", data.get("amount"))), 2)
    except (TypeError, ValueError):
        raise RuntimeError("FamGateway returned an invalid payable amount")
    if not order_id or not qr_url.startswith("https://famgateway.in/"):
        raise RuntimeError("FamGateway response is missing a valid order ID or QR image URL")
    if abs(returned_amount - amount) >= 0.005:
        raise RuntimeError("FamGateway returned an amount that does not match the Panel Army order")
    return {
        "order_id": order_id, "qr_url": qr_url, "checkout_url": str(data.get("checkout_url") or ""),
        "upi_intent": str(data.get("upi_intent") or ""), "amount": returned_amount,
        "expires_at_ist": data.get("expires_at_ist"),
    }


async def verify_payment(fam_order_id: str, expected_amount: float):
    """Server-to-server verification; only exact matching SUCCESS is accepted."""
    _require_key()
    session = await _get_session()
    params = {"order_id": str(fam_order_id)}
    async with session.get(f"{BASE_URL}/api/verify-order.php", params=params, headers={"X-Api-Key": FAMGATEWAY_API_KEY}) as response:
        try:
            body = await response.json(content_type=None)
        except Exception as exc:
            raise RuntimeError("FamGateway returned invalid JSON during payment verification") from exc
        if response.status != 200 or not isinstance(body, dict):
            message = body.get("message") if isinstance(body, dict) else "provider error"
            raise RuntimeError(f"FamGateway verify-order HTTP {response.status}: {str(message or 'provider error')[:180]}")
    data = body.get("data") or {}
    status = str(body.get("status") or data.get("status") or "unknown").lower()
    returned_id = str(data.get("order_id") or body.get("order_id") or "")
    try:
        paid_amount = round(float(data.get("amount") or data.get("payable_amount") or 0), 2)
    except (TypeError, ValueError):
        paid_amount = 0.0
    id_matches = returned_id == str(fam_order_id)
    amount_matches = abs(paid_amount - round(float(expected_amount), 2)) < 0.005
    is_paid = status == "success" and id_matches and amount_matches
    if status == "success" and (not id_matches or not amount_matches):
        raise RuntimeError("FamGateway verification mismatch: order ID or paid amount does not match")
    return is_paid, status.upper(), paid_amount
