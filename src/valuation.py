"""/valuation: is a stock cheap or expensive for the medium-long term, and why.

fetch() gathers the numbers (yfinance: price, multiples, five fiscal years of income,
cash flow and balance sheet, estimate trends and revisions, insiders, the next
earnings; Finnhub: peers). analyse() turns them into signals:

  valuation  -- multiples now vs the stock's own history and vs its peers, a reverse
               DCF (the growth today's price assumes) and a simple three-scenario DCF
  quality    -- margins and their trend, ROIC, free cash flow vs profit, debt, dilution
  momentum   -- estimate revisions, insiders, analysts (sentiment, not value)

and a verdict: cheap / about fair / expensive, a quality grade and red flags.
Every assumption is printed with the result. It is a structured picture, not advice.
"""

import math
from datetime import date, datetime, timedelta

import requests

DISCOUNT = 0.10          # required return a year
TERMINAL = 0.03          # growth after year 10
YEARS = 10


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _row(df, *names):
    """[(fiscal year end date, value)] newest first, for the first row name that exists."""
    if df is None or getattr(df, 'empty', True):
        return []
    for name in names:
        if name in df.index:
            out = []
            for col, v in df.loc[name].items():
                v = _num(v)
                if v is not None:
                    out.append((col.date() if hasattr(col, 'date') else col, v))
            return sorted(out, key=lambda p: p[0], reverse=True)
    return []


def _df_dict(df):
    try:
        return {str(k): {str(c): _num(v) for c, v in row.items()} for k, row in df.iterrows()}
    except Exception:
        return {}


# ----------------------------------------------------------------------------- fetching

def fetch(symbol, finnhub_key=None, peer_limit=5):
    """Everything analyse() needs. Blocking (network)."""
    import yfinance as yf
    t = yf.Ticker(symbol)
    info = t.info or {}
    if not (info.get('currentPrice') or info.get('regularMarketPrice')):
        raise ValueError('no price for %s' % symbol)
    raw = {'symbol': symbol.upper(), 'info': info}
    inc, cf, bs = t.income_stmt, t.cashflow, t.balance_sheet
    raw['revenue'] = _row(inc, 'Total Revenue', 'Operating Revenue')
    raw['gross'] = _row(inc, 'Gross Profit')
    raw['op_income'] = _row(inc, 'Operating Income', 'Total Operating Income As Reported')
    raw['ebit'] = _row(inc, 'EBIT')
    raw['ebitda'] = _row(inc, 'EBITDA', 'Normalized EBITDA')
    raw['net_income'] = _row(inc, 'Net Income', 'Net Income Common Stockholders')
    raw['eps'] = _row(inc, 'Diluted EPS', 'Basic EPS')
    raw['shares'] = _row(inc, 'Diluted Average Shares', 'Basic Average Shares')
    raw['interest'] = _row(inc, 'Interest Expense', 'Interest Expense Non Operating')
    raw['tax_rate'] = _row(inc, 'Tax Rate For Calcs')
    raw['fcf'] = _row(cf, 'Free Cash Flow')
    raw['sbc'] = _row(cf, 'Stock Based Compensation')
    raw['debt'] = _row(bs, 'Total Debt')
    raw['cash'] = _row(bs, 'Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents')
    raw['equity'] = _row(bs, 'Stockholders Equity', 'Common Stock Equity')
    # the price at each fiscal year end, for the history of the multiples
    raw['fy_prices'] = {}
    ends = [d for d, _ in raw['revenue']]
    if ends:
        try:
            hist = t.history(start=str(min(ends) - timedelta(days=10)), auto_adjust=False)
            closes = [(ts.date(), float(c)) for ts, c in hist['Close'].items()]
            for end in ends:
                before = [c for d, c in closes if d <= end]
                if before:
                    raw['fy_prices'][end] = before[-1]
        except Exception:
            pass
    for name in ('eps_trend', 'eps_revisions', 'growth_estimates'):
        try:
            raw[name] = _df_dict(getattr(t, name))
        except Exception:
            raw[name] = {}
    raw['insider_net_pct'] = None
    try:
        ip = t.insider_purchases
        for _, row in ip.iterrows():
            if str(row.iloc[0]).startswith('% Net Shares'):
                raw['insider_net_pct'] = _num(row.iloc[1])
    except Exception:
        pass
    try:
        cal = t.calendar or {}
        when = cal.get('Earnings Date')
        raw['earnings'] = {'date': str(when[0] if isinstance(when, (list, tuple)) and when else when or ''),
                           'eps': _num(cal.get('Earnings Average')), 'revenue': _num(cal.get('Revenue Average'))}
    except Exception:
        raw['earnings'] = {}
    raw['peers'] = []
    if finnhub_key:
        try:
            r = requests.get('https://finnhub.io/api/v1/stock/peers', timeout=20,
                             params={'symbol': symbol.upper(), 'token': finnhub_key})
            names = [p for p in (r.json() or []) if p and p.upper() != symbol.upper() and '.' not in p][:peer_limit]
        except Exception:
            names = []
        for p in names:
            try:
                pi = yf.Ticker(p).info or {}
            except Exception:
                continue
            raw['peers'].append({'symbol': p, 'forwardPE': _num(pi.get('forwardPE')),
                                 'ev_ebitda': _num(pi.get('enterpriseToEbitda')),
                                 'ps': _num(pi.get('priceToSalesTrailing12Months')),
                                 'growth': _num(pi.get('revenueGrowth')), 'op_margin': _num(pi.get('operatingMargins'))})
    return raw


# ----------------------------------------------------------------------------- the maths

def cagr(series, years=3):
    """Yearly growth over up to `years` years of a newest-first [(date, value)] series."""
    if len(series) < 2:
        return None
    n = min(years, len(series) - 1)
    new, old = series[0][1], series[n][1]
    if old <= 0 or new <= 0:
        return None
    return (new / old) ** (1 / n) - 1


def dcf_value(fcf0, growth, years=YEARS, discount=DISCOUNT, terminal=TERMINAL, fade_from=5):
    """Present value of free cash flow growing at `growth` for `fade_from` years, then
    fading in a straight line to `terminal` by year `years`, plus a terminal value."""
    value, fcf = 0.0, fcf0
    for year in range(1, years + 1):
        g = growth if year <= fade_from else growth + (terminal - growth) * (year - fade_from) / (years - fade_from)
        fcf *= 1 + g
        value += fcf / (1 + discount) ** year
    value += fcf * (1 + terminal) / (discount - terminal) / (1 + discount) ** years
    return value


def implied_growth(market_value, fcf0):
    """The growth (first 5 years, fading to 3%) that makes the DCF equal today's value."""
    if not fcf0 or fcf0 <= 0 or not market_value:
        return None
    lo, hi = -0.5, 1.5
    if dcf_value(fcf0, hi) < market_value:
        return hi
    for _ in range(80):
        mid = (lo + hi) / 2
        if dcf_value(fcf0, mid) < market_value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _median(values):
    v = sorted(x for x in values if x is not None and x > 0)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _score_ratio(ratio, cheap=0.8, very_cheap=0.6, dear=1.25, very_dear=1.6):
    """+2..-2: below 1 is cheaper than the reference."""
    if ratio is None:
        return 0
    if ratio <= very_cheap:
        return 2
    if ratio <= cheap:
        return 1
    if ratio >= very_dear:
        return -2
    if ratio >= dear:
        return -1
    return 0


def analyse(raw):
    info = raw['info']
    price = _num(info.get('currentPrice') or info.get('regularMarketPrice'))
    mcap = _num(info.get('marketCap'))
    shares_now = _num(info.get('sharesOutstanding')) or (mcap / price if mcap and price else None)
    fcf0 = raw['fcf'][0][1] if raw['fcf'] else _num(info.get('freeCashflow'))
    revenue0 = raw['revenue'][0][1] if raw['revenue'] else _num(info.get('totalRevenue'))
    debt = raw['debt'][0][1] if raw['debt'] else _num(info.get('totalDebt')) or 0.0
    cash = raw['cash'][0][1] if raw['cash'] else _num(info.get('totalCash')) or 0.0
    r = {'symbol': raw['symbol'], 'price': price, 'mcap': mcap, 'name': info.get('shortName') or raw['symbol'],
         'sector': info.get('sector'), 'industry': info.get('industry'), 'beta': _num(info.get('beta')),
         'signals': [], 'flags': [], 'good': [], 'fcf0': fcf0,
         'growth_rev_now': _num(info.get('revenueGrowth'))}

    # multiples now
    m = {'pe': _num(info.get('trailingPE')), 'fpe': _num(info.get('forwardPE')),
         'peg': _num(info.get('trailingPegRatio') or info.get('pegRatio')),
         'ev_ebitda': _num(info.get('enterpriseToEbitda')), 'ps': _num(info.get('priceToSalesTrailing12Months')),
         'pfcf': (mcap / fcf0) if mcap and fcf0 and fcf0 > 0 else None}
    m['fcf_yield'] = (fcf0 / mcap) if mcap and fcf0 else None
    r['multiples'] = m

    # vs the stock's own history (fiscal year ends)
    hist = {'pe': [], 'ps': [], 'pfcf': []}
    shares = dict(raw['shares'])
    for end, p in raw['fy_prices'].items():
        eps = dict(raw['eps']).get(end)
        rev = dict(raw['revenue']).get(end)
        fcf = dict(raw['fcf']).get(end)
        sh = shares.get(end) or shares_now
        if eps and eps > 0:
            hist['pe'].append(p / eps)
        if rev and sh:
            hist['ps'].append(p * sh / rev)
        if fcf and fcf > 0 and sh:
            hist['pfcf'].append(p * sh / fcf)
    r['history'] = {}
    own = []
    for key in ('pe', 'ps', 'pfcf'):
        med = _median(hist[key])
        if med and m.get(key):
            ratio = m[key] / med
            r['history'][key] = {'now': m[key], 'median': med, 'low': min(hist[key]), 'high': max(hist[key]),
                                 'n': len(hist[key]), 'ratio': ratio}
            own.append(ratio)
    if own:
        ratio = sorted(own)[len(own) // 2]
        s = _score_ratio(ratio)
        r['signals'].append(('vs_history', s, ratio))

    # vs peers
    peers = raw.get('peers') or []
    r['peers'] = peers
    pm = {k: _median([p.get(k) for p in peers]) for k in ('forwardPE', 'ev_ebitda', 'ps')}
    pm['growth'] = _median([p.get('growth') for p in peers if p.get('growth') and p['growth'] > 0])
    r['peer_median'] = pm
    peer_ratios = [m[a] / pm[b] for a, b in (('fpe', 'forwardPE'), ('ev_ebitda', 'ev_ebitda'), ('ps', 'ps'))
                   if m.get(a) and pm.get(b)]
    if peer_ratios:
        ratio = sorted(peer_ratios)[len(peer_ratios) // 2]
        growth = _num(info.get('revenueGrowth'))
        # a faster grower deserves some premium: adjust by relative growth (capped)
        adj = 1.0
        if growth and pm.get('growth') and growth > 0:
            adj = max(0.5, min(2.0, (1 + growth) / (1 + pm['growth'])))
        r['peer_ratio'], r['peer_adj'] = ratio, adj
        r['signals'].append(('vs_peers', _score_ratio(ratio / adj), ratio))

    # growth
    g = {'rev_3y': cagr(raw['revenue']), 'eps_3y': cagr(raw['eps']), 'fcf_3y': cagr(raw['fcf']),
         'next_year': None, 'long_term': None}
    ge = raw.get('growth_estimates') or {}
    g['next_year'] = (ge.get('+1y') or {}).get('stockTrend')
    g['long_term'] = (ge.get('LTG') or {}).get('stockTrend')
    r['growth'] = g
    g['rev_now'] = r['growth_rev_now']
    plausible = sorted(x for x in (g['long_term'], g['next_year'], g['rev_3y'], g['rev_now']) if x is not None)
    # the lower middle: a one-off recovery year should not set the long-term growth
    base_growth = max(0.0, min(0.30, plausible[(len(plausible) - 1) // 2])) if plausible else 0.05
    r['base_growth'] = base_growth

    # reverse DCF and the three-scenario DCF (on the equity: market cap and net cash)
    net_cash = cash - debt
    r['net_cash'] = net_cash
    if fcf0 and fcf0 > 0 and mcap:
        imp = implied_growth(mcap - net_cash, fcf0)
        r['implied_growth'] = imp
        if imp is not None:
            ref = base_growth if base_growth > 0 else 0.02
            if imp < ref * 0.7:
                r['signals'].append(('reverse_dcf', 1, imp))
            elif imp > ref * 1.3 + 0.02:
                r['signals'].append(('reverse_dcf', -1 if imp < ref * 2 else -2, imp))
            else:
                r['signals'].append(('reverse_dcf', 0, imp))
        sc = {}
        for name, gr in (('bear', base_growth * 0.5), ('base', base_growth), ('bull', min(0.45, base_growth * 1.5 + 0.02))):
            equity = dcf_value(fcf0, gr) + net_cash
            sc[name] = {'growth': gr, 'per_share': equity / shares_now if shares_now else None}
        r['scenarios'] = sc
        fv = sc['base']['per_share']
        if fv and price:
            r['signals'].append(('dcf', _score_ratio(price / fv, 0.95, 0.8, 1.05, 1.25), price / fv))
    else:
        r['implied_growth'] = None
        r['scenarios'] = None
        r['flags'].append('אין תזרים מזומנים חופשי חיובי — אי אפשר להעריך לפי DCF; רק לפי מכפילים')

    # quality
    q = {}
    if raw['revenue'] and raw['gross']:
        rev = dict(raw['revenue'])
        gm = [(d, v / rev[d]) for d, v in raw['gross'] if rev.get(d)]
        if gm:
            q['gross_margin'], q['gross_margin_old'] = gm[0][1], gm[-1][1]
    if raw['revenue'] and raw['op_income']:
        rev = dict(raw['revenue'])
        om = [(d, v / rev[d]) for d, v in raw['op_income'] if rev.get(d)]
        if om:
            q['op_margin'], q['op_margin_old'] = om[0][1], om[-1][1]
    ebit = raw['ebit'][0][1] if raw['ebit'] else None
    tax = raw['tax_rate'][0][1] if raw['tax_rate'] else 0.21
    equity = raw['equity'][0][1] if raw['equity'] else None
    invested = (debt + equity) if equity and equity > 0 else None     # cash not netted: keeps ROIC sane for cash-rich firms
    q['roic'] = (ebit * (1 - (tax or 0.21)) / invested) if ebit and invested and invested > 0 else None
    ni = raw['net_income'][0][1] if raw['net_income'] else None
    q['fcf_conversion'] = (fcf0 / ni) if fcf0 and ni and ni > 0 else None
    ebitda = raw['ebitda'][0][1] if raw['ebitda'] else _num(info.get('ebitda'))
    q['net_debt_ebitda'] = ((debt - cash) / ebitda) if ebitda and ebitda > 0 else None
    interest = raw['interest'][0][1] if raw['interest'] else None
    q['interest_cover'] = (ebit / abs(interest)) if ebit and interest else None
    q['dilution'] = cagr(raw['shares'])
    sbc = raw['sbc'][0][1] if raw['sbc'] else None
    q['sbc_pct'] = (sbc / revenue0) if sbc and revenue0 else None
    r['quality'] = q

    points, checks = 0, 0
    def check(ok_, good, bad):
        nonlocal points, checks
        if ok_ is None:
            return
        checks += 1
        if ok_:
            points += 1
            r['good'].append(good)
        elif bad:
            r['flags'].append(bad)
    check(None if q.get('roic') is None else q['roic'] >= 0.15, 'ROIC גבוה (%.0f%%) — העסק מייצר תשואה טובה על ההון' % ((q.get('roic') or 0) * 100),
          'ROIC נמוך (%.0f%%)' % ((q.get('roic') or 0) * 100) if q.get('roic') is not None and q['roic'] < 0.08 else None)
    check(None if q.get('fcf_conversion') is None else q['fcf_conversion'] >= 0.8, 'הרווח הופך למזומן (FCF/רווח %.0f%%)' % ((q.get('fcf_conversion') or 0) * 100),
          'רק %.0f%% מהרווח הופך למזומן חופשי' % ((q.get('fcf_conversion') or 0) * 100) if q.get('fcf_conversion') is not None and q['fcf_conversion'] < 0.6 else None)
    if q.get('op_margin') is not None and q.get('op_margin_old') is not None:
        check(q['op_margin'] >= q['op_margin_old'] - 0.02, 'שולי הרווח התפעולי יציבים/עולים',
              'שולי הרווח התפעולי ירדו (%.0f%% → %.0f%%)' % (q['op_margin_old'] * 100, q['op_margin'] * 100))
    check(None if q.get('net_debt_ebitda') is None else q['net_debt_ebitda'] < 2, 'חוב נמוך',
          'חוב גבוה: חוב נטו פי %.1f מה-EBITDA' % (q.get('net_debt_ebitda') or 0) if (q.get('net_debt_ebitda') or 0) >= 3 else None)
    check(None if q.get('dilution') is None else q['dilution'] < 0.02, 'בלי דילול משמעותי של המניות',
          'דילול: מספר המניות עולה %.1f%% בשנה' % ((q.get('dilution') or 0) * 100) if (q.get('dilution') or 0) >= 0.03 else None)
    r['quality_score'] = (points, checks)
    if q.get('sbc_pct') and q['sbc_pct'] > 0.15:
        r['flags'].append('תגמול במניות גבוה: %.0f%% מההכנסות' % (q['sbc_pct'] * 100))

    # momentum of the fundamentals and sentiment
    trend = raw.get('eps_trend') or {}
    ny = trend.get('+1y') or {}
    if ny.get('current') and ny.get('90daysAgo'):
        r['revision_90d'] = ny['current'] / ny['90daysAgo'] - 1
    rev = raw.get('eps_revisions') or {}
    r['revisions'] = (sum((v.get('upLast30days') or 0) for v in rev.values()),
                      sum((v.get('downLast30days') or 0) for v in rev.values()))
    r['insider_net_pct'] = raw.get('insider_net_pct')
    if r['insider_net_pct'] is not None and r['insider_net_pct'] <= -0.02:
        r['flags'].append('בעלי עניין מכרו נטו %.1f%% מהחזקותיהם ב-6 חודשים' % (-r['insider_net_pct'] * 100))
    elif r['insider_net_pct'] is not None and r['insider_net_pct'] >= 0.01:
        r['good'].append('בעלי עניין קנו נטו ב-6 חודשים')
    r['insiders_pct'] = _num(info.get('heldPercentInsiders'))
    r['institutions_pct'] = _num(info.get('heldPercentInstitutions'))
    r['target'] = _num(info.get('targetMeanPrice'))
    r['analysts'] = (info.get('recommendationKey'), info.get('numberOfAnalystOpinions'))
    r['earnings'] = raw.get('earnings') or {}

    if r.get('revision_90d') is not None:
        if r['revision_90d'] > 0.05:
            r['good'].append('תחזיות הרווח לשנה הבאה עלו %.0f%% ב-90 יום' % (r['revision_90d'] * 100))
        elif r['revision_90d'] < -0.05:
            r['flags'].append('תחזיות הרווח לשנה הבאה ירדו %.0f%% ב-90 יום' % (-r['revision_90d'] * 100))
    if r['beta'] and r['beta'] > 1.8:
        r['flags'].append('תנודתיות גבוהה (בטא %.1f) — ירידות חדות אפשריות' % r['beta'])

    total = sum(s for _, s, _ in r['signals'])
    r['value_score'] = total
    r['verdict'] = 'cheap' if total >= 2 else ('expensive' if total <= -2 else 'fair')
    return r


# ----------------------------------------------------------------------------- the report

VERDICT = {'cheap': '💚 *נראה זול* ביחס לנתונים', 'fair': '🟡 *בערך מחיר הוגן*', 'expensive': '🔴 *נראה יקר* ביחס לנתונים'}
SIGNAL_NAME = {'vs_history': 'מול ההיסטוריה של המניה', 'vs_peers': 'מול המתחרות', 'reverse_dcf': 'DCF הפוך',
               'dcf': 'DCF (תרחיש בסיס)'}


def _pct(x, sign=False):
    return '—' if x is None else (('%+.1f%%' if sign else '%.1f%%') % (x * 100))


def _x(x):
    return '—' if x is None else '%.1f' % x


def _big(usd):
    if usd is None:
        return '—'
    a = abs(usd)
    for div, unit in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M')):
        if a >= div:
            return '%s$%.1f%s' % ('-' if usd < 0 else '', a / div, unit)
    return '$%.0f' % usd


def _arrow(score):
    return {2: '💚💚', 1: '💚', 0: '⚪', -1: '🔴', -2: '🔴🔴'}.get(score, '⚪')


def format_report(r):
    m = r['multiples']
    lines = ['🔬 *ניתוח שווי — %s (%s)*' % (r['symbol'], r['name'].replace('*', '')),
             '_%s · %s · מחיר $%.2f · שווי שוק %s_' % (r['sector'] or '', r['industry'] or '', r['price'] or 0, _big(r['mcap'])),
             '', VERDICT[r['verdict']] + '  _(ציון שווי %+d)_' % r['value_score']]
    points, checks = r['quality_score']
    if checks:
        lines.append('🏗 איכות העסק: *%d/%d*' % (points, checks))
    lines += ['', '*💲 מכפילים עכשיו*',
              'P/E %s · Forward P/E %s · PEG %s' % (_x(m['pe']), _x(m['fpe']), _x(m['peg'])),
              'EV/EBITDA %s · P/S %s · P/FCF %s · תשואת FCF %s' % (_x(m['ev_ebitda']), _x(m['ps']), _x(m['pfcf']),
                                                                     _pct(m['fcf_yield']))]

    lines += ['', '*📜 מול ההיסטוריה של המניה*']
    names = {'pe': 'P/E', 'ps': 'P/S', 'pfcf': 'P/FCF'}
    for key, h in r['history'].items():
        lines.append('%s: עכשיו %s · חציון %s (טווח %s–%s, %d שנים) → %s' % (
            names[key], _x(h['now']), _x(h['median']), _x(h['low']), _x(h['high']), h['n'],
            'יקר מהרגיל' if h['ratio'] > 1.25 else ('זול מהרגיל' if h['ratio'] < 0.8 else 'בטווח הרגיל')))
    if not r['history']:
        lines.append('_אין מספיק היסטוריה_')

    lines += ['', '*👥 מול המתחרות*']
    peers = [p for p in r['peers'] if p.get('forwardPE') or p.get('ps')]
    if peers:
        lines.append('_%s_' % ', '.join(p['symbol'] for p in peers))
        pm = r['peer_median']
        lines.append('Forward P/E %s מול %s · EV/EBITDA %s מול %s · P/S %s מול %s' % (
            _x(m['fpe']), _x(pm.get('forwardPE')), _x(m['ev_ebitda']), _x(pm.get('ev_ebitda')), _x(m['ps']), _x(pm.get('ps'))))
        if r.get('peer_adj') and abs(r['peer_adj'] - 1) > 0.05:
            lines.append('_צמיחת הכנסות %s מול חציון המתחרות %s — %s_' % (
                _pct(r.get('growth_rev_now')), _pct(pm.get('growth')),
                'צומחת מהר יותר, אז פרמיה מוצדקת חלקית' if r['peer_adj'] > 1 else 'צומחת לאט יותר'))
    else:
        lines.append('_לא נמצאו מתחרות להשוואה_')

    g = r['growth']
    lines += ['', '*🌱 צמיחה*',
              'הכנסות 3 שנים: %s בשנה (עכשיו %s) · EPS: %s · FCF: %s' % (_pct(g['rev_3y']), _pct(g.get('rev_now')),
                                                                       _pct(g['eps_3y']), _pct(g['fcf_3y'])),
              'תחזית אנליסטים: שנה הבאה %s · טווח ארוך %s' % (_pct(g['next_year']), _pct(g['long_term']))]

    lines += ['', '*🧮 DCF*']
    if r.get('implied_growth') is not None:
        lines.append('🔄 המחיר היום מגלם צמיחת FCF של *%s בשנה* ל-5 שנים (ואז דעיכה ל-3%%)' % _pct(r['implied_growth']))
        lines.append('   מול צמיחה סבירה (השמרנית מבין היסטוריה ותחזיות, עד 30%%): %s' % _pct(r['base_growth']))
    if r.get('scenarios'):
        sc = r['scenarios']
        lines.append('שווי למניה: 🐻 $%s (%s) · ⚖️ *$%s* (%s) · 🐂 $%s (%s)' % (
            '%.0f' % sc['bear']['per_share'], _pct(sc['bear']['growth']), '%.0f' % sc['base']['per_share'],
            _pct(sc['base']['growth']), '%.0f' % sc['bull']['per_share'], _pct(sc['bull']['growth'])))
        lines.append('_הנחות: היוון %d%%, צמיחה סופית %d%%, FCF אחרון %s, מזומן נטו %s_' % (
            DISCOUNT * 100, TERMINAL * 100, _big(r.get('fcf0')), _big(r['net_cash'])))

    q = r['quality']
    lines += ['', '*🏗 איכות וסיכון*',
              'שולי גולמי %s · תפעולי %s (היה %s) · ROIC %s' % (_pct(q.get('gross_margin')), _pct(q.get('op_margin')),
                                                            _pct(q.get('op_margin_old')), _pct(q.get('roic'))),
              'FCF/רווח %s · %s · כיסוי ריבית %s · דילול %s/שנה · SBC %s מההכנסות' % (
                  _pct(q.get('fcf_conversion')),
                  ('מזומן נטו %s' % _big(r['net_cash'])) if (q.get('net_debt_ebitda') or 0) < 0
                  else ('חוב נטו/EBITDA %s' % _x(q.get('net_debt_ebitda'))),
                  _x(q.get('interest_cover')), _pct(q.get('dilution')), _pct(q.get('sbc_pct')))]

    up, down = r['revisions']
    lines += ['', '*📣 תחזיות, בעלי עניין ואנליסטים*',
              'תחזית EPS לשנה הבאה ב-90 יום: %s · עדכונים ב-30 יום: ⬆️%d ⬇️%d' % (_pct(r.get('revision_90d'), True), up, down),
              'בעלי עניין מחזיקים %s · מוסדיים %s%s' % (_pct(r['insiders_pct']), _pct(r['institutions_pct']),
                                                       (' · קניות/מכירות נטו 6 ח׳: %s' % _pct(r['insider_net_pct'], True))
                                                       if r.get('insider_net_pct') is not None else '')]
    rec, n = r['analysts']
    if r.get('target') and r.get('price'):
        lines.append('יעד אנליסטים ממוצע $%.0f (%s) · %s, %s אנליסטים _(סנטימנט, לא שווי)_' % (
            r['target'], _pct(r['target'] / r['price'] - 1, True), rec or '—', n or '—'))
    e = r['earnings']
    if e.get('date'):
        lines.append('📅 דוח הבא: %s%s' % (e['date'], (' · צפי EPS $%.2f' % e['eps']) if e.get('eps') else ''))

    lines += ['', '*🧾 מאיפה הציון*']
    for key, score, val in r['signals']:
        lines.append('%s %s' % (_arrow(score), SIGNAL_NAME[key]))
    if r['good']:
        lines += ['', '*✅ לטובה*'] + ['• ' + x for x in r['good'][:6]]
    if r['flags']:
        lines += ['', '*⚠️ דגלים*'] + ['• ' + x for x in r['flags'][:6]]
    lines += ['', '_תמונה מבוססת נתונים (Yahoo Finance, Finnhub) לעזרה בהחלטה — לא המלצת השקעה._']
    return '\n'.join(lines)
