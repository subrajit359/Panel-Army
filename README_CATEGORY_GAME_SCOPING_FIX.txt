PANELARMY V14 — GAME / CATEGORY / PRODUCT MANAGEMENT FIX

What changed
------------
1. Categories are now owned by a game (composite key: game + category name).
2. Empty categories are retained and shown in that game's customer store and admin catalogue.
3. The customer store shows a friendly empty-category message and a Categories back button.
4. Product duplicate checks are scoped to the same game and category. The same product name
   can be used in another game without a false duplicate error.
5. Category rename, product counting, and category deletion are scoped to the selected game.
   Deleting a category in one game no longer deletes products from another game.
6. Renaming a game also moves its category folders.
7. Inventory/stock management now asks for a game first, then filters categories and products
   to that game.
8. The global category manager identifies each category's game.

Database migration
------------------
On startup, init_db() performs an additive PostgreSQL migration:
- Adds game to legacy product_categories rows (legacy empty folders with no ownership metadata
  are assigned to Free Fire because their original game cannot be inferred).
- Copies categories to every game that currently has products using that category name.
- Changes the category primary key from name to (game, name).
- Backfills per-game category folders from existing products.
Existing products, plans, stock, and order records are not intentionally deleted or rewritten
by this migration.

Deployment safety
-----------------
1. Take a PostgreSQL/Railway database backup before deploying.
2. Deploy the full contents of this ZIP, not only db.py or main.py.
3. Keep the existing DATABASE_URL and other environment variables unchanged.
4. Let the bot start once so init_db() can apply the migration.
5. Test by creating a category with the same name in two games, adding same-named products
   under both games, renaming one category, and deleting one category. Confirm the other
   game's category/products remain intact.

Validation performed
--------------------
- db.py and main.py pass Python bytecode compilation.
- Static checks confirm game-scoped category create/list/rename/delete and duplicate checks.
- Live PostgreSQL/Railway integration tests were not possible in this environment.
