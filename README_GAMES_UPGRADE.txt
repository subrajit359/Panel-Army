PANEL ARMY — GAME SELECTOR UPGRADE

Customer flow:
Choose Game -> Choose Category -> Existing Product -> Existing Plan.

Games currently exposed:
- Free Fire
- PUBG Mobile
- 8 Ball Pool
- Carrom Pool

Database migration:
- Adds products.game with a DEFAULT of 'Free Fire'.
- Existing products are assigned to Free Fire automatically by PostgreSQL.
- Existing product IDs, plan IDs, key-stock rows, orders, wallets, and payment history are not rewritten.
- New products created from Admin > Products are assigned to the currently selected game.

Admin flow:
Admin > Products > Choose Game > Choose Category > Existing Product / Plans.

IMPORTANT:
1. Take a backup of the live PostgreSQL database before deploying.
2. Deploy the complete project files together, not only main.py.
3. On startup, init_db() runs the additive ALTER TABLE migration.
4. Verify existing products appear under Free Fire, then add categories/products under other games.
5. This package has been syntax-checked, but not tested against your live Telegram bot or production database.
