PANEL ARMY - COLOURED TELEGRAM BUTTON UPDATE

Updated all InlineKeyboardButton definitions with Telegram button styles:
- primary (blue): navigation, menus, shop and admin controls
- success (green): payment, purchase, confirmation and claim actions
- danger (red): delete, remove, cancel and deactivate actions

Updated requirement: aiogram>=3.25.0,<4 (supports the Telegram button style field).

No callback_data values, handlers, database logic, payment logic, or product workflows were intentionally changed.

Note: Telegram clients must support button styles; unsupported clients may display their default button appearance. Telegram Premium is not required for button styles.
