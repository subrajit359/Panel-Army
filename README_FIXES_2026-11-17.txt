PANEL ARMY HOTFIX — 2026-11-17

1. Telegram customer category prompt
- Corrected the Free Fire game/category prompt strings to contain actual Python newline escapes rather than literal backslash+n characters.
- The rendered message is now split across lines: game title, blank line, then “Choose Category”.

2. FamGateway startup payment recovery
- HTTP 408 from verify-order (including the provider's “Order expired” response) is treated as an unpaid EXPIRED result, not an exception.
- Startup recovery now catches failures per order and continues processing the remaining reconciliation rows.
- Only a server-verified successful payment can trigger fulfillment; an expired response never marks an order paid.

Compatibility
- Based on PanelArmy_Game_Category_Upgrade_v3.zip.
- Existing database schema, product/game/category/plan records, stock, wallets, orders, payment records, callbacks, and fulfillment code are retained.

Validation
- Python syntax compilation passed for main.py, famgateway.py, and db.py.
- Live provider verification and Telegram deployment were not performed in this environment.
