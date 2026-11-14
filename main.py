import asyncio
import os
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from config import BOT_TOKEN, ADMIN_IDS, PUBLIC_BASE_URL
from db import init_db, get_or_create_user, list_products, get_product, create_order, get_order, fulfill_paid_order, add_product, add_stock, list_orders
from cashfree import create_payment_link, fetch_payment_link, verify_webhook_signature

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("panel_army")
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

class CheckoutState(StatesGroup):
    waiting_phone = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍 Store", callback_data="store")],
        [InlineKeyboardButton(text="📦 My Orders", callback_data="orders")],
        [InlineKeyboardButton(text="ℹ️ Help", callback_data="help")],
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        "<b>⚔️ PANEL ARMY</b>\n\nWelcome! Browse available digital products and receive your purchased license key automatically after verified payment.",
        reply_markup=main_keyboard()
    )

@dp.callback_query(F.data == "store")
async def store(call: CallbackQuery):
    products = await list_products()
    if not products:
        await call.message.edit_text("The store is currently empty. Please check again later.", reply_markup=main_keyboard())
        await call.answer()
        return
    rows = [[InlineKeyboardButton(text=f"{p['name']} — ₹{p['price_inr']:.2f} (stock {p['stock']})", callback_data=f"product:{p['id']}")] for p in products if p["stock"] > 0]
    rows.append([InlineKeyboardButton(text="⬅️ Home", callback_data="home")])
    await call.message.edit_text("<b>🛍 Panel Army Store</b>\nChoose a product:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()

@dp.callback_query(F.data.startswith("product:"))
async def product_view(call: CallbackQuery):
    product_id = int(call.data.split(":", 1)[1])
    p = await get_product(product_id)
    if not p or p["stock"] < 1:
        await call.answer("Out of stock.", show_alert=True); return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Pay ₹{p['price_inr']:.2f}", callback_data=f"buy:{product_id}")],
        [InlineKeyboardButton(text="⬅️ Store", callback_data="store")]
    ])
    await call.message.edit_text(f"<b>{p['name']}</b>\n\n{p['description']}\n\nPrice: <b>₹{p['price_inr']:.2f}</b>\nAvailable stock: {p['stock']}", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery, state: FSMContext):
    product_id = int(call.data.split(":", 1)[1])
    p = await get_product(product_id)
    if not p or p["stock"] < 1:
        await call.answer("Out of stock.", show_alert=True)
        return
    order = await create_order(call.from_user.id, product_id, p["price_inr"])
    await state.update_data(order_id=order["order_id"], product_id=product_id, amount=p["price_inr"])
    await state.set_state(CheckoutState.waiting_phone)
    await call.message.answer(
        f"Order <code>{order['order_id']}</code> created for ₹{p['price_inr']:.2f}.\n"
        "Please send your 10-digit Indian mobile number to generate the Cashfree payment link."
    )
    await call.answer()

@dp.message(CheckoutState.waiting_phone, F.text)
async def checkout_phone(message: Message, state: FSMContext):
    phone = "".join(ch for ch in message.text if ch.isdigit())
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    if len(phone) != 10 or phone[0] not in "6789":
        await message.answer("Please send a valid 10-digit Indian mobile number.")
        return
    data = await state.get_data()
    order = await get_order(data["order_id"])
    if not order or order["status"] != "PENDING":
        await state.clear()
        await message.answer("This order is no longer pending. Please start a new purchase.")
        return
    try:
        payment = await create_payment_link(
            data["order_id"], data["amount"], message.from_user.id,
            message.from_user.full_name or f"user{message.from_user.id}", phone
        )
        await message.answer(
            f"Order <code>{data['order_id']}</code>\nAmount: <b>₹{data['amount']:.2f}</b>\n\n"
            f"Pay securely with Cashfree:\n{payment['payment_link']}\n\n"
            "Your key will be sent here after payment verification.",
            disable_web_page_preview=True
        )
    except Exception:
        log.exception("Cashfree payment link creation failed")
        await message.answer("Could not create the payment link. Please retry your purchase.")
    await state.clear()

@dp.callback_query(F.data == "orders")
async def orders(call: CallbackQuery):
    rows = await list_orders(call.from_user.id)
    if not rows:
        msg = "You have no orders yet."
    else:
        msg = "<b>Your recent orders</b>\n" + "\n".join(
            f"• <code>{o['order_id']}</code> — ₹{o['amount_inr']:.2f} — {o['status']}" for o in rows[:10]
        )
    await call.message.edit_text(msg, reply_markup=main_keyboard())
    await call.answer()

@dp.callback_query(F.data == "help")
async def help_cb(call: CallbackQuery):
    await call.message.edit_text("For order or delivery support, contact the store administrator.", reply_markup=main_keyboard())
    await call.answer()

@dp.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text("⚔️ <b>PANEL ARMY</b>\nChoose an option:", reply_markup=main_keyboard())
    await call.answer()

@dp.message(Command("admin"))
async def admin_help(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "<b>Admin commands</b>\n"
        "/addproduct NAME|PRICE|DESCRIPTION — create product\n"
        "/addstock PRODUCT_ID — then send keys as one key per line\n"
        "/products — list products\n"
        "/orders — recent orders"
    )

@dp.message(Command("addproduct"))
async def admin_addproduct(message: Message):
    if not is_admin(message.from_user.id): return
    raw = message.text.partition(" ")[2]
    parts = raw.split("|", 2)
    if len(parts) != 3:
        await message.answer("Usage: /addproduct NAME|PRICE|DESCRIPTION"); return
    try:
        name, price, desc = parts[0].strip(), float(parts[1]), parts[2].strip()
        if price <= 0: raise ValueError()
        p = await add_product(name, price, desc)
        await message.answer(f"Product created: ID <code>{p['id']}</code> — {p['name']}")
    except ValueError:
        await message.answer("Invalid price. Use a positive number.")

@dp.message(Command("addstock"))
async def admin_addstock(message: Message):
    if not is_admin(message.from_user.id): return
    try:
        product_id = int(message.text.partition(" ")[2].strip())
    except ValueError:
        await message.answer("Usage: /addstock PRODUCT_ID"); return
    await message.answer(f"Send the keys for product ID {product_id}, one key per line. Send /cancel to abort.")
    # State is tracked simply per-admin in memory for this starter.
    pending_stock[message.from_user.id] = product_id

pending_stock = {}

@dp.message(Command("cancel"))
async def cancel(message: Message):
    pending_stock.pop(message.from_user.id, None)
    await message.answer("Cancelled.")

@dp.message(F.text, ~F.text.startswith("/"))
async def receive_stock(message: Message):
    product_id = pending_stock.get(message.from_user.id)
    if not product_id or not is_admin(message.from_user.id): return
    keys = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not keys: await message.answer("No keys found. Send one key per line."); return
    added = await add_stock(product_id, keys)
    pending_stock.pop(message.from_user.id, None)
    await message.answer(f"Added {added} key(s) to product ID {product_id}.")

@dp.message(Command("products"))
async def admin_products(message: Message):
    if not is_admin(message.from_user.id): return
    products = await list_products(include_empty=True)
    await message.answer("\n".join(f"ID {p['id']} | {p['name']} | ₹{p['price_inr']:.2f} | stock {p['stock']}" for p in products) or "No products.")

@dp.message(Command("orders"))
async def admin_orders(message: Message):
    if not is_admin(message.from_user.id): return
    rows = await list_orders(None)
    await message.answer("\n".join(f"{o['order_id']} | user {o['user_id']} | ₹{o['amount_inr']:.2f} | {o['status']}" for o in rows[:20]) or "No orders.")

async def run_webhook_server():
    # aiohttp endpoint: Cashfree webhook raw body is signature-verified before parsing.
    from aiohttp import web
    import json
    async def webhook(request):
        raw = await request.read()
        timestamp = request.headers.get("x-webhook-timestamp", "")
        signature = request.headers.get("x-webhook-signature", "")
        if not verify_webhook_signature(timestamp, raw, signature):
            return web.Response(status=401, text="Invalid signature")
        try:
            payload = json.loads(raw)
            data = payload.get("data", {})
            link_details = data.get("link_details", {}) or {}
            order_id = (link_details.get("link_id") or data.get("link_id") or payload.get("link_id")
                        or (data.get("order", {}) or {}).get("order_id"))
            # Confirm status and paid amount with Cashfree API rather than trusting webhook body alone.
            if order_id:
                order = await get_order(order_id)
                if order and order["status"] == "PENDING":
                    remote = await fetch_payment_link(order_id)
                    paid_amount = float(remote.get("link_amount_paid") or 0)
                    expected_amount = float(order["amount_inr"])
                    if remote.get("link_status") == "PAID" and abs(paid_amount - expected_amount) < 0.005:
                        result = await fulfill_paid_order(order_id)
                        if result and result.get("key_text"):
                            await bot.send_message(order["user_id"],
                                f"✅ <b>Payment verified!</b>\n\nYour key:\n<code>{result['key_text']}</code>\n\n"
                                f"Order: <code>{order_id}</code>")
                        elif result and not result.get("key_text"):
                            await bot.send_message(order["user_id"],
                                f"Payment confirmed for <code>{order_id}</code>, but stock ran out. Please contact support for a refund.")
        except Exception:
            log.exception("Webhook processing failed")
            return web.Response(status=500, text="Webhook processing error")
        return web.Response(text="OK")
    app = web.Application()
    app.router.add_post("/cashfree/webhook", webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("Webhook listening on port %s", port)
    return runner

async def main():
    await init_db()
    runner = await run_webhook_server()
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    import os
    asyncio.run(main())
