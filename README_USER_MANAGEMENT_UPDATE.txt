PANELARMY USER MANAGEMENT UPDATE

Admin Menu > Users now opens two options:
1. Search User: searches by Telegram numeric ID, username (with or without @), or name. /cancel exits the search.
2. Show All Users: displays registered-user count and lifetime paid product spend, then lists users newest-first in pages of 10.

Each listed user has a profile button. The profile shows Telegram ID, username, wallet balance, customer/reseller role, ban status, paid order count, paid product spend, and join date. Existing Ban/Unban and reseller-toggle actions are retained.

Total paid product spend counts PAID orders and excludes wallet top-ups (TOPUP/FAM_TOPUP), so wallet deposits are not counted as purchases.

No existing database tables or user records are deleted or reset. New database functions are read-only queries.
