import os, secrets, string
from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text,
    select, func, text, UniqueConstraint
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from config import PUBLIC_BASE_URL

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required. Set it to your Neon PostgreSQL connection string.")

# Normalize Neon/Railway PostgreSQL URLs for SQLAlchemy's asyncpg driver.
# asyncpg does not accept libpq's `sslmode` query parameter; configure TLS
# through connect_args instead.
from sqlalchemy.engine import make_url

url = make_url(DATABASE_URL)
if url.drivername in ("postgres", "postgresql"):
    url = url.set(drivername="postgresql+asyncpg")

query = dict(url.query)
sslmode = query.pop("sslmode", None)
query.pop("channel_binding", None)  # libpq-specific; asyncpg does not need this
query.pop("ssl", None)  # avoid duplicate/conflicting SSL configuration
url = url.set(query=query)

# Neon requires TLS. Preserve that requirement even if the original URL used
# `sslmode=require` or omitted an SSL parameter.
engine = create_async_engine(
    url,
    pool_pre_ping=True,
    connect_args={"ssl": "require"},
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

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    price_inr: Mapped[float] = mapped_column(Numeric(10,2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class KeyStock(Base):
    __tablename__ = "key_stock"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    key_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="AVAILABLE", index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

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

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_or_create_user(user_id, username, full_name):
    async with Session() as s:
        user = await s.get(User, user_id)
        if not user:
            s.add(User(user_id=user_id, username=username, full_name=full_name))
        else:
            user.username, user.full_name = username, full_name
        await s.commit()

async def list_products(include_empty=False):
    async with Session() as s:
        stmt = select(Product, func.count(KeyStock.id).label("stock")).outerjoin(
            KeyStock, (KeyStock.product_id == Product.id) & (KeyStock.status == "AVAILABLE")
        ).where(Product.active == True).group_by(Product.id).order_by(Product.id)
        rows = (await s.execute(stmt)).all()
        return [{"id":p.id,"name":p.name,"description":p.description,"price_inr":float(p.price_inr),"stock":int(stock)} for p,stock in rows if include_empty or stock > 0]

async def get_product(product_id):
    async with Session() as s:
        p = await s.get(Product, product_id)
        if not p or not p.active: return None
        stock = await s.scalar(select(func.count(KeyStock.id)).where(KeyStock.product_id == product_id, KeyStock.status == "AVAILABLE"))
        return {"id":p.id,"name":p.name,"description":p.description,"price_inr":float(p.price_inr),"stock":int(stock or 0)}

async def create_order(user_id, product_id, amount):
    order_id = "PA-" + secrets.token_hex(8).upper()
    async with Session() as s:
        s.add(Order(order_id=order_id,user_id=user_id,product_id=product_id,amount_inr=amount,status="PENDING"))
        await s.commit()
    return {"order_id":order_id}

async def get_order(order_id):
    async with Session() as s:
        o = await s.get(Order, order_id)
        return {"order_id":o.order_id,"user_id":o.user_id,"product_id":o.product_id,"amount_inr":float(o.amount_inr),"status":o.status} if o else None

async def fulfill_paid_order(order_id):
    # Row locks serialize key allocation and make fulfillment idempotent.
    async with Session() as s:
        async with s.begin():
            order = await s.scalar(select(Order).where(Order.order_id == order_id).with_for_update())
            if not order: return None
            if order.status == "PAID": return {"key_text": order.key_text, "user_id": order.user_id}
            if order.status != "PENDING": return None
            key = await s.scalar(select(KeyStock).where(
                KeyStock.product_id == order.product_id, KeyStock.status == "AVAILABLE"
            ).order_by(KeyStock.id).with_for_update(skip_locked=True).limit(1))
            if not key:
                order.status = "PAID_NO_STOCK"
                order.paid_at = datetime.now(timezone.utc)
                return {"key_text": None, "user_id": order.user_id}
            key.status = "SOLD"
            key.order_id = order.order_id
            order.status = "PAID"
            order.key_text = key.key_text
            order.paid_at = datetime.now(timezone.utc)
            return {"key_text": key.key_text, "user_id": order.user_id}

async def add_product(name, price, description):
    async with Session() as s:
        p = Product(name=name, price_inr=price, description=description)
        s.add(p); await s.commit(); await s.refresh(p)
        return {"id":p.id,"name":p.name}

async def add_stock(product_id, keys):
    async with Session() as s:
        p = await s.get(Product, product_id)
        if not p: return 0
        # ignore duplicate key strings within DB using query before inserting
        existing = set((await s.scalars(select(KeyStock.key_text).where(KeyStock.product_id == product_id))).all())
        new_keys = [k for k in dict.fromkeys(keys) if k not in existing]
        s.add_all([KeyStock(product_id=product_id,key_text=k,status="AVAILABLE") for k in new_keys])
        await s.commit()
        return len(new_keys)

async def list_orders(user_id):
    async with Session() as s:
        stmt = select(Order).order_by(Order.created_at.desc()).limit(30)
        if user_id is not None: stmt = stmt.where(Order.user_id == user_id)
        rows = (await s.scalars(stmt)).all()
        return [{"order_id":o.order_id,"user_id":o.user_id,"amount_inr":float(o.amount_inr),"status":o.status} for o in rows]
