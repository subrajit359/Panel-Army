PANEL ARMY STORE - BULK PRICING, STOREFRONT AND CASCADE DELETE UPDATE

1) Bulk Customer Plans
- Admin > Product > Add Customer Plan accepts multiple lines:
  Duration | Customer INR
- Existing duration: only customer price changes.
- New duration: reseller price starts equal to customer price.
- Duplicate/invalid lines are rejected before preview.
- Confirm & Save All applies the batch in one database transaction.

2) Bulk Reseller Plan Prices
- Admin > Product > Set Reseller Plan Price accepts multiple lines:
  Existing Duration | Reseller INR
- All durations must already exist.
- Only reseller prices change; customer prices are preserved.
- Batch is validated and saved atomically.

3) Storefront stock visibility
- Plans always show Online and plan buttons are never disabled due to stock.
- Customer/reseller storefront does not expose stock counts or out-of-stock labels.
- Purchases proceed to payment. Inventory is checked only during fulfillment.
- If a paid purchase cannot be fulfilled, the amount is credited to the wallet once using the existing idempotent refund transaction.
- Product maintenance behaviour is preserved.

4) Product/category deletion
- Deleting a product permanently deletes its product plans and associated stock rows.
- Deleting a category permanently deletes its products, plans and associated stock rows.
- Historical orders are preserved; product_id and plan_id links are set to NULL before catalogue rows are removed. Order amount, duration, key_text, status and timestamps remain.
- This is destructive for catalogue inventory. Confirm screen warns before deletion.

Validation performed: Python syntax compilation for all project Python files and ZIP integrity check.
Live Telegram/Railway/PostgreSQL/payment tests were not performed in this environment.
