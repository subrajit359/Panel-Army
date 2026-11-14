import os, secrets
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, select, func, text, or_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.engine import make_url
from config import PUBLIC_BASE_URL

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Set it to your Neon PostgreSQL connection string.")
url = make_url(DATABASE_URL)
if url.drivername in ("postgres", "postgresql"):
    url = url.set(drivername="postgresql+asyncpg")
query = dict(url.query)
query.pop("sslmode", None)
query.pop("channel_binding", None)
query.pop("ssl", None)
url = url.set(query=query)
engine = create_async_engine(url, pool_pre_ping=True, connect_args={"ssl": "require"})
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

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    price_inr: Mapped[float] = mapped_column(Numeric(10,2), default=0)  # legacy compatibility
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String(100), default="Other Products")

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

class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
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
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS category VARCHAR(100) NOT NULL DEFAULT 'Other Products'",
            "ALTER TABLE key_stock ADD COLUMN IF NOT EXISTS plan_id INTEGER REFERENCES product_plans(id)",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS plan_id INTEGER REFERENCES product_plans(id)",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS duration VARCHAR(80) NOT NULL DEFAULT '1 Day'",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quantity INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) NOT NULL DEFAULT 'CASHFREE'",
        ]
        for statement in migrations:
            await conn.execute(text(statement))

async def get_or_create_user(user_id, username, full_name):
    async with Session() as s:
        user = await s.get(User, user_id)
        if not user:
            s.add(User(user_id=user_id, username=username, full_name=full_name))
        else:
            user.username, user.full_name = username, full_name
        await s.commit()

async def get_user(user_id):
    async with Session() as s:
        u = await s.get(User, user_id)
        return {"user_id":u.user_id,"wallet_balance":float(u.wallet_balance or 0),"is_reseller":u.is_reseller,"is_banned":u.is_banned} if u else None

async def list_categories():
    async with Session() as s:
        rows = (await s.execute(select(Product.category, func.count(Product.id)).where(Product.active == True).group_by(Product.category).order_by(Product.category))).all()
        return [{"name":name,"count":int(count)} for name,count in rows]

async def list_products(category=None, include_empty=False):
    async with Session() as s:
        stmt = select(Product).where(Product.active == True).order_by(Product.id)
        if category: stmt = stmt.where(Product.category == category)
        products = (await s.scalars(stmt)).all()
        output=[]
        for p in products:
            plans=(await s.scalars(select(ProductPlan).where(ProductPlan.product_id==p.id, ProductPlan.active==True).order_by(ProductPlan.id))).all()
            stock_count=0
            for plan in plans:
                count=await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.plan_id==plan.id,KeyStock.status=="AVAILABLE"))
                stock_count += int(count or 0)
            if include_empty or stock_count>0 or plans:
                output.append({"id":p.id,"name":p.name,"description":p.description,"category":p.category,"stock":stock_count,"plans":[{"id":pl.id,"duration":pl.duration,"price_inr":float(pl.price_inr),"price_usd":float(pl.price_usd),"reseller_price_inr":float(pl.reseller_price_inr),"reseller_price_usd":float(pl.reseller_price_usd),"stock":int(await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.plan_id==pl.id,KeyStock.status=="AVAILABLE")) or 0)} for pl in plans]})
        return output

async def get_product(product_id):
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p or not p.active:return None
        plans=(await s.scalars(select(ProductPlan).where(ProductPlan.product_id==p.id,ProductPlan.active==True).order_by(ProductPlan.id))).all()
        return {"id":p.id,"name":p.name,"description":p.description,"category":p.category,"plans":[{"id":pl.id,"duration":pl.duration,"price_inr":float(pl.price_inr),"price_usd":float(pl.price_usd),"reseller_price_inr":float(pl.reseller_price_inr),"reseller_price_usd":float(pl.reseller_price_usd),"stock":int(await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.plan_id==pl.id,KeyStock.status=="AVAILABLE")) or 0)} for pl in plans]}

async def get_plan(plan_id):
    async with Session() as s:
        pl=await s.get(ProductPlan,plan_id)
        if not pl or not pl.active:return None
        p=await s.get(Product,pl.product_id)
        stock=int(await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.plan_id==pl.id,KeyStock.status=="AVAILABLE")) or 0)
        return {"id":pl.id,"product_id":pl.product_id,"product_name":p.name,"category":p.category,"description":p.description,"duration":pl.duration,"price_inr":float(pl.price_inr),"price_usd":float(pl.price_usd),"reseller_price_inr":float(pl.reseller_price_inr),"reseller_price_usd":float(pl.reseller_price_usd),"stock":stock}

async def create_order(user_id, plan_id, amount, quantity=1, payment_method="CASHFREE"):
    pl=await get_plan(plan_id)
    if not pl or pl["stock"]<quantity: raise ValueError("Insufficient stock")
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
    if not pl or pl["stock"]<quantity: raise ValueError("Insufficient stock")
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
                u.wallet_balance=float(u.wallet_balance or 0)+amount
                o.status="FAILED"
                raise ValueError("Stock changed; wallet charge rolled back")
    return {"order_id":order_id,"amount_inr":amount,"key_text":result["key_text"],"product_name":pl["product_name"],"duration":pl["duration"],"quantity":quantity}

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
            if order.status=="PAID":return {"key_text":order.key_text,"user_id":order.user_id}
            if order.status not in ("PENDING","EXPIRED"):return None
            result=await _fulfill_locked(s,order)
            if not result:
                order.status="PAID_NO_STOCK";order.paid_at=datetime.now(timezone.utc)
                return {"key_text":None,"user_id":order.user_id}
            return result

async def add_product(name, price, description, category="Other Products"):
    async with Session() as s:
        p=Product(name=name,price_inr=price,description=description,category=category)
        s.add(p);await s.commit();await s.refresh(p)
        return {"id":p.id,"name":p.name}

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
        stmt=select(Order).order_by(Order.created_at.desc()).limit(30)
        if user_id is not None:stmt=stmt.where(Order.user_id==user_id)
        rows=(await s.scalars(stmt)).all()
        return [{"order_id":o.order_id,"user_id":o.user_id,"amount_inr":float(o.amount_inr),"status":o.status,"duration":o.duration,"quantity":o.quantity} for o in rows]

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
        paid=int(await s.scalar(select(func.count(Order.order_id)).where(Order.status.in_(["PAID","PAID_NO_STOCK"]))) or 0)
        revenue=float(await s.scalar(select(func.coalesce(func.sum(Order.amount_inr),0)).where(Order.status.in_(["PAID","PAID_NO_STOCK"]))) or 0)
        stock=int(await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.status=="AVAILABLE")) or 0)
        return {"users":users,"orders":orders,"paid":paid,"revenue":revenue,"stock":stock}

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
        spent=float(await s.scalar(select(func.coalesce(func.sum(Order.amount_inr),0)).where(Order.user_id==user_id,Order.status.in_(["PAID","PAID_NO_STOCK"]))) or 0)
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

async def deactivate_product(product_id):
    async with Session() as s:
        p=await s.get(Product,product_id)
        if not p:return False
        p.active=False
        await s.execute(text("UPDATE product_plans SET active=FALSE WHERE product_id=:pid"),{"pid":product_id})
        await s.commit();return True

async def create_coupon(code, discount_percent, usage_limit):
    async with Session() as s:
        code=code.upper().strip()
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
