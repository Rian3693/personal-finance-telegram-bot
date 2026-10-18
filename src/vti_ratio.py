"""/vtiratio: how far the US stocks are from a VTI / other-stocks ratio, how many months of
monthly VTI purchases close the gap, and how calm or wild each ratio has been.

The gap is closed by buying VTI only (nothing is sold): with VTI worth V and the other
stocks O, reaching a VTI share r needs V' = r / (1 - r) * O, so (V' - V) more in VTI.
Prices are held where they are today -- markets will move, so the months are a guide.

Risk comes from real daily prices (5 years) of VTI and of your other stocks, weighted as
you hold them: yearly volatility, the deepest fall from a peak, the worst month, the fall
in the 2022 decline, and a rough 2008 estimate (the mix's beta to VTI times VTI's 2008 fall).
"""

import math
from datetime import date, timedelta

VTI = 'VTI'
VTI_2008_FALL = 0.55            # VTI fell about 55% from its 2007 peak to March 2009
DEPOSITS = list(range(1800, 2501, 100))
RATIOS = (60, 70, 80, 90)
HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר',
              'אוקטובר', 'נובמבר', 'דצמבר']


# ----------------------------------------------------------------------------- data

def fetch(holdings, years=5):
    """{symbol: shares}, {symbol: [(date, close)]} from yfinance (blocking)."""
    import yfinance as yf
    shares = {}
    for h in holdings or []:
        s = float(h.get('shares') or 0)
        if s > 0:
            shares[h['symbol'].upper()] = shares.get(h['symbol'].upper(), 0.0) + s
    symbols = sorted(set(shares) | {VTI})
    data = yf.download(symbols, period='%dy' % years, interval='1d', auto_adjust=True,
                       progress=False, group_by='ticker', threads=True)
    history = {}
    for sym in symbols:
        try:
            closes = data[sym]['Close'].dropna() if len(symbols) > 1 else data['Close'].dropna()
        except Exception:
            continue
        history[sym] = [(ts.date(), float(c)) for ts, c in closes.items()]
    return shares, history


# ----------------------------------------------------------------------------- the gap

def split(shares, prices):
    """(VTI value, other stocks value, {symbol: value}) in $."""
    values = {s: shares[s] * prices[s] for s in shares if prices.get(s)}
    vti = values.get(VTI, 0.0)
    others = {s: v for s, v in values.items() if s != VTI}
    return vti, sum(others.values()), others


def needed(vti, others, ratio):
    """$ more in VTI to make it `ratio` (0-1) of the stocks; 0 if already there."""
    if ratio >= 1:
        return math.inf if others > 0 else 0.0
    return max(0.0, ratio / (1 - ratio) * others - vti)


def add_months(day, n):
    m = day.month - 1 + n
    return date(day.year + m // 12, m % 12 + 1, 1)


def months_table(gap, today, deposits=DEPOSITS):
    """[(monthly $, months, the month it is reached)]."""
    rows = []
    for d in deposits:
        n = 0 if gap <= 0 else math.ceil(gap / d)
        rows.append((d, n, add_months(today, n)))
    return rows


# ----------------------------------------------------------------------------- risk

def _returns(history):
    """{symbol: {date: daily return}}."""
    out = {}
    for sym, rows in history.items():
        r = {}
        for (d0, p0), (d1, p1) in zip(rows, rows[1:]):
            if p0 > 0:
                r[d1] = p1 / p0 - 1
        out[sym] = r
    return out


def mix_series(history, other_weights, ratio):
    """[(date, daily return)] of ratio*VTI + (1-ratio)*others (others weighted as held;
    on days a stock has no price yet, the others present share its weight)."""
    rets = _returns(history)
    vti = rets.get(VTI, {})
    days = sorted(vti)
    series = []
    for d in days:
        present = {s: w for s, w in other_weights.items() if d in rets.get(s, {})}
        total_w = sum(present.values())
        other = sum(rets[s][d] * w for s, w in present.items()) / total_w if total_w else vti[d]
        series.append((d, ratio * vti[d] + (1 - ratio) * other))
    return series


def stats(series, vti_series=None):
    if len(series) < 30:
        return None
    rs = [r for _, r in series]
    mean = sum(rs) / len(rs)
    vol = math.sqrt(sum((r - mean) ** 2 for r in rs) / (len(rs) - 1)) * math.sqrt(252)
    level, peak, max_dd = 1.0, 1.0, 0.0
    monthly, month_start, last_month = [], 1.0, None
    levels = {}
    for d, r in series:
        if last_month and (d.year, d.month) != last_month:
            monthly.append(level / month_start - 1)
            month_start = level
        last_month = (d.year, d.month)
        level *= 1 + r
        levels[d] = level
        peak = max(peak, level)
        max_dd = min(max_dd, level / peak - 1)
    out = {'vol': vol, 'max_dd': max_dd, 'worst_month': min(monthly) if monthly else None,
           'years': (series[-1][0] - series[0][0]).days / 365.25,
           'growth': (level ** (1 / max(0.5, (series[-1][0] - series[0][0]).days / 365.25)) - 1)}
    # the 2022 decline: from the high in Jan 2022 to the low that October
    in22 = [(d, v) for d, v in levels.items() if date(2022, 1, 1) <= d <= date(2022, 10, 31)]
    if in22:
        pk, worst = 0.0, 0.0
        for _, v in in22:
            pk = max(pk, v)
            worst = min(worst, v / pk - 1)
        out['fall_2022'] = worst
    if vti_series:
        vm = dict(vti_series)
        pairs = [(r, vm[d]) for d, r in series if d in vm]
        if len(pairs) > 30:
            mx = sum(b for _, b in pairs) / len(pairs)
            my = sum(a for a, _ in pairs) / len(pairs)
            cov = sum((a - my) * (b - mx) for a, b in pairs)
            var = sum((b - mx) ** 2 for _, b in pairs)
            out['beta'] = cov / var if var else None
            if out['beta'] is not None:
                out['crash_2008'] = -min(0.95, out['beta'] * VTI_2008_FALL)
    return out


def label(vol):
    if vol is None:
        return '⚪'
    if vol < 0.18:
        return '🟢 רגוע יחסית'
    if vol < 0.25:
        return '🟡 בינוני'
    if vol < 0.35:
        return '🟠 תנודתי'
    return '🔴 פראי'


# ----------------------------------------------------------------------------- reports

def _usd(x):
    return '$' + format(round(x), ',')


def _month(d):
    return '%s %d' % (HEB_MONTHS[d.month - 1], d.year)


def format_plan(vti, others, ratio, today, deposits=DEPOSITS):
    total = vti + others
    now = vti / total if total else 0
    gap = needed(vti, others, ratio)
    lines = ['🎯 *VTI מול שאר המניות — יעד %d/%d*' % (round(ratio * 100), round((1 - ratio) * 100)), '',
             '📊 *עכשיו:* VTI %s (*%.0f%%*) · שאר המניות %s (*%.0f%%*)' % (_usd(vti), now * 100, _usd(others), (1 - now) * 100)]
    if ratio >= 1:
        lines.append('_100% VTI אי אפשר להשיג רק בקנייה — צריך למכור את שאר המניות._')
        return '\n'.join(lines)
    if gap <= 0:
        lines.append('✅ כבר שם — VTI הוא %.0f%% (היעד %.0f%%)' % (now * 100, ratio * 100))
        return '\n'.join(lines)
    lines += ['💵 *חסר ב-VTI: %s* — אז VTI יהיה %s מתוך %s' % (_usd(gap), _usd(vti + gap), _usd(total + gap)), '',
              '*כמה חודשים, אם כל ההפקדה הולכת ל-VTI:*']
    for d, n, when in months_table(gap, today, deposits):
        lines.append('`%s/חודש` → *%d חודשים* (%s)' % (_usd(d), n, _month(when)))
    lines += ['', '_בלי מכירות ובלי שינויי מחירים — אם שאר המניות יעלו, ייקח יותר; אם ירדו, פחות._']
    return '\n'.join(lines)


def format_risk(rows, current_ratio, years, target=None):
    """rows: [(ratio, stats)]"""
    lines = ['🌪 *כמה בטוח / פראי — לפי %.0f שנות מחירים אמיתיים של המניות שלך*' % years, '']
    for ratio, s in rows:
        if not s:
            continue
        tag = ' ← עכשיו' if abs(ratio - current_ratio) < 0.005 else (
            ' ← היעד' if target is not None and abs(ratio - target) < 0.005 else '')
        lines.append('*%d/%d*%s — %s' % (round(ratio * 100), round((1 - ratio) * 100), tag, label(s['vol'])))
        parts = ['תנודתיות %.0f%%/שנה' % (s['vol'] * 100), 'ירידה מקסימלית %.0f%%' % (s['max_dd'] * 100)]
        if s.get('worst_month') is not None:
            parts.append('חודש גרוע %.0f%%' % (s['worst_month'] * 100))
        lines.append('   ' + ' · '.join(parts))
        extra = []
        if s.get('fall_2022') is not None:
            extra.append('ב-2022: %.0f%%' % (s['fall_2022'] * 100))
        if s.get('crash_2008') is not None:
            extra.append('קריסה כמו 2008: ~%.0f%%' % (s['crash_2008'] * 100))
        if extra:
            lines.append('   ' + ' · '.join(extra))
    lines += ['', '_תנודתיות = כמה הערך קופץ בשנה רגילה · ירידה מקסימלית = הנפילה הכי עמוקה מהשיא בתקופה._',
              '_"2008" = הערכה: הבטא של התמהיל מול VTI × הנפילה של VTI אז (~55%). העבר לא מבטיח את העתיד._']
    return '\n'.join(lines)


# ----------------------------------------------------------------------------- defensive ETFs

DEFENSIVE = [
    ('SGOV', 'אג"ח ממשלתי קצר מאוד (0–3 חודשים)'),
    ('SHY', 'אג"ח ממשלתי 1–3 שנים'),
    ('IEF', 'אג"ח ממשלתי 7–10 שנים'),
    ('TLT', 'אג"ח ממשלתי 20+ שנים'),
    ('BND', 'אג"ח כללי — כל שוק האג"ח בארה"ב'),
    ('GLD', 'זהב'),
    ('USMV', 'מניות בתנודתיות נמוכה'),
    ('XLP', 'צריכה בסיסית (מזון, מוצרי בית)'),
    ('XLU', 'תשתיות וחשמל'),
    ('SCHD', 'מניות דיבידנד איכותיות'),
    ('DBMF', 'Managed Futures — מגמות (מניות, אג"ח, סחורות, מט"ח)'),
]
OTHERS = '_OTHERS'
WINDOWS = {'2008': (date(2007, 10, 1), date(2009, 6, 30)),
           '2020': (date(2020, 2, 1), date(2020, 5, 1)),
           '2022': (date(2022, 1, 1), date(2022, 10, 31))}
# sample mixes: VTI / your other stocks / defensive ETFs -- illustrations, not advice
MIXES = [
    ('80/20 (בלי הגנה)', {VTI: 0.80, OTHERS: 0.20}),
    ('קלאסי 60/40', {VTI: 0.60, 'BND': 0.40}),
    ('מאוזן עם זהב', {VTI: 0.60, OTHERS: 0.10, 'BND': 0.20, 'GLD': 0.10}),
    ('כרית מזומן', {VTI: 0.70, OTHERS: 0.10, 'SHY': 0.20}),
    ('שקט', {VTI: 0.50, OTHERS: 0.10, 'SHY': 0.20, 'GLD': 0.10, 'USMV': 0.10}),
    ('גידור לאינפלציה (כמו 2022)', {VTI: 0.60, OTHERS: 0.10, 'DBMF': 0.15, 'GLD': 0.15}),
]


def fetch_long(symbols):
    """Full price history (adjusted, dividends in) for these symbols. Blocking."""
    import yfinance as yf
    symbols = sorted(set(symbols))
    data = yf.download(symbols, period='max', interval='1d', auto_adjust=True,
                       progress=False, group_by='ticker', threads=True)
    out = {}
    for sym in symbols:
        try:
            closes = data[sym]['Close'].dropna() if len(symbols) > 1 else data['Close'].dropna()
        except Exception:
            continue
        out[sym] = [(ts.date(), float(c)) for ts, c in closes.items()]
    return out


def window_drop(rows, start, end):
    """Peak-to-trough fall inside [start, end]; None when the data starts after the window."""
    inside = [(d, v) for d, v in rows if start <= d <= end]
    if not inside or inside[0][0] > start + timedelta(days=31):
        return None
    peak, worst = 0.0, 0.0
    for _, v in inside:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def market_fall_dates(vti_rows, start, end):
    """VTI's peak and trough dates of its deepest fall inside the window."""
    inside = [(d, v) for d, v in vti_rows if start <= d <= end]
    if not inside:
        return None
    peak_d, peak_v, best = inside[0][0], inside[0][1], (0.0, None, None)
    for d, v in inside:
        if v > peak_v:
            peak_d, peak_v = d, v
        if v / peak_v - 1 < best[0]:
            best = (v / peak_v - 1, peak_d, d)
    return (best[1], best[2]) if best[1] else None


def change_between(rows, start_day, end_day):
    """Change from start_day to end_day (last price on or before each); None without data."""
    before = [v for d, v in rows if d <= start_day]
    after = [v for d, v in rows if d <= end_day]
    if not before or not after or rows[0][0] > start_day:
        return None
    return after[-1] / before[-1] - 1


def _five_years(rows, today):
    return [(d, v) for d, v in rows if d >= today - timedelta(days=int(365.25 * 5))]


def path_stats(rows, today, vti_rows=None):
    """Stats of one price/level path: last 5 years (volatility, max fall, yearly growth,
    correlation with VTI) and the three crash windows."""
    five = _five_years(rows, today)
    out = {}
    if len(five) > 60:
        rs = [b / a - 1 for (_, a), (_, b) in zip(five, five[1:]) if a]
        mean = sum(rs) / len(rs)
        out['vol'] = math.sqrt(sum((r - mean) ** 2 for r in rs) / (len(rs) - 1)) * math.sqrt(252)
        peak, dd = 0.0, 0.0
        for _, v in five:
            peak = max(peak, v)
            dd = min(dd, v / peak - 1)
        out['max_dd'] = dd
        yrs = (five[-1][0] - five[0][0]).days / 365.25
        out['growth'] = (five[-1][1] / five[0][1]) ** (1 / yrs) - 1 if yrs > 0.5 else None
        if vti_rows:
            vm = dict(vti_rows)
            pairs = []
            for (d0, a), (d1, b) in zip(five, five[1:]):
                if d0 in vm and d1 in vm and a and vm[d0]:
                    pairs.append((b / a - 1, vm[d1] / vm[d0] - 1))
            if len(pairs) > 60:
                mx = sum(p for p, _ in pairs) / len(pairs)
                my = sum(q for _, q in pairs) / len(pairs)
                cov = sum((p - mx) * (q - my) for p, q in pairs)
                vx = sum((p - mx) ** 2 for p, _ in pairs)
                vy = sum((q - my) ** 2 for _, q in pairs)
                out['corr'] = cov / math.sqrt(vx * vy) if vx and vy else None
    # each crash: what this did from the market's (VTI's) peak to its trough
    for key, (a, b) in WINDOWS.items():
        dates = market_fall_dates(vti_rows or rows, a, b)
        out['fall_' + key] = change_between(rows, *dates) if dates else None
    return out


def mix_path(long_hist, other_rows, other_beta, weights):
    """Daily level path of a mix (rebalanced daily). Your other stocks before their own
    history starts are stood in for by VTI times their beta. Starts once every ETF in it trades."""
    vti = dict(long_hist.get(VTI) or [])
    series = {k: dict(long_hist.get(k) or []) for k in weights if k not in (VTI, OTHERS)}
    other = dict(other_rows or [])
    days = sorted(vti)
    level, path = 1.0, []
    for d0, d1 in zip(days, days[1:]):
        if any(d0 not in s or d1 not in s for s in series.values()):
            continue
        r = weights.get(VTI, 0) * (vti[d1] / vti[d0] - 1)
        for k, s in series.items():
            r += weights[k] * (s[d1] / s[d0] - 1)
        if weights.get(OTHERS):
            ro = (other[d1] / other[d0] - 1) if d0 in other and d1 in other and other[d0] else other_beta * (vti[d1] / vti[d0] - 1)
            r += weights[OTHERS] * ro
        level *= 1 + r
        path.append((d1, level))
    return path


def others_path(history, other_weights):
    """Your other stocks as one basket (weights as held), as a level path."""
    rets = _returns(history)
    days = sorted(set().union(*[set(rets.get(s, {})) for s in other_weights])) if other_weights else []
    level, path = 1.0, []
    for d in days:
        present = {s: w for s, w in other_weights.items() if d in rets.get(s, {})}
        tw = sum(present.values())
        if not tw:
            continue
        level *= 1 + sum(rets[s][d] * w for s, w in present.items()) / tw
        path.append((d, level))
    return path


def _pct(x):
    return '—' if x is None else '%.0f%%' % (x * 100)


def _chg(x):
    return '—' if x is None else '%+.0f%%' % (x * 100)


def format_defensive(etf_stats, vti_stats):
    lines = ['🛡 *ETF הגנתיים — מה קרה להם באמת במשברים*',
             '_בכל משבר: השינוי מהשיא של השוק (VTI) עד השפל שלו · 5 שנים אחרונות: תנודתיות, ירידה מקסימלית, מתאם עם VTI_', '',
             '📈 *VTI להשוואה*: 2008 %s · 2020 %s · 2022 %s · תנודתיות %s' % (
                 _chg(vti_stats.get('fall_2008')), _chg(vti_stats.get('fall_2020')), _chg(vti_stats.get('fall_2022')),
                 _pct(vti_stats.get('vol'))), '']
    for sym, name in DEFENSIVE:
        s = etf_stats.get(sym)
        if not s:
            continue
        lines.append('*%s* — %s' % (sym, name))
        lines.append('   2008 %s · 2020 %s · 2022 %s · תנודתיות %s · מקס׳ %s · מתאם %s' % (
            _chg(s.get('fall_2008')), _chg(s.get('fall_2020')), _chg(s.get('fall_2022')), _pct(s.get('vol')),
            _pct(s.get('max_dd')), '—' if s.get('corr') is None else '%.1f' % s['corr']))
    lines += ['', '_"—" = ה-ETF עוד לא היה קיים. מתאם נמוך/שלילי = נוטה לזוז אחרת מהמניות — זה מה שמגן._',
              '_שים לב: ב-2022 גם אג"ח ארוך טווח נפל חזק (ריבית עלתה) — הגנה שעבדה ב-2008 לא עבדה אז._']
    return '\n'.join(lines)


def format_mixes(rows, current):
    """rows: [(name, weights, stats)]; current: (name, weights, stats) of today's mix."""
    def weights_text(w):
        names = {VTI: 'VTI', OTHERS: 'שלך'}
        return ' / '.join('%d%% %s' % (round(v * 100), names.get(k, k)) for k, v in w.items())
    lines = ['🧪 *תמהילים לדוגמה — איך היו עוברים את המשברים*',
             '_חישוב על מחירים אמיתיים; המניות שלך לפני שהיו להן מחירים — מוערכות לפי הבטא שלהן מול VTI._',
             '_הצמיחה של "שלך" היא בדיעבד — לפי המניות שאתה מחזיק היום (שכבר עלו), אז היא נוטה להיראות טוב מהמציאות._', '']
    for name, w, s in [current] + rows:
        lines.append('*%s*%s' % (name, ' ← עכשיו' if (name, w, s) == current else ''))
        lines.append('   ' + weights_text(w))
        lines.append('   במשברים: 2008 %s · 2020 %s · 2022 %s' % (_chg(s.get('fall_2008')), _chg(s.get('fall_2020')),
                                                                _chg(s.get('fall_2022'))))
        lines.append('   5 שנים: תנודתיות %s · ירידה מקס׳ %s · צמיחה %s/שנה' % (
            _pct(s.get('vol')), _pct(s.get('max_dd')), _pct(s.get('growth'))))
    lines += ['', '_יותר הגנה = בדרך כלל פחות צמיחה בשנים טובות. אלה דוגמאות לחישוב — לא המלצה; ההחלטה שלך._',
              '_העבר לא מבטיח את העתיד; כל משבר שונה (2008 — אג"ח הגן, 2022 — אג"ח נפל יחד עם המניות)._']
    return '\n'.join(lines)
