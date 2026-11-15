PANEL ARMY 2.0 — SAFETY, PERFORMANCE & ADMIN UPDATE

DATABASE
- PostgreSQL is the supported database. Keep Railway and PostgreSQL in Singapore and use the private/internal connection URL when both services share a Railway network. If PostgreSQL is external (for example RDS), use its TLS-enabled endpoint and confirm the actual network route.
- The bot uses SQLAlchemy async + asyncpg, a bounded keep-alive connection pool, pool pre-ping, and pool recycling. Defaults: DB_POOL_SIZE=5, DB_MAX_OVERFLOW=5, DB_POOL_TIMEOUT=8, DB_POOL_RECYCLE=1800. Tune these to the PostgreSQL connection limit and the number of running bot replicas; do not increase blindly.
- DB_SSL=require by default. Use DB_SSL=disable only for a trusted private/local database connection that does not support TLS.
- Startup applies additive PostgreSQL migrations and creates query indexes. Take a PostgreSQL backup before first deployment of this update.

INVENTORY SAFETY
- Stock upload now checks duplicate keys globally across all products/plans, not only within one plan. Comparison ignores letter case and outer whitespace; concurrent inserts are protected by a PostgreSQL unique expression index.
- If older data already contains duplicate keys, the migration preserves every row but marks all duplicate copies except the oldest as DUPLICATE. Review these rows before manually restoring stock.
- Bulk plan creation now previews the batch and saves all rows in one transaction. Duplicate durations within the batch or already on the product are rejected before saving.
- Key records and historical orders are retained. Product deletion continues to archive products with stock/order history instead of destroying historical data.

PAYMENT & WALLET SAFETY
- Product checkout amount is recalculated/validated server-side against the current plan and the user's customer/reseller role; edited callback data cannot set an arbitrary price.
- Wallet transactions for Cashfree top-ups, wallet purchases and no-stock credits have unique reference IDs to prevent repeat ledger entries.
- Payment reconciliation in Admin > Payments lists pending/expired/no-stock orders for manual provider review. It does not mark an order paid by itself; verify the Cashfree provider status before any manual action.
- Existing webhook signature verification, provider payment-status/amount verification, order row locking and stock row locking remain enabled.

ADMIN & OPERATIONS
- Dashboard now includes customers/users, reseller count, paid/pending review orders, lifetime and today's revenue, available keys and sold keys.
- GET /health checks both the HTTP service and PostgreSQL connection. Railway healthcheck is configured to use /health.
- Admin changes continue to be recorded in admin_logs where the existing handlers call the audit logger.

BACKUP
Run a PostgreSQL backup from a trusted machine/container with PostgreSQL client tools installed:
  pg_dump "$DATABASE_URL" --format=custom --no-owner --no-privileges --file="panel-army-$(date -u +%Y%m%dT%H%M%SZ).dump"
Restore to a test database first using pg_restore. Store backups outside the Railway service filesystem (for example encrypted object storage); Railway container files are not durable backups. Schedule daily backups and periodically test a restore.

DEPLOY CHECKLIST
1. Back up PostgreSQL and retain the dump outside Railway.
2. Replace the deployed project files with this ZIP's contents (project root is pa_dup_fix/).
3. Ensure DATABASE_URL is a PostgreSQL URL and asyncpg is installed from requirements.txt.
4. Keep BOT_TOKEN, Cashfree credentials and database credentials in Railway Variables only; never commit secrets.
5. Keep CASHFREE_ENV=sandbox until end-to-end payment, duplicate webhook, stock exhaustion, wallet refund and reseller pricing tests pass.
6. Verify https://YOUR_DOMAIN/health returns {"status":"ok","database":"ok"}.
7. Test one customer purchase, one reseller purchase, one wallet purchase, a duplicate webhook, a duplicate stock upload across two plans, and an insufficient-stock payment.
8. Only switch Cashfree to production after the provider approves the business/category and all test cases pass.

IMPORTANT LIMITATIONS
- This update has been syntax-checked locally, but no connection to your live PostgreSQL database, Telegram bot, Railway deployment or Cashfree merchant account was available here. Therefore live migrations, real payment callbacks, QR timing and end-to-end delivery must still be tested in your environment.
- Before going live, ensure every product is permitted by Cashfree and complies with applicable laws and the relevant game/platform terms.
