# Capturing safe screenshots

No screenshots exist yet. Take them by hand, against a **separate demo bot with made-up data**. Never use the
real bot or real data.

## 1. Set up an isolated demo

1. In Telegram, create a **new** bot with @BotFather (e.g. `my_finance_demo_bot`). Do not reuse the real bot's token.
2. Run the bot from **this portfolio folder** (`python src/telegram_bot.py`; it contains no data files), with a `.env` that has only:
   - `TELEGRAM_BOT_TOKEN` = the demo bot's token
   - `TELEGRAM_CHAT_ID` = your user id
   Leave the AI keys empty unless you want to show an AI feature (each call costs money).
3. Enter **synthetic** data only, with round, obviously fake amounts (income ₪9,000, balances ₪20,000, etc.).
4. Before every capture, check that no real name, balance, holding, user id or phone number is visible
   (your Telegram profile photo and name can appear in the chat header — crop it out).

## 2. Suggested shots

| File | What to show | How | Caption |
|---|---|---|---|
| `docs/screenshots/01-menu.png` | The command menu | Tap the bot's menu button | "100+ commands grouped by area: stocks, spending, savings." |
| `docs/screenshots/02-setplan-month.png` | One month of the planner | `/setplan`, answer with fake income/spending, reach a month | "Each month's split, previewed in shekels before it is saved." |
| `docs/screenshots/03-setplan-summary.png` | The finished plan + "change a month" button | Finish `/setplan` for 2–3 months | "The 12-month projection, with goals and one-tap editing of any month." |
| `docs/screenshots/04-expense.png` | Logging an expense with a category | `/ilspend` with a fake ₪45 grocery purchase | "Expenses by card, categorised automatically from the store name." |
| `docs/screenshots/05-receipt.png` (optional, costs one Claude call) | Receipt scan result | Photograph a **receipt you print yourself** with made-up items | "A receipt photo read into store, items and total." |
| `docs/screenshots/06-price-alert.png` | A price alert being set | `/pricealert` on a large public stock | "Background price alerts." |

Prefer shots where every number on screen came from you typing it into the demo bot.

## 3. Without running anything

`docs/examples/` already holds real output of the planner's formatting code with synthetic numbers; they can be
linked from the README or LinkedIn instead of screenshots.
