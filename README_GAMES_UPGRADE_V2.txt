PANEL ARMY GAME CATALOGUE + MESSAGE FIX UPDATE

Changes in this update:
- Customer game selection and product/category messages now use actual newline characters, so Telegram displays separate lines.
- Removed the hardcoded game list. The game catalogue is stored in a new `games` table.
- Existing product game names are imported into the game catalogue at startup; Free Fire is always seeded.
- Admin > Products now offers Add game and Manage games.
- Admin can add, rename, and archive/remove games. Renaming updates products' game ownership in place; product IDs, plans, stock and order history are retained.
- Removing a game archives it from customer selection and retains its catalogue and history. Re-adding the same name restores it.
- Out-of-stock refund messages now include a Contact Admin URL button to https://t.me/subro98.

Database migration is additive. Existing products, product plans, prices, reseller prices, stock, wallets, orders and payment records are not deleted or recreated.

Validation performed: Python syntax compilation for main.py and db.py. Live Telegram/database deployment was not performed.
