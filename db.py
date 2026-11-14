import os, secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, select, func, text, or_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.engine import make_url
from config import PUBLIC_BASE_URL

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Set it to your PostgreSQL connection string (AWS RDS is supported).")
url = make_url(DATABASE_URL)
if url.drivername in ("postgres", "postgresql"):
    url = url.set(drivername="postgresql+asyncpg")
query = dict(url.query)
query.pop("sslmode", None)
query.pop("channel_binding", None)
query.pop("ssl", None)
url = url.set(query=query)
# Keep the async PostgreSQL pool warm for Railway/AWS Singapore deployments.
# Values are environment-tunable so small RDS instances can keep a low connection cap.
def _positive_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))

_pool_size = _positive_int_env("DB_POOL_SIZE", 5, 1, 30)
_max_overflow = _positive_int_env("DB_MAX_OVERFLOW", 5, 0, 30)
_pool_timeout = _positive_int_env("DB_POOL_TIMEOUT", 8, 2, 60)
_pool_recycle = _positive_int_env("DB_POOL_RECYCLE", 1800, 300, 7200)
engine = create_async_engine(
    url,
    pool_pre_ping=True,
    pool_size=_pool_size,
    max_overflow=_max_overflow,
    pool_timeout=_pool_timeout,
    pool_recycle=_pool_recycle,
    pool_use_lifo=True,
    connect_args={"ssl": "require", "server_settings": {"application_name": "panel-army-bot"}},
)
Session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    wallet_balance: Mapped[float] = mapped_column(Numeric(12,2), default=0)
    is_reseller: Mapped[bool] = mapped_column(Boolean, default=False)
    phone: Mapped[str | None] = mapped_column(String(10))
    referred_by: Mapped[int | None] = mapped_column(BigInteger, index=True)
    referral_rewarded: Mapped[bool] = mapped_column(Boolean, default=False)

class ProductCategory(Base):
    __tablename__ = "product_categories"
    name: Mapped[str] = mapped_column(String(100), primary_key=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    price_inr: Mapped[float] = mapped_column(Numeric(10,2), default=0)  # legacy compatibility
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String(100), default="Other Products")
    maintenance: Mapped[bool] = mapped_column(Boolean, default=False)

class ProductPlan(Base):
    __tablename__ = "product_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    duration: Mapped[str] = mapped_column(String(80))
    price_inr: Mapped[float] = mapped_column(Numeric(10,2))
    price_usd: Mapped[float] = mapped_column(Numeric(10,2), default=0)
    reseller_price_inr: Mapped[float] = mapped_column(Numeric(10,2), default=0)
    reseller_price_usd: Mapped[float] = mapped_column(Numeric(10,2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class KeyStock(Base):
    __tablename__ = "key_stock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    key_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE", index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("product_plans.id"), index=True)

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(12,2))
    kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(255), default="")
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AdminLog(Base):
    __tablename__ = "admin_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Coupon(Base):
    __tablename__ = "coupons"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    discount_percent: Mapped[int] = mapped_column(Integer)
    usage_limit: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class RefundRecord(Base):
    __tablename__ = "refund_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="REQUESTED")
    note: Mapped[str] = mapped_column(Text, default="")
    admin_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class BotSetting(Base):
    __tablename__ = "bot_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")

class ReferralKeyStock(Base):
    __tablename__ = "referral_key_stock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reward_type: Mapped[str] = mapped_column(String(20), index=True)
    key_text: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE", index=True)
    claimed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    referred_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    reward_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    key_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    amount_inr: Mapped[float] = mapped_column(Numeric(10,2))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    key_text: Mapped[str | None] = mapped_column(Text)
    cashfree_payment_link: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("product_plans.id"), index=True)
    duration: Mapped[str] = mapped_column(String(80), default="1 Day")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    payment_method: Mapped[str] = mapped_column(String(20), default="CASHFREE")

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive migrations for databases created by the original starter. Existing data is preserved.
        migrations = [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_balance NUMERIC(12,2) NOT NULL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_reseller BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(10)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_rewarded BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(100) NOT NULL DEFAULT 'Other Products'",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS maintenance BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE key_stock ADD COLUMN IF NOT EXISTS plan_id INTEGER REFERENCES product_plans(id)",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS plan_id INTEGER REFERENCES product_plans(id)",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS duration VARCHAR(80) NOT NULL DEFAULT '1 Day'",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) NOT NULL DEFAULT 'CASHFREE'",
            "ALTER TABLE orders ALTER COLUMN product_id DROP NOT NULL",
            "CREATE INDEX IF NOT EXISTS ix_key_stock_plan_status_id ON key_stock (plan_id, status, id)",
            "CREATE INDEX IF NOT EXISTS ix_orders_user_created ON orders (user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_orders_status_created ON orders (status, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_products_active_category_id ON products (active, category, id)",
            "CREATE INDEX IF NOT EXISTS ix_product_plans_product_active_id ON product_plans (product_id, active, id)",
            "CREATE INDEX IF NOT EXISTS ix_wallet_transactions_user_created ON wallet_transactions (user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_admin_logs_created ON admin_logs (created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_referral_rewards_referrer_status ON referral_rewards (referrer_id, status)",
        ]
        for statement in migrations:
            await conn.execute(text(statement))

async def get_or_create_user(user_id, username, full_name):
    async with Session() as s:
        user = await s.get(User, user_id)
        created = user is None
        if not user:
            s.add(User(user_id=user_id, username=username, full_name=full_name))
        else:
            user.username, user.full_name = username, full_name
        await s.commit()
        return created

async def get_user(user_id):
    async with Session() as s:
        u = await s.get(User, user_id)
        return {"user_id":u.user_id,"username":u.username,"full_name":u.full_name,"created_at":u.created_at,"wallet_balance":float(u.wallet_balance or 0),"is_reseller":u.is_reseller,"is_banned":u.is_banned,"phone":u.phone} if u else None

async def is_user_banned(user_id):
    async with Session() as s:
        value = await s.scalar(select(User.is_banned).where(User.user_id == user_id))
        return bool(value) if value is not None else False

async def close_db():
    await engine.dispose()

async def set_user_phone(user_id, phone):
    async with Session() as s:
        u=await s.get(User,user_id)
        if u:
            u.phone=phone
            await s.commit()

async def list_categories():
    async with Session() as s:
        rows = (await s.execute(select(Product.category, func.count(Product.id)).where(Product.active == True).group_by(Product.category))).all()
        counts = {name: int(count) for name, count in rows}
        saved = (await s.scalars(select(ProductCategory.name).order_by(ProductCategory.name))).all()
        for name in saved:
            counts.setdefault(name, 0)
        return [{"name": name, "count": counts[name]} for name in sorted(counts)]

async def create_category_admin(name):
    name=(name or "").strip()
    if not name or len(name)>100: return False
    async with Session() as s:
        exists=await s.get(ProductCategory,name)
        product_exists=await s.scalar(select(func.count(Product.id)).where(Product.category==name))
        if exists or product_exists: return False
        s.add(ProductCategory(name=name))
        await s.commit()
        return True

async def list_products(category=None, include_empty=False):
    """Load the catalogue in a bounded number of queries (avoid per-plan N+1 counts)."""
    async with Session() as s:
        product_stmt = select(Product).where(Product.active == True).order_by(Product.id)
        if category:
            # Match category names robustly if older rows contain accidental
            # whitespace/case differences from previous admin versions.
            product_stmt = product_stmt.where(func.lower(func.trim(Product.category)) == str(category).strip().lower())
        products = (await s.scalars(product_stmt)).all()
        if not products:
            return []
        product_ids = [p.id for p in products]
        plans = (await s.scalars(
            select(ProductPlan).where(
                ProductPlan.product_id.in_(product_ids), ProductPlan.active == True
            ).order_by(ProductPlan.id)
        )).all()
        plan_ids = [pl.id for pl in plans]
        stock_counts = {}
        # Customer catalogue never displays stock, so skip the stock-count query there.
        # Admin inventory views request include_empty=True and still receive exact counts.
        if plan_ids and include_empty:
            rows = (await s.execute(
                select(KeyStock.plan_id, func.count(KeyStock.id))
                .where(KeyStock.plan_id.in_(plan_ids), KeyStock.status == "AVAILABLE")
                .group_by(KeyStock.plan_id)
            )).all()
            stock_counts = {int(pid): int(count) for pid, count in rows}
        plans_by_product = {}
        for pl in plans:
            plans_by_product.setdefault(pl.product_id, []).append({
                "id": pl.id, "duration": pl.duration,
                "price_inr": float(pl.price_inr), "price_usd": float(pl.price_usd),
                "reseller_price_inr": float(pl.reseller_price_inr),
                "reseller_price_usd": float(pl.reseller_price_usd),
                "stock": stock_counts.get(pl.id, 0),
            })
        output = []
        for p in products:
            product_plans = plans_by_product.get(p.id, [])
            stock_count = sum(pl["stock"] for pl in product_plans)
            if include_empty or stock_count > 0 or product_plans:
                output.append({
                    "id": p.id, "name": p.name, "description": p.description,
                    "category": p.category, "maintenance": bool(p.maintenance), "stock": stock_count, "plans": product_plans,
                })
        return output

async def get_product(product_id):
    """Fetch a customer-facing product and its plans in one round trip.

    Stock is deliberately not queried here: the shop does not reveal availability,
    and inventory is checked atomically only after successful payment.
    """
    async with Session() as s:
        rows = (await s.execute(
            select(Product, ProductPlan)
            .outerjoin(ProductPlan, (ProductPlan.product_id == Product.id) & (ProductPlan.active == True))
            .where(Product.id == product_id, Product.active == True)
            .order_by(ProductPlan.id)
        )).all()
        if not rows:
            return None
        product = rows[0][0]
        plans = [{
            "id": pl.id, "duration": pl.duration,
            "price_inr": float(pl.price_inr), "price_usd": float(pl.price_usd),
            "reseller_price_inr": float(pl.reseller_price_inr),
            "reseller_price_usd": float(pl.reseller_price_usd),
            "stock": 0,
        } for _, pl in rows if pl is not None]
        return {
            "id": product.id, "name": product.name, "description": product.description,
            "category": product.category, "maintenance": bool(product.maintenance), "plans": plans,
        }

async def get_plan(plan_id):
    async with Session() as s:
        stock_count = select(func.count(KeyStock.id)).where(
            KeyStock.plan_id == ProductPlan.id, KeyStock.status == "AVAILABLE"
        ).correlate(ProductPlan).scalar_subquery()
        row = (await s.execute(
            select(ProductPlan, Product, stock_count.label("stock"))
            .join(Product, Product.id == ProductPlan.product_id)
            .where(ProductPlan.id == plan_id, ProductPlan.active == True, Product.active == True)
        )).first()
        if not row:
            return None
        pl, p, stock = row
        return {
            "id": pl.id, "product_id": pl.product_id, "product_name": p.name,
            "category": p.category, "description": p.description, "maintenance": bool(p.maintenance),
            "duration": pl.duration, "price_inr": float(pl.price_inr),
            "price_usd": float(pl.price_usd),
            "reseller_price_inr": float(pl.reseller_price_inr),
            "reseller_price_usd": float(pl.reseller_price_usd), "stock": int(stock or 0),
        }

async def create_order(user_id, plan_id, amount, quantity=1, payment_method="CASHFREE"):
    pl=await get_plan(plan_id)
    if not pl or quantity < 1 or quantity > 100: raise ValueError("Invalid plan or quantity (maximum 100)")
    amount = round(float(amount), 2)
    if amount <= 0 or amount > 500000: raise ValueError("Invalid order amount")
    order_id="PA-"+secrets.token_hex(8).upper()
    async with Session() as s:
        s.add(Order(order_id=order_id,user_id=user_id,product_id=pl["product_id"],plan_id=plan_id,duration=pl["duration"],quantity=quantity,amount_inr=amount,status="PENDING",payment_method=payment_method))
        await s.commit()
    return {"order_id":order_id}

async def get_order(order_id):
    async with Session() as s:
        o=await s.get(Order,order_id)
        return {"order_id":o.order_id,"user_id":o.user_id,"product_id":o.product_id,"plan_id":o.plan_id,"duration":o.duration,"quantity":o.quantity,"amount_inr":float(o.amount_inr),"status":o.status,"payment_method":o.payment_method,"created_at":o.created_at} if o else None

async def expire_order(order_id):
    async with Session() as s:
        async with s.begin():
            o=await s.scalar(select(Order).where(Order.order_id==order_id).with_for_update())
            if o and o.status=="PENDING":o.status="EXPIRED"

async def set_payment_link(order_id, url):
    async with Session() as s:
        o=await s.get(Order,order_id)
        if o:o.cashfree_payment_link=url;await s.commit()

async def pay_wallet(user_id, plan_id, quantity=1):
    pl=await get_plan(plan_id)
    user=await get_user(user_id)
    if not pl or quantity < 1 or quantity > 100: raise ValueError("Invalid plan or quantity (maximum 100)")
    if pl.get("maintenance"): raise ValueError(f"{pl['product_name']} is under maintenance")
    price=pl["reseller_price_inr"] if user and user["is_reseller"] else pl["price_inr"]
    amount=round(price*quantity,2)
    order_id="PA-"+secrets.token_hex(8).upper()
    async with Session() as s:
        async with s.begin():
            u=await s.scalar(select(User).where(User.user_id==user_id).with_for_update())
            if not u or float(u.wallet_balance or 0)<amount: raise ValueError("Insufficient wallet balance")
            o=Order(order_id=order_id,user_id=user_id,product_id=pl["product_id"],plan_id=plan_id,duration=pl["duration"],quantity=quantity,amount_inr=amount,status="PENDING",payment_method="WALLET")
            s.add(o)
            u.wallet_balance=float(u.wallet_balance or 0)-amount
            s.add(WalletTransaction(user_id=user_id,amount=amount,kind="DEBIT",note=f"Purchase {order_id}",admin_id=None))
            await s.flush()
            result=await _fulfill_locked(s,o)
            if not result or not result.get("key_text"):
                o.status="PAID_NO_STOCK"
                o.paid_at=datetime.now(timezone.utc)
                no_stock=True
            else:
                no_stock=False
    return {"order_id":order_id,"amount_inr":amount,"key_text":result.get("key_text") if result else None,"product_name":pl["product_name"],"duration":pl["duration"],"quantity":quantity,"no_stock":no_stock}

async def _fulfill_locked(s,o):
    keys=(await s.scalars(select(KeyStock).where(KeyStock.plan_id==o.plan_id,KeyStock.status=="AVAILABLE").order_by(KeyStock.id).with_for_update(skip_locked=True).limit(o.quantity))).all()
    if len(keys)<o.quantity:return None
    for k in keys:k.status="SOLD";k.order_id=o.order_id
    o.status="PAID";o.key_text="\n".join(k.key_text for k in keys);o.paid_at=datetime.now(timezone.utc)
    return {"key_text":o.key_text,"user_id":o.user_id}

async def fulfill_paid_order(order_id):
    async with Session() as s:
        async with s.begin():
            order=await s.scalar(select(Order).where(Order.order_id==order_id).with_for_update())
            if not order:return None
            # Idempotency: never return a previously delivered key on a repeated
            # Cashfree webhook / status check. Concurrent duplicate callbacks can
            # both read PENDING before this row lock; the second must not resend.
            if order.status=="PAID":return {"key_text":None,"user_id":order.user_id,"already_paid":True}
            if order.status not in ("PENDING","EXPIRED"):return None
            result=await _fulfill_locked(s,order)
            if not result:
                order.status="PAID_NO_STOCK";order.paid_at=datetime.now(timezone.utc)
                return {"key_text":None,"user_id":order.user_id}
            return result


async def credit_wallet_for_no_stock(order_id):
    """Credit a successful Cashfree payment to the buyer's wallet exactly once."""
    async with Session() as s:
        async with s.begin():
            order=await s.scalar(select(Order).where(Order.order_id==order_id).with_for_update())
            if not order:
                return None
            if order.status=="REFUNDED":
                return {"credited":False,"user_id":order.user_id,"amount":float(order.amount_inr)}
            if order.status!="PAID_NO_STOCK":
                return {"credited":False,"user_id":order.user_id,"amount":float(order.amount_inr)}
            user=await s.scalar(select(User).where(User.user_id==order.user_id).with_for_update())
            if not user:
                raise ValueError(f"Cannot refund order {order_id}: user does not exist")
            amount=round(float(order.amount_inr),2)
            user.wallet_balance=round(float(user.wallet_balance or 0)+amount,2)
            s.add(WalletTransaction(user_id=order.user_id,amount=amount,kind="CREDIT",
                                    note=f"Automatic no-stock refund {order_id}",admin_id=None))
            order.status="REFUNDED"
            return {"credited":True,"user_id":order.user_id,"amount":amount}

async def add_referral_stock(reward_type, keys):
    reward_type=(reward_type or "").strip().upper()
    if reward_type not in ("ROOT", "NON_ROOT"): return 0
    async with Session() as s:
        existing=set((await s.scalars(select(ReferralKeyStock.key_text))).all())
        new_keys=[k for k in dict.fromkeys(keys) if k not in existing]
        s.add_all([ReferralKeyStock(reward_type=reward_type,key_text=k,status="AVAILABLE") for k in new_keys])
        await s.commit();return len(new_keys)

async def attach_referrer(user_id, referrer_id):
    if not referrer_id or int(referrer_id)==int(user_id): return False
    async with Session() as s:
        async with s.begin():
            u=await s.scalar(select(User).where(User.user_id==user_id).with_for_update())
            r=await s.get(User,int(referrer_id))
            if not u or not r or u.referred_by or u.referral_rewarded: return False
            # Only attach on first registration, before any paid order.
            prior=int(await s.scalar(select(func.count(Order.order_id)).where(Order.user_id==user_id,Order.status=="PAID")) or 0)
            if prior: return False
            u.referred_by=int(referrer_id)
            return True

async def award_referral_after_purchase(referred_user_id):
    """Create one pending reward for a referrer after their invitee's first paid purchase."""
    async with Session() as s:
        async with s.begin():
            u=await s.scalar(select(User).where(User.user_id==referred_user_id).with_for_update())
            if not u or not u.referred_by or u.referral_rewarded: return None
            # The caller invokes this only after a key was successfully delivered.
            u.referral_rewarded=True
            reward=ReferralReward(referrer_id=u.referred_by,referred_user_id=referred_user_id,status="PENDING")
            s.add(reward);await s.flush()
            return {"referrer_id":u.referred_by,"reward_id":reward.id}

async def referral_stats(user_id):
    async with Session() as s:
        total=int(await s.scalar(select(func.count(User.user_id)).where(User.referred_by==user_id)) or 0)
        active=int(await s.scalar(select(func.count(User.user_id)).where(User.referred_by==user_id,User.referral_rewarded==True)) or 0)
        trials=int(await s.scalar(select(func.count(ReferralReward.id)).where(ReferralReward.referrer_id==user_id,ReferralReward.status=="CLAIMED")) or 0)
        pending=int(await s.scalar(select(func.count(ReferralReward.id)).where(ReferralReward.referrer_id==user_id,ReferralReward.status=="PENDING")) or 0)
        return {"total":total,"active":active,"trials":trials,"pending":pending}

async def claim_referral_reward(user_id, reward_type):
    reward_type=(reward_type or "").strip().upper()
    if reward_type not in ("ROOT","NON_ROOT"): return None
    async with Session() as s:
        async with s.begin():
            reward=await s.scalar(select(ReferralReward).where(ReferralReward.referrer_id==user_id,ReferralReward.status=="PENDING").order_by(ReferralReward.id).with_for_update(skip_locked=True).limit(1))
            if not reward: return {"error":"NO_REWARD"}
            key=await s.scalar(select(ReferralKeyStock).where(ReferralKeyStock.reward_type==reward_type,ReferralKeyStock.status=="AVAILABLE").order_by(func.random()).with_for_update(skip_locked=True).limit(1))
            if not key: return {"error":"NO_STOCK"}
            key.status="CLAIMED";key.claimed_by=user_id
            reward.reward_type=reward_type;reward.key_text=key.key_text;reward.status="CLAIMED";reward.claimed_at=datetime.now(timezone.utc)
            return {"key_text":key.key_text,"reward_type":reward_type,"reward_id":reward.id}

async def add_product(name, price, description, category="Other Products"):
    # Normalize and persist category explicitly so newly created products are
    # immediately visible in the customer catalogue and admin category list.
    name=(name or "").strip()
    category=(category or "Other Products").strip()
    if not name or len(name)>160 or not category or len(category)>100:
        raise ValueError("Invalid product name or category")
    async with Session() as s:
        async with s.begin():
            cat=await s.get(ProductCategory, category)
            if not cat:
                s.add(ProductCategory(name=category))
            p=Product(name=name,price_inr=price,description=description or "",category=category,active=True,maintenance=False)
            s.add(p)
            await s.flush()
            result={"id":p.id,"name":p.name,"category":p.category,"active":bool(p.active)}
        return result

async def add_plan(product_id,duration,price_inr,price_usd,reseller_price_inr,reseller_price_usd):
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p:return None
        prior=await s.scalar(select(func.count(ProductPlan.id)).where(ProductPlan.product_id==product_id))
        pl=ProductPlan(product_id=product_id,duration=duration,price_inr=price_inr,price_usd=price_usd,reseller_price_inr=reseller_price_inr,reseller_price_usd=reseller_price_usd)
        s.add(pl);await s.flush()
        # Preserve stock entered against legacy products before plans existed.
        if not prior:
            await s.execute(text("UPDATE key_stock SET plan_id=:plan WHERE product_id=:product AND plan_id IS NULL"),{"plan":pl.id,"product":product_id})
        await s.commit();await s.refresh(pl)
        return {"id":pl.id,"duration":pl.duration}

async def add_stock(plan_id, keys):
    async with Session() as s:
        pl=await s.get(ProductPlan,plan_id)
        if not pl:return 0
        existing=set((await s.scalars(select(KeyStock.key_text).where(KeyStock.plan_id==plan_id))).all())
        new_keys=[k for k in dict.fromkeys(keys) if k not in existing]
        s.add_all([KeyStock(product_id=pl.product_id,plan_id=plan_id,key_text=k,status="AVAILABLE") for k in new_keys])
        await s.commit();return len(new_keys)

async def list_orders(user_id):
    async with Session() as s:
        stmt=(select(Order, Product.name).outerjoin(Product, Product.id==Order.product_id).where(Order.user_id==user_id, Order.payment_method!="TOPUP").order_by(Order.created_at.desc()).limit(30))
        rows=(await s.execute(stmt)).all()
        return [{"order_id":o.order_id,"user_id":o.user_id,"product_name":name or "Wallet Balance Top-up","amount_inr":float(o.amount_inr),"status":o.status,"duration":o.duration,"quantity":o.quantity,"key_text":o.key_text,"created_at":o.created_at,"payment_method":o.payment_method} for o,name in rows]

async def create_topup_order(user_id, amount):
    amount = round(float(amount), 2)
    if amount < 10 or amount > 50000:
        raise ValueError("Top-up amount must be between ₹10 and ₹50,000")
    order_id="PA-TOPUP-"+secrets.token_hex(7).upper()
    async with Session() as s:
        s.add(Order(order_id=order_id,user_id=user_id,product_id=None,plan_id=None,duration="Wallet Balance",quantity=1,amount_inr=round(float(amount),2),status="PENDING",payment_method="TOPUP"))
        await s.commit()
    return {"order_id":order_id}

async def fulfill_wallet_topup(order_id):
    async with Session() as s:
        async with s.begin():
            o=await s.scalar(select(Order).where(Order.order_id==order_id).with_for_update())
            if not o or o.payment_method!="TOPUP": return None
            if o.status=="PAID": return {"credited":False,"user_id":o.user_id,"amount":float(o.amount_inr)}
            if o.status not in ("PENDING","EXPIRED"): return None
            u=await s.scalar(select(User).where(User.user_id==o.user_id).with_for_update())
            if not u:return None
            u.wallet_balance=float(u.wallet_balance or 0)+float(o.amount_inr)
            o.status="PAID";o.paid_at=datetime.now(timezone.utc)
            s.add(WalletTransaction(user_id=o.user_id,amount=o.amount_inr,kind="CREDIT",note=f"Cashfree wallet top-up {order_id}",admin_id=None))
            return {"credited":True,"user_id":o.user_id,"amount":float(o.amount_inr)}

async def user_order_stats(user_id):
    async with Session() as s:
        count=int(await s.scalar(select(func.count(Order.order_id)).where(Order.user_id==user_id,Order.status=="PAID",Order.payment_method!="TOPUP")) or 0)
        spent=float(await s.scalar(select(func.coalesce(func.sum(Order.amount_inr),0)).where(Order.user_id==user_id,Order.status=="PAID",Order.payment_method!="TOPUP")) or 0)
        return {"orders":count,"spent":spent}

async def set_reseller(user_id, enabled=True):
    async with Session() as s:
        u=await s.get(User,user_id)
        if u:u.is_reseller=enabled;await s.commit()

async def credit_wallet(user_id, amount):
    async with Session() as s:
        async with s.begin():
            u=await s.scalar(select(User).where(User.user_id==user_id).with_for_update())
            if not u:return None
            u.wallet_balance=float(u.wallet_balance or 0)+float(amount)
            return float(u.wallet_balance)


async def admin_log(admin_id, action, details=""):
    async with Session() as s:
        s.add(AdminLog(admin_id=admin_id, action=action[:80], details=str(details)[:4000])); await s.commit()

async def dashboard_stats():
    async with Session() as s:
        users=int(await s.scalar(select(func.count(User.user_id))) or 0)
        orders=int(await s.scalar(select(func.count(Order.order_id))) or 0)
        paid=int(await s.scalar(select(func.count(Order.order_id)).where(Order.status=="PAID", Order.payment_method!="TOPUP")) or 0)
        revenue=float(await s.scalar(select(func.coalesce(func.sum(Order.amount_inr),0)).where(Order.status=="PAID", Order.payment_method!="TOPUP")) or 0)
        stock=int(await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.status=="AVAILABLE")) or 0)
        india_tz=timezone(timedelta(hours=5, minutes=30)); now=datetime.now(india_tz); today_start=now.replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc)
        today_revenue=float(await s.scalar(select(func.coalesce(func.sum(Order.amount_inr),0)).where(Order.status=="PAID", Order.payment_method!="TOPUP", Order.paid_at >= today_start)) or 0)
        return {"users":users,"orders":orders,"paid":paid,"revenue":revenue,"today_revenue":today_revenue,"stock":stock}

async def search_users(term, limit=15):
    async with Session() as s:
        stmt=select(User).order_by(User.created_at.desc()).limit(limit)
        if term:
            t=f"%{term}%"
            if term.isdigit(): stmt=stmt.where(or_(User.user_id==int(term), User.username.ilike(t), User.full_name.ilike(t)))
            else: stmt=stmt.where(or_(User.username.ilike(t), User.full_name.ilike(t)))
        rows=(await s.scalars(stmt)).all()
        return [{"user_id":u.user_id,"username":u.username,"full_name":u.full_name,"wallet_balance":float(u.wallet_balance or 0),"is_banned":u.is_banned,"is_reseller":u.is_reseller,"created_at":u.created_at} for u in rows]

async def admin_user(user_id):
    async with Session() as s:
        u=await s.get(User,user_id)
        if not u:return None
        count=int(await s.scalar(select(func.count(Order.order_id)).where(Order.user_id==user_id)) or 0)
        spent=float(await s.scalar(select(func.coalesce(func.sum(Order.amount_inr),0)).where(Order.user_id==user_id,Order.status=="PAID")) or 0)
        return {"user_id":u.user_id,"username":u.username,"full_name":u.full_name,"wallet_balance":float(u.wallet_balance or 0),"is_banned":u.is_banned,"is_reseller":u.is_reseller,"orders":count,"spent":spent,"created_at":u.created_at}

async def set_banned(user_id, enabled):
    async with Session() as s:
        u=await s.get(User,user_id)
        if not u:return False
        u.is_banned=bool(enabled);await s.commit();return True

async def adjust_wallet(user_id, amount, admin_id, note="Admin adjustment"):
    async with Session() as s:
        async with s.begin():
            u=await s.scalar(select(User).where(User.user_id==user_id).with_for_update())
            if not u:return None
            new=round(float(u.wallet_balance or 0)+float(amount),2)
            if new<0:raise ValueError("Wallet balance cannot become negative")
            u.wallet_balance=new
            s.add(WalletTransaction(user_id=user_id,amount=abs(amount),kind="CREDIT" if amount>=0 else "DEBIT",note=note,admin_id=admin_id))
            return new

async def wallet_history(user_id, limit=10):
    async with Session() as s:
        rows=(await s.scalars(select(WalletTransaction).where(WalletTransaction.user_id==user_id).order_by(WalletTransaction.created_at.desc()).limit(limit))).all()
        return [{"amount":float(x.amount),"kind":x.kind,"note":x.note,"created_at":x.created_at} for x in rows]

async def admin_orders(limit=20):
    async with Session() as s:
        rows=(await s.scalars(select(Order).order_by(Order.created_at.desc()).limit(limit))).all()
        return [{"order_id":o.order_id,"user_id":o.user_id,"amount_inr":float(o.amount_inr),"status":o.status,"payment_method":o.payment_method,"created_at":o.created_at} for o in rows]

async def admin_stock_summary():
    async with Session() as s:
        rows=(await s.execute(select(KeyStock.plan_id,KeyStock.status,func.count(KeyStock.id)).group_by(KeyStock.plan_id,KeyStock.status))).all()
        return [{"plan_id":pid,"status":status,"count":int(count)} for pid,status,count in rows]

async def set_reseller_pricing(plan_id, inr, usd):
    async with Session() as s:
        pl=await s.get(ProductPlan,plan_id)
        if not pl:return False
        pl.reseller_price_inr=inr;pl.reseller_price_usd=usd;await s.commit();return True

async def edit_product(product_id, name=None, category=None, description=None):
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p:return False
        if name is not None:p.name=name
        if category is not None:p.category=category
        if description is not None:p.description=description
        await s.commit();return True

async def set_product_maintenance(product_id, enabled):
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p:return False
        p.maintenance=bool(enabled);await s.commit();return True

async def deactivate_product(product_id):
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p:return False
        p.active=False
        await s.execute(text("UPDATE product_plans SET active=FALSE WHERE product_id=:pid"),{"pid":product_id})
        await s.commit();return True

async def create_coupon(code, discount_percent, usage_limit):
    code=str(code).upper().strip()
    discount_percent=int(discount_percent); usage_limit=int(usage_limit)
    if not code or len(code)>40 or not code.replace("-","").replace("_","").isalnum() or not 1<=discount_percent<=100 or usage_limit<0:return False
    async with Session() as s:
        if await s.get(Coupon,code):return False
        s.add(Coupon(code=code,discount_percent=discount_percent,usage_limit=usage_limit));await s.commit();return True

async def get_bot_settings():
    async with Session() as s:
        rows=(await s.scalars(select(BotSetting))).all();return {x.key:x.value for x in rows}

async def set_bot_setting(key,value):
    async with Session() as s:
        row=await s.get(BotSetting,key)
        if row:row.value=str(value)
        else:s.add(BotSetting(key=key,value=str(value)))
        await s.commit()

async def recent_admin_logs(limit=20):
    async with Session() as s:
        rows=(await s.scalars(select(AdminLog).order_by(AdminLog.created_at.desc()).limit(limit))).all()
        return [{"admin_id":x.admin_id,"action":x.action,"details":x.details,"created_at":x.created_at} for x in rows]

async def broadcast_user_ids(resellers=False):
    async with Session() as s:
        stmt=select(User.user_id).where(User.is_banned==False)
        if resellers:stmt=stmt.where(User.is_reseller==True)
        return list((await s.scalars(stmt)).all())

async def set_key_status(key_id, status):
    if status not in {"AVAILABLE","SOLD","EXPIRED"}:return False
    async with Session() as s:
        key=await s.get(KeyStock,key_id)
        if not key:return False
        key.status=status
        if status=="AVAILABLE":key.order_id=None
        await s.commit();return True


async def record_refund(order_id, status, note, admin_id):
    allowed={"REQUESTED","PROCESSING","REFUNDED","REJECTED"}
    status=status.upper()
    if status not in allowed:return False
    async with Session() as s:
        if not await s.get(Order,order_id):return False
        s.add(RefundRecord(order_id=order_id,status=status,note=note,admin_id=admin_id));await s.commit();return True

async def refund_history(limit=20):
    async with Session() as s:
        rows=(await s.scalars(select(RefundRecord).order_by(RefundRecord.created_at.desc()).limit(limit))).all()
        return [{"order_id":r.order_id,"status":r.status,"note":r.note,"admin_id":r.admin_id,"created_at":r.created_at} for r in rows]

async def list_keys(plan_id, status=None, limit=50):
    async with Session() as s:
        stmt=select(KeyStock).where(KeyStock.plan_id==plan_id).order_by(KeyStock.id.desc()).limit(limit)
        if status:stmt=stmt.where(KeyStock.status==status.upper())
        rows=(await s.scalars(stmt)).all()
        return [{"id":k.id,"status":k.status,"created_at":k.created_at,"order_id":k.order_id} for k in rows]

# Button-driven catalogue administration
async def admin_all_products():
    async with Session() as s:
        rows=(await s.scalars(select(Product).where(Product.active == True).order_by(Product.category,Product.id))).all()
        return [{"id":p.id,"name":p.name,"category":p.category,"active":p.active,"maintenance":bool(p.maintenance)} for p in rows]

async def admin_all_plans(product_id):
    async with Session() as s:
        rows=(await s.scalars(select(ProductPlan).where(ProductPlan.product_id==product_id).order_by(ProductPlan.id))).all()
        return [{"id":p.id,"duration":p.duration,"price_inr":float(p.price_inr),"reseller_price_inr":float(p.reseller_price_inr),"active":p.active} for p in rows]

async def edit_plan_admin(plan_id, duration=None, price_inr=None, reseller_price_inr=None):
    async with Session() as s:
        p=await s.get(ProductPlan,plan_id)
        if not p:return False
        if duration is not None:p.duration=duration
        if price_inr is not None:p.price_inr=price_inr
        if reseller_price_inr is not None:p.reseller_price_inr=reseller_price_inr
        await s.commit();return True

async def deactivate_plan_admin(plan_id):
    async with Session() as s:
        p=await s.get(ProductPlan,plan_id)
        if not p:return False
        p.active=False;await s.commit();return True

async def rename_category_admin(old_name,new_name):
    new_name=(new_name or "").strip()
    if not new_name or len(new_name)>100:return False
    async with Session() as s:
        rows=(await s.scalars(select(Product).where(Product.category==old_name))).all()
        category=await s.get(ProductCategory,old_name)
        if not rows and not category:return False
        if new_name != old_name:
            collision=await s.get(ProductCategory,new_name)
            product_collision=await s.scalar(select(func.count(Product.id)).where(Product.category==new_name))
            if collision or product_collision:return False
        for product in rows: product.category=new_name
        if category:
            await s.delete(category)
        s.add(ProductCategory(name=new_name))
        await s.commit();return True

async def category_products_admin(name):
    async with Session() as s:
        return int(await s.scalar(select(func.count(Product.id)).where(Product.category==name)) or 0)


async def list_resellers(limit=50):
    async with Session() as s:
        rows=(await s.scalars(select(User).where(User.is_reseller==True).order_by(User.created_at.desc()).limit(limit))).all()
        return [{"user_id":u.user_id,"username":u.username,"full_name":u.full_name,"wallet_balance":float(u.wallet_balance or 0)} for u in rows]

async def list_coupons(limit=50):
    async with Session() as s:
        rows=(await s.scalars(select(Coupon).order_by(Coupon.created_at.desc()).limit(limit))).all()
        return [{"code":c.code,"discount_percent":c.discount_percent,"usage_limit":c.usage_limit,"used_count":c.used_count,"active":c.active} for c in rows]

async def update_coupon(code, active=None, discount_percent=None, usage_limit=None):
    async with Session() as s:
        c=await s.get(Coupon,code.upper().strip())
        if not c:return False
        if active is not None:c.active=bool(active)
        if discount_percent is not None:c.discount_percent=int(discount_percent)
        if usage_limit is not None:c.usage_limit=int(usage_limit)
        await s.commit();return True

async def delete_coupon(code):
    async with Session() as s:
        c=await s.get(Coupon,code.upper().strip())
        if not c:return False
        await s.delete(c);await s.commit();return True

async def delete_category_admin(name):
    async with Session() as s:
        result=await s.execute(select(Product).where(Product.category==name))
        rows=result.scalars().all()
        for product in rows: product.category="Other Products"
        category=await s.get(ProductCategory,name)
        if category: await s.delete(category)
        await s.commit();return len(rows) + (1 if category else 0)


async def delete_product_admin(product_id):
    """Hard-delete only products with no historical orders or key records; otherwise archive safely."""
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p:return "NOT_FOUND"
        order_count=int(await s.scalar(select(func.count(Order.order_id)).where(Order.product_id==product_id)) or 0)
        key_count=int(await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.product_id==product_id)) or 0)
        if order_count or key_count:
            p.active=False
            await s.execute(text("UPDATE product_plans SET active=FALSE WHERE product_id=:pid"),{"pid":product_id})
            await s.commit();return "ARCHIVED"
        await s.execute(text("DELETE FROM product_plans WHERE product_id=:pid"),{"pid":product_id})
        await s.delete(p);await s.commit();return "DELETED"
