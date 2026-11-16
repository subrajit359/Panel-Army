Panel Army Store Improvements Update

Implemented:
1. My Orders now shows only paid product orders that have a stored delivered key; pending, expired, failed and wallet top-up orders are hidden.
2. Admin plan management now has separate Add Customer Plan and Set Reseller Plan Price actions. Both prices remain attached to the same catalogue plan and inventory.
3. Wallet top-ups continue to credit the wallet automatically after server-side payment confirmation. The top-up payment button now reads Payment with UPI/Paytm (INR).
4. Customer-facing payment messages do not disclose the payment provider.
5. Download Files opens the supplied Telegram channel invite.
6. Customer-facing and admin command pricing uses INR only. Legacy database USD columns are retained for compatibility and are not shown.
7. QR instructions state: This order will expire in 5 minutes. Background verification runs for the 5-minute order window.
8. Available plan cards show status, customer price, reseller price and reseller savings. Plans without available keys are shown Offline and cannot be selected for payment.
9. Inventory status legend explains AVAILABLE, SOLD, DUPLICATE and EXPIRED.

No database schema migration or new environment variable is required. Existing database records and Railway variables are preserved.

Validation performed: Python syntax compilation and ZIP integrity checks. Live Railway deployment and real-money payment tests have not been performed.
