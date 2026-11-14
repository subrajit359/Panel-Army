PANEL ARMY STORE - BULK ADD PLANS UPDATE

In Admin > Products > choose category > choose product > Add plan, the bot now accepts multiple plans in one message.

Format (one plan per line):
Plan Name - Customer INR | Reseller INR

Example:
3 Hours   - 27 | 9
6 Hours   - 54 | 18
12 Hours  - 90 | 30
1 Day     - 162 | 54
7 Days    - 540 | 180
30 Days   - 900 | 300

All lines are validated before any plan is created. Prices are stored in INR; USD values are set to zero. After creation, the bot shows the created plans and a Back to Product button. Upload keys separately inside each plan.

Deployment: replace the existing bot files with this project update and redeploy on Railway. Keep your existing environment variables and database.
