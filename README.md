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

## Admin controls
- `/admin` opens the inline admin control panel.
- Open **Key Stock** → **Add / Update Key Stock** for the guided, button-first inventory workflow.
- Select an existing category, or tap **Create new category**.
- Select an existing product, or create a product and enter an optional description.
- Select an existing plan, or create a plan by entering its duration and four prices (customer INR, customer USD, reseller INR, reseller USD).
- Paste keys in bulk, one key per line. Duplicate keys are skipped and the result reports submitted, added, and duplicate counts.
- `/addstock PLAN_ID` remains available as a legacy shortcut; it now uses the same state-based bulk upload flow.
- `/wallet USER_ID|AMOUNT_INR` — admin credit to a user's wallet
- `/setreseller USER_ID` — enable reseller pricing
- `/products`
- `/orders`
- `/cancel`

The shop flow includes category → product → duration plan → wallet or UPI / Paytm (INR) checkout via Cashfree. Cashfree payment links are displayed as a QR code and online-payment button, with a five-minute expiry. Verified payments fulfill keys automatically. Wallet purchases debit and fulfill within a database transaction.

## Important production hardening
- Cashfree webhook signature verification is included. The webhook queries Cashfree Payment Links API status and amount before fulfillment. Test event payloads with your Cashfree sandbox dashboard before live use.
- The checkout flow requests a valid Indian mobile number before creating the Cashfree Payment Link.
- Configure wallet top-up flow before letting users self-fund wallets; the included `/wallet` command is admin-only. Add delivery retry queue, rate limits, admin audit logs, privacy notice, refund process, and backup/monitoring before launch.
- Never commit `.env` or real payment credentials.
- Sell only authorized, lawful digital goods. Do not use this bot to distribute spyware, stolen credentials, or unauthorized personal-data access.


## Railway startup troubleshooting

- Set `BOT_TOKEN` in Railway Variables to the token from @BotFather. The app intentionally exits if this variable is missing.
- This package installs SQLAlchemy with its asyncio extra (`SQLAlchemy[asyncio]`), which includes `greenlet`. Redeploy after updating the requirements.

## Telegram admin control panel
Open `/admin` as an account listed in `ADMIN_IDS` to use the inline admin menu. The panel provides dashboard totals, user search/profile, ban/unban, wallet adjustment/history, product maintenance, stock status, order/payment review, reseller controls, broadcasts, coupon creation, settings storage, and admin audit logs. The Key Stock section includes a guided category → product → plan → bulk-key workflow; categories, products and plans can all be created from inline-button prompts without typing commands.

### Additional admin commands
- `/walletadjust USER_ID|AMOUNT` — credit with a positive amount or deduct with a negative amount; refuses a negative resulting balance.
- `/wallethistory USER_ID` — wallet adjustment and wallet-purchase ledger.
- `/editproduct ID|NAME|CATEGORY|DESCRIPTION` — edit product metadata.
- `/deleteproduct ID` — soft-delete a product and its plans (inventory/order history is retained).
- `/keys PLAN_ID|STATUS` — list key IDs/status (status is optional).
- `/stockstatus KEY_ID|AVAILABLE` (or `SOLD` / `EXPIRED`) — update an individual key state.
- `/paymentcheck ORDER_ID` — query the current Cashfree payment-link status and paid amount.
- `/refundrecord ORDER_ID|STATUS|NOTE` and `/refunds` — track refund progress. Actual refunds must be initiated in Cashfree's dashboard; this bot does not issue refunds through the Cashfree API.
- `/resellerprice PLAN_ID|INR|USD`, `/unreseller USER_ID` — reseller pricing and deactivation.
- `/coupon CODE|DISCOUNT_PERCENT|USAGE_LIMIT` — create a coupon record (checkout redemption is not yet connected).
- `/setting KEY|VALUE` — persist a bot setting (the current payment credentials and deployment configuration still come from environment variables; generic settings are not yet applied to checkout logic).
- `/broadcast_resellers` — start a reseller-only broadcast; `/admin` → Broadcast sends to all non-banned users.

New tables for wallet transactions, coupons, bot settings, refund records and admin logs are created automatically by SQLAlchemy `create_all`; existing tables are not dropped. Back up the database before deploying schema changes.


## Latest customer menu update
- `/start` is listed as **Open Shop Menu** and returns verified users to the full store welcome screen.
- Dashboard/back navigation returns to the store welcome screen.
- Profile and order history show wallet, purchase statistics, delivered keys, dates, and order status.
- Bulk checkout supports quantities 1, 5, 10, 15, and a custom quantity, limited by available stock.
- Wallet top-ups support ₹10, ₹20, ₹50, ₹100, or a custom amount (minimum ₹10) through Cashfree UPI QR. Successful top-ups are credited once via webhook or manual status check.
- Support screen points to @subro98.

The database startup migration makes `orders.product_id` nullable so wallet top-up records can share the existing payment tracking table. Existing order and user data are preserved.


## Referral rewards
- Each customer has a unique Telegram deep link: `https://t.me/panelxarmy_bot?start=ref_USER_ID`.
- A new user is attributed only once, cannot refer themselves, and must join through the link before making a paid purchase.
- After that referred user's first successful key delivery (Cashfree or wallet), the referrer receives one pending trial-key reward.
- The referrer chooses Root or Non-Root. The bot randomly reserves one available key from a product whose name/category identifies it as Root or Non-Root.
- Admins add referral trial keys through **🎁 Reward Key Stock** in the admin menu. Root and Non-Root reward inventories are separate from normal shop inventory. If the selected type has no available reward key, the reward stays pending until stock is added.
- Existing users are not retroactively assigned a referrer. Referral counts and claimed trial keys are stored in PostgreSQL.

