import asyncio, os, logging, html, time, hashlib
from collections import deque, OrderedDict
from datetime import datetime, timedelta, timezone
from io import BytesIO
import qrcode
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, BotCommand
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import BaseMiddleware
from config import BOT_TOKEN, ADMIN_IDS, PUBLIC_BASE_URL
from db import (init_db, close_db, is_user_banned, get_or_create_user, list_categories, list_products, get_product, get_plan,
                create_order, get_order, fulfill_paid_order, credit_wallet_for_no_stock, add_product, add_plan, add_stock, create_topup_order, fulfill_wallet_topup,
                list_orders, get_user, pay_wallet, set_payment_link, expire_order, dashboard_stats, search_users,
                admin_user, set_banned, adjust_wallet, wallet_history, admin_orders, admin_stock_summary,
                set_reseller, set_reseller_pricing, edit_product, deactivate_product, create_coupon, set_user_phone,
                set_bot_setting, recent_admin_logs, admin_log, record_refund, refund_history, list_keys, user_order_stats, list_resellers, list_coupons, update_coupon, delete_coupon, set_product_maintenance, delete_category_admin, delete_product_admin,
                attach_referrer, award_referral_after_purchase, referral_stats, claim_referral_reward, add_referral_stock, admin_all_products, admin_all_plans, edit_plan_admin, deactivate_plan_admin, rename_category_admin, category_products_admin)
from cashfree import create_upi_qr_order, fetch_order_payments, verify_webhook_signature, close_cashfree_session

logging.basicConfig(level=logging.INFO)
log=logging.getLogger("panel_army")
bot=Bot(BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp=Dispatcher()

class CheckoutState(StatesGroup):
    waiting_phone=State()
    custom_quantity=State()
    custom_topup=State()

class ContactState(StatesGroup):
    waiting_contact=State()

class AdminState(StatesGroup):
    search_user=State()
    broadcast=State()
    stock_category_name=State()
    stock_product_name=State()
    stock_product_description=State()
    stock_plan_duration=State()
    stock_plan_prices=State()
    stock_keys=State()
    reward_keys=State()
    admin_input=State()
    broadcast_collect=State()
    broadcast_confirm=State()

def is_admin(user_id:int)->bool:return user_id in ADMIN_IDS

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Dashboard",callback_data="adm:dashboard"),InlineKeyboardButton(text="👥 Users",callback_data="adm:users")],
        [InlineKeyboardButton(text="💰 Wallet",callback_data="adm:wallet"),InlineKeyboardButton(text="📦 Products",callback_data="adm:products")],
        [InlineKeyboardButton(text="🔑 Key Stock",callback_data="adm:stock"),InlineKeyboardButton(text="🎁 Reward Key Stock",callback_data="rewardstock:menu")],
        [InlineKeyboardButton(text="💳 Payments",callback_data="adm:payments")],
        [InlineKeyboardButton(text="👑 Resellers",callback_data="adm:resellers"),InlineKeyboardButton(text="📢 Broadcast",callback_data="adm:broadcast")],
        [InlineKeyboardButton(text="🎟️ Coupons",callback_data="adm:coupons"),InlineKeyboardButton(text="⚙️ Settings",callback_data="adm:settings")],
        [InlineKeyboardButton(text="📜 Admin Logs",callback_data="adm:logs")],
    ])

def admin_nav_rows():
    return [list(row) for row in admin_keyboard().inline_keyboard]

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛍️ Shop Now",callback_data="shop")],
        [InlineKeyboardButton(text="📦 My Orders",callback_data="orders"),InlineKeyboardButton(text="👤 Profile",callback_data="profile")],
        [InlineKeyboardButton(text="💰 Add Balance",callback_data="balance"),InlineKeyboardButton(text="🎁 Referral",callback_data="referral")],
        [InlineKeyboardButton(text="🎰 Lucky Spin",callback_data="spin"),InlineKeyboardButton(text="⚡ Reseller Dashboard",callback_data="reseller")],
        [InlineKeyboardButton(text="📥 Download Files",callback_data="downloads"),InlineKeyboardButton(text="📺 How to Use",callback_data="howto")],
        [InlineKeyboardButton(text="🎧 Support",callback_data="support")],
    ])

def store_welcome(name="Customer"):
    safe=html.escape(name or "Customer")
    return ("🏪 ━━ Panel Army Store ━━ 🏪\n\n" f"👋 Welcome, {safe}!\n\n"
            "⭐ ━ STORE HIGHLIGHTS ━ ⭐\n\n│ 🔑 Premium Game Keys\n│ ⚡ Instant Delivery 24/7\n│ 🔒 100% Secure Payment\n│ 💰 Best Prices Guaranteed\n│ 🎁 Referral Rewards\n│ 📞 Professional Support\n\n━━━━━━━━━━━━━━━━━━━━━\n\n🚀 Tap Shop Now to Start!")

def home_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🛍️ Open Shop Menu",callback_data="home")]])

def quantity_keyboard(plan_id, product_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1",callback_data=f"qty:{plan_id}:1"),InlineKeyboardButton(text="5",callback_data=f"qty:{plan_id}:5"),InlineKeyboardButton(text="10",callback_data=f"qty:{plan_id}:10"),InlineKeyboardButton(text="15",callback_data=f"qty:{plan_id}:15")],
        [InlineKeyboardButton(text="✍️ Custom Quantity",callback_data=f"qtycustom:{plan_id}")],
        [InlineKeyboardButton(text="🔙 Back",callback_data=f"product:{product_id}")]])

def quantity_payment_keyboard(plan_id, quantity, amount, balance, product_id=None):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Pay with Wallet (₹{amount:.2f}) · Balance ₹{balance:.2f}",callback_data=f"wallet:{plan_id}:{quantity}")],
        [InlineKeyboardButton(text="💳 Pay with Paytm/UPI (INR)",callback_data=f"upi:{plan_id}:{quantity}")],
        [InlineKeyboardButton(text="📦 Bulk Purchase",callback_data=f"bulk:{plan_id}")],
        [InlineKeyboardButton(text="🔙 Back",callback_data=f"product:{product_id or plan_id}")]])

def topup_amount_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="₹10",callback_data="topup:10"),InlineKeyboardButton(text="₹20",callback_data="topup:20"),InlineKeyboardButton(text="₹50",callback_data="topup:50")],
        [InlineKeyboardButton(text="₹100",callback_data="topup:100"),InlineKeyboardButton(text="✍️ Custom Amount",callback_data="topup:custom")],
        [InlineKeyboardButton(text="🔙 Dashboard",callback_data="home")]])

def category_keyboard(categories):
    rows=[[InlineKeyboardButton(text=cat['name'],callback_data="category:"+hashlib.sha256(cat['name'].encode("utf-8")).hexdigest()[:16])] for cat in categories]
    rows.append([InlineKeyboardButton(text="🔙 Back to Menu",callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def product_keyboard(products):
    rows=[[InlineKeyboardButton(text=p['name'],callback_data=f"product:{p['id']}")] for p in products]
    rows.append([InlineKeyboardButton(text="🔙 All Categories",callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def price_details(p,user):
    reseller=bool(user and user['is_reseller'])
    shown_inr=p['reseller_price_inr'] if reseller else p['price_inr']
    price_label="👑 Reseller Price" if reseller else "🏷️ Price"
    lines=[f"🎮 <b>{html.escape(p['product_name'])} — {html.escape(p['duration'])}</b>","━━━━━━━━━━━━━━━━━━",
           "⚡ <b>PLAN DETAILS:</b>",
           f"🔹 {html.escape(p['duration'])}",
           
           f"{price_label}: ₹{shown_inr:.2f}",
           "━━━━━━━━━━━━━━━━━━","🎯 Select your plan below:"]
    return "\n".join(lines)

def plan_keyboard(product,user=None):
    reseller=bool(user and user["is_reseller"])
    rows=[]
    for plan in product['plans']:
        shown_inr=plan['reseller_price_inr'] if reseller else plan['price_inr']
        # Availability is intentionally not exposed to customers. The order is
        # accepted and stock is checked only after successful payment.
        rows.append([InlineKeyboardButton(text=f"🔑 [{plan['duration']}] » ₹{shown_inr:.2f}",callback_data=f"plan:{plan['id']}")])
    rows.append([InlineKeyboardButton(text="🔙 Back to Shop",callback_data="shop")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def success_message(game,duration,quantity,key):
    keys=html.escape(key or "")
    return ("✅ <b>Payment Successful!</b>\n\n"
            f"🎮 Game: {html.escape(game)}\n⏳ Duration: {html.escape(duration)}\n📦 Quantity: {quantity}\n🔑 Key: <code>{keys}</code>\n\n🙏 Thank you for your purchase!")

# Telegram requires callback queries to be acknowledged quickly. A tiny bounded
# cache avoids a second database lookup on rapid taps; changes are invalidated on ban/unban.
_callback_answered = set()
_callback_answered_order = deque()
_ban_cache = OrderedDict()
_BAN_CACHE_TTL = 3.0

async def callback_answer(call: CallbackQuery, text=None, show_alert=False):
    if call.id in _callback_answered:
        # The callback has already been acknowledged by middleware. Preserve important
        # validation/error feedback as a normal chat message instead of a failed second answer.
        if text and show_alert and call.message:
            await call.message.answer(text)
        return
    _callback_answered.add(call.id)
    _callback_answered_order.append(call.id)
    if len(_callback_answered_order) > 5000:
        old = _callback_answered_order.popleft()
        _callback_answered.discard(old)
    try:
        await call.answer(text=text, show_alert=show_alert)
    except Exception:
        # Expired callbacks must not break the actual handler operation.
        pass

class BanGuard(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user=getattr(event,"from_user",None)
        if isinstance(event, CallbackQuery):
            await callback_answer(event, "⏳")
        if user and not is_admin(user.id):
            now = time.monotonic()
            cached = _ban_cache.get(user.id)
            if cached and cached[0] > now:
                banned = cached[1]
                _ban_cache.move_to_end(user.id)
            else:
                banned = await is_user_banned(user.id)
                _ban_cache[user.id] = (now + _BAN_CACHE_TTL, banned)
                _ban_cache.move_to_end(user.id)
                while len(_ban_cache) > 5000:
                    _ban_cache.popitem(last=False)
            if banned:
                if isinstance(event,Message):
                    await event.answer("Your account is restricted. Contact support.")
                elif isinstance(event,CallbackQuery) and event.message:
                    await event.message.answer("Your account is restricted. Contact support.")
                return
        return await handler(event,data)

dp.message.outer_middleware(BanGuard())
dp.callback_query.outer_middleware(BanGuard())

@dp.message(CommandStart())
async def start(message:Message,state:FSMContext):
    is_new_user=await get_or_create_user(message.from_user.id,message.from_user.username,message.from_user.full_name)
    parts=(message.text or "").split(maxsplit=1)
    if is_new_user and len(parts)>1 and parts[1].startswith("ref_") and parts[1][4:].isdigit():
        await attach_referrer(message.from_user.id,int(parts[1][4:]))
    user=await get_user(message.from_user.id)
    if not user or not user.get("phone"):
        await state.set_state(ContactState.waiting_contact)
        kb=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Verify My Number",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
        display_name=html.escape(message.from_user.first_name or "Customer")
        verification_text=(
            "🏪 <b>Panel Army Store</b>\n\n"
            f"👋 Welcome, <b>{display_name}</b>!\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔐 <b>IDENTITY CHECK NEEDED</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Before you explore our store, we need a quick verification.\n\n"
            "🛡️ <b>Here's why:</b>\n"
            "• Safeguard your orders\n"
            "• Enable instant key delivery\n"
            "• Keep your account protected\n\n"
            "👇 <b>Tap the button below to get started:</b>"
        )
        await message.answer(verification_text,reply_markup=kb)
        return
    await state.clear()
    await message.answer(store_welcome(message.from_user.first_name),reply_markup=main_keyboard())

@dp.message(ContactState.waiting_contact,F.contact)
async def save_start_contact(message:Message,state:FSMContext):
    contact=message.contact
    if contact.user_id != message.from_user.id:
        await message.answer("Please use the button to share your own Telegram contact.")
        return
    phone="".join(ch for ch in (contact.phone_number or "") if ch.isdigit())
    if len(phone)==12 and phone.startswith("91"):phone=phone[2:]
    if len(phone)!=10 or phone[0] not in "6789":
        await message.answer("Please share a valid Indian mobile number using the button.")
        return
    await set_user_phone(message.from_user.id,phone)
    await state.clear()
    await message.answer("🛡️ <b>Identity Confirmed Successfully!</b>\n\n✅ Your phone number has been verified.\n🔒 Your account is now protected.\n⚡ You can now shop and receive instant key delivery.",reply_markup=ReplyKeyboardRemove())
    await message.answer(store_welcome(message.from_user.first_name),reply_markup=main_keyboard())

@dp.callback_query(F.data.in_({"shop","store"}))
async def shop(call:CallbackQuery):
    cats=await list_categories()
    if not cats:
        await call.message.edit_text("🛍️ The shop is empty right now. Please check back later.",reply_markup=main_keyboard())
    else:
        await call.message.edit_text("🎮 <b>— CHOOSE A CATEGORY —</b>\n\n✨ Pick what you play on:",reply_markup=category_keyboard(cats))
    await callback_answer(call, )

@dp.callback_query(F.data.startswith("category:"))
async def category(call:CallbackQuery):
    category_hash=call.data.split(":",1)[1]
    categories=await list_categories()
    name=next((c["name"] for c in categories if hashlib.sha256(c["name"].encode("utf-8")).hexdigest()[:16] == category_hash),None)
    if not name:
        await callback_answer(call, "Category list changed. Please open the shop again.", show_alert=True);return
    products=await list_products(category=name)
    if not products:
        await callback_answer(call, "No products in this category yet.",show_alert=True);return
    await call.message.edit_text(f"🎮 — 🤖 <b>{html.escape(name.upper())}</b> — 🎮\n\n✨ Available Products\n\n💎 Premium Keys\n⚡ Instant Delivery\n🔒 Secure Payment\n📞 Support\n\n🛒 Select a product below:",reply_markup=product_keyboard(products))
    await callback_answer(call, )

@dp.callback_query(F.data.startswith("product:"))
async def product_view(call:CallbackQuery):
    product_id=int(call.data.split(":",1)[1]);p=await get_product(product_id)
    if not p:
        await callback_answer(call, "Product not found.",show_alert=True);return
    if p.get("maintenance"):
        await call.message.edit_text(f"🛠️ <b>{html.escape(p['name'])} is under maintenance.</b>\nPlease check back later.",reply_markup=home_keyboard()); return
    user=await get_user(call.from_user.id)
    reseller=bool(user and user['is_reseller'])
    lines=[f"🏪 <b>PANEL ARMY</b>",f"🎮 <b>{html.escape(p['name'])}</b>","━━━━━━━━━━━━━━━━━━","⚡ <b>AVAILABLE PLANS:</b>"]
    for pl in p['plans']:
        price_inr=pl['reseller_price_inr'] if reseller else pl['price_inr']
        price_label="👑 Reseller Price" if reseller else "🏷️ Price"
        lines.extend([f"\n🔹 {html.escape(pl['duration'])}",f"{price_label}: ₹{price_inr:.2f}"])
    lines.extend(["━━━━━━━━━━━━━━━━━━","🎯 Select your plan below:"])
    await call.message.edit_text("\n".join(lines),reply_markup=plan_keyboard(p,user));await callback_answer(call, )

@dp.callback_query(F.data.startswith("outstock:"))
async def outstock(call:CallbackQuery):await callback_answer(call, "This plan is out of stock.",show_alert=True)

@dp.callback_query(F.data.startswith("plan:"))
async def plan_view(call:CallbackQuery):
    plan_id=int(call.data.split(":",1)[1]);p=await get_plan(plan_id)
    if not p:await callback_answer(call, "This plan is unavailable.",show_alert=True);return
    if p.get("maintenance"):
        await call.message.edit_text(f"🛠️ <b>{html.escape(p['product_name'])} is under maintenance.</b>\nPlease check back later.",reply_markup=home_keyboard()); return
    u=await get_user(call.from_user.id);reseller=bool(u and u['is_reseller']);unit=p['reseller_price_inr'] if reseller else p['price_inr'];amount=round(unit,2)
    await call.message.edit_text(f"🎮 <b>{html.escape(p['product_name'])} — {html.escape(p['duration'])}</b>\n━━━━━━━━━━━━━━━━━━\n📦 Quantity: <b>1 key</b>\n💰 Total: <b>₹{amount:.2f}</b>\n👛 Wallet: ₹{(u['wallet_balance'] if u else 0):.2f}\n\nChoose a payment method:",reply_markup=quantity_payment_keyboard(plan_id,1,amount,u['wallet_balance'] if u else 0,p['product_id']));await callback_answer(call, )

@dp.callback_query(F.data.startswith("bulk:"))
async def bulk_purchase_menu(call:CallbackQuery):
    plan_id=int(call.data.split(":",1)[1]);p=await get_plan(plan_id)
    if not p:
        await callback_answer(call, "This plan is unavailable.",show_alert=True);return
    if p.get("maintenance"):
        await callback_answer(call, f"{p['product_name']} is under maintenance.",show_alert=True); return
    await call.message.edit_text(f"🎮 <b>{html.escape(p['product_name'])} — {html.escape(p['duration'])}</b>\n\n📦 Select bulk purchase quantity:",reply_markup=quantity_keyboard(plan_id,p['product_id']))
    await callback_answer(call, )

@dp.callback_query(F.data.startswith("qty:"))
async def quantity_pick(call:CallbackQuery):
    _,pid_s,qty_s=call.data.split(":");plan_id=int(pid_s);quantity=int(qty_s);p=await get_plan(plan_id)
    if not p or quantity<1 or quantity>100:await callback_answer(call, "Please choose a quantity from 1 to 100.",show_alert=True);return
    if p.get("maintenance"): await callback_answer(call, f"{p['product_name']} is under maintenance.",show_alert=True); return
    u=await get_user(call.from_user.id);reseller=bool(u and u['is_reseller']);unit=p['reseller_price_inr'] if reseller else p['price_inr'];amount=round(unit*quantity,2)
    await call.message.edit_text(f"🎮 <b>{html.escape(p['product_name'])} — {html.escape(p['duration'])}</b>\n━━━━━━━━━━━━━━━━━━\n📦 Quantity: <b>{quantity}</b>\n💰 Total: ₹{amount:.2f}\n👛 Wallet: ₹{(u['wallet_balance'] if u else 0):.2f}\n\nChoose payment method:",reply_markup=quantity_payment_keyboard(plan_id,quantity,amount,u['wallet_balance'] if u else 0,p['product_id']));await callback_answer(call, )

@dp.callback_query(F.data.startswith("qtycustom:"))
async def quantity_custom(call:CallbackQuery,state:FSMContext):
    plan_id=int(call.data.split(":",1)[1]);await state.update_data(custom_plan_id=plan_id);await state.set_state(CheckoutState.custom_quantity);await call.message.answer("Send the quantity you want to buy (whole number).");await callback_answer(call, )

@dp.message(CheckoutState.custom_quantity)
async def quantity_custom_received(message:Message,state:FSMContext):
    try:quantity=int(message.text.strip())
    except Exception:await message.answer("Please send a whole number, for example 25.");return
    data=await state.get_data();plan_id=int(data['custom_plan_id']);await state.clear();p=await get_plan(plan_id)
    if quantity < 1 or quantity > 100 or not p:
        await message.answer("Please choose a valid quantity between 1 and 100.");return
    if p.get("maintenance"):
        await message.answer(f"🛠️ {html.escape(p['product_name'])} is under maintenance. Please check back later."); return
    u=await get_user(message.from_user.id);unit=p['reseller_price_inr'] if u and u['is_reseller'] else p['price_inr'];amount=round(unit*quantity,2)
    await message.answer(f"🎮 <b>{html.escape(p['product_name'])} — {html.escape(p['duration'])}</b>\n📦 Quantity: <b>{quantity}</b>\n💰 Total: ₹{amount:.2f}\n👛 Wallet: ₹{(u['wallet_balance'] if u else 0):.2f}\n\nChoose payment method:",reply_markup=quantity_payment_keyboard(plan_id,quantity,amount,u['wallet_balance'] if u else 0,p['product_id']))

def no_stock_refund_message(amount):
    text=("📦 <b>Out of Stock!</b>\n"
          "━━━━━━━━━━━━━━━━━━━━\n"
          "This product is currently out of stock.\n\n"
          f"Your ₹{float(amount):.2f} has been returned to your wallet.\n"
          "Please check back later or contact admin.")
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎫 Contact Support",url="https://t.me/subro98")]])
    return text,kb


async def notify_referral_reward(referred_user_id):
    reward=await award_referral_after_purchase(referred_user_id)
    if reward:
        try:
            await bot.send_message(reward["referrer_id"],"🎁 <b>You earned a Referral Trial Key!</b>\n\nYour friend completed their first purchase. Open Referral from the dashboard and choose Root or Non Root to claim your random trial key.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Claim Referral Reward",callback_data="referral")]]))
        except Exception: log.exception("Could not notify referrer")

@dp.callback_query(F.data.startswith("wallet:"))
async def wallet_pay(call:CallbackQuery):
    parts=call.data.split(":");plan_id=int(parts[1]);quantity=int(parts[2]) if len(parts)>2 else 1
    try:
        result=await pay_wallet(call.from_user.id,plan_id,quantity)
        if result.get("no_stock"):
            refund=await credit_wallet_for_no_stock(result["order_id"])
            if refund and refund.get("credited"):
                text,kb=no_stock_refund_message(refund["amount"])
                await call.message.answer(text,reply_markup=kb)
            else:
                await call.message.answer("Your wallet payment was already returned.")
        else:
            await call.message.answer(success_message(result['product_name'],result['duration'],result['quantity'],result['key_text']))
            await notify_referral_reward(call.from_user.id)
        await callback_answer(call, "Purchase processed!")
    except ValueError as e:
        await callback_answer(call, str(e),show_alert=True)
    except Exception:
        log.exception("Wallet purchase failed");await callback_answer(call, "Wallet purchase failed. Please try again.",show_alert=True)

@dp.callback_query(F.data.startswith("upi:"))
async def upi_begin(call:CallbackQuery,state:FSMContext):
    # Stop Telegram's callback spinner immediately; Cashfree may take a few seconds.
    await callback_answer(call, "Request received")
    progress = await call.message.answer("⏳ Connecting to secure UPI payment gateway…\nPlease wait while your QR is generated.")
    parts=call.data.split(":");plan_id=int(parts[1]);quantity=int(parts[2]) if len(parts)>2 else 1
    if quantity < 1 or quantity > 100:
        await progress.edit_text("❌ Quantity must be between 1 and 100.");return
    p=await get_plan(plan_id)
    if not p:
        try: await progress.edit_text("❌ This plan is unavailable. Please choose another plan.")
        except Exception: pass
        return
    if p.get("maintenance"):
        await progress.edit_text(f"🛠️ {html.escape(p['product_name'])} is under maintenance. Please check back later."); return
    user=await get_user(call.from_user.id)
    if not user or not user.get("phone"):
        await call.message.answer("Please restart the bot and share your phone number first.");return
    unit=p['reseller_price_inr'] if user and user['is_reseller'] else p['price_inr'];amount=round(unit*quantity,2)
    order=await create_order(call.from_user.id,plan_id,amount,quantity,"CASHFREE")
    try:
        payment_title=f"Payment for {p['product_name']} ({p['duration']})"
        payment=await create_upi_qr_order(order['order_id'],amount,call.from_user.id,call.from_user.full_name or f"user{call.from_user.id}",user['phone'],payment_title)
        await set_payment_link(order['order_id'],payment['cashfree_order_id'])
        if payment.get("qr_image_bytes"):
            # Cashfree supplied the rendered QR image; send it directly.
            qr_image = payment["qr_image_bytes"]
        else:
            # Compatibility with Cashfree responses that return a UPI URI.
            qr=qrcode.QRCode(box_size=8,border=3);qr.add_data(payment['qr_value']);qr.make(fit=True)
            image=qr.make_image(fill_color="black",back_color="white")
            bio=BytesIO();image.save(bio,format="PNG");bio.seek(0)
            qr_image = bio.getvalue()
        caption=(f"💸 <b>{html.escape(payment_title)}</b>\n\n🧾 Order: <code>{order['order_id']}</code>\n🎮 Product: {html.escape(p['product_name'])} ({html.escape(p['duration'])})\n📦 Quantity: {quantity} key(s)\n💰 Amount: <b>₹{amount:.2f}</b>\n\n📱 Scan this unique QR using any UPI app, including Paytm.\n⚡ Your payment will be verified automatically and your key delivered here.\n⏰ Payment window: 5 minutes.")
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔎 Check Payment Status",callback_data=f"check:{order['order_id']}")]])
        try: await progress.delete()
        except Exception: pass
        await call.message.answer_photo(BufferedInputFile(qr_image,filename="cashfree_upi_qr.png"),caption=caption,reply_markup=kb)
    except Exception:
        log.exception("Cashfree UPI QR creation failed")
        try: await progress.edit_text("❌ Could not generate the UPI QR. Please try again.")
        except Exception: pass
        await expire_order(order['order_id'])
        await call.message.answer("❌ Cashfree could not create the UPI QR for this order. No payment was taken. Please try again or contact support.")

@dp.callback_query(F.data.startswith("check:"))
async def check_payment(call:CallbackQuery):
    order_id=call.data.split(":",1)[1];order=await get_order(order_id)
    if not order or order['user_id']!=call.from_user.id:await callback_answer(call, "Order not found.",show_alert=True);return
    if order['status']=="PAID":await callback_answer(call, "Payment already completed.");return
    if order['status']=="REFUNDED":
        await callback_answer(call, "Payment was refunded to your wallet.",show_alert=True);return
    age=datetime.now(timezone.utc)-order['created_at'].astimezone(timezone.utc)
    try:
        remote=await fetch_order_payments(order_id)
        payments=remote if isinstance(remote,list) else remote.get("payments",[]) if isinstance(remote,dict) else []
        successful=next((x for x in payments if x.get("payment_status")=="SUCCESS" and abs(float(x.get("payment_amount") or 0)-order['amount_inr'])<0.005),None)
        if successful:
            if order.get("payment_method")=="TOPUP":
                credited=await fulfill_wallet_topup(order_id)
                if credited and credited.get("credited"):
                    await call.message.answer(f"✅ <b>Wallet Top-up Successful!</b>\n\n💰 ₹{credited['amount']:.2f} has been added to your wallet.")
                else: await call.message.answer("This wallet top-up has already been credited.")
                await callback_answer(call, "Payment verified!");return
            result=await fulfill_paid_order(order_id) if order['status'] in ("PENDING","EXPIRED") else {"key_text":None} if order['status']=="PAID_NO_STOCK" else None
            if result and result.get('key_text'):
                plan=await get_plan(order['plan_id']) if order.get('plan_id') else None
                game=plan['product_name'] if plan else "Product"
                await call.message.answer(success_message(game,order['duration'],order['quantity'],result['key_text']))
                await notify_referral_reward(call.from_user.id)
            elif result and not result.get('key_text'):
                refund=await credit_wallet_for_no_stock(order_id)
                if refund and refund.get('credited'):
                    text,kb=no_stock_refund_message(refund['amount'])
                    await call.message.answer(text,reply_markup=kb)
                else:
                    await call.message.answer("Your payment was already refunded to your wallet.")
            await callback_answer(call, "Payment verified!");return
        if age>timedelta(minutes=5):
            await expire_order(order_id)
            await call.message.answer(f"⌛ <b>Payment Timed Out!</b>\nThe payment for this order has expired. Please try again if you still want to purchase.")
            await callback_answer(call, "Payment window expired.",show_alert=True);return
        await callback_answer(call, "Payment not yet confirmed. Try again in a moment.",show_alert=True)
    except Exception:
        log.exception("Payment status check failed");await callback_answer(call, "Could not check payment status.",show_alert=True)

@dp.callback_query(F.data=="orders")
async def orders_cb(call:CallbackQuery):
    rows=await list_orders(call.from_user.id)
    if not rows:msg="🛍️ ━━ MY ORDERS ━━ 🛍️\n\nYou have no orders yet."
    else:
        chunks=["🛍️ ━━ MY ORDERS ━━ 🛍️\n"]
        for o in rows[:10]:
            key=html.escape(o.get('key_text') or "Pending / not delivered")
            dt=o['created_at'].strftime("%Y-%m-%d %H:%M:%S") if o.get('created_at') else "—"
            chunks.append(f"🎮 <b>{html.escape(o['product_name'])}</b>\n   ⏳ {html.escape(o['duration'])}\n   🔑 <code>{key}</code>\n   💰 ₹{o['amount_inr']:.2f} │ 📅 {dt}\n   📌 Status: {html.escape(o['status'])}\n━━━━━━━━━━━━━━━━━━━━━━")
        msg="\n".join(chunks)
    await call.message.edit_text(msg,reply_markup=home_keyboard());await callback_answer(call, )

@dp.callback_query(F.data=="profile")
async def profile(call:CallbackQuery):
    u=await get_user(call.from_user.id);stats=await user_order_stats(call.from_user.id)
    spent=stats['spent'];orders_count=stats['orders'];balance=u['wallet_balance'] if u else 0;refstats=await referral_stats(call.from_user.id);joined=u['created_at'].strftime("%Y-%m-%d %H:%M:%S") if u and u.get('created_at') else "—"
    role="👑 Reseller" if u and u['is_reseller'] else "🧑‍💼 Customer"
    msg=("👤 ━━ YOUR PROFILE ━━ 👤\n\n" f"🆔 User ID: <code>{call.from_user.id}</code>\n📛 Name: {html.escape(call.from_user.full_name or 'Customer')}\n👑 Account: {role}\n\n💰 ━ Balance ━\n   💳 Current: ₹{balance:.2f}\n\n📊 ━ Statistics ━\n   📦 Orders: {orders_count}\n   💸 Spent: ₹{spent:.2f}\n   👥 Referrals: {refstats['total']}\n\n📅 Joined: {joined}")
    await call.message.edit_text(msg,reply_markup=home_keyboard());await callback_answer(call, )

@dp.callback_query(F.data=="balance")
async def balance_menu(call:CallbackQuery):
    u=await get_user(call.from_user.id);balance=u['wallet_balance'] if u else 0
    msg=("💰 ━━ ADD BALANCE ━━ 💰\n\n" f"💳 Current Balance: ₹{balance:.2f}\n\n━━━━━━━━━━━━━━━━━━━━━━\n💳 Available Payment Methods:\n  🇮🇳 Paytm/UPI (INR)\n\n✅ Use balance for purchases!\n━━━━━━━━━━━━━━━━━━━━━━\n\nSelect amount to deposit.\nYou'll choose your payment method next:\n\nMinimum deposit: ₹10")
    await call.message.edit_text(msg,reply_markup=topup_amount_keyboard());await callback_answer(call, )

@dp.callback_query(F.data=="topup:custom")
async def topup_custom(call:CallbackQuery,state:FSMContext):
    await state.set_state(CheckoutState.custom_topup);await call.message.answer("Enter the amount to add. Minimum ₹10.");await callback_answer(call, )

@dp.message(CheckoutState.custom_topup)
async def topup_custom_received(message:Message,state:FSMContext):
    try:amount=round(float(message.text.strip()),2)
    except Exception:await message.answer("Enter a valid amount, for example 150.");return
    await state.clear()
    if amount<10 or amount>50000:await message.answer("Minimum top-up is ₹10. Maximum is ₹50,000.");return
    await show_topup_method(message,amount)

async def show_topup_method(target,amount):
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🇮🇳 Paytm / UPI (INR)",callback_data=f"topuppay:{amount:.2f}")],[InlineKeyboardButton(text="🔙 Back",callback_data="balance")]])
    await target.answer(f"💰 Deposit amount: <b>₹{amount:.2f}</b>\n\nSelect your payment method:",reply_markup=kb)

async def start_topup_payment(message:Message,amount:float,user_id=None,customer_name=None):
    user_id=user_id or message.from_user.id;customer_name=customer_name or message.from_user.full_name or "Customer"
    u=await get_user(user_id)
    if not u or not u.get('phone'):await message.answer("Please verify your phone number with /start before adding balance.");return
    order=await create_topup_order(user_id,amount)
    try:
        title=f"Panel Army Wallet Top-up ₹{amount:.2f}"
        payment=await create_upi_qr_order(order['order_id'],amount,user_id,customer_name,u['phone'],title)
        await set_payment_link(order['order_id'],payment['cashfree_order_id'])
        qrbytes=payment.get('qr_image_bytes')
        if not qrbytes:
            qr=qrcode.QRCode(box_size=8,border=3);qr.add_data(payment['qr_value']);qr.make(fit=True);img=qr.make_image(fill_color="black",back_color="white");bio=BytesIO();img.save(bio,format="PNG");qrbytes=bio.getvalue()
        caption=f"💸 <b>{html.escape(title)}</b>\n\n🧾 Order: <code>{order['order_id']}</code>\n💰 Amount: <b>₹{amount:.2f}</b>\n\n📱 Scan using any UPI app, including Paytm. Wallet balance will be credited automatically after payment confirmation."
        await message.answer_photo(BufferedInputFile(qrbytes,filename="wallet_topup_qr.png"),caption=caption,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔎 Check Payment Status",callback_data=f"check:{order['order_id']}")]]))
    except Exception:
        log.exception("Wallet top-up QR creation failed");await expire_order(order['order_id']);await message.answer("Cashfree could not create the QR. No payment was taken. Please try again.")

@dp.callback_query(F.data.startswith("topup:"))
async def topup_fixed(call:CallbackQuery):
    amount=float(call.data.split(":",1)[1])
    if amount<10:await callback_answer(call, "Minimum top-up is ₹10.",show_alert=True);return
    await show_topup_method(call.message,amount)
    await callback_answer(call, )

@dp.callback_query(F.data.startswith("topuppay:"))
async def topup_pay_method(call:CallbackQuery):
    amount=float(call.data.split(":",1)[1])
    await callback_answer(call, "Creating UPI QR…")
    await start_topup_payment(call.message,amount,call.from_user.id,call.from_user.full_name)

@dp.callback_query(F.data=="referral")
async def referral_menu(call:CallbackQuery):
    st=await referral_stats(call.from_user.id)
    link=f"https://t.me/panelxarmy_bot?start=ref_{call.from_user.id}"
    msg=("🎁 <b>REFERRAL PROGRAM</b>\n\n✅ Status: Active\n━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>YOUR STATS:</b>\n"
         f"├ 👥 Total Referrals: {st['total']}\n├ 🛒 Active (Purchased): {st['active']}\n└ 🎟️ Total Trial Keys You Got: {st['trials']}\n\n"
         "━━━━━━━━━━━━━━━━━━━━━━\n🔗 <b>Your Referral Link:</b>\n"
         f"<code>{link}</code>\n\n📱 <b>How it works:</b>\n1. Share your link\n2. Friend joins using your link\n3. When they buy any product, you can claim one random Trial Key (Root or Non-Root)\n\n"
         "💡 <b>Reward:</b> After your referred friend completes their first successful purchase, choose Root or Non Root. One available key is selected randomly from matching stock.")
    rows=[]
    if st['pending']:
        rows=[[InlineKeyboardButton(text="🌳 Claim Root Trial Key",callback_data="refclaim:ROOT"),InlineKeyboardButton(text="📱 Claim Non-Root Trial Key",callback_data="refclaim:NON_ROOT")]]
    rows.append([InlineKeyboardButton(text="🔙 Back",callback_data="home")])
    await call.message.edit_text(msg,reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback_answer(call, )

@dp.callback_query(F.data.startswith("refclaim:"))
async def referral_claim(call:CallbackQuery):
    kind=call.data.split(":",1)[1]
    result=await claim_referral_reward(call.from_user.id,kind)
    if not result or result.get("error"):
        error=(result or {}).get("error")
        msg={"NO_REWARD":"No pending referral reward yet.","NO_STOCK":"No matching trial keys are currently available. Please try again later."}.get(error,"Could not claim reward.")
        await callback_answer(call, msg,show_alert=True);return
    await call.message.answer(f"🎉 <b>Referral Trial Key Claimed!</b>\n\nType: {html.escape(result['reward_type'])}\n🔑 Key: <code>{html.escape(result['key_text'])}</code>")
    await call.message.edit_text("🎁 Referral reward claimed successfully!\n\nYour trial key was sent above.",reply_markup=home_keyboard())
    await callback_answer(call, "Trial key delivered!")

@dp.callback_query(F.data.in_({"spin","reseller","downloads","howto","support","help"}))
async def menu_stub(call:CallbackQuery):
    if call.data=="support":msg="🎫 ━━ SUPPORT CENTER ━━ 🎫\n━━━━━━━━━━━━━━━━━━━━━━\n\nNeed help? We're here for you! 💬\nContact with @subro98\n━━━━━━━━━━━━━━━━━━━━━"
    else:msg={"spin":"🎰 Lucky Spin will be available soon.","reseller":"⚡ Contact support to activate reseller access.","downloads":"📥 Download files will be available soon.","howto":"📺 How-to guides will be available soon.","help":"Contact support at @subro98 for order and delivery help."}[call.data]
    await call.message.edit_text(msg,reply_markup=home_keyboard());await callback_answer(call, )

@dp.callback_query(F.data=="home")
async def home(call:CallbackQuery):
    u=await get_user(call.from_user.id);await call.message.edit_text(store_welcome(u.get('full_name') if u else call.from_user.first_name),reply_markup=main_keyboard());await callback_answer(call, )

@dp.message(Command("admin"))
async def admin_help(message:Message):
    if not is_admin(message.from_user.id):return
    await message.answer("<b>⚔️ PANEL ARMY — ADMIN CONTROL</b>\nChoose a management section:",reply_markup=admin_keyboard())

@dp.callback_query(F.data.startswith("adm:"))
async def admin_menu(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required.",show_alert=True);return
    await state.clear()
    section=call.data.split(":",1)[1]
    if section=="dashboard":
        d=await dashboard_stats()
        msg=("📊 <b>Dashboard</b>\n\n" f"👥 Users: {d['users']}\n📦 Orders: {d['orders']}\n✅ Paid orders: {d['paid']}\n💰 Revenue: ₹{d['revenue']:.2f}\n📅 Today's revenue: ₹{d['today_revenue']:.2f}\n🔑 Available keys: {d['stock']}")
    elif section=="users":
        await state.set_state(AdminState.search_user)
        msg="👥 <b>User management</b>\nSend a Telegram ID, username, or name to search. Use /cancel to stop."
    elif section=="wallet":
        await state.set_state(AdminState.admin_input);await state.update_data(admin_action="wallet")
        msg="💰 <b>Wallet control</b>\nSend <code>USER_ID | AMOUNT</code>. Use a positive amount to credit and a negative amount to deduct."
    elif section=="products":
        products=await admin_all_products()
        rows=[[InlineKeyboardButton(text=f"{'🛠️' if p.get('maintenance') else '📦'} {p['name']} · {p['category']}",callback_data=f"ac:product:{p['id']}")] for p in products]
        rows += [[InlineKeyboardButton(text="➕ Add product",callback_data="ac:addproduct")],[InlineKeyboardButton(text="📁 Manage categories",callback_data="ac:categories")],[InlineKeyboardButton(text="🔙 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
        await call.message.edit_text("📦 <b>PRODUCT & CATEGORY MANAGEMENT</b>\nSelect an item to edit or deactivate it.",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback_answer(call, );return
    elif section=="stock":
        rows=await admin_stock_summary()
        msg="🔑 <b>Key stock & inventory</b>\n\nChoose a guided action below. You can select an existing category, product and plan, or create any missing item without typing commands.\n\n"+("\n".join(f"Plan {r['plan_id']}: {r['status']} — {r['count']}" for r in rows) if rows else "No stock records yet.")
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add / Update Key Stock",callback_data="stk:start")],
            [InlineKeyboardButton(text="📋 View Products & Plans",callback_data="stk:catalog")],
            [InlineKeyboardButton(text="🔙 Admin Menu",callback_data="stk:admin")],
        ] + admin_nav_rows())
        await call.message.edit_text(msg,reply_markup=kb);await callback_answer(call, );return
    elif section=="payments":
        rows=await admin_orders(20)
        msg="💳 <b>PAYMENTS & ORDERS</b>\n━━━━━━━━━━━━━━━━━━━━━━\nSelect an order to inspect its payment details.\n\n"+("\n".join(f"• <b>{o['order_id']}</b> · {o['status']} · ₹{o['amount_inr']:.2f}" for o in rows) if rows else "No payment/order records found.")
        pay_rows=[[InlineKeyboardButton(text=f"{('✅' if o['status']=='PAID' else '⏳' if o['status']=='PENDING' else '❌')} {o['order_id']} · ₹{o['amount_inr']:.2f}",callback_data=f"admpay:view:{o['order_id']}")] for o in rows]
        pay_rows += [[InlineKeyboardButton(text="🔄 Refresh Payments",callback_data="admpay:list")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
        await call.message.edit_text(msg,reply_markup=InlineKeyboardMarkup(inline_keyboard=pay_rows));await callback_answer(call, );return
    elif section=="resellers":
        rows=await list_resellers(50)
        kb=[[InlineKeyboardButton(text=f"👑 {r['full_name'] or r['user_id']} · {r['user_id']}",callback_data=f"admres:{r['user_id']}:0")] for r in rows]
        kb += [[InlineKeyboardButton(text="➕ Add reseller",callback_data="admres:add")],[InlineKeyboardButton(text="🔄 Refresh",callback_data="adm:resellers")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
        await call.message.edit_text("👑 <b>RESELLER MANAGEMENT</b>\nTap a reseller to remove access, or add a user by Telegram ID.",reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)); await callback_answer(call); return
    elif section=="broadcast":
        kb=[[InlineKeyboardButton(text="👥 All users",callback_data="bc:all")],[InlineKeyboardButton(text="🛍️ Customers",callback_data="bc:customers")],[InlineKeyboardButton(text="👑 Resellers",callback_data="bc:resellers")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
        await call.message.edit_text("📢 <b>BROADCAST</b>\nChoose who should receive your messages.",reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)); await callback_answer(call); return
    elif section=="coupons":
        coupons=await list_coupons()
        rows=[[InlineKeyboardButton(text=f"{'🟢' if c['active'] else '⏸️'} {c['code']} · {c['discount_percent']}% · {c['used_count']}/{c['usage_limit'] or '∞'}",callback_data=f"cp:view:{c['code']}")] for c in coupons]
        rows += [[InlineKeyboardButton(text="➕ Create coupon",callback_data="cp:create")],[InlineKeyboardButton(text="🔄 Refresh",callback_data="adm:coupons")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
        await call.message.edit_text("🎟️ <b>COUPON MANAGEMENT</b>\nSelect a coupon to edit, pause or delete.",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await callback_answer(call); return
    elif section=="settings":
        settings=await get_bot_settings()
        rows=[[InlineKeyboardButton(text=f"⚙️ {k[:25]}: {v[:20]}",callback_data=f"setting:edit:{k}")] for k,v in settings.items()]
        rows += [[InlineKeyboardButton(text="➕ Add / change setting",callback_data="setting:add")],[InlineKeyboardButton(text="🔄 Refresh",callback_data="adm:settings")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
        await call.message.edit_text("⚙️ <b>BOT SETTINGS</b>\nSelect a saved setting or add a key/value setting.",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)); await callback_answer(call); return
    elif section=="logs":
        rows=await recent_admin_logs(20);msg="📜 <b>Recent admin actions</b>\n"+("\n".join(f"{r['created_at']:%Y-%m-%d %H:%M} · {r['admin_id']} · {r['action']} · {html.escape(r['details'][:120])}" for r in rows) if rows else "No admin actions logged yet.")
    else:msg="Unknown section."
    await call.message.edit_text(msg,reply_markup=admin_keyboard());await callback_answer(call, )


@dp.callback_query(F.data=="admpay:list")
async def admin_payments_list(call:CallbackQuery):
    if not is_admin(call.from_user.id):
        await callback_answer(call, "Admin access required",show_alert=True);return
    rows=await admin_orders(20)
    msg="💳 <b>PAYMENTS & ORDERS</b>\n━━━━━━━━━━━━━━━━━━━━━━\nSelect an order to inspect its payment details.\n\n"+("\n".join(f"• <b>{o['order_id']}</b> · {o['status']} · ₹{o['amount_inr']:.2f}" for o in rows) if rows else "No payment/order records found.")
    pay_rows=[[InlineKeyboardButton(text=f"{('✅' if o['status']=='PAID' else '⏳' if o['status']=='PENDING' else '❌')} {o['order_id']} · ₹{o['amount_inr']:.2f}",callback_data=f"admpay:view:{o['order_id']}")] for o in rows]
    pay_rows += [[InlineKeyboardButton(text="🔄 Refresh Payments",callback_data="admpay:list")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
    await call.message.edit_text(msg,reply_markup=InlineKeyboardMarkup(inline_keyboard=pay_rows));await callback_answer(call, "Payments refreshed")

@dp.callback_query(F.data.startswith("admpay:view:"))
async def admin_payment_detail(call:CallbackQuery):
    if not is_admin(call.from_user.id):
        await callback_answer(call, "Admin access required",show_alert=True);return
    order_id=call.data.split(":",2)[2]
    o=await get_order(order_id)
    if not o:
        await callback_answer(call, "Order not found",show_alert=True);return
    dt=o['created_at'].strftime("%Y-%m-%d %H:%M:%S") if o.get('created_at') else "—"
    msg=("💳 <b>PAYMENT DETAILS</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
         f"🧾 Order: <code>{html.escape(order_id)}</code>\n👤 User ID: <code>{o['user_id']}</code>\n"
         f"💰 Amount: <b>₹{o['amount_inr']:.2f}</b>\n📌 Status: <b>{html.escape(o['status'])}</b>\n"
         f"🏦 Method: {html.escape(o['payment_method'])}\n📅 Created: {dt}\n"
         f"🔑 Key: <code>{html.escape(o.get('key_text') or 'Not delivered / wallet top-up')}</code>")
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Refresh status list",callback_data="admpay:list")],[InlineKeyboardButton(text="🔙 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows())
    await call.message.edit_text(msg,reply_markup=kb);await callback_answer(call, )

@dp.message(AdminState.search_user,F.text)
async def admin_user_search(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    term=message.text.strip();rows=await search_users(term)
    await state.clear()
    if not rows:await message.answer("No matching users.",reply_markup=admin_keyboard());return
    for u in rows:
        uname=("@"+u['username']) if u['username'] else "no username"
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="View profile",callback_data=f"admuser:{u['user_id']}")]])
        await message.answer(f"👤 <b>{html.escape(u['full_name'] or 'User')}</b> · {uname}\nID <code>{u['user_id']}</code> · Wallet ₹{u['wallet_balance']:.2f} · {'BANNED' if u['is_banned'] else 'Active'}",reply_markup=kb)

@dp.callback_query(F.data.startswith("admuser:"))
async def admin_user_profile(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    uid=int(call.data.split(":",1)[1]);u=await admin_user(uid)
    if not u:await callback_answer(call, "User not found",show_alert=True);return
    action="Unban" if u['is_banned'] else "Ban"
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"🚫 {action} user",callback_data=f"admban:{uid}:{0 if u['is_banned'] else 1}")],[InlineKeyboardButton(text="👑 Toggle reseller",callback_data=f"admres:{uid}:{0 if u['is_reseller'] else 1}")]])
    msg=(f"👤 <b>{html.escape(u['full_name'] or 'User')}</b>\nID: <code>{uid}</code>\nUsername: @{html.escape(u['username'] or '—')}\nWallet: ₹{u['wallet_balance']:.2f}\nReseller: {u['is_reseller']}\nBanned: {u['is_banned']}\nOrders: {u['orders']}\nPaid spend: ₹{u['spent']:.2f}\nJoined: {u['created_at']:%Y-%m-%d}")
    await call.message.answer(msg,reply_markup=kb);await callback_answer(call, )

@dp.callback_query(F.data.startswith("admban:"))
async def admin_ban_toggle(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    _,uid,enabled=call.data.split(":");ok=await set_banned(int(uid),bool(int(enabled)))
    if ok:
        _ban_cache.pop(int(uid), None)
        await admin_log(call.from_user.id,"USER_BAN" if int(enabled) else "USER_UNBAN",uid)
    await callback_answer(call, "Updated" if ok else "User not found",show_alert=True)

@dp.callback_query(F.data=="admres:add")
async def reseller_add_button(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    await state.set_state(AdminState.admin_input); await state.update_data(admin_action="reseller")
    await call.message.answer("Send the Telegram user ID to grant reseller access."); await callback_answer(call)

@dp.callback_query(F.data.startswith("admres:"))
async def admin_res_toggle(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    _,uid,enabled=call.data.split(":");ok=await set_reseller(int(uid),bool(int(enabled)));await admin_log(call.from_user.id,"RESELLER_TOGGLE",f"{uid}={enabled}")
    rows=await list_resellers(50)
    kb=[[InlineKeyboardButton(text=f"👑 {r['full_name'] or r['user_id']} · {r['user_id']}",callback_data=f"admres:{r['user_id']}:0")] for r in rows]
    kb += [[InlineKeyboardButton(text="➕ Add reseller",callback_data="admres:add")],[InlineKeyboardButton(text="🔄 Refresh",callback_data="adm:resellers")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()
    await call.message.edit_text("👑 <b>RESELLER MANAGEMENT</b>\nTap a reseller to remove access, or add a user by Telegram ID.",reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback_answer(call, "Reseller status updated" if ok else "User not found",show_alert=True)

@dp.callback_query(F.data=="ac:categories")
async def ac_categories(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    products=await admin_all_products();cats=sorted({p["category"] for p in products})
    rows=[[InlineKeyboardButton(text=f"📁 {c}",callback_data="ac:category:"+str(i))] for i,c in enumerate(cats)]
    rows.append([InlineKeyboardButton(text="🔙 Products",callback_data="adm:products")]); rows += admin_nav_rows()
    await call.message.edit_text("📁 <b>Categories</b>\nSelect a category to rename or move its products.",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback_answer(call, )
    # Store names per admin in FSM is not needed: callback index resolves from fresh sorted list.

@dp.callback_query(F.data.startswith("ac:category:"))
async def ac_category_detail(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    products=await admin_all_products();cats=sorted({p["category"] for p in products})
    try:name=cats[int(call.data.rsplit(":",1)[1])]
    except (ValueError,IndexError):await callback_answer(call, "Category list changed. Refresh.",show_alert=True);return
    count=await category_products_admin(name)
    await state.update_data(category_name=name)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ Rename category",callback_data="ac:categoryrename")],[InlineKeyboardButton(text="🗑️ Delete category (move products to Other Products)",callback_data="ac:categorydelete")],[InlineKeyboardButton(text="🔙 Categories",callback_data="ac:categories")]] + admin_nav_rows())
    await call.message.edit_text(f"📁 <b>{html.escape(name)}</b>\nProducts: {count}\nDelete safely moves its products to Other Products; it does not delete sold order history.",reply_markup=kb);await callback_answer(call, )

@dp.callback_query(F.data=="ac:categoryrename")
async def ac_category_rename(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    await state.set_state(AdminState.admin_input);await state.update_data(admin_action="category_rename")
    await call.message.answer("Send the new category name:");await callback_answer(call, )

@dp.callback_query(F.data=="ac:categorydelete")
async def ac_category_delete(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    d=await state.get_data();old=d.get("category_name")
    if not old:await callback_answer(call, "Select category again.",show_alert=True);return
    ok=bool(await delete_category_admin(old))
    await admin_log(call.from_user.id,"CATEGORY_DELETE_MOVE",old)
    await call.message.edit_text("✅ Category removed. Its products were moved to Other Products." if ok else "Category not found.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📁 Categories",callback_data="ac:categories")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()));await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:product:"))
async def ac_product_detail(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);p=await get_product(pid)
    if not p:await callback_answer(call, "Product not found or inactive",show_alert=True);return
    plans=await admin_all_plans(pid)
    rows=[[InlineKeyboardButton(text=f"🗓️ {pl['duration']} · ₹{pl['price_inr']:.2f}",callback_data=f"ac:plan:{pl['id']}")] for pl in plans]
    rows += [[InlineKeyboardButton(text=("🟢 Disable maintenance" if p.get("maintenance") else "🛠️ Put under maintenance"),callback_data=f"ac:maintenance:{pid}:{0 if p.get('maintenance') else 1}")],[InlineKeyboardButton(text="✏️ Edit name",callback_data=f"ac:editname:{pid}"),InlineKeyboardButton(text="📁 Change category",callback_data=f"ac:editcat:{pid}")],[InlineKeyboardButton(text="➕ Add plan",callback_data=f"ac:addplan:{pid}")],[InlineKeyboardButton(text="🗑️ Delete product",callback_data=f"ac:deleteproduct:{pid}")],[InlineKeyboardButton(text="🔙 Products",callback_data="adm:products")]] + admin_nav_rows()
    await call.message.edit_text(f"📦 <b>{html.escape(p['name'])}</b>\nCategory: {html.escape(p['category'])}\nStatus: {'🛠️ UNDER MAINTENANCE' if p.get('maintenance') else '🟢 Active'}\nChoose a plan or action:",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows));await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:maintenance:"))
async def ac_product_maintenance(call:CallbackQuery):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    _,_,pid_s,enabled_s=call.data.split(":"); pid=int(pid_s); enabled=bool(int(enabled_s))
    ok=await set_product_maintenance(pid,enabled)
    if ok: await admin_log(call.from_user.id,"PRODUCT_MAINTENANCE",f"{pid}={enabled}")
    p=await get_product(pid)
    if p:
        plans=await admin_all_plans(pid)
        rows=[[InlineKeyboardButton(text=f"🗓️ {pl['duration']} · ₹{pl['price_inr']:.2f}",callback_data=f"ac:plan:{pl['id']}")] for pl in plans]
        rows += [[InlineKeyboardButton(text=("🟢 Disable maintenance" if p.get("maintenance") else "🛠️ Put under maintenance"),callback_data=f"ac:maintenance:{pid}:{0 if p.get('maintenance') else 1}")],[InlineKeyboardButton(text="✏️ Edit name",callback_data=f"ac:editname:{pid}"),InlineKeyboardButton(text="📁 Change category",callback_data=f"ac:editcat:{pid}")],[InlineKeyboardButton(text="➕ Add plan",callback_data=f"ac:addplan:{pid}")],[InlineKeyboardButton(text="🗑️ Delete product",callback_data=f"ac:deleteproduct:{pid}")],[InlineKeyboardButton(text="🔙 Products",callback_data="adm:products")]] + admin_nav_rows()
        await call.message.edit_text(f"📦 <b>{html.escape(p['name'])}</b>\nStatus: {'🛠️ UNDER MAINTENANCE' if p.get('maintenance') else '🟢 Active'}\nCategory: {html.escape(p['category'])}",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback_answer(call,"Updated")

@dp.callback_query(F.data.startswith("ac:editname:"))
async def ac_editname(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);await state.set_state(AdminState.admin_input);await state.update_data(admin_action="product_name",product_id=pid)
    await call.message.answer("Send the new product name:");await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:editcat:"))
async def ac_editcat(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);await state.set_state(AdminState.admin_input);await state.update_data(admin_action="product_category",product_id=pid)
    await call.message.answer("Send the category name (existing or new):");await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:deleteproduct:"))
async def ac_deleteproduct(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1])
    await call.message.edit_text("⚠️ <b>Confirm product deletion</b>\nIf this product has orders or key inventory, it will be safely archived so historical records are not damaged. Otherwise it will be permanently deleted.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑️ Confirm delete",callback_data=f"ac:deleteconfirm:{pid}")],[InlineKeyboardButton(text="↩ Cancel",callback_data=f"ac:product:{pid}")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]])); await callback_answer(call)

@dp.callback_query(F.data.startswith("ac:deleteconfirm:"))
async def ac_deleteproduct_confirm(call:CallbackQuery):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    pid=int(call.data.rsplit(":",1)[1]); result=await delete_product_admin(pid)
    if result!="NOT_FOUND": await admin_log(call.from_user.id,"PRODUCT_"+result,str(pid))
    msg={"DELETED":"✅ Product permanently deleted from the database.","ARCHIVED":"✅ Product archived because it has keys or order history. Existing records are preserved.","NOT_FOUND":"Product not found."}.get(result,"Could not delete product.")
    await call.message.edit_text(msg,reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📦 Products",callback_data="adm:products")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows())); await callback_answer(call)


@dp.callback_query(F.data.startswith("ac:addplan:"))
async def ac_addplan(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);await state.update_data(stock_product_id=pid);await state.set_state(AdminState.stock_plan_duration)
    await call.message.answer("Send plan duration/name (e.g. 1 Hour, 10 Days):");await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:plan:"))
async def ac_plan_detail(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);pl=await get_plan(pid)
    if not pl:await callback_answer(call, "Plan not found",show_alert=True);return
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ Edit plan & INR prices",callback_data=f"ac:planedit:{pid}")],[InlineKeyboardButton(text="🔑 Add keys to this plan",callback_data=f"stk:plan:{pid}")],[InlineKeyboardButton(text="🗑️ Deactivate plan",callback_data=f"ac:plandelete:{pid}")],[InlineKeyboardButton(text="🔙 Product",callback_data=f"ac:product:{pl['product_id']}")]] + admin_nav_rows())
    await call.message.edit_text(f"🗓️ <b>{html.escape(pl['duration'])}</b>\nCustomer: ₹{pl['price_inr']:.2f}\nReseller: ₹{pl['reseller_price_inr']:.2f}\nAvailable keys: {pl['stock']}",reply_markup=kb);await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:planedit:"))
async def ac_plan_edit(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);await state.set_state(AdminState.admin_input);await state.update_data(admin_action="plan_edit",plan_id=pid)
    await call.message.answer("Send <code>Duration | Customer INR | Reseller INR</code> (example: <code>10 Days | 99 | 79</code>):");await callback_answer(call, )

@dp.callback_query(F.data.startswith("ac:plandelete:"))
async def ac_plan_delete(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    pid=int(call.data.rsplit(":",1)[1]);ok=await deactivate_plan_admin(pid)
    if ok:await admin_log(call.from_user.id,"PLAN_DEACTIVATE",str(pid))
    await call.message.edit_text("✅ Plan deactivated. Historical orders are preserved." if ok else "Plan not found.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows()));await callback_answer(call, )

@dp.callback_query(F.data=="ac:addproduct")
async def ac_addproduct(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin only",show_alert=True);return
    await state.update_data(stock_category="Other Products");await state.set_state(AdminState.stock_product_name)
    await call.message.answer("Send product name. You can change its category after creation.");await callback_answer(call, )

@dp.callback_query(F.data=="cp:create")
async def coupon_create_start(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    await state.set_state(AdminState.admin_input); await state.update_data(admin_action="coupon")
    await call.message.answer("Send CODE | DISCOUNT_PERCENT | USAGE_LIMIT (0 = unlimited)."); await callback_answer(call)

@dp.callback_query(F.data.startswith("cp:view:"))
async def coupon_view(call:CallbackQuery):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    code=call.data.split(":",2)[2]; c=next((x for x in await list_coupons(100) if x['code']==code),None)
    if not c: await callback_answer(call,"Coupon not found",show_alert=True); return
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=("⏸️ Pause coupon" if c['active'] else "▶️ Activate coupon"),callback_data=f"cp:toggle:{code}")],[InlineKeyboardButton(text="✏️ Edit discount / limit",callback_data=f"cp:edit:{code}")],[InlineKeyboardButton(text="🗑️ Delete coupon",callback_data=f"cp:delete:{code}")],[InlineKeyboardButton(text="🔙 Coupons",callback_data="adm:coupons")]] + admin_nav_rows())
    await call.message.edit_text(f"🎟️ <b>{html.escape(code)}</b>\nDiscount: {c['discount_percent']}%\nUsage: {c['used_count']}/{c['usage_limit'] or 'Unlimited'}\nStatus: {'Active' if c['active'] else 'Paused'}",reply_markup=kb); await callback_answer(call)

@dp.callback_query(F.data.startswith("cp:toggle:"))
async def coupon_toggle(call:CallbackQuery):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    code=call.data.split(":",2)[2]; c=next((x for x in await list_coupons(100) if x['code']==code),None)
    ok=await update_coupon(code,active=not c['active']) if c else False
    await callback_answer(call,"Coupon updated" if ok else "Coupon not found");
    if ok: await coupon_view_refresh(call)

async def coupon_view_refresh(call):
    code=call.data.split(":",2)[2]; c=next((x for x in await list_coupons(100) if x['code']==code),None)
    if c: await call.message.edit_text(f"🎟️ <b>{html.escape(code)}</b>\nDiscount: {c['discount_percent']}%\nUsage: {c['used_count']}/{c['usage_limit'] or 'Unlimited'}\nStatus: {'Active' if c['active'] else 'Paused'}",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=("⏸️ Pause coupon" if c['active'] else "▶️ Activate coupon"),callback_data=f"cp:toggle:{code}")],[InlineKeyboardButton(text="✏️ Edit discount / limit",callback_data=f"cp:edit:{code}")],[InlineKeyboardButton(text="🗑️ Delete coupon",callback_data=f"cp:delete:{code}")],[InlineKeyboardButton(text="🔙 Coupons",callback_data="adm:coupons")]] + admin_nav_rows()))

@dp.callback_query(F.data.startswith("cp:edit:"))
async def coupon_edit_start(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    code=call.data.split(":",2)[2]; await state.set_state(AdminState.admin_input); await state.update_data(admin_action="coupon_edit",coupon_code=code)
    await call.message.answer("Send NEW_DISCOUNT_PERCENT | NEW_USAGE_LIMIT (0 = unlimited)."); await callback_answer(call)

@dp.callback_query(F.data.startswith("cp:delete:"))
async def coupon_delete(call:CallbackQuery):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    code=call.data.split(":",2)[2]; ok=await delete_coupon(code); await admin_log(call.from_user.id,"COUPON_DELETE",code)
    await call.message.edit_text("✅ Coupon deleted." if ok else "Coupon not found.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟️ Coupons",callback_data="adm:coupons")],[InlineKeyboardButton(text="🏠 Admin Menu",callback_data="stk:admin")]] + admin_nav_rows())); await callback_answer(call)

@dp.callback_query(F.data=="setting:add")
async def setting_add_start(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    await state.set_state(AdminState.admin_input); await state.update_data(admin_action="setting")
    await call.message.answer("Send SETTING_KEY | VALUE."); await callback_answer(call)

@dp.callback_query(F.data.startswith("setting:edit:"))
async def setting_edit_start(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    key=call.data.split(":",2)[2]; await state.set_state(AdminState.admin_input); await state.update_data(admin_action="setting_value",setting_key=key)
    await call.message.answer(f"Send the new value for <code>{html.escape(key)}</code>."); await callback_answer(call)

@dp.callback_query(F.data.in_({"bc:all","bc:customers","bc:resellers"}))
async def broadcast_audience(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    audience=call.data.split(":",1)[1]; await state.update_data(audience=audience,broadcast_items=[]); await state.set_state(AdminState.broadcast_collect)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Finish & Preview",callback_data="bc:finish")],[InlineKeyboardButton(text="✖ Cancel",callback_data="bc:cancel")]])
    await call.message.edit_text(f"📢 <b>Broadcast to {audience}</b>\nNow send text, photo, video or other Telegram messages one by one. Use Add another after each message; Finish when ready.",reply_markup=kb); await callback_answer(call)

@dp.message(AdminState.broadcast_collect)
async def broadcast_collect_message(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id): return
    if message.text and message.text.strip().lower() in {"/cancel","cancel"}:
        await state.clear(); await message.answer("Broadcast cancelled.",reply_markup=admin_keyboard()); return
    d=await state.get_data(); items=d.get("broadcast_items",[])
    items.append({"chat_id":message.chat.id,"message_id":message.message_id})
    await state.update_data(broadcast_items=items)
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Add another message",callback_data="bc:more")],[InlineKeyboardButton(text="✅ Finish & Preview",callback_data="bc:finish")],[InlineKeyboardButton(text="✖ Cancel",callback_data="bc:cancel")]])
    await message.answer(f"✅ Message {len(items)} added to broadcast. Add more or finish.",reply_markup=kb)

@dp.callback_query(F.data=="bc:more")
async def broadcast_more(call:CallbackQuery):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    await call.message.answer("Send the next broadcast message."); await callback_answer(call)

@dp.callback_query(F.data=="bc:finish")
async def broadcast_finish(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    d=await state.get_data(); items=d.get("broadcast_items",[])
    if not items: await callback_answer(call,"Add at least one message first",show_alert=True); return
    await state.set_state(AdminState.broadcast_confirm)
    await call.message.edit_text(f"📢 <b>Confirm broadcast</b>\nAudience: {d.get('audience','all')}\nMessages: {len(items)}\nSend these messages to the selected audience?",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Send broadcast",callback_data="bc:send")],[InlineKeyboardButton(text="✖ Cancel",callback_data="bc:cancel")]] + admin_nav_rows())); await callback_answer(call)

@dp.callback_query(F.data=="bc:cancel")
async def broadcast_cancel(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    await state.clear(); await call.message.edit_text("Broadcast cancelled.",reply_markup=admin_keyboard()); await callback_answer(call)

@dp.callback_query(F.data=="bc:send")
async def broadcast_send(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id): await callback_answer(call,"Admin only",show_alert=True); return
    from db import broadcast_user_ids
    d=await state.get_data(); audience=d.get("audience","all"); items=d.get("broadcast_items",[])
    if audience=="resellers": ids=await broadcast_user_ids(resellers=True)
    elif audience=="customers": ids=await broadcast_user_ids(resellers=False)
    else: ids=await broadcast_user_ids(resellers=False)
    if audience=="customers":
        from db import Session, User
        from sqlalchemy import select
        async with Session() as session: ids=list((await session.scalars(select(User.user_id).where(User.is_banned==False,User.is_reseller==False))).all())
    sent=failed=0
    await callback_answer(call,"Broadcast started")
    for uid in ids:
        ok=True
        for item in items:
            try: await bot.copy_message(uid,item["chat_id"],item["message_id"])
            except Exception as exc:
                retry_after=getattr(exc,"retry_after",None)
                if retry_after:
                    await asyncio.sleep(float(retry_after)+0.5)
                    try: await bot.copy_message(uid,item["chat_id"],item["message_id"])
                    except Exception: ok=False
                else: ok=False
        if ok: sent+=1
        else: failed+=1
        await asyncio.sleep(0.04)
    await state.clear(); await admin_log(call.from_user.id,"BROADCAST",f"audience={audience}, messages={len(items)}, sent={sent}, failed={failed}")
    await call.message.edit_text(f"✅ Broadcast complete\nMessages: {len(items)}\nUsers reached: {sent}\nFailed: {failed}",reply_markup=admin_keyboard())

@dp.message(AdminState.admin_input,F.text)
async def admin_button_input(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    data=await state.get_data();action=data.get("admin_action");raw=message.text.strip()
    try:
        if action=="wallet":
            uid_s,amount_s=[x.strip() for x in raw.split("|",1)];amount=float(amount_s)
            if amount==0:raise ValueError
            balance=await adjust_wallet(int(uid_s),amount,message.from_user.id,"Admin button adjustment")
            if balance is None:await message.answer("User not found.")
            else:await admin_log(message.from_user.id,"WALLET_ADJUST",f"user={uid_s}, amount={amount}");await message.answer(f"✅ Wallet updated. New balance: ₹{balance:.2f}",reply_markup=admin_keyboard())
        elif action=="reseller":
            uid=int(raw);u=await admin_user(uid)
            if not u:await message.answer("User not found. Send another ID.");return
            enabled=not bool(u["is_reseller"]);await set_reseller(uid,enabled);await admin_log(message.from_user.id,"RESELLER_TOGGLE",f"{uid}={enabled}")
            await message.answer(f"✅ Reseller access {'enabled' if enabled else 'disabled'} for {uid}.",reply_markup=admin_keyboard())
        elif action=="coupon":
            code,discount,limit=[x.strip() for x in raw.split("|")];ok=await create_coupon(code,int(discount),int(limit))
            await message.answer("✅ Coupon created." if ok else "Coupon already exists or input is invalid.",reply_markup=admin_keyboard())
        elif action=="product_name":
            pid=int(data["product_id"]);ok=await edit_product(pid,name=raw)
            await message.answer("✅ Product name updated." if ok else "Product not found.",reply_markup=admin_keyboard())
        elif action=="product_category":
            pid=int(data["product_id"]);ok=await edit_product(pid,category=raw)
            await message.answer("✅ Product category updated." if ok else "Product not found.",reply_markup=admin_keyboard())
        elif action=="category_rename":
            old=data["category_name"];ok=await rename_category_admin(old,raw)
            await message.answer("✅ Category renamed." if ok else "Category not found.",reply_markup=admin_keyboard())
        elif action=="plan_edit":
            pid=int(data["plan_id"]);duration,price,reseller=[x.strip() for x in raw.split("|")]
            ok=await edit_plan_admin(pid,duration,float(price),float(reseller))
            await message.answer("✅ Plan updated." if ok else "Plan not found.",reply_markup=admin_keyboard())
        elif action=="setting":
            key,value=[x.strip() for x in raw.split("|",1)]
            if not key or len(key)>80 or len(value)>1000:raise ValueError
            await set_bot_setting(key.lower(),value);await admin_log(message.from_user.id,"SETTING_UPDATE",key.lower())
            await message.answer("✅ Setting saved.",reply_markup=admin_keyboard())
        elif action=="coupon_edit":
            discount,limit=[x.strip() for x in raw.split("|",1)]
            discount=int(discount); limit=int(limit)
            if not 1<=discount<=100 or limit<0: raise ValueError
            ok=await update_coupon(data["coupon_code"],discount_percent=discount,usage_limit=limit)
            await message.answer("✅ Coupon updated." if ok else "Coupon not found.",reply_markup=admin_keyboard())
        elif action=="setting_value":
            key=data.get("setting_key")
            if not key or len(raw)>1000:raise ValueError
            await set_bot_setting(key,raw);await admin_log(message.from_user.id,"SETTING_UPDATE",key)
            await message.answer("✅ Setting updated.",reply_markup=admin_keyboard())
        await state.clear()
    except (ValueError,TypeError):
        await message.answer("Invalid format. Please try again using the format shown above.")

# Guided, button-first stock and catalogue management

def stock_category_keyboard(categories):
    rows=[]
    for i,cat in enumerate(categories):
        rows.append([InlineKeyboardButton(text=f"📁 {cat['name']} ({cat['count']})",callback_data=f"stk:cat:{i}")])
    rows.append([InlineKeyboardButton(text="➕ Create new category",callback_data="stk:newcat")])
    rows.append([InlineKeyboardButton(text="✖ Cancel",callback_data="stk:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def show_stock_categories(target, state):
    await state.clear()
    categories=await list_categories()
    await state.update_data(stock_categories=[c['name'] for c in categories])
    if categories:
        await target.answer("📁 <b>Step 1 of 4 — Choose a category</b>\nSelect an existing category or create a new one:",reply_markup=stock_category_keyboard(categories))
    else:
        await target.answer("📁 <b>Step 1 of 4 — Create a category</b>\nNo categories exist yet. Tap below to add the first category:",reply_markup=stock_category_keyboard([]))

async def show_stock_products(target, state, category):
    await state.clear()
    products=await list_products(category=category,include_empty=True)
    rows=[[InlineKeyboardButton(text=f"📦 {p['name']}",callback_data=f"stk:product:{p['id']}")] for p in products]
    rows += [[InlineKeyboardButton(text="➕ Create new product",callback_data="stk:newproduct")],
             [InlineKeyboardButton(text="⬅ Change category",callback_data="stk:start")],
             [InlineKeyboardButton(text="✖ Cancel",callback_data="stk:cancel")]]
    await state.update_data(stock_category=category)
    await target.answer(f"📦 <b>Step 2 of 4 — Choose a product</b>\nCategory: <b>{html.escape(category)}</b>\nSelect a product or create a new one:",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

async def show_stock_plans(target, state, product_id):
    p=await get_product(product_id)
    if not p:
        await target.answer("Product not found. Please start again.");await state.clear();return
    await state.clear()
    rows=[[InlineKeyboardButton(text=f"🗓️ {pl['duration']} · {pl['stock']} in stock",callback_data=f"stk:plan:{pl['id']}")] for pl in p['plans']]
    rows += [[InlineKeyboardButton(text="➕ Create new plan",callback_data="stk:newplan")],
             [InlineKeyboardButton(text="⬅ Choose another product",callback_data="stk:backproducts")],
             [InlineKeyboardButton(text="✖ Cancel",callback_data="stk:cancel")]]
    await state.update_data(stock_product_id=product_id,stock_product_name=p['name'])
    await target.answer(f"🗓️ <b>Step 3 of 4 — Choose a plan</b>\nProduct: <b>{html.escape(p['name'])}</b>\nChoose a plan or create a new one:",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@dp.callback_query(F.data=="rewardstock:menu")
async def reward_stock_menu(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):
        await callback_answer(call, "Admin access required",show_alert=True);return
    await state.clear()
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌳 Add Root Trial Keys",callback_data="rewardstock:type:ROOT")],
        [InlineKeyboardButton(text="📱 Add Non-Root Trial Keys",callback_data="rewardstock:type:NON_ROOT")],
        [InlineKeyboardButton(text="🔙 Admin Menu",callback_data="stk:admin")]])
    await call.message.answer("🎁 <b>Referral Reward Key Stock</b>\n\nThis is a separate inventory reserved only for referral rewards. Keys added here will NOT appear in normal shop stock or be sold to customers.",reply_markup=kb)
    await callback_answer(call, )

@dp.callback_query(F.data.startswith("rewardstock:type:"))
async def reward_stock_type(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):
        await callback_answer(call, "Admin access required",show_alert=True);return
    kind=call.data.rsplit(":",1)[1]
    if kind not in ("ROOT","NON_ROOT"):
        await callback_answer(call, "Invalid reward type",show_alert=True);return
    await state.clear();await state.update_data(reward_stock_type=kind);await state.set_state(AdminState.reward_keys)
    await call.message.answer(f"Send {kind.replace('_','-')} referral trial keys, one key per line. These keys are separate from shop inventory. Send /cancel to stop.")
    await callback_answer(call, )

@dp.message(AdminState.reward_keys,F.text)
async def reward_stock_receive(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    data=await state.get_data();kind=data.get("reward_stock_type")
    keys=[line.strip() for line in message.text.splitlines() if line.strip()]
    if not keys:
        await message.answer("No keys found. Send one key per line.");return
    added=await add_referral_stock(kind,keys)
    await admin_log(message.from_user.id,"REFERRAL_KEY_UPLOAD",f"type={kind}, added={added}, submitted={len(keys)}")
    await state.clear()
    await message.answer(f"✅ <b>Referral Reward Stock Updated</b>\n\nType: {kind.replace('_','-')}\n📥 Submitted: {len(keys)}\n➕ Added: {added}\n♻️ Duplicates skipped: {len(set(keys))-added}\n\nThese keys are reserved for referral claims only.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Add more reward keys",callback_data="rewardstock:menu")],[InlineKeyboardButton(text="🏠 Admin menu",callback_data="stk:admin")]]))

@dp.callback_query(F.data=="stk:start")
async def stock_flow_start(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    await state.clear();await show_stock_categories(call.message,state);await callback_answer(call, )

@dp.callback_query(F.data=="stk:catalog")
async def stock_catalog(call:CallbackQuery):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    products=await list_products(include_empty=True)
    if not products:await call.message.answer("No products found yet.");await callback_answer(call, );return
    lines=[]
    for p in products:
        lines.append(f"📁 <b>{html.escape(p['category'])}</b> / 📦 <b>{html.escape(p['name'])}</b>")
        for pl in p['plans']:
            lines.append(f"   • {html.escape(pl['duration'])}: {pl['stock']} keys · ₹{pl['price_inr']:.2f}")
    await call.message.answer("\n".join(lines));await callback_answer(call, )

@dp.callback_query(F.data.startswith("stk:cat:"))
async def stock_pick_category(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    data=await state.get_data();cats=data.get('stock_categories',[])
    try:category=cats[int(call.data.rsplit(':',1)[1])]
    except (ValueError,IndexError):await callback_answer(call, "List expired. Start again.",show_alert=True);return
    await show_stock_products(call.message,state,category);await callback_answer(call, )

@dp.callback_query(F.data=="stk:newcat")
async def stock_new_category(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    await state.set_state(AdminState.stock_category_name)
    await call.message.answer("✍️ <b>New category</b>\nSend the category name (up to 100 characters). Send /cancel to stop.");await callback_answer(call, )

@dp.message(AdminState.stock_category_name,F.text)
async def stock_save_category(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    name=message.text.strip()
    if not name or len(name)>100:await message.answer("Please send a category name between 1 and 100 characters.");return
    await state.update_data(stock_category=name)
    await admin_log(message.from_user.id,"CATEGORY_CREATE",name)
    await show_stock_products(message,state,name)

@dp.callback_query(F.data.startswith("stk:product:"))
async def stock_pick_product(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    try:pid=int(call.data.rsplit(':',1)[1])
    except ValueError:await callback_answer(call, "Invalid product",show_alert=True);return
    await show_stock_plans(call.message,state,pid);await callback_answer(call, )

@dp.callback_query(F.data=="stk:newproduct")
async def stock_new_product(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    await state.set_state(AdminState.stock_product_name)
    await call.message.answer("✍️ <b>New product</b>\nSend the product name. Send /cancel to stop.");await callback_answer(call, )

@dp.message(AdminState.stock_product_name,F.text)
async def stock_product_name(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    name=message.text.strip()
    if not name or len(name)>160:await message.answer("Product name must be 1–160 characters.");return
    data=await state.get_data()
    try:
        # Product descriptions are optional; create the product with a blank description.
        p=await add_product(name,0,"",data['stock_category'])
        await admin_log(message.from_user.id,"PRODUCT_CREATE",f"{p['id']} {p['name']} category={data['stock_category']}")
        await message.answer(f"✅ Product created: <b>{html.escape(p['name'])}</b>")
        await show_stock_plans(message,state,p['id'])
    except Exception:
        log.exception("Guided product creation failed");await message.answer("Could not create product. Please try again or contact support.");await state.clear()

@dp.callback_query(F.data=="stk:backproducts")
async def stock_back_products(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    data=await state.get_data();await show_stock_products(call.message,state,data.get('stock_category','Other Products'));await callback_answer(call, )

@dp.callback_query(F.data.startswith("stk:plan:"))
async def stock_pick_plan(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    try:plan_id=int(call.data.rsplit(':',1)[1])
    except ValueError:await callback_answer(call, "Invalid plan",show_alert=True);return
    plan=await get_plan(plan_id)
    if not plan:await callback_answer(call, "Plan not found",show_alert=True);return
    await state.update_data(stock_plan_id=plan_id)
    await state.set_state(AdminState.stock_keys)
    await call.message.answer(f"🔑 <b>Step 4 of 4 — Upload keys</b>\nCategory: {html.escape(plan['category'])}\nProduct: {html.escape(plan['product_name'])}\nPlan: {html.escape(plan['duration'])}\n\nNow send keys, one per line. You can paste a large batch. Send /cancel to stop.")
    await callback_answer(call, )

@dp.callback_query(F.data=="stk:newplan")
async def stock_new_plan(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    await state.set_state(AdminState.stock_plan_duration)
    await call.message.answer("🗓️ <b>New plan</b>\nSend the plan name/duration (example: 1 Month, 3 Months, Lifetime). Send /cancel to stop.");await callback_answer(call, )

@dp.message(AdminState.stock_plan_duration,F.text)
async def stock_plan_duration(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    duration=message.text.strip()
    if not duration or len(duration)>80:await message.answer("Plan name must be 1–80 characters.");return
    await state.update_data(stock_new_duration=duration);await state.set_state(AdminState.stock_plan_prices)
    await message.answer("💰 Send INR prices only: <code>Customer INR | Reseller INR</code>\nExample: <code>499 | 399</code>")

@dp.message(AdminState.stock_plan_prices,F.text)
async def stock_plan_prices(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    try:
        vals=[float(x.strip()) for x in message.text.replace('|',',').split(',') if x.strip()]
        if len(vals)==2: vals=[vals[0],0.0,vals[1],0.0]
        if len(vals)!=4 or any(v<0 for v in vals):raise ValueError
        data=await state.get_data();pl=await add_plan(data['stock_product_id'],data['stock_new_duration'],*vals)
        if not pl:await message.answer("Product not found. Please start the stock flow again.");await state.clear();return
        await admin_log(message.from_user.id,"PLAN_CREATE",f"{pl['id']} {pl['duration']} product={data['stock_product_id']}")
        await state.update_data(stock_plan_id=pl['id']);await state.set_state(AdminState.stock_keys)
        await message.answer(f"✅ Plan created: <b>{html.escape(pl['duration'])}</b>\n\n🔑 <b>Step 4 of 4 — Upload keys</b>\nSend keys, one per line. Paste a large batch if needed. Send /cancel to stop.")
    except ValueError:await message.answer("Invalid prices. Send two non-negative INR amounts: Customer | Reseller, e.g. 499 | 399.")
    except Exception:
        log.exception("Guided plan creation failed");await message.answer("Could not create plan. Please try again.");await state.clear()

@dp.message(AdminState.stock_keys,F.text)
async def stock_receive_keys(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    keys=[line.strip() for line in message.text.splitlines() if line.strip()]
    if not keys:await message.answer("No keys found. Paste one key per line.");return
    data=await state.get_data();plan_id=data.get('stock_plan_id')
    added=await add_stock(plan_id,keys)
    await admin_log(message.from_user.id,"REWARD_KEY_UPLOAD" if data.get("reward_stock_type") else "KEY_BULK_UPLOAD",f"plan={plan_id}, type={data.get('reward_stock_type','SHOP')}, added={added}, submitted={len(keys)}")
    await state.clear()
    await message.answer(f"✅ <b>{'Reward key stock' if data.get('reward_stock_type') else 'Stock'} upload complete</b>\n\n📥 Submitted: {len(keys)}\n➕ Added: {added}\n♻️ Duplicates skipped: {len(set(keys))-added}\n\nYour inventory is updated.",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎁 Add more reward keys",callback_data="rewardstock:menu")],[InlineKeyboardButton(text="📋 View inventory",callback_data="stk:catalog")],[InlineKeyboardButton(text="🏠 Admin menu",callback_data="stk:admin")]]))

@dp.callback_query(F.data=="stk:admin")
async def stock_back_admin(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    await state.clear();await call.message.edit_text("⚔️ <b>Admin Control</b>\nChoose a management section:",reply_markup=admin_keyboard());await callback_answer(call, )

@dp.callback_query(F.data=="stk:cancel")
async def stock_flow_cancel(call:CallbackQuery,state:FSMContext):
    if not is_admin(call.from_user.id):await callback_answer(call, "Admin access required",show_alert=True);return
    await state.clear();await call.message.answer("Stock update cancelled.",reply_markup=admin_keyboard());await callback_answer(call, )

@dp.message(Command("cancel"))
async def admin_cancel_flow(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    await state.clear();await message.answer("Current admin operation cancelled.",reply_markup=admin_keyboard())

@dp.message(Command("addproduct"))
async def admin_addproduct(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|",2)
    if len(parts)!=3:await message.answer("Usage: /addproduct CATEGORY|NAME|DESCRIPTION");return
    try:
        category,name,desc=(x.strip() for x in parts);p=await add_product(name,0,desc,category)
        await admin_log(message.from_user.id,"PRODUCT_CREATE",f"{p['id']} {p['name']}");await message.answer(f"Product created: ID <code>{p['id']}</code> — {html.escape(p['name'])}. Add durations with /addplan.")
    except Exception:log.exception("Add product error");await message.answer("Could not create product.")

@dp.message(Command("addplan"))
async def admin_addplan(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|")
    if len(parts)!=6:await message.answer("Usage: /addplan PRODUCT_ID|DURATION|PRICE_INR|PRICE_USD|RESELLER_INR|RESELLER_USD");return
    try:
        pid=int(parts[0]);duration=parts[1].strip();vals=[float(x) for x in parts[2:]]
        if min(vals)<0:raise ValueError()
        pl=await add_plan(pid,duration,*vals)
        if not pl:await message.answer("Product ID not found.");return
        await admin_log(message.from_user.id,"PLAN_CREATE",f"{pl['id']} {pl['duration']}");await message.answer(f"Plan created: ID <code>{pl['id']}</code> — {html.escape(pl['duration'])}. Add keys using /addstock {pl['id']}.")
    except ValueError:await message.answer("Invalid command values; prices must be numeric and non-negative.")

@dp.message(Command("addstock"))
async def admin_addstock(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    try:plan_id=int(message.text.partition(" ")[2].strip())
    except ValueError:await message.answer("Usage: /addstock PLAN_ID");return
    plan=await get_plan(plan_id)
    if not plan:await message.answer("Plan not found.");return
    await state.update_data(stock_plan_id=plan_id);await state.set_state(AdminState.stock_keys)
    await message.answer(f"Send keys for {html.escape(plan['product_name'])} — {html.escape(plan['duration'])}, one per line. Send /cancel to abort.")

@dp.message(Command("products"))
async def admin_products(message:Message):
    if not is_admin(message.from_user.id):return
    products=await list_products(include_empty=True)
    await message.answer("\n".join(f"ID {p['id']} | {p['category']} | {p['name']} | stock {p['stock']}\n"+"; ".join(f"plan {pl['id'] if 'id' in pl else ''} {pl['duration']} ₹{pl['price_inr']} stock {pl['stock']}" for pl in p['plans']) for p in products) or "No products.")

@dp.message(Command("orders"))
async def admin_orders(message:Message):
    if not is_admin(message.from_user.id):return
    rows=await list_orders(None);await message.answer("\n".join(f"{o['order_id']} | user {o['user_id']} | ₹{o['amount_inr']:.2f} | {o['status']}" for o in rows[:20]) or "No orders.")

@dp.message(Command("wallet"))
async def admin_wallet(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|")
    if len(parts)!=2:await message.answer("Usage: /wallet USER_ID|AMOUNT_INR");return
    try:
        uid=int(parts[0].strip());amount=float(parts[1].strip())
        if amount<=0:raise ValueError()
        balance=await adjust_wallet(uid,amount,message.from_user.id,"Admin wallet credit")
        if balance is None:await message.answer("User has not started the bot yet.")
        else:await admin_log(message.from_user.id,"WALLET_CREDIT",f"user={uid}, amount={amount}");await message.answer(f"Wallet credited. User {uid} balance: ₹{balance:.2f}")
    except ValueError:await message.answer("Enter a valid user ID and positive amount.")

@dp.message(Command("setreseller"))
async def set_reseller_command(message:Message):
    if not is_admin(message.from_user.id):return
    from db import set_reseller
    try:uid=int(message.text.partition(" ")[2]);await set_reseller(uid,True);await admin_log(message.from_user.id,"RESELLER_ENABLE",str(uid));await message.answer(f"Reseller enabled for user {uid}.")
    except ValueError:await message.answer("Usage: /setreseller USER_ID")

@dp.message(Command("walletadjust"))
async def admin_wallet_adjust(message:Message):
    if not is_admin(message.from_user.id):return
    try:
        uid_s,amount_s=message.text.partition(" ")[2].split("|",1);amount=float(amount_s)
        if amount==0:raise ValueError()
        balance=await adjust_wallet(int(uid_s),amount,message.from_user.id,"Admin adjustment")
        if balance is None:await message.answer("User not found.")
        else:
            await admin_log(message.from_user.id,"WALLET_ADJUST",f"user={uid_s}, amount={amount}")
            await message.answer(f"Wallet updated. New balance: ₹{balance:.2f}")
    except ValueError as e:await message.answer(f"Invalid input: {e}\nUsage: /walletadjust USER_ID|AMOUNT (negative deducts)")

@dp.message(Command("wallethistory"))
async def admin_wallet_history(message:Message):
    if not is_admin(message.from_user.id):return
    try:uid=int(message.text.partition(" ")[2]);rows=await wallet_history(uid)
    except ValueError:await message.answer("Usage: /wallethistory USER_ID");return
    await message.answer("💰 Wallet history\n"+("\n".join(f"{x['created_at']:%Y-%m-%d} {x['kind']} ₹{x['amount']:.2f} — {html.escape(x['note'])}" for x in rows) if rows else "No wallet adjustments recorded."))

@dp.message(Command("editproduct"))
async def admin_edit_product(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|",3)
    if len(parts)!=4:await message.answer("Usage: /editproduct ID|NAME|CATEGORY|DESCRIPTION");return
    try:pid=int(parts[0]);ok=await edit_product(pid,parts[1].strip(),parts[2].strip(),parts[3].strip())
    except ValueError:ok=False
    if ok:await admin_log(message.from_user.id,"PRODUCT_EDIT",str(pid))
    await message.answer("Product updated." if ok else "Product not found or invalid ID.")

@dp.message(Command("deleteproduct"))
async def admin_delete_product(message:Message):
    if not is_admin(message.from_user.id):return
    try:pid=int(message.text.partition(" ")[2]);ok=await deactivate_product(pid)
    except ValueError:ok=False
    if ok:await admin_log(message.from_user.id,"PRODUCT_DEACTIVATE",str(pid))
    await message.answer("Product and its plans hidden from the shop (soft delete)." if ok else "Product not found.")

@dp.message(Command("keys"))
async def admin_list_keys(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|",1)
    try:pid=int(parts[0].strip());status=parts[1].strip().upper() if len(parts)>1 and parts[1].strip() else None
    except ValueError:await message.answer("Usage: /keys PLAN_ID|STATUS (optional)");return
    if status and status not in {"AVAILABLE","SOLD","EXPIRED"}:await message.answer("Status must be AVAILABLE, SOLD or EXPIRED.");return
    rows=await list_keys(pid,status)
    await message.answer("🔑 <b>Key inventory</b>\n"+("\n".join(f"ID {r['id']} · {r['status']} · order {r['order_id'] or '—'}" for r in rows) if rows else "No keys found."))

@dp.message(Command("stockstatus"))
async def admin_stock_status(message:Message):
    if not is_admin(message.from_user.id):return
    try:from db import set_key_status
    except Exception:return
    try:key_id_s,status=message.text.partition(" ")[2].split("|",1);ok=await set_key_status(int(key_id_s),status.strip().upper())
    except ValueError:ok=False
    if ok:await admin_log(message.from_user.id,"KEY_STATUS",f"{key_id_s}={status}")
    await message.answer("Key status updated." if ok else "Usage: /stockstatus KEY_ID|AVAILABLE or SOLD or EXPIRED")

@dp.message(Command("resellerprice"))
async def admin_reseller_price(message:Message):
    if not is_admin(message.from_user.id):return
    try:pid_s,inr_s,usd_s=message.text.partition(" ")[2].split("|");ok=await set_reseller_pricing(int(pid_s),float(inr_s),float(usd_s))
    except ValueError:ok=False
    if ok:await admin_log(message.from_user.id,"RESELLER_PRICE",f"plan={pid_s}, INR={inr_s}, USD={usd_s}")
    await message.answer("Reseller pricing updated." if ok else "Usage: /resellerprice PLAN_ID|INR|USD")

@dp.message(Command("unreseller"))
async def admin_unreseller(message:Message):
    if not is_admin(message.from_user.id):return
    try:uid=int(message.text.partition(" ")[2]);await set_reseller(uid,False);await admin_log(message.from_user.id,"RESELLER_DISABLE",str(uid));await message.answer("Reseller deactivated.")
    except ValueError:await message.answer("Usage: /unreseller USER_ID")

@dp.message(Command("coupon"))
async def admin_coupon(message:Message):
    if not is_admin(message.from_user.id):return
    try:
        code,discount,limit=message.text.partition(" ")[2].split("|");discount=int(discount);limit=int(limit)
        if not 1<=discount<=100 or limit<0:raise ValueError()
        ok=await create_coupon(code,discount,limit)
        if ok:await admin_log(message.from_user.id,"COUPON_CREATE",f"{code.upper()} {discount}% limit={limit}")
        await message.answer("Coupon created." if ok else "That coupon code already exists.")
    except ValueError:await message.answer("Usage: /coupon CODE|DISCOUNT_PERCENT|USAGE_LIMIT (0 = unlimited)")

@dp.message(Command("setting"))
async def admin_setting(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|",1)
    if len(parts)!=2 or not parts[0].strip():await message.answer("Usage: /setting KEY|VALUE");return
    await set_bot_setting(parts[0].strip().lower(),parts[1].strip());await admin_log(message.from_user.id,"SETTING_UPDATE",parts[0].strip().lower());await message.answer("Setting saved.")

@dp.message(Command("paymentcheck"))
async def admin_payment_check(message:Message):
    if not is_admin(message.from_user.id):return
    order_id=message.text.partition(" ")[2].strip()
    if not order_id:await message.answer("Usage: /paymentcheck ORDER_ID");return
    order=await get_order(order_id)
    if not order:await message.answer("Order not found.");return
    if order["payment_method"]!="CASHFREE":await message.answer(f"{order_id}: {order['status']} (wallet payment)");return
    try:
        remote=await fetch_order_payments(order_id)
        payments=remote if isinstance(remote,list) else remote.get("payments",[]) if isinstance(remote,dict) else []
        successful=next((x for x in payments if x.get("payment_status")=="SUCCESS"),None)
        status=successful.get("payment_status") if successful else (payments[-1].get("payment_status") if payments else "NO PAYMENT ATTEMPT")
        paid=float(successful.get("payment_amount") or 0) if successful else 0.0
        await message.answer(f"🧾 <b>{order_id}</b>\nLocal status: {order['status']}\nCashfree status: {html.escape(str(status))}\nPaid amount: ₹{paid:.2f}\nOrder amount: ₹{order['amount_inr']:.2f}")
    except Exception:
        log.exception("Admin Cashfree status lookup failed");await message.answer("Could not fetch status from Cashfree.")

@dp.message(Command("refundrecord"))
async def admin_refund_record(message:Message):
    if not is_admin(message.from_user.id):return
    parts=message.text.partition(" ")[2].split("|",2)
    if len(parts)!=3:await message.answer("Usage: /refundrecord ORDER_ID|REQUESTED/PROCESSING/REFUNDED/REJECTED|NOTE");return
    ok=await record_refund(parts[0].strip(),parts[1].strip(),parts[2].strip(),message.from_user.id)
    if ok:await admin_log(message.from_user.id,"REFUND_STATUS",f"{parts[0]}={parts[1]}")
    await message.answer("Refund progress recorded." if ok else "Order not found or invalid status.")

@dp.message(Command("refunds"))
async def admin_refunds(message:Message):
    if not is_admin(message.from_user.id):return
    rows=await refund_history()
    await message.answer("💳 <b>Refund tracking</b>\n"+("\n".join(f"{r['order_id']} · {r['status']} · {html.escape(r['note'])} · admin {r['admin_id']}" for r in rows) if rows else "No refund records."))

@dp.message(Command("broadcast_resellers"))
async def broadcast_resellers_start(message:Message,state:FSMContext):
    if not is_admin(message.from_user.id):return
    await state.update_data(audience="resellers",broadcast_items=[]);await state.set_state(AdminState.broadcast_collect)
    await message.answer("Send the first message for the reseller broadcast. Then use Add another / Finish buttons.")

async def run_webhook_server():
    from aiohttp import web
    import json
    async def webhook(request):
        raw=await request.read();timestamp=request.headers.get("x-webhook-timestamp","");signature=request.headers.get("x-webhook-signature","")
        if not verify_webhook_signature(timestamp,raw,signature):return web.Response(status=401,text="Invalid signature")
        try:
            payload=json.loads(raw);data=payload.get("data",{}) or {};order_data=data.get("order",{}) or {}
            order_id=order_data.get("order_id") or data.get("order_id") or payload.get("order_id")
            if order_id:
                order=await get_order(order_id)
                if order and order['status'] in ("PENDING","EXPIRED","PAID_NO_STOCK"):
                    payments=await fetch_order_payments(order_id)
                    rows=payments if isinstance(payments,list) else payments.get("payments",[]) if isinstance(payments,dict) else []
                    successful=next((x for x in rows if x.get("payment_status")=="SUCCESS" and abs(float(x.get("payment_amount") or 0)-order['amount_inr'])<0.005),None)
                    if successful:
                        if order.get("payment_method")=="TOPUP":
                            credited=await fulfill_wallet_topup(order_id)
                            if credited and credited.get("credited"):
                                await bot.send_message(order['user_id'],f"✅ <b>Wallet Top-up Successful!</b>\n\n💰 ₹{credited['amount']:.2f} has been added to your wallet.")
                            return web.Response(text="OK")
                        result=await fulfill_paid_order(order_id) if order['status'] in ("PENDING","EXPIRED") else {"key_text":None}
                        if result and result.get("key_text"):
                            plan=await get_plan(order['plan_id']) if order.get('plan_id') else None
                            await bot.send_message(order['user_id'],success_message(plan['product_name'] if plan else "Product",order['duration'],order['quantity'],result['key_text']))
                            await notify_referral_reward(order['user_id'])
                        elif result and not result.get("key_text"):
                            refund=await credit_wallet_for_no_stock(order_id)
                            if refund and refund.get("credited"):
                                text,kb=no_stock_refund_message(refund['amount'])
                                await bot.send_message(order['user_id'],text,reply_markup=kb)
                    elif order['status']=="PENDING" and datetime.now(timezone.utc)-order['created_at'].astimezone(timezone.utc)>timedelta(minutes=5):
                        await expire_order(order_id)
        except Exception:log.exception("Webhook processing failed");return web.Response(status=500,text="Webhook processing error")
        return web.Response(text="OK")
    app=web.Application(client_max_size=1024 * 1024);app.router.add_post("/cashfree/webhook",webhook)
    runner=web.AppRunner(app);await runner.setup();port=int(os.getenv("PORT","8080"));site=web.TCPSite(runner,"0.0.0.0",port);await site.start();log.info("Webhook listening on port %s",port);return runner

async def main():
    await init_db();await bot.set_my_commands([BotCommand(command="start",description="Open Shop Menu")]);runner=await run_webhook_server()
    try:await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await close_cashfree_session()
        await close_db()
        await bot.session.close()

if __name__=="__main__":asyncio.run(main())
