PANEL ARMY STORE — PERFORMANCE, EXPIRY & RELIABILITY UPDATE

Changes:
1. Customer-facing get_product/get_plan lookups no longer run stock-count subqueries.
   Admin plan detail explicitly opts into stock counts; inventory lists retain their counts.
2. Wallet purchases now read and lock the user and plan in one transaction, calculate
   the authoritative price inside that transaction, and use a persisted callback request
   token to prevent the same Telegram callback update from charging twice.
3. Rapid concurrent wallet callbacks from the same user are guarded while a purchase runs.
4. Reseller bulk price updates now use the same product-level PostgreSQL advisory lock as
   customer bulk pricing.
5. Category deletion matches category text case-insensitively after trimming whitespace.
6. FamGateway QR expiry is persisted as expires_at when the QR is created and expires
   after five minutes. The monitor marks unpaid orders EXPIRED at the deadline and informs
   the customer. A verified payment arriving late is still processed safely.
7. Startup recovery checks recent in-flight FamGateway orders after a Railway restart and
   resumes monitoring QR orders whose five-minute window has not ended.
8. Wallet purchase callback is acknowledged before database work to make the bot feel
   more responsive.

Database migration:
- Startup init_db() adds orders.expires_at and orders.request_token and creates a partial
  unique index for non-null request tokens. No manual SQL migration is required.

Validation performed:
- Python source files passed py_compile.
- ZIP integrity check passed.
- No live Railway, Telegram, PostgreSQL, or FamGateway payment test was possible here.
