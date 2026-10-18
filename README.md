# Personal Finance & Stock Research Telegram Bot

A single-user Telegram bot, written in Python, that combines **stock-portfolio tracking and research** with
**personal budgeting and savings planning** (built around Israeli banking: shekel checking account, a Visa
billing cycle, training funds). Everything happens in a chat: commands, inline buttons and step-by-step
conversations.

> **Not a trading system.** The bot records trades you enter yourself, tracks prices and produces research.
> It does not connect to a broker and never places orders. Its research output is information for your own
> decisions, not investment advice.

The repository also contains an earlier **command-line stock analyser** (`stock_agent.py`, `cli.py`) that
scores stocks from technical, fundamental and sentiment data.

---

## Features

**Stocks**
- Holdings, buys and sells with profit/loss, an Israeli tax-loss "shield" balance and per-broker cash.
- Background monitors: price alerts, P/L checks and a news watch (`_auto_price_alert_loop`,
  `_pl_monitor_loop`, `_news_watch_loop` in `telegram_bot.py`).
- `/shouldisell`: a research pipeline for one holding — market data, technicals, analyst data, news and a
  research step, then a structured verdict. Share counts, tax and cash are computed in code, not by the model
  (`stock_decision.py`).
- `/valuation`, a weekly P/L report, rebalancing against target weights, an investment thesis per stock,
  and earnings reports with a pre-earnings prediction that is graded afterwards
  (`valuation.py`, `weekly.py`, `rebalance.py`, `thesis.py`, `earnings_ai.py`).

**Spending**
- Expense logging by card (debit / Visa) with the Visa purchases set aside until the monthly charge
  (`expenses.py`).
- Categories and sub-categories, learned from the store name (`categories.py`); monthly budgets per category.
- Receipt photos read into store, items and total (`receipts.py`).
- Recurring subscriptions with a check before each renewal (`recurring.py`), future planned expenses
  (`planned.py`), daily balance and overspending alerts (`money_alerts.py`).

**Savings planning**
- `/setplan`: a 12-month wizard. For each month: expected income, expected spending, a fixed deposit to a
  self-employed training fund, then a percentage split between emergency fund, future expenses, euro savings
  and stocks. Every month is previewed in shekels before it is saved, and any single month can be changed
  later (`savings_planner.py`).
- `/payment` turns an actual salary into transfers in the order the money moves; `/allocated` records what
  was really moved and updates the stored balances (`allocations.py`).
- Net-worth snapshots, savings rate, emergency-fund runway, financial-independence and pension projections,
  a tax-year summary and a monthly score (`wealth.py`, `fi.py`, `pension.py`, `taxyear.py`, `score.py`).

See [`docs/examples/`](docs/examples/) for real output of the planner's formatters, rendered with synthetic data.

---

## Technology

| | Used for |
|---|---|
| Python 3.12 | everything |
| [python-telegram-bot](https://python-telegram-bot.org/) (v20+ async API) | commands, inline keyboards, `ConversationHandler` wizards |
| asyncio | background monitors and scheduled daily jobs; blocking calls moved off the event loop with `asyncio.to_thread` |
| yfinance | prices, financial statements, exchange rates |
| Finnhub REST API | earnings calendar, company news, peers |
| Anthropic Claude API | receipt reading, earnings analysis, `/debrief`, spending review, `/shouldisell` decision — with JSON-schema structured output |
| OpenAI API | older analysis and summary commands, the CLI's AI advisor |
| Perplexity API | the research step of `/shouldisell` |
| pandas, numpy, `ta`, rich | the command-line analyser |
| JSON files | storage (one file per area; created on first use) |

---

## Architecture

```
telegram_bot.py        Telegram layer: handlers, conversations, background loops, scheduling
config.py              settings, read from environment variables
savings_planner.py     plan model: payment breakdown, month-by-month projection, message formatting
allocations.py         suggested vs. actual allocation records
expenses.py            spending ledger, Visa cycle
categories.py          categories, sub-categories, store memory, budgets
receipts.py            receipt image -> structured data (Claude)
stock_decision.py      /shouldisell research pipeline (network legs injectable for testing)
earnings_ai.py         earnings prediction, report and grading (Claude)
eur_fund.py, keren_self.py, ils_funds.py, wealth.py, fi.py, pension.py, ...   domain modules
api_spend.py           cost log for every paid API call
backup_manager.py      hourly and manual backups of the data files
collectors/, analyzers/ data collection and scoring for the CLI analyser
research_agents/, primo_agent/   multi-agent research experiments
```

Most domain modules are plain functions over dictionaries and do not import Telegram, so the money logic can
be exercised without the bot.

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (source .venv/bin/activate elsewhere)
pip install -r requirements.txt
copy .env.example .env            # then edit .env
python telegram_bot.py
```

1. Create a bot with [@BotFather](https://t.me/BotFather) and put its token in `TELEGRAM_BOT_TOKEN`.
2. Put **your own** numeric Telegram user id in `TELEGRAM_CHAT_ID`. Only that user can use the bot, and
   scheduled messages go there.
3. AI and market-data keys are optional; commands that need a missing key will not work.

The command-line analyser runs separately: `python cli.py` or `python stock_agent.py AAPL`.

### Costs

Claude, OpenAI and Perplexity calls are billed by those providers per use. The bot logs an estimated cost for
paid AI calls (`api_spend.py`). Finnhub and Yahoo Finance are subject to the rate limits of your access plan.

---

## Privacy and security

- The bot keeps **real personal financial data** (balances, holdings, spending, receipts) in local JSON files
  and a `receipts/` folder next to the code. `.gitignore` excludes all of them; **never commit them**.
- Secrets live only in `.env` (excluded). `.env.example` holds placeholders.
- Access is limited to one Telegram user id (`ALLOWED_USER_IDS` in `telegram_bot.py`).
- Receipt images and the data sent for AI analysis are transmitted to the AI provider's API.

## Limitations

- Single user, local JSON storage, no database.
- `telegram_bot.py` is large (~37k lines); the logic is being moved into separate modules over time.
- Spending and balances are entered by hand or from receipts; there is no bank connection.
- The interface mixes Hebrew and English.
- The automated regression tests used during development are not included in this repository yet.

## Development

Developed as a personal project, with AI-assisted development (Claude Code).
