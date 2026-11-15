PANEL ARMY STORE - CASHFREE PAYMENT LINKS UPDATE

WHAT CHANGED
- Product purchases now create one unique Cashfree Payment Link per order using POST /pg/links.
- Wallet top-ups use the same Payment Links flow.
- The old restricted POST /orders/pay UPI QR initiation call is no longer used by new checkouts.
- Customers receive a Cashfree Pay Now button in Telegram and a Check Payment Status button.
- Payment Links are configured for INR and UPI, disallow partial payments, and expire after 10 minutes.
- The per-link notify_url points to https://YOUR_PUBLIC_BASE_URL/cashfree/webhook.
- The bot verifies the signature, then fetches the link from Cashfree and checks link ID, currency, full paid amount and PAID status before fulfillment.
- Existing QR-based orders remain supported by the legacy order-payment status lookup.
- The existing PostgreSQL schema is retained; the existing cashfree_payment_link column stores the new URL.
- Fixed the missing get_bot_settings import used by /admin.

RAILWAY VARIABLES
No new environment variables are required. Keep the existing:
BOT_TOKEN
ADMIN_IDS
DATABASE_URL
CASHFREE_APP_ID
CASHFREE_SECRET_KEY
CASHFREE_ENV
PUBLIC_BASE_URL

IMPORTANT CASHFREE ACCOUNT REQUIREMENT
Payment Links API is a separate Cashfree product/permission from the S2S UPI QR initiation API. This code avoids POST /orders/pay, but it cannot grant Payment Links API access to the merchant account. Test a new order after deployment. If Cashfree returns an API permission/approval error for POST /links, contact Cashfree support and request Payment Links API access for the merchant MID.

WEBHOOK
The Payment Link request sends a per-link notify_url to:
https://YOUR_PUBLIC_BASE_URL/cashfree/webhook
Keep the Railway service publicly reachable over HTTPS. The handler uses the existing Cashfree webhook signature verification and re-fetches payment-link status from Cashfree before delivering a key or crediting wallet balance.

TESTING LIMITS
Python syntax compilation, Payment Link amount/status helper checks, and ZIP integrity were checked. A live Cashfree API payment, webhook delivery, Telegram delivery, Railway deployment and PostgreSQL integration test were not possible in this environment. Start with Cashfree sandbox credentials and complete an end-to-end test before enabling production payments.
