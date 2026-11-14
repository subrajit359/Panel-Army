PANEL ARMY ADMIN UPDATE

Based on the latest Singapore performance/security ZIP.

ADMIN PANEL
- Main admin dashboard/menu uses inline buttons and can be returned to with Admin Menu.
- Payments list and order detail screens use inline buttons and refresh.
- Reseller list supports adding by Telegram ID and removing an existing reseller.
- Broadcast supports all users, customers, or resellers; collect multiple text/photo/video messages; then confirm Send or Cancel.
- Coupons support create, pause/activate, edit discount/usage limit, and delete from inline buttons.
- Settings support viewing stored key/value settings and editing/adding values through inline buttons.
- Dashboard includes today's revenue in India Standard Time (IST). Wallet top-ups are excluded from store revenue.

PRODUCTS
- Product maintenance toggle is available in product management. Customers see "<Product> is under maintenance" and cannot open plans or start a new purchase.
- Delete asks for confirmation. If a product has historical orders or key records, it is archived (deactivated) to protect foreign-key and order history. If no related records exist, it is permanently deleted from the database.
- Deleting a category moves its products to "Other Products" because categories are stored as product category values, not a separate categories table.

DATABASE
- Adds an additive PostgreSQL migration for products.maintenance; existing rows default to FALSE.
- Existing database and environment variables are retained. Do not reset the AWS database.

IMPORTANT LIMITATIONS
- Generic settings are stored and editable, but only settings explicitly read by application code affect runtime behavior. This update does not change Railway environment variables or Cashfree credentials.
- Coupon admin CRUD is available, but customer checkout coupon redemption is not added by this admin-only update.
- Broadcast sends copies of messages from the admin chat; media/text formatting is preserved by Telegram copy_message. It sends one user at a time with a short delay to reduce flood-limit risk.

DEPLOY
1. Extract this ZIP.
2. Replace the existing project files with the files inside pa_dup_fix.
3. Keep the current Railway environment variables and AWS PostgreSQL DATABASE_URL.
4. Redeploy. Startup applies the additive maintenance-column migration.

Validation performed: Python syntax compilation and ZIP integrity. Live Telegram, Railway, AWS PostgreSQL, and Cashfree integration tests require deployment credentials and were not run here.
