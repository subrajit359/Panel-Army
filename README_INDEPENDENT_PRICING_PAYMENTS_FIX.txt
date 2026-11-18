PANEL ARMY — INDEPENDENT PRICING & PAYMENTS SCREEN FIX

Changes in this update

1. Independent plan pricing
- Updating an existing customer's price changes only price_inr / price_usd.
- Updating an existing reseller's price changes only reseller_price_inr / reseller_price_usd.
- Bulk customer-price updates do not alter reseller prices.
- Bulk reseller-price updates do not alter customer prices.
- Creating a new customer plan initializes reseller pricing as unset (stored as zero); it does not copy the customer price. Admin bulk-add instructions now accurately state that reseller price remains Not Set until configured.
- Editing both fields remains possible through the existing combined plan editor.

2. Store price visibility
- Customers see only customer pricing.
- Resellers see only reseller pricing.
- A missing, cleared, null, or zero role price is displayed as "Not Set".
- A role cannot start checkout when its own price is not set.
- The store does not display ₹0.00 or reveal the other role's price.
- Admin can clear an individual role price by entering 0; the store then displays "Not Set".

3. Admin Payments screen
- The database order-list function is imported as db_admin_orders to avoid collision with the Telegram /orders command handler name.
- Payments list and refresh now catch/report database errors rather than leaving the screen blank.
- Reconciliation errors are also handled and logged.

Compatibility and data
- No database tables or columns were removed or renamed.
- Existing product, plan, key, user, wallet, order and payment records are not reset or migrated by this update.
- Existing bot features and handlers are retained.

Validation
- Python syntax compilation completed for main.py, db.py, config.py and famgateway.py.
- ZIP archive integrity checked after packaging.
- Live Telegram, Railway/PostgreSQL and FamGateway transactions were not available for end-to-end testing; deploy to a test environment first if possible.
