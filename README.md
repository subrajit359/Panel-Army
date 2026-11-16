# Panel Army Store

Telegram storefront built with Python, aiogram and PostgreSQL.

## Railway environment variables

Required:
- `BOT_TOKEN`
- `ADMIN_IDS`
- `DATABASE_URL`
- `FAMGATEWAY_API_KEY`
- `PUBLIC_BASE_URL` — public HTTPS Railway domain, without a trailing slash

Optional PostgreSQL pool tuning:
- `DB_POOL_SIZE` (default 5)
- `DB_MAX_OVERFLOW` (default 5)
- `DB_POOL_TIMEOUT` (default 8)
- `DB_POOL_RECYCLE` (default 1800)
- `DB_SSL` (default `require`)

## Payment flow

Product purchases and wallet top-ups use FamGateway dynamic UPI QR sessions. The bot displays the QR image in Telegram, polls FamGateway server-side every four seconds, and also accepts signed webhooks. Payment is only fulfilled after an authoritative FamGateway status check and exact order/amount matching. Database locks and unique wallet transaction references prevent duplicate delivery or credit.

See `README_FAMGATEWAY_INTEGRATION.txt` for the FamGateway dashboard and webhook setup.

## Deploy

1. Replace the old project files with the contents of this ZIP.
2. Set the environment variables above in Railway.
3. Keep your existing PostgreSQL `DATABASE_URL`; do not reset the database.
4. Set the webhook URL in FamGateway to `https://YOUR-RAILWAY-DOMAIN/famgateway/webhook`.
5. Deploy and make a small real payment test. Confirm that funds reach the intended receiving account and the bot fulfills the order once.

The startup migration adds the FamGateway order reference and unique index without deleting existing order or inventory records. Old Cashfree code is no longer active in this build; historical database columns are retained to avoid destructive schema changes.

## Important

Live FamGateway merchant access, Railway deployment, Telegram delivery and real-money transactions cannot be tested from this build environment. Confirm the provider's terms and that your product category is permitted before accepting payments. Never share your API key, bot token or database URL.
