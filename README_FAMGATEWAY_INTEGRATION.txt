PANEL ARMY STORE — FAMGATEWAY DYNAMIC UPI QR INTEGRATION

PAYMENT FLOW
1. A customer selects a product plan or wallet top-up.
2. Panel Army creates a local pending order and calls FamGateway POST /api/create-order.
3. The bot sends the returned dynamic QR image in Telegram. UPI intent and hosted checkout buttons are shown when returned by FamGateway.
4. The bot checks status in the background every 4 seconds. The FamGateway webhook is also enabled as a fast path.
5. A webhook is accepted only after HMAC-SHA256 validation using the FamGateway API key and a second server-to-server verification.
6. Order ID and exact INR amount are checked before fulfillment. Database row locks and unique wallet transaction references prevent duplicate key delivery or wallet credit.
7. The customer can still use Check Payment Status as a manual fallback.

RAILWAY VARIABLES
Required:
- BOT_TOKEN
- ADMIN_IDS
- DATABASE_URL
- FAMGATEWAY_API_KEY
- PUBLIC_BASE_URL (public HTTPS Railway domain, no trailing slash)

FAMGATEWAY DASHBOARD
1. Sign in at https://famgateway.in.
2. Connect and activate the receiving gateway in the dashboard.
3. Create/copy the merchant API key. Keep it private.
4. In Webhooks settings, register: https://YOUR-RAILWAY-DOMAIN/famgateway/webhook
5. The webhook signature uses the FamGateway API key as its HMAC-SHA256 secret; no separate webhook secret variable is used by this integration.
6. If using FamPay Gmail verification, complete the provider's Gmail/IMAP connection steps in its dashboard. If using Paytm for Business, complete the provider's merchant setup instead.

DEPLOYMENT
- Replace the old project files with this ZIP's contents.
- Add FAMGATEWAY_API_KEY and PUBLIC_BASE_URL in Railway Variables.
- Keep the existing DATABASE_URL, BOT_TOKEN, and ADMIN_IDS.
- Do not reset PostgreSQL. Startup migration adds famgateway_order_id and its unique index without deleting existing data.
- Deploy, then make a small test purchase and wallet top-up. Confirm the payment reaches the intended bank/wallet account and the bot delivers/credits exactly once.

NOTES
- FamGateway QR sessions expire according to the provider's returned expiry/status.
- Background polling is every 4 seconds, within the provider's documented 3–5 second interval. Webhooks are also used.
- The API key stays server-side in Railway Variables. Never share it in Telegram or chat.
- Live API, merchant account, Railway, Telegram, and real-money end-to-end tests have not been performed in this build environment.
- Confirm your business/product category is permitted by the provider before accepting customer payments.
