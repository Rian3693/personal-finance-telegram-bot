"""Should I sell, hold or add? -- research one position and recommend an action.

The pipeline for one stock the user already owns:

  1. facts      what is held, what it cost, what it is worth, free cash, tax shield
  2. market     price history (short / medium / long), technicals, analyst targets,
                upgrades and downgrades, insiders, earnings date, headlines, Zacks
  3. research   Perplexity: a finance-domain search and, unless `quick`, Deep Research --
                two independent looks at the news and context, run in parallel
  4. decision   Claude Opus 5.5 reads everything above and returns a structured
                verdict with reasons, price levels and a hold-until horizon
  5. money      shares to sell, tax, shield and net cash are computed HERE, from the
                same rules /sell applies. The model never does arithmetic that ends
                up as a number the user acts on.
  6. alerts     the price levels in the verdict become /pricealert entries

The module holds no API keys and imports nothing from the bot, so it can be tested
without spending anything: every network leg can be replaced through `legs=`.
This is research output for the user's own decision. It never places an order.
"""

import asyncio
import json
import math
import os
import re
import statistics
import time
from datetime import date, datetime, timedelta

import requests

import api_spend

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shouldisell_history.json')

# The bot's own rule (see /sell): flat 25% on gains, a loss banks a shield of 25% of
# the loss, and a gain consumes the shield before any tax is withheld.
TAX_RATE = 0.25

# --- models and what they cost, USD per million tokens --------------------------
# Prices from each provider's pricing page, checked 2026-10-02. They only feed the
# cost line shown to the user; nothing is billed from these numbers.
OPUS_MODEL = 'claude-opus-5-5'
OPUS_IN, OPUS_OUT = 4.0, 20.0
PPLX_FINANCE_MODEL = 'sonar-pro'
PPLX_DEEP_MODEL = 'sonar-deep-research'

FINANCE_DOMAINS = ['finance.yahoo.com', 'reuters.com', 'bloomberg.com', 'seekingalpha.com',
                   'marketwatch.com', 'cnbc.com', 'barrons.com', 'wsj.com', 'ft.com',
                   'investing.com', 'benzinga.com', 'sec.gov']

SELL_ALL, SELL_PART, HOLD, ADD = 'SELL_ALL', 'SELL_PART', 'HOLD', 'ADD'
ACTIONS = (SELL_ALL, SELL_PART, HOLD, ADD)
ACTION_EMOJI = {SELL_ALL: '\U0001F534', SELL_PART: '\U0001F7E0', HOLD: '\U0001F7E1', ADD: '\U0001F7E2'}
ACTION_LABEL = {SELL_ALL: 'SELL ALL', SELL_PART: 'SELL PART', HOLD: 'HOLD', ADD: 'ADD'}

# What a run costs, shown on the buttons. Measured on real runs (Quick $0.15, Normal
# $0.69); the exact figure for each run is printed at the end of its report.
COST_HINT = {'quick': '~$0.15-0.20', 'full': '~$0.65-0.70'}

DISCLAIMER = ('AI-generated research to help you think, not licensed financial advice. '
              'Nothing here was bought or sold: the bot never places orders.')


def usd(amount):
    amount = float(amount or 0)
    return ('-' if amount < 0 else '') + '$' + format(abs(amount), ',.2f')


def usd_short(amount):
    amount = float(amount or 0)
    # (smallest amount worth abbreviating, divisor, suffix): thousands only start
    # at 10K, since $9,999.00 reads fine and $9.9K would throw away digits.
    for floor, divisor, suffix in ((1e9, 1e9, 'B'), (1e6, 1e6, 'M'), (1e4, 1e3, 'K')):
        if abs(amount) >= floor:
            return '$%.1f%s' % (amount / divisor, suffix)
    return usd(amount)


def signed_usd(amount):
    amount = float(amount or 0)
    return ('+' if amount >= 0 else '-') + '$' + format(abs(amount), ',.2f')


def pct(value, digits=1, sign=True):
    if value is None:
        return None
    return (('%+.' if sign else '%.') + str(digits) + 'f%%') % (value * 100)


def md(text):
    """Escape model- or web-sourced text for Telegram's legacy Markdown, where an
    unmatched underscore or asterisk would otherwise reject the whole message."""
    return re.sub(r'([_*`\[])', r'\\\1', str(text or ''))


# --------------------------------------------------------------------------- position and tax

def days_held(purchase_date):
    """Days since purchase, or None. Positions built up over several buys carry the
    label 'Combined', which has no single date."""
    try:
        return (date.today() - datetime.strptime(str(purchase_date)[:10], '%Y-%m-%d').date()).days
    except (ValueError, TypeError):
        return None


def typical_sell_commission(portfolio):
    """The commission to assume on a sell: the median of what past sells paid. The
    /sell flow asks for it each time, so there is no fixed rate to read."""
    rows = [float(r.get('sell_commission', 0) or 0) for r in (portfolio.get('sold_history') or [])]
    rows = [r for r in rows if r > 0]
    return round(statistics.median(rows), 2) if rows else 0.0


def position_facts(portfolio, symbol, price, weight=None):
    """What is held in `symbol`, or None when it is not in the portfolio."""
    symbol = symbol.upper()
    holding = next((h for h in portfolio.get('holdings', []) if h.get('symbol', '').upper() == symbol), None)
    if not holding:
        return None
    shares = float(holding['shares'])
    cost = float(holding['total_cost'])
    value = shares * price
    return {
        'symbol': symbol, 'shares': shares, 'total_cost': cost,
        'avg_cost': cost / shares if shares else 0.0, 'price': price,
        'value': value, 'pl': value - cost, 'pl_pct': (value - cost) / cost if cost else 0.0,
        'purchase_date': holding.get('purchase_date'),
        'days_held': days_held(holding.get('purchase_date')),
        'free_cash': float(portfolio.get('free_cash', 0) or 0),
        'shield': float(portfolio.get('tax_shield_balance', 0) or 0),
        'weight': weight,
        'sell_commission': typical_sell_commission(portfolio),
    }


def sale_math(facts, shares, price=None, commission=None):
    """What selling `shares` would do, by the exact rules of the /sell command.

    Cost basis is proportional (it already includes the buy commission); the
    sell commission comes off the proceeds; a gain pays 25% after consuming the
    banked shield, and a loss banks 25% of itself as new shield.
    """
    price = facts['price'] if price is None else price
    commission = facts['sell_commission'] if commission is None else commission
    shares = min(float(shares), facts['shares'])
    gross = shares * price
    proceeds = gross - commission
    basis = facts['total_cost'] / facts['shares'] * shares if facts['shares'] else 0.0
    pl = proceeds - basis

    owed = used = withheld = earned = 0.0
    if pl > 0:
        owed = round(pl * TAX_RATE, 2)
        used = round(min(facts['shield'], owed), 2)
        withheld = round(owed - used, 2)
    elif pl < 0:
        earned = round(abs(pl) * TAX_RATE, 2)

    return {
        'shares': shares, 'price': price, 'gross': round(gross, 2), 'commission': commission,
        'proceeds': round(proceeds, 2), 'basis': round(basis, 2), 'pl': round(pl, 2),
        'pl_pct': (pl / basis) if basis else 0.0,
        'tax_owed': owed, 'shield_used': used, 'tax_withheld': withheld,
        'shield_earned': earned,
        'shield_after': round(facts['shield'] - used + earned, 2),
        'net_cash': round(proceeds - withheld, 2),
        'fraction': shares / facts['shares'] if facts['shares'] else 0.0,
        'remaining_shares': round(facts['shares'] - shares, 4),
    }


def sale_options(facts):
    """Selling 25 / 50 / 75 / 100% today, so the model can weigh the tax."""
    out = {}
    for label, frac in (('25%', 0.25), ('50%', 0.5), ('75%', 0.75), ('100%', 1.0)):
        shares = facts['shares'] * frac
        shares = shares if frac == 1.0 or facts['shares'] < 2 else max(1.0, math.floor(shares))
        out[label] = sale_math(facts, shares)
    return out


def whole_shares(facts, fraction):
    """Shares to sell for a fractional recommendation. Whole shares when the
    position is big enough to split; never zero, and never the whole position
    (that is SELL_ALL's job)."""
    total = facts['shares']
    if total < 2:
        return total
    shares = max(1.0, math.floor(total * fraction + 0.5))
    return min(shares, total - 1.0) if shares >= total else shares


# --------------------------------------------------------------------------- market statistics

WINDOWS = (('1W', 5), ('1M', 21), ('3M', 63), ('6M', 126), ('1Y', 252), ('3Y', 756))
HORIZON_OF = {'1W': 'short', '1M': 'short', '3M': 'medium', '6M': 'medium', '1Y': 'long', '3Y': 'long'}


def _closes(hist):
    try:
        series = hist['Close'].dropna()
        return series if len(series) else None
    except Exception:
        return None


def period_return(close, bars):
    if close is None or len(close) <= bars:
        return None
    start = float(close.iloc[-1 - bars])
    return float(close.iloc[-1]) / start - 1 if start else None


def performance_table(hist, bench_hist=None):
    """Return over each window, next to the benchmark's, so a rise that was only
    the market lifting everything is not mistaken for strength."""
    close, bench = _closes(hist), _closes(bench_hist)
    rows = []
    for label, bars in WINDOWS:
        own, ref = period_return(close, bars), period_return(bench, bars)
        rows.append({'window': label, 'horizon': HORIZON_OF[label], 'stock': own,
                     'bench': ref,
                     'relative': (own - ref) if own is not None and ref is not None else None})
    return rows


def rsi(close, length=14):
    if close is None or len(close) < length + 2:
        return None
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    last_loss = float(loss.iloc[-1])
    if last_loss == 0:
        return 100.0
    return 100 - 100 / (1 + float(gain.iloc[-1]) / last_loss)


def technicals(hist):
    """Trend, momentum and risk numbers from daily bars."""
    close = _closes(hist)
    if close is None or len(close) < 30:
        return {}
    last = float(close.iloc[-1])
    out = {'price': last}
    for n in (20, 50, 200):
        if len(close) >= n:
            out['sma%d' % n] = float(close.iloc[-n:].mean())
    year = close.iloc[-252:]
    out['high_52w'], out['low_52w'] = float(year.max()), float(year.min())
    out['from_high'] = last / out['high_52w'] - 1
    out['from_low'] = last / out['low_52w'] - 1
    out['rsi14'] = rsi(close)
    returns = close.pct_change().dropna()
    if len(returns) > 20:
        out['volatility'] = float(returns.iloc[-252:].std() * math.sqrt(252))
    peak = year.cummax()
    out['max_drawdown_1y'] = float((year / peak - 1).min())
    try:
        hi, lo = hist['High'].dropna(), hist['Low'].dropna()
        prev = hist['Close'].shift(1)
        tr = (hi - lo).combine((hi - prev).abs(), max).combine((lo - prev).abs(), max)
        out['atr14'] = float(tr.iloc[-14:].mean())
    except Exception:
        pass
    out['support_recent'] = float(close.iloc[-60:].min()) if len(close) >= 60 else None
    out['resistance_recent'] = float(close.iloc[-60:].max()) if len(close) >= 60 else None

    if 'sma50' in out and 'sma200' in out:
        if last > out['sma50'] > out['sma200']:
            out['trend'] = 'uptrend (price above 50d above 200d)'
        elif last < out['sma50'] < out['sma200']:
            out['trend'] = 'downtrend (price below 50d below 200d)'
        elif last > out['sma200']:
            out['trend'] = 'above the 200d but mixed short term'
        else:
            out['trend'] = 'below the 200d, weak'
    return out


# --------------------------------------------------------------------------- data collection

def _safe(fn, gaps, label, default=None):
    """Run one data fetch; a failure becomes a named gap, not a crash."""
    try:
        return fn()
    except Exception as e:
        gaps.append('%s unavailable (%s)' % (label, str(e)[:60]))
        return default


def _insider_summary(df, days=180):
    """Buys versus sells by insiders over the last `days`."""
    if df is None or getattr(df, 'empty', True):
        return None
    cutoff = datetime.now() - timedelta(days=days)
    buys = sells = 0
    buy_shares = sell_shares = buy_value = sell_value = 0.0
    for _, row in df.iterrows():
        when = row.get('Start Date')
        try:
            if when is not None and hasattr(when, 'to_pydatetime') and when.to_pydatetime().replace(tzinfo=None) < cutoff:
                continue
        except Exception:
            pass
        text = (' '.join(str(row.get(c, '') or '') for c in ('Text', 'Transaction'))).lower()
        shares = abs(float(row.get('Shares', 0) or 0))
        value = abs(float(row.get('Value', 0) or 0))
        if 'sale' in text or 'sold' in text:
            sells += 1
            sell_shares += shares
            sell_value += value
        elif 'purchase' in text or 'bought' in text or 'buy' in text:
            buys += 1
            buy_shares += shares
            buy_value += value
    return {'days': days, 'buys': buys, 'sells': sells, 'buy_shares': buy_shares,
            'sell_shares': sell_shares, 'buy_value': buy_value, 'sell_value': sell_value}


def _analyst_actions(df, days=90, limit=8):
    if df is None or getattr(df, 'empty', True):
        return None
    cutoff = datetime.now() - timedelta(days=days)
    rows, up, down = [], 0, 0
    for when, row in df.iterrows():
        try:
            stamp = when.to_pydatetime().replace(tzinfo=None)
        except Exception:
            continue
        if stamp < cutoff:
            continue
        action = str(row.get('Action', '') or '').lower()
        up += action == 'up'
        down += action == 'down'
        rows.append({'date': stamp.strftime('%Y-%m-%d'), 'firm': str(row.get('Firm', '')),
                     'action': str(row.get('Action', '')), 'to': str(row.get('ToGrade', '')),
                     'from': str(row.get('FromGrade', '')),
                     'target': row.get('currentPriceTarget') if 'currentPriceTarget' in row else None})
    return {'days': days, 'upgrades': int(up), 'downgrades': int(down), 'recent': rows[:limit]}


def fetch_market(symbol, finnhub_key=None, zacks_fn=None):
    """Everything free that can be known about `symbol`. Blocking: run in a thread.

    Each source is fetched independently so that one dead feed leaves a named gap
    in the dossier rather than sinking the analysis.
    """
    import yfinance as yf

    gaps = []
    out = {'symbol': symbol, 'gaps': gaps}
    ticker = yf.Ticker(symbol)

    out['hist'] = _safe(lambda: ticker.history(period='5y'), gaps, 'price history')
    out['spy'] = _safe(lambda: yf.Ticker('SPY').history(period='5y'), gaps, 'SPY history')
    out['qqq'] = _safe(lambda: yf.Ticker('QQQ').history(period='1y'), gaps, 'QQQ history')
    out['vix'] = _safe(lambda: yf.Ticker('^VIX').history(period='3mo'), gaps, 'VIX')

    def last_price():
        try:
            value = float(ticker.fast_info.last_price)
            if not math.isnan(value) and value > 0:
                return value
        except Exception:
            pass
        close = _closes(out.get('hist'))
        return float(close.iloc[-1]) if close is not None else None
    out['price'] = last_price()

    info = _safe(lambda: ticker.info, gaps, 'company info', {}) or {}
    out['name'] = info.get('shortName') or info.get('longName') or symbol
    out['sector'] = info.get('sector')
    out['industry'] = info.get('industry')
    out['pe'] = info.get('trailingPE')
    out['forward_pe'] = info.get('forwardPE')
    out['market_cap'] = info.get('marketCap')
    out['beta'] = info.get('beta')

    out['targets'] = _safe(lambda: dict(ticker.analyst_price_targets or {}), gaps, 'analyst price targets')
    summary = _safe(lambda: ticker.recommendations_summary, gaps, 'analyst ratings')
    out['ratings'] = None
    if summary is not None and not getattr(summary, 'empty', True):
        out['ratings'] = {k: int(summary.iloc[0].get(k, 0) or 0)
                          for k in ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')}
    out['actions'] = _analyst_actions(_safe(lambda: ticker.upgrades_downgrades, gaps, 'upgrades/downgrades'))
    out['insiders'] = _insider_summary(_safe(lambda: ticker.insider_transactions, gaps, 'insider transactions'))

    def earnings():
        cal = ticker.calendar or {}
        when = cal.get('Earnings Date')
        if isinstance(when, (list, tuple)) and when:
            when = when[0]
        return {'date': str(when) if when else None, 'eps_avg': cal.get('Earnings Average'),
                'revenue_avg': cal.get('Revenue Average')}
    out['earnings'] = _safe(earnings, gaps, 'earnings date')

    if finnhub_key:
        today = date.today()

        def finnhub(path, **params):
            response = requests.get('https://finnhub.io/api/v1/' + path, timeout=20,
                                    params=dict(params, symbol=symbol, token=finnhub_key))
            response.raise_for_status()
            return response.json()

        def news():
            items = finnhub('company-news', **{'from': str(today - timedelta(days=14)), 'to': str(today)})
            seen, rows = set(), []
            for item in sorted(items, key=lambda i: i.get('datetime', 0), reverse=True):
                head = (item.get('headline') or '').strip()
                if head and head.lower() not in seen:
                    seen.add(head.lower())
                    rows.append({'date': datetime.fromtimestamp(item.get('datetime', 0)).strftime('%Y-%m-%d'),
                                 'source': item.get('source'), 'headline': head})
                if len(rows) >= 12:
                    break
            return rows
        out['news'] = _safe(news, gaps, 'Finnhub news', [])
        out['finnhub_ratings'] = _safe(lambda: finnhub('stock/recommendation')[:3], gaps, 'Finnhub ratings')

        def insider_sentiment():
            data = finnhub('stock/insider-sentiment', **{'from': str(today - timedelta(days=180)),
                                                           'to': str(today)}).get('data', [])
            return [{'month': '%d-%02d' % (d['year'], d['month']), 'net_shares': d.get('change'),
                     'mspr': round(d.get('mspr', 0), 1)} for d in data[-6:]]
        out['insider_sentiment'] = _safe(insider_sentiment, gaps, 'Finnhub insider sentiment')
    else:
        gaps.append('Finnhub key not configured: no headlines or insider sentiment from Finnhub')

    if zacks_fn:
        out['zacks'] = _safe(lambda: zacks_fn(symbol), gaps, 'Zacks')
        if out['zacks'] and out['zacks'].get('error'):
            gaps.append('Zacks: %s' % out['zacks']['error'])
            out['zacks'] = None

    out['stats'] = technicals(out.get('hist'))
    out['performance'] = performance_table(out.get('hist'), out.get('spy'))
    out['market'] = market_context(out)
    return out


def market_context(data):
    """The backdrop: is the broad market helping or hurting."""
    ctx = {}
    spy, qqq, vix = _closes(data.get('spy')), _closes(data.get('qqq')), _closes(data.get('vix'))
    if spy is not None:
        ctx['spy_1m'], ctx['spy_3m'] = period_return(spy, 21), period_return(spy, 63)
        if len(spy) >= 200:
            ctx['spy_vs_200d'] = float(spy.iloc[-1]) / float(spy.iloc[-200:].mean()) - 1
    if qqq is not None:
        ctx['qqq_1m'], ctx['qqq_3m'] = period_return(qqq, 21), period_return(qqq, 63)
    if vix is not None:
        ctx['vix'] = float(vix.iloc[-1])
        ctx['vix_1m_ago'] = float(vix.iloc[-22]) if len(vix) > 22 else None
    return ctx


# --------------------------------------------------------------------------- AI legs
# Every leg returns the same shape, so the orchestrator and the cost line treat
# them alike:  {'name', 'ok', 'skipped', 'text', 'cost', 'seconds', 'error', 'citations'}

def _leg(name):
    return {'name': name, 'ok': False, 'skipped': False, 'text': '', 'cost': 0.0,
            'seconds': 0.0, 'error': None, 'citations': [], 'detail': ''}


def _research_question(symbol, name, facts, today):
    return (
        "Today is %s. I own %s shares of %s (%s), bought at an average of %s, now about %s "
        "(%s). I am deciding whether to SELL, HOLD or ADD.\n\n"
        "Research it as an investor would, using current information. Cover, with dates:\n"
        "1. The latest company news and what it means for the stock.\n"
        "2. Why the stock moved over the last month and quarter.\n"
        "3. Recent analyst rating and price-target changes, and the consensus.\n"
        "4. Insider and institutional buying or selling.\n"
        "5. Upcoming catalysts and dates (earnings, product, regulatory, macro).\n"
        "6. Sector and market conditions that affect it, and how the stock trades against them.\n"
        "7. The main risks and the bear case, then the bull case.\n"
        "Be specific and quantitative, give dates and numbers, and say plainly where sources "
        "disagree or information is thin. Do not pad; no generic disclaimers."
    ) % (today, ('%g' % facts['shares']), symbol, name, usd(facts['avg_cost']), usd(facts['price']),
         pct(facts['pl_pct']) + ' on cost')


def ask_perplexity_finance(symbol, name, facts, key, today=None, session=requests):
    """Perplexity Sonar Pro, searching only finance and news domains."""
    leg = _leg('Perplexity finance (sonar-pro)')
    if not key:
        leg.update(skipped=True, error='PERPLEXITY_API_KEY not set')
        return leg
    started = time.time()
    try:
        response = session.post(
            'https://api.perplexity.ai/chat/completions',
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
            json={'model': PPLX_FINANCE_MODEL, 'temperature': 0.2, 'max_tokens': 2200,
                  'search_domain_filter': FINANCE_DOMAINS, 'search_recency_filter': 'month',
                  'web_search_options': {'search_context_size': 'high'},
                  'messages': [
                      {'role': 'system', 'content': 'You are a precise equity research analyst with live web '
                                                    'access. Cite dates and figures. Never invent data.'},
                      {'role': 'user', 'content': _research_question(symbol, name, facts,
                                                                     today or date.today().isoformat())}]},
            timeout=120)
        _read_perplexity(leg, response)
    except Exception as e:
        leg['error'] = '%s: %s' % (type(e).__name__, str(e)[:120])
    leg['seconds'] = round(time.time() - started, 1)
    return leg


def ask_perplexity_deep(symbol, name, facts, key, today=None, session=requests, effort='low'):
    """Perplexity Sonar Deep Research: slower and dearer, reads far more sources."""
    leg = _leg('Perplexity deep research')
    if not key:
        leg.update(skipped=True, error='PERPLEXITY_API_KEY not set')
        return leg
    started = time.time()
    body = {'model': PPLX_DEEP_MODEL, 'max_tokens': 4000, 'reasoning_effort': effort,
            'messages': [{'role': 'user', 'content': _research_question(
                symbol, name, facts, today or date.today().isoformat())}]}
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    try:
        response = session.post('https://api.perplexity.ai/chat/completions', headers=headers,
                                json=body, timeout=420)
        if response.status_code == 400:        # an option this account's API does not take
            body.pop('reasoning_effort', None)
            response = session.post('https://api.perplexity.ai/chat/completions', headers=headers,
                                    json=body, timeout=420)
        _read_perplexity(leg, response)
    except Exception as e:
        leg['error'] = '%s: %s' % (type(e).__name__, str(e)[:120])
    leg['seconds'] = round(time.time() - started, 1)
    return leg


def _read_perplexity(leg, response):
    if response.status_code != 200:
        leg['error'] = 'HTTP %s: %s' % (response.status_code, response.text[:140])
        return
    body = response.json()
    leg['text'] = (body['choices'][0]['message']['content'] or '').strip()
    # Deep Research prints its chain of thought inside <think>; it is not research.
    leg['text'] = re.sub(r'<think>.*?</think>', '', leg['text'], flags=re.S).strip()
    usage = body.get('usage') or {}
    cost = (usage.get('cost') or {}).get('total_cost')
    leg['cost'] = float(cost) if cost is not None else 0.0
    leg['detail'] = '%s tokens' % usage.get('total_tokens', '?')
    leg['citations'] = (body.get('citations') or [])[:40]
    leg['ok'] = bool(leg['text'])
    if not leg['ok']:
        leg['error'] = 'empty answer'


# --------------------------------------------------------------------------- the dossier and the verdict

SYSTEM_PROMPT = """You are a senior equity analyst advising ONE private investor on a position they already hold. \
They will act on your answer with real money, so be rigorous and honest about uncertainty.

Rules:
- Decide exactly one action: SELL_ALL, SELL_PART, HOLD or ADD. SELL_PART requires a sell_fraction between 0.1 and 0.9.
- Ground every reason in the supplied evidence and name which kind of evidence it is. Where the research texts \
disagree with the hard market data in the dossier, trust the market data and say so. Never invent numbers, \
dates, ratings or news that are not in the material.
- Weigh the TAX and POSITION facts you are given: selling a loser banks a tax shield, selling a winner pays \
25% after any shield, and a stock that is a large share of the portfolio carries concentration risk. Do not \
recommend a sale merely because it is profitable, nor a hold merely because it is a loss. Judge the outlook.
- Compare against the alternative actions. A HOLD or ADD must be defended against selling, and vice versa.
- ADD is only sensible with free cash; the user's free cash is given. Say when to add: now, or on a dip to a price.
- Give concrete price levels, a time horizon, and a review date. The levels become alerts the user is notified on.
- price_targets.take_profit must be above the current price; add_below and review_below must be below it. \
review_below is the level at which the thesis is broken and the position should be re-examined or cut.
- Give a bull, base and bear scenario with a price and probability each (probabilities sum to about 100).
- Be calibrated: confidence is your honest probability that this action beats the alternatives over the horizon, \
not enthusiasm. If the evidence is mixed, say HOLD with modest confidence rather than forcing a call.
- Output ONLY one JSON object, no prose before or after, no markdown fences."""

OUTPUT_SCHEMA = """{
  "action": "SELL_ALL | SELL_PART | HOLD | ADD",
  "confidence": 0-100,
  "headline": "one sentence a busy person can act on",
  "sell_fraction": 0.1-0.9 or null,
  "add_budget_pct_of_free_cash": 0-100 or null,
  "add_when": {"mode": "now | on_dip | after_event | null", "price": number or null, "condition": "string"},
  "reasons": [{"factor": "performance|technicals|analysts|zacks|insiders|news|market|valuation|tax|position_size|risk",
               "stance": "bullish|bearish|neutral", "weight": "high|medium|low", "point": "specific, evidenced"}],
  "performance_view": {"short": "1w-1m read", "medium": "3-6m read", "long": "1-3y read"},
  "outlook": "what you expect to happen and why, in 2-4 sentences",
  "scenarios": [{"name": "bull|base|bear", "price": number, "probability_pct": number, "why": "string"}],
  "price_targets": {"take_profit": [numbers above price, ascending], "add_below": number or null,
                    "review_below": number or null, "fair_value_estimate": number or null},
  "hold_plan": {"hold_until": "a date or a condition", "horizon": "weeks | months | quarters",
                "review_date": "YYYY-MM-DD", "exit_triggers": ["string"],
                "catalysts": [{"date": "string", "event": "string"}]},
  "risks": ["string"],
  "what_would_change_my_mind": ["string"],
  "tax_comment": "how tax and the shield bear on this decision",
  "data_gaps": ["anything important you could not verify"]
}"""


def _fmt(value, spec='%.2f', none='n/a'):
    return none if value is None else spec % value


def build_dossier(facts, data, research, options, previous=None, today=None):
    """Everything the model gets to see, as one document."""
    today = today or date.today().isoformat()
    stats = data.get('stats') or {}
    lines = ['TODAY: %s' % today, '',
             '=== YOUR POSITION: %s (%s) ===' % (facts['symbol'], data.get('name', facts['symbol']))]
    lines.append('Shares %g | average cost %s (incl. buy commission) | price now %s'
                 % (facts['shares'], usd(facts['avg_cost']), usd(facts['price'])))
    lines.append('Position value %s | unrealized P/L %s (%s)'
                 % (usd(facts['value']), signed_usd(facts['pl']), pct(facts['pl_pct'])))
    if facts.get('weight') is not None:
        lines.append('Share of the stock portfolio: %.1f%%' % (facts['weight'] * 100))
    if facts.get('days_held') is not None:
        lines.append('Held for %d days (first bought %s)' % (facts['days_held'], facts['purchase_date']))
    else:
        lines.append('Holding period: built over several purchases')
    lines.append('FREE CASH available: %s | banked tax shield: %s | assumed sell commission: %s'
                 % (usd(facts['free_cash']), usd(facts['shield']), usd(facts['sell_commission'])))
    lines += ['', '=== WHAT SELLING WOULD DO TODAY (computed, 25% tax with shield) ===']
    for label, opt in options.items():
        lines.append('Sell %s (%g sh): net cash %s | P/L %s | tax withheld %s | shield used %s | shield banked %s'
                     % (label, opt['shares'], usd(opt['net_cash']), signed_usd(opt['pl']),
                        usd(opt['tax_withheld']), usd(opt['shield_used']), usd(opt['shield_earned'])))

    lines += ['', '=== PERFORMANCE vs SPY (stock / SPY / relative) ===']
    for row in data.get('performance', []):
        lines.append('%s (%s term): %s / %s / %s' % (row['window'], row['horizon'], pct(row['stock']) or 'n/a',
                                                      pct(row['bench']) or 'n/a', pct(row['relative']) or 'n/a'))
    lines += ['', '=== TECHNICALS ===']
    if stats:
        lines.append('Price %s | 20d %s | 50d %s | 200d %s | trend: %s'
                     % (_fmt(stats.get('price')), _fmt(stats.get('sma20')), _fmt(stats.get('sma50')),
                        _fmt(stats.get('sma200')), stats.get('trend', 'n/a')))
        lines.append('52w range %s - %s | from high %s | from low %s'
                     % (_fmt(stats.get('low_52w')), _fmt(stats.get('high_52w')),
                        pct(stats.get('from_high')) or 'n/a', pct(stats.get('from_low')) or 'n/a'))
        lines.append('RSI14 %s | annualized volatility %s | max drawdown 1y %s | ATR14 %s'
                     % (_fmt(stats.get('rsi14'), '%.0f'), pct(stats.get('volatility'), 0, sign=False) or 'n/a',
                        pct(stats.get('max_drawdown_1y'), 0) or 'n/a', _fmt(stats.get('atr14'))))
        lines.append('60-day support %s | 60-day resistance %s'
                     % (_fmt(stats.get('support_recent')), _fmt(stats.get('resistance_recent'))))
    else:
        lines.append('unavailable')

    lines += ['', '=== VALUATION ===',
              'Sector %s / %s | P/E %s | forward P/E %s | beta %s | market cap %s'
              % (data.get('sector'), data.get('industry'), _fmt(data.get('pe'), '%.1f'),
                 _fmt(data.get('forward_pe'), '%.1f'), _fmt(data.get('beta'), '%.2f'),
                 ('$%.1fB' % (data['market_cap'] / 1e9)) if data.get('market_cap') else 'n/a')]

    lines += ['', '=== ANALYSTS ===']
    t = data.get('targets') or {}
    if t:
        upside = (t['mean'] / facts['price'] - 1) if t.get('mean') else None
        lines.append('Price targets: mean %s | median %s | low %s | high %s | mean implies %s vs now'
                     % (_fmt(t.get('mean')), _fmt(t.get('median')), _fmt(t.get('low')), _fmt(t.get('high')),
                        pct(upside) or 'n/a'))
    r = data.get('ratings')
    if r:
        lines.append('Ratings (Yahoo): strong buy %d, buy %d, hold %d, sell %d, strong sell %d'
                     % (r['strongBuy'], r['buy'], r['hold'], r['sell'], r['strongSell']))
    for item in (data.get('finnhub_ratings') or [])[:2]:
        lines.append('Ratings (Finnhub %s): strong buy %s, buy %s, hold %s, sell %s, strong sell %s'
                     % (item.get('period'), item.get('strongBuy'), item.get('buy'), item.get('hold'),
                        item.get('sell'), item.get('strongSell')))
    a = data.get('actions')
    if a:
        lines.append('Last %d days: %d upgrades, %d downgrades' % (a['days'], a['upgrades'], a['downgrades']))
        for row in a['recent'][:6]:
            lines.append('  %s %s: %s %s -> %s%s' % (row['date'], row['firm'], row['action'], row['from'], row['to'],
                                                    (' PT %s' % row['target']) if row.get('target') else ''))
    z = data.get('zacks')
    if z and z.get('rank'):
        lines.append('Zacks Rank: %s (%s) | industry: %s | style scores: %s'
                     % (z['rank'], z['rank_text'], z.get('industry_rank'), z.get('style_scores') or 'n/a'))
    else:
        lines.append('Zacks: unavailable')

    lines += ['', '=== INSIDERS ===']
    ins = data.get('insiders')
    if ins:
        lines.append('Last %d days: %d buys (%s sh, %s) vs %d sells (%s sh, %s)'
                     % (ins['days'], ins['buys'], format(ins['buy_shares'], ',.0f'), usd(ins['buy_value']),
                        ins['sells'], format(ins['sell_shares'], ',.0f'), usd(ins['sell_value'])))
    for row in data.get('insider_sentiment') or []:
        lines.append('  %s: net shares %s, MSPR %s' % (row['month'], row['net_shares'], row['mspr']))

    lines += ['', '=== EARNINGS ===']
    e = data.get('earnings') or {}
    lines.append('Next earnings: %s | consensus EPS %s | consensus revenue %s'
                 % (e.get('date') or 'unknown', _fmt(e.get('eps_avg')), e.get('revenue_avg') or 'n/a'))

    lines += ['', '=== MARKET BACKDROP ===']
    m = data.get('market') or {}
    lines.append('SPY 1m %s, 3m %s, vs 200d %s | QQQ 1m %s, 3m %s | VIX %s (a month ago %s)'
                 % (pct(m.get('spy_1m')) or 'n/a', pct(m.get('spy_3m')) or 'n/a', pct(m.get('spy_vs_200d')) or 'n/a',
                    pct(m.get('qqq_1m')) or 'n/a', pct(m.get('qqq_3m')) or 'n/a',
                    _fmt(m.get('vix'), '%.1f'), _fmt(m.get('vix_1m_ago'), '%.1f')))

    lines += ['', '=== HEADLINES (Finnhub, last 14 days) ===']
    for row in (data.get('news') or [])[:12]:
        lines.append('%s [%s] %s' % (row['date'], row['source'], row['headline']))
    if not data.get('news'):
        lines.append('none retrieved')

    for leg in research:
        lines += ['', '=== RESEARCH: %s ===' % leg['name']]
        lines.append(leg['text'][:9000] if leg['ok'] else '(not available: %s)' % leg['error'])

    if previous:
        lines += ['', '=== YOUR PREVIOUS CALL ON THIS STOCK ===',
                  '%s: %s at %s, confidence %s%%. Headline: %s'
                  % (previous['date'], previous['action'], usd(previous['price']), previous.get('confidence'),
                     previous.get('headline', ''))]
    if data.get('gaps'):
        lines += ['', '=== DATA GAPS ==='] + ['- ' + g for g in data['gaps']]
    return '\n'.join(lines)


def decision_request(dossier):
    return ('%s\n\n----\nReturn ONE JSON object in exactly this shape (keys as shown):\n%s' % (dossier, OUTPUT_SCHEMA))


def ask_opus(client, dossier, effort='high'):
    """Claude Opus 5.5 reads the dossier and returns the verdict as text."""
    leg = _leg('Claude Opus 5.5')
    started = time.time()
    messages = [{'role': 'user', 'content': decision_request(dossier)}]
    try:
        try:
            message = client.messages.create(model=OPUS_MODEL, max_tokens=12000, system=SYSTEM_PROMPT,
                                             thinking={'type': 'adaptive'}, output_config={'effort': effort},
                                             messages=messages)
        except Exception as first:
            if 'thinking' not in str(first).lower() and 'output_config' not in str(first).lower():
                raise
            message = client.messages.create(model=OPUS_MODEL, max_tokens=12000, system=SYSTEM_PROMPT,
                                             messages=messages)
        leg['text'] = ''.join(getattr(b, 'text', '') for b in message.content
                              if getattr(b, 'type', None) == 'text').strip()
        usage = message.usage
        leg['cost'] = (usage.input_tokens * OPUS_IN + usage.output_tokens * OPUS_OUT) / 1e6
        leg['detail'] = '%s in / %s out tokens' % (format(usage.input_tokens, ','), format(usage.output_tokens, ','))
        leg['ok'] = bool(leg['text'])
        if not leg['ok']:
            leg['error'] = 'empty answer'
    except Exception as e:
        leg['error'] = '%s: %s' % (type(e).__name__, str(e)[:160])
    leg['seconds'] = round(time.time() - started, 1)
    return leg


# --------------------------------------------------------------------------- reading the verdict

def extract_json(text):
    """The first complete JSON object in `text`, tolerating fences and chatter."""
    if not text:
        return None
    text = re.sub(r'```(?:json)?', '', text)
    start = text.find('{')
    while start != -1:
        depth, in_string, escaped = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == '\\':
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    chunk = text[start:i + 1]
                    for candidate in (chunk, re.sub(r',\s*([}\]])', r'\1', chunk)):
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                return parsed
                        except ValueError:
                            pass
                    break
        start = text.find('{', start + 1)
    return None


def _number(value):
    try:
        number = float(str(value).replace('$', '').replace(',', ''))
        return number if math.isfinite(number) and number > 0 else None
    except (TypeError, ValueError):
        return None


def _text(value, limit=500):
    """Trim to `limit`, and say so: a sentence that just stops reads like a bug."""
    text = str(value or '').strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def _text_list(values, limit=8, size=300):
    return [_text(v, size) for v in (values or []) if _text(v)][:limit] if isinstance(values, list) else []


def normalize_decision(raw, price):
    """Turn whatever the model returned into a verdict the rest of the code can
    trust, recording every correction so none is silent."""
    warnings = []
    raw = raw if isinstance(raw, dict) else {}

    action = str(raw.get('action', '')).upper().replace(' ', '_')
    if action not in ACTIONS:
        warnings.append('Unrecognised action %r: treated as HOLD.' % raw.get('action'))
        action = HOLD

    try:
        confidence = int(round(float(raw.get('confidence', 50))))
    except (TypeError, ValueError):
        confidence = 50
        warnings.append('No usable confidence: shown as 50.')
    confidence = max(0, min(100, confidence))

    fraction = None
    if action == SELL_PART:
        try:
            fraction = float(raw.get('sell_fraction'))
        except (TypeError, ValueError):
            fraction = 0.5
            warnings.append('SELL_PART gave no fraction: 50% assumed.')
        if fraction >= 0.95:
            action, fraction = SELL_ALL, None
            warnings.append('A fraction of 95%+ was treated as selling everything.')
        elif fraction < 0.1:
            fraction = 0.1
            warnings.append('Fraction raised to the 10% minimum.')

    targets_in = raw.get('price_targets') if isinstance(raw.get('price_targets'), dict) else {}
    take = sorted({round(n, 2) for n in (_number(v) for v in (targets_in.get('take_profit') or [])
                                         if v is not None) if n})
    kept_take = [n for n in take if n > price * 1.005][:3]
    if len(kept_take) != len(take):
        warnings.append('Dropped take-profit levels that were not above the current price.')
    add_below, review_below = _number(targets_in.get('add_below')), _number(targets_in.get('review_below'))
    if add_below and add_below >= price * 0.995:
        add_below = None
        warnings.append('Dropped an add-below level that was not below the current price.')
    if review_below and review_below >= price * 0.995:
        review_below = None
        warnings.append('Dropped a review-below level that was not below the current price.')

    reasons = []
    for item in (raw.get('reasons') or [])[:10]:
        if isinstance(item, dict) and _text(item.get('point')):
            reasons.append({'factor': _text(item.get('factor'), 30).lower() or 'other',
                            'stance': (_text(item.get('stance'), 12).lower() if _text(item.get('stance'), 12).lower()
                                       in ('bullish', 'bearish', 'neutral') else 'neutral'),
                            'weight': (_text(item.get('weight'), 8).lower() if _text(item.get('weight'), 8).lower()
                                       in ('high', 'medium', 'low') else 'medium'),
                            'point': _text(item.get('point'), 700)})

    scenarios = []
    for item in (raw.get('scenarios') or [])[:3]:
        if isinstance(item, dict) and _number(item.get('price')):
            try:
                probability = max(0.0, min(100.0, float(item.get('probability_pct', 0))))
            except (TypeError, ValueError):
                probability = 0.0
            scenarios.append({'name': _text(item.get('name'), 10).lower() or 'scenario',
                              'price': _number(item.get('price')), 'probability': probability,
                              'why': _text(item.get('why'), 400)})
    total = sum(s['probability'] for s in scenarios)
    if scenarios and not 90 <= total <= 110:
        warnings.append('Scenario probabilities add up to %.0f%%, not 100%%.' % total)

    when = raw.get('add_when') if isinstance(raw.get('add_when'), dict) else {}
    plan = raw.get('hold_plan') if isinstance(raw.get('hold_plan'), dict) else {}
    view = raw.get('performance_view') if isinstance(raw.get('performance_view'), dict) else {}
    budget = None
    if action == ADD:
        try:
            budget = max(0.0, min(100.0, float(raw.get('add_budget_pct_of_free_cash', 100))))
        except (TypeError, ValueError):
            budget = 100.0

    return {
        'action': action, 'confidence': confidence, 'sell_fraction': fraction,
        'add_budget_pct': budget,
        'add_when': {'mode': _text(when.get('mode'), 20).lower() or None, 'price': _number(when.get('price')),
                     'condition': _text(when.get('condition'), 300)},
        'headline': _text(raw.get('headline'), 400), 'outlook': _text(raw.get('outlook'), 900),
        'reasons': reasons,
        'performance_view': {k: _text(view.get(k), 450) for k in ('short', 'medium', 'long')},
        'scenarios': scenarios,
        'price_targets': {'take_profit': kept_take, 'add_below': add_below, 'review_below': review_below,
                          'fair_value': _number(targets_in.get('fair_value_estimate'))},
        'hold_plan': {'hold_until': _text(plan.get('hold_until'), 450), 'horizon': _text(plan.get('horizon'), 20),
                      'review_date': _text(plan.get('review_date'), 12),
                      'exit_triggers': _text_list(plan.get('exit_triggers'), 6, 380),
                      'catalysts': [{'date': _text(c.get('date'), 40), 'event': _text(c.get('event'), 280)}
                                    for c in (plan.get('catalysts') or []) if isinstance(c, dict)][:6]},
        'risks': _text_list(raw.get('risks'), 6, 340), 'change_my_mind': _text_list(raw.get('what_would_change_my_mind'), 5),
        'tax_comment': _text(raw.get('tax_comment'), 500), 'data_gaps': _text_list(raw.get('data_gaps'), 6),
        'warnings': warnings,
    }


# --------------------------------------------------------------------------- the money and the alerts

def derive_plan(decision, facts):
    """Turn the verdict into amounts: what to sell and what it nets, or what an add
    would cost and whether the free cash covers it."""
    plan = {'action': decision['action'], 'sale': None, 'reference_sale': sale_math(facts, facts['shares']),
            'add': None}
    action = decision['action']

    if action == SELL_ALL:
        plan['sale'] = sale_math(facts, facts['shares'])
    elif action == SELL_PART:
        shares = whole_shares(facts, decision['sell_fraction'])
        plan['sale'] = sale_math(facts, shares)

    if action == ADD:
        cash = facts['free_cash']
        budget = cash * (decision['add_budget_pct'] or 0) / 100
        when = decision['add_when']
        add_price = when['price'] if (when['mode'] == 'on_dip' and when['price']
                                      and when['price'] < facts['price']) else facts['price']
        affordable = math.floor(budget / add_price) if add_price else 0
        plan['add'] = {'free_cash': cash, 'budget': round(budget, 2), 'at_price': add_price,
                       'shares': affordable, 'cost': round(affordable * add_price, 2),
                       'one_share': round(add_price, 2), 'enough_cash': affordable >= 1,
                       'when_mode': when['mode'], 'condition': when['condition']}
        if affordable >= 1:
            new_shares = facts['shares'] + affordable
            new_cost = facts['total_cost'] + affordable * add_price
            plan['add'].update(new_shares=new_shares, new_avg=new_cost / new_shares)
        else:
            plan['add']['cash_needed'] = round(max(0.0, add_price - cash), 2)
    return plan


def build_alert_specs(symbol, decision, facts, today=None):
    """The price levels in the verdict, as alert descriptions ready to be saved."""
    today = today or date.today().isoformat()
    action = ACTION_LABEL[decision['action']]
    targets = decision['price_targets']
    specs = []

    def note(kind, level, why):
        return ('\U0001F916 /shouldisell research on %s (called %s at %s, %s%% confident): %s %s. %s'
                % (today, action, usd(facts['price']), decision['confidence'], kind, usd(level), why)).strip()

    reason = decision['headline']
    for i, level in enumerate(targets['take_profit'], 1):
        specs.append({'direction': 'UP', 'price': level,
                      'note': note('take-profit target %d' % i if len(targets['take_profit']) > 1 else 'take-profit target',
                                   level, reason)})
    if targets['add_below']:
        specs.append({'direction': 'DOWN', 'price': targets['add_below'],
                      'note': note('add / buy level', targets['add_below'], decision['add_when']['condition'] or reason)})
    if targets['review_below']:
        specs.append({'direction': 'DOWN', 'price': targets['review_below'],
                      'note': note('stop / re-examine level', targets['review_below'],
                                   '; '.join(decision['hold_plan']['exit_triggers'][:2]) or reason)})
    return specs


def make_alert(symbol, name, price, spec, now=None):
    """One entry in the exact shape /pricealert stores, so the existing monitor,
    /pricealert list and /triggered all handle it without knowing where it came from."""
    now = now or datetime.now()
    level = float(spec['price'])
    return {
        'symbol': symbol, 'name': name, 'direction': spec['direction'], 'alert_type': 'price_target',
        'base_price': round(price, 2), 'base_type': 'current', 'open_price': round(price, 2),
        'current_price': round(price, 2), 'target_price': round(level, 2),
        'percent': round(abs(level - price) / price * 100, 2), 'note': spec['note'][:900],
        'created_at': now.strftime('%Y-%m-%d %H:%M'), 'triggered': False, 'triggered_at': None,
        'source': 'shouldisell',
    }


def merge_alerts(existing, new_alerts, symbol):
    """Replace this stock's earlier /shouldisell alerts with the new ones.

    Alerts the user set themselves, and ones already triggered, are never touched:
    only still-pending alerts that this feature created for `symbol` are replaced.
    Returns (merged, number_replaced).
    """
    kept, replaced = [], 0
    for alert in existing:
        if (alert.get('source') == 'shouldisell' and alert.get('symbol') == symbol
                and not alert.get('triggered')):
            replaced += 1
        else:
            kept.append(alert)
    return kept + list(new_alerts), replaced


# --------------------------------------------------------------------------- history

def load_history(path=None):
    try:
        with open(path or HISTORY_FILE, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError, OSError):
        return []


def last_call(symbol, path=None):
    rows = [r for r in load_history(path) if r.get('symbol') == symbol]
    return rows[-1] if rows else None


def record_call(symbol, facts, decision, plan, cost, path=None):
    rows = load_history(path)
    rows.append({
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'), 'symbol': symbol, 'price': round(facts['price'], 2),
        'action': decision['action'], 'confidence': decision['confidence'], 'headline': decision['headline'],
        'sell_fraction': decision['sell_fraction'], 'shares_held': facts['shares'],
        'targets': decision['price_targets'], 'review_date': decision['hold_plan']['review_date'],
        'cost_usd': round(cost, 3),
    })
    with open(path or HISTORY_FILE, 'w', encoding='utf-8') as fh:
        json.dump(rows[-500:], fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- orchestration

async def research(symbol, portfolio, keys, *, quick=False, zacks_fn=None, progress=None, legs=None,
                   weight_fn=None, history_path=None):
    """Run the whole pipeline for one held stock and return everything needed to
    report on it. Nothing is written here except the history entry."""
    legs = legs or {}

    async def say(text):
        if progress:
            try:
                await progress(text)
            except Exception:
                pass

    market_fn = legs.get('market') or (lambda: fetch_market(symbol, keys.get('finnhub'), zacks_fn))
    await say('\U0001F4CA Pulling price history, analysts, insiders, Zacks and news...')
    data = await asyncio.to_thread(market_fn)
    price = data.get('price')
    if not price:
        return {'error': 'No price available for %s right now.' % symbol}

    weight = None
    if weight_fn:
        try:
            weight = await asyncio.to_thread(weight_fn, symbol, price)
        except Exception:
            weight = None
    facts = position_facts(portfolio, symbol, price, weight)
    if not facts:
        return {'error': '%s is not in your portfolio.' % symbol}
    name = data.get('name', symbol)

    pplx_key = keys.get('perplexity')
    jobs = [
        ('finance', legs.get('pplx_finance') or (lambda: ask_perplexity_finance(symbol, name, facts, pplx_key))),
    ]
    if not quick:
        jobs.append(('deep', legs.get('pplx_deep') or (lambda: ask_perplexity_deep(symbol, name, facts, pplx_key))))
    await say('\U0001F50E Researching the news and context (%s)...' %
              ('Perplexity finance' if quick else 'Perplexity finance + Deep Research'))
    outcomes = await asyncio.gather(*[asyncio.to_thread(fn) for _, fn in jobs], return_exceptions=True)
    research_legs = []
    for (label, _), outcome in zip(jobs, outcomes):
        if isinstance(outcome, Exception):
            leg = _leg(label)
            leg['error'] = '%s: %s' % (type(outcome).__name__, str(outcome)[:120])
            outcome = leg
        research_legs.append(outcome)

    options = sale_options(facts)
    previous = last_call(symbol, history_path)
    dossier = build_dossier(facts, data, [leg for leg in research_legs if leg['ok']] or research_legs,
                            options, previous)

    await say('\U0001F9E0 Opus 5.5 is weighing it all up...')
    opus_fn = legs.get('opus') or (lambda: ask_opus(keys['anthropic_client'], dossier,
                                                     'medium' if quick else 'high'))
    opus = await asyncio.to_thread(opus_fn)
    parsed = extract_json(opus['text']) if opus['ok'] else None
    if opus['ok'] and parsed is None:
        # One retry, asking for the JSON alone; the first answer's cost still counts.
        await say('♻️ Reformatting the verdict...')
        retry_fn = legs.get('opus_retry') or (lambda: ask_opus(
            keys['anthropic_client'], dossier + '\n\nYour previous answer was not valid JSON. '
                                                'Return ONLY the JSON object.', 'low'))
        retry = await asyncio.to_thread(retry_fn)
        opus['cost'] += retry['cost']
        parsed = extract_json(retry['text']) if retry['ok'] else None

    # Counted before anything can fail below: a run that ends in an error has
    # still been billed, and the credit estimate must not forget it.
    try:
        api_spend.record_spend(research_legs + [opus], symbol)
    except Exception:
        pass                      # bookkeeping must never cost the user their research
    if parsed is None:
        return {'error': 'The model did not return a usable verdict (%s).' % (opus.get('error') or 'bad format'),
                'legs': research_legs + [opus], 'facts': facts, 'data': data,
                'cost': sum(leg['cost'] for leg in research_legs + [opus])}

    decision = normalize_decision(parsed, price)
    plan = derive_plan(decision, facts)
    all_legs = research_legs + [opus]
    total_cost = round(sum(leg['cost'] for leg in all_legs), 4)
    record_call(symbol, facts, decision, plan, total_cost, history_path)
    return {'symbol': symbol, 'name': name, 'facts': facts, 'data': data, 'decision': decision, 'plan': plan,
            'legs': all_legs, 'cost': total_cost, 'previous': previous, 'quick': quick,
            'alert_specs': build_alert_specs(symbol, decision, facts)}


# --------------------------------------------------------------------------- messages

def _stance_emoji(stance):
    return {'bullish': '\U0001F7E2', 'bearish': '\U0001F534'}.get(stance, '⚪')


def format_report(result, alert_info=None):
    """The report as a list of messages, each under Telegram's size limit."""
    facts, data, decision, plan = result['facts'], result['data'], result['decision'], result['plan']
    action = decision['action']
    sym = result['symbol']
    out = []

    # 1 -- verdict and position
    head = ['%s *%s — %s*  _(confidence %d%%)_' % (ACTION_EMOJI[action], ACTION_LABEL[action], sym,
                                                       decision['confidence'])]
    if action == SELL_PART and plan['sale']:
        sale = plan['sale']
        head[0] = '%s *SELL PART — %s: %g of %g shares*  _(confidence %d%%)_' % (
            ACTION_EMOJI[action], sym, sale['shares'], facts['shares'], decision['confidence'])
    if decision['headline']:
        head.append('_%s_' % md(decision['headline']))
    head += ['', '\U0001F4E6 *Your position*',
             '   %g shares · avg cost %s · now *%s*' % (facts['shares'], usd(facts['avg_cost']), usd(facts['price'])),
             '   Value %s · P/L *%s* (%s)' % (usd(facts['value']), signed_usd(facts['pl']), pct(facts['pl_pct']))]
    if facts.get('weight') is not None:
        head.append('   %.1f%% of your stock portfolio' % (facts['weight'] * 100))
    head.append('   Free cash %s · banked tax shield %s' % (usd(facts['free_cash']), usd(facts['shield'])))
    prev = result.get('previous')
    if prev:
        moved = facts['price'] / prev['price'] - 1 if prev.get('price') else None
        head.append('   _Last time (%s): %s at %s%s_' % (
            prev['date'][:10], ACTION_LABEL.get(prev['action'], prev['action']), usd(prev['price']),
            (', since then %s' % pct(moved)) if moved is not None else ''))
    out.append('\n'.join(head))

    # 2 -- why
    why = ['\U0001F9E0 *WHY*', '━' * 16, '']
    for reason in decision['reasons']:
        weight = {'high': '●●●', 'medium': '●●○', 'low': '●○○'}[reason['weight']]
        why.append('%s %s _%s_ · %s' % (_stance_emoji(reason['stance']), md(reason['factor'].replace('_', ' ')).upper(),
                                              weight, md(reason['point'])))
    if decision['outlook']:
        why += ['', '\U0001F52E *What I expect*', md(decision['outlook'])]
    out.append('\n'.join(why))

    # 3 -- performance and evidence
    perf = ['\U0001F4CA *PERFORMANCE*  _(vs SPY)_', '`      stock    SPY   vs SPY`']
    for row in data.get('performance', []):
        perf.append('`%-3s %7s %7s %7s`' % (row['window'], pct(row['stock']) or 'n/a', pct(row['bench']) or 'n/a',
                                             pct(row['relative']) or 'n/a'))
    view = decision['performance_view']
    for label, key in (('Short', 'short'), ('Medium', 'medium'), ('Long', 'long')):
        if view.get(key):
            perf.append('• *%s:* %s' % (label, md(view[key])))
    stats = data.get('stats') or {}
    if stats:
        perf += ['', '\U0001F4C8 *Technicals*',
                 '• %s' % md(stats.get('trend', 'n/a')),
                 '• RSI %s · 52w range %s–%s (%s from high)' % (
                     _fmt(stats.get('rsi14'), '%.0f'), _fmt(stats.get('low_52w')), _fmt(stats.get('high_52w')),
                     pct(stats.get('from_high')) or 'n/a'),
                 '• Volatility %s · worst drawdown 1y %s' % (pct(stats.get('volatility'), 0, sign=False) or 'n/a',
                                                                      pct(stats.get('max_drawdown_1y'), 0) or 'n/a')]
    ev = ['', '\U0001F3AF *Street view*']
    t = data.get('targets') or {}
    if t.get('mean'):
        ev.append('• Analyst targets: mean %s · median %s · range %s–%s (mean %s vs now)' % (
            usd(t['mean']), usd(t.get('median')), usd(t.get('low')), usd(t.get('high')),
            pct(t['mean'] / facts['price'] - 1)))
    r = data.get('ratings')
    if r:
        ev.append('• Ratings: %d strong buy · %d buy · %d hold · %d sell · %d strong sell' % (
            r['strongBuy'], r['buy'], r['hold'], r['sell'], r['strongSell']))
    a = data.get('actions')
    if a:
        ev.append('• Last %dd: %d upgrades, %d downgrades' % (a['days'], a['upgrades'], a['downgrades']))
    z = data.get('zacks')
    if z and z.get('rank'):
        ev.append('• Zacks Rank %s — %s' % (z['rank'], md(z['rank_text'])))
    ins = data.get('insiders')
    if ins:
        ev.append('• Insiders (%dd): %d buys vs %d sells (%s sold)' % (
            ins['days'], ins['buys'], ins['sells'], usd_short(ins['sell_value'])))
    e = data.get('earnings') or {}
    if e.get('date'):
        ev.append('• Next earnings: %s' % e['date'])
    out.append('\n'.join(perf + ev))

    # 4 -- money
    money = []
    if action in (SELL_ALL, SELL_PART) and plan['sale']:
        money += _sale_block('IF YOU SELL: %g of %g shares' % (plan['sale']['shares'], facts['shares']), plan['sale'],
                             facts)
        if action == SELL_PART:
            money.append('   Keeps *%g shares* running.' % plan['sale']['remaining_shares'])
        if decision['tax_comment']:
            money.append('\U0001F4DD %s' % md(decision['tax_comment']))
        if action == SELL_PART:
            money += [''] + _sale_block('FOR REFERENCE: selling everything today', plan['reference_sale'], facts,
                                       compact=True)
    else:
        money += _sale_block('FOR REFERENCE: if you sold everything today', plan['reference_sale'], facts, compact=True)
        if decision['tax_comment']:
            money.append('\U0001F4DD %s' % md(decision['tax_comment']))
    if action == ADD and plan['add']:
        money += [''] + _add_block(plan['add'], facts, decision)
    out.append('\n'.join(money))

    # 5 -- plan
    out.append('\n'.join(_plan_block(decision, facts, alert_info)))

    # 6 -- sources and cost
    out.append('\n'.join(_footer(result)))
    return pack_messages([part for message in out for part in split_message(message)])


def pack_messages(messages, limit=2400):
    """Join neighbouring sections so the report is a few messages, not a dozen
    small ones. The limit is well under Telegram's, to keep each one readable."""
    packed = []
    for message in messages:
        if packed and len(packed[-1]) + 2 + len(message) <= limit:
            packed[-1] += '\n\n' + message
        else:
            packed.append(message)
    return packed


def split_message(text, limit=3800):
    """Cut a message to Telegram's size limit on blank lines first, then on single
    lines, so a bullet or a Markdown pair is never torn in half."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ''
    for block in text.split('\n\n'):
        pieces = [block] if len(block) <= limit else block.split('\n')
        glue = '\n\n' if len(block) <= limit else '\n'
        for piece in pieces:
            if current and len(current) + len(glue) + len(piece) > limit:
                parts.append(current)
                current = piece
            else:
                current = (current + glue + piece) if current else piece
        if glue == '\n' and current:         # an oversized block ended: keep blocks apart
            parts.append(current)
            current = ''
    if current:
        parts.append(current)
    return [p for p in parts if p.strip()]


def _sale_block(title, sale, facts, compact=False):
    lines = ['\U0001F4B0 *%s*' % title]
    lines.append('   Proceeds %s  (%g × %s, − %s commission est.)' % (
        usd(sale['proceeds']), sale['shares'], usd(sale['price']), usd(sale['commission'])))
    lines.append('   Cost basis %s → %s *%s* (%s)' % (usd(sale['basis']), 'gain' if sale['pl'] >= 0 else 'loss',
                                                          signed_usd(sale['pl']), pct(sale['pl_pct'])))
    if sale['pl'] > 0:
        lines.append('   \U0001F4B8 Tax 25%%: *%s*' % usd(sale['tax_owed']))
        if sale['shield_used']:
            lines.append('   \U0001F6E1 Shield covers %s → withheld *%s*  _(shield left %s)_' % (
                usd(sale['shield_used']), usd(sale['tax_withheld']), usd(sale['shield_after'])))
        else:
            lines.append('   \U0001F6E1 No shield banked, so all %s is withheld' % usd(sale['tax_withheld']))
    elif sale['pl'] < 0:
        lines.append('   \U0001F6E1 Tax shield earned: *+%s*  _(25%% of the loss; banked total %s)_' % (
            usd(sale['shield_earned']), usd(sale['shield_after'])))
        lines.append('   No tax to pay on a loss.')
    else:
        lines.append('   No gain or loss, so no tax.')
    lines.append('   ✅ *Net cash to you: %s*' % usd(sale['net_cash']))
    return lines


def _add_block(add, facts, decision):
    lines = ['\U0001F7E2 *IF YOU ADD*']
    when = {'now': 'now', 'on_dip': 'on a dip to %s' % usd(add['at_price']),
            'after_event': 'after the event below'}.get(add['when_mode'], 'when the conditions below are met')
    if add['enough_cash']:
        lines.append('   Free cash %s → buy *%d shares* %s (≈ %s)' % (
            usd(add['free_cash']), add['shares'], when, usd(add['cost'])))
        lines.append('   Position becomes %g shares at avg %s' % (add['new_shares'], usd(add['new_avg'])))
    else:
        lines.append('   ⚠️ Not enough free cash: you have %s and one share is %s.' % (
            usd(add['free_cash']), usd(add['one_share'])))
        lines.append('   You would need to deposit at least %s to add.' % usd(add['cash_needed']))
    if add['condition']:
        lines.append('   When: %s' % md(add['condition']))
    return lines


def _plan_block(decision, facts, alert_info):
    plan = decision['hold_plan']
    targets = decision['price_targets']
    lines = ['⏳ *HOLD PLAN & LEVELS*', '━' * 16, '']
    if plan['hold_until']:
        lines.append('\U0001F4C5 *Hold until:* %s' % md(plan['hold_until']))
    if plan['review_date']:
        lines.append('\U0001F50D *Review on:* %s' % md(plan['review_date']))
    if targets['take_profit']:
        lines.append('\U0001F3AF *Take profit:* %s' % ' → '.join(
            '%s (%s)' % (usd(t), pct(t / facts['price'] - 1)) for t in targets['take_profit']))
    if targets['add_below']:
        lines.append('\U0001F4C9 *Add / buy below:* %s (%s)' % (usd(targets['add_below']),
                                                              pct(targets['add_below'] / facts['price'] - 1)))
    if targets['review_below']:
        lines.append('⛔ *Re-examine / cut below:* %s (%s)' % (usd(targets['review_below']),
                                                                   pct(targets['review_below'] / facts['price'] - 1)))
    if targets['fair_value']:
        lines.append('⚖️ *Fair value estimate:* %s' % usd(targets['fair_value']))
    if decision['scenarios']:
        lines += ['', '\U0001F52E *Scenarios*']
        for s in decision['scenarios']:
            lines.append('• %s %.0f%% → *%s* (%s) — %s' % (
                md(s['name']).title(), s['probability'], usd(s['price']), pct(s['price'] / facts['price'] - 1),
                md(s['why'])))
    if plan['catalysts']:
        lines += ['', '\U0001F4C6 *Catalysts*'] + ['• %s — %s' % (md(c['date']), md(c['event']))
                                                   for c in plan['catalysts']]
    if plan['exit_triggers']:
        lines += ['', '\U0001F6AA *Sell / cut if*'] + ['• %s' % md(x) for x in plan['exit_triggers']]
    if decision['change_my_mind']:
        lines += ['', '\U0001F500 *What would change this call*'] + ['• %s' % md(x) for x in decision['change_my_mind']]
    if decision['risks']:
        lines += ['', '⚠️ *Risks*'] + ['• %s' % md(x) for x in decision['risks']]
    if alert_info:
        lines += ['', '\U0001F514 *Price alerts set* (see /pricealert list)']
        for row in alert_info['created']:
            lines.append('• %s %s %s' % ('\U0001F4C8' if row['direction'] == 'UP' else '\U0001F4C9',
                                              'above' if row['direction'] == 'UP' else 'below', usd(row['price'])))
        if alert_info.get('replaced'):
            lines.append('_Replaced %d earlier alert%s from a past /shouldisell run on this stock._' % (
                alert_info['replaced'], '' if alert_info['replaced'] == 1 else 's'))
        if alert_info.get('error'):
            lines.append('⚠️ _Could not save alerts: %s_' % md(alert_info['error']))
    return lines


def _footer(result):
    lines = ['\U0001F9FE *HOW THIS WAS BUILT*', '━' * 16]
    for leg in result['legs']:
        if leg['ok']:
            lines.append('✅ %s — %s%s · %.0fs' % (md(leg['name']), '$%.3f' % leg['cost'],
                                                               (' · ' + md(leg['detail'])) if leg['detail'] else '',
                                                               leg['seconds']))
        elif leg['skipped']:
            lines.append('⏭ %s — skipped: %s' % (md(leg['name']), md(leg['error'])))
        else:
            lines.append('❌ %s — failed: %s' % (md(leg['name']), md(leg['error'])))
    lines.append('\U0001F4B5 *This research cost about $%.2f*' % result['cost'])
    try:
        credit = api_spend.footer_line()
    except Exception:
        credit = ''
    if credit:
        lines.append(credit)
    gaps = result['data'].get('gaps') or []
    if gaps:
        lines.append('⚠️ _Not available: %s_' % md('; '.join(gaps[:5])))
    for warning in result['decision']['warnings']:
        lines.append('ℹ️ _%s_' % md(warning))
    sources = []
    for leg in result['legs']:
        sources += leg.get('citations') or []
    if sources:
        shown = []
        for url in sources:
            host = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
            if host not in shown:
                shown.append(host)
        lines.append('\U0001F517 _Sources: %s_' % md(', '.join(shown[:10])))
    lines += ['', '_%s_' % DISCLAIMER]
    return lines
