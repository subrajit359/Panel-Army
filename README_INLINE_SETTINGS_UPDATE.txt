PANELARMY V13 - INLINE SETTINGS

Replaced the generic SETTING_KEY | VALUE screen with guided inline controls:
- Store ON/OFF
- Global maintenance ON/OFF
- Purchases ON/OFF
- Customer access ON/OFF
- Reseller access ON/OFF
- Edit support Telegram username
- Edit welcome message (send /clear to restore default)
- Set minimum wallet top-up amount

Settings are stored in the existing bot_settings table; no database schema or
existing customer/order/product data migration is required. Defaults preserve
previous behavior: store ON, maintenance OFF, purchases ON, customer access ON,
reseller access ON, support @subro98, minimum top-up ₹10.

Store/maintenance/access settings are checked while browsing the catalogue.
Purchase setting is checked again before wallet/UPI purchase processing to stop
stale inline buttons from bypassing the setting. Minimum top-up is validated
both when the amount is entered and immediately before QR creation.

Python syntax compilation passed. Live Telegram/Railway/payment-provider tests
were not run in this environment.
