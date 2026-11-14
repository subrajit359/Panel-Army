# Panel Army (flat-root Railway project)

This starter is a Telegram storefront for legitimate digital products/license keys, with PostgreSQL inventory and Cashfree payment integration. All project files are in this root directory; there are no nested project folders.

## Railway variables
Set these in Railway:
- `BOT_TOKEN`: BotFather token
- `ADMIN_IDS`: Telegram admin user IDs, comma-separated
- `DATABASE_URL`: Railway PostgreSQL connection URL
- `CASHFREE_APP_ID`
- `CASHFREE_SECRET_KEY`
- `CASHFREE_ENV`: `sandbox` while testing; `production` for live
- `PUBLIC_BASE_URL`: your Railway public domain including `https://`

## Deploy
1. Create a Railway project and add a PostgreSQL service.
2. Deploy this repository.
3. Add the variables above to the bot service. Ensure `DATABASE_URL` is available from the PostgreSQL service reference.
4. Set the Cashfree webhook URL to `https://YOUR_DOMAIN/cashfree/webhook`.
5. Test with Cashfree sandbox before switching to production.

## Admin commands
- `/admin` shows commands
- `/addproduct NAME|PRICE|DESCRIPTION`
- `/addstock PRODUCT_ID` then send keys one per line
- `/products`
- `/orders`
- `/cancel`

## Important production hardening
- Cashfree webhook signature verification is included. The webhook queries Cashfree Payment Links API status and amount before fulfillment. Test event payloads with your Cashfree sandbox dashboard before live use.
- The checkout flow requests a valid Indian mobile number before creating the Cashfree Payment Link.
- Add pending-order expiry, delivery retry queue, stock-reservation strategy, rate limits, admin audit logs, privacy notice, refund process, and backup/monitoring before launch.
- Never commit `.env` or real payment credentials.
- Sell only authorized, lawful digital goods. Do not use this bot to distribute spyware, stolen credentials, or unauthorized personal-data access.
