"""/debrief: after a holding reports -- what happened, whether the reaction fits the stock's
own history, and the options in numbers. It informs the owner's decision; it does not make it.

  history_table() : every past report -- EPS surprise, the next session's reaction, and the
                    drift 5 / 20 / 60 trading days later
  fit()           : how this reaction compares with past reports with a surprise of the same
                    sign, and what followed past sharp drops
  options()       : hold / trim half / sell all -- realised result, tax after the shield,
                    the stock's weight in the US stocks afterwards
  Claude          : the report, sentiment, macro, sector, micro -- facts and context, no advice
"""

import json
import math

import earnings_ai as ea

TAX_RATE = 0.25
SECTOR_ETF = {'Technology': 'XLK', 'Industrials': 'XLI', 'Communication Services': 'XLC',
              'Financial Services': 'XLF', 'Utilities': 'XLU', 'Energy': 'XLE', 'Consumer Cyclical': 'XLY',
              'Healthcare': 'XLV', 'Consumer Defensive': 'XLP', 'Basic Materials': 'XLB', 'Real Estate': 'XLRE'}
DESTINATIONS = [('VTI', 'כל שוק המניות בארה"ב'), ('SGOV', 'אג"ח ממשלתי 0–3 חודשים (כמו פיקדון)'),
                ('SHY', 'אג"ח ממשלתי 1–3 שנים'), ('BND', 'כל שוק האג"ח'), ('GLD', 'זהב')]


def sector_etfs(info):
    out = []
    if 'semiconductor' in str(info.get('industry') or '').lower():
        out.append('SMH')
    etf = SECTOR_ETF.get(info.get('sector'))
    if etf:
        out.append(etf)
    return out


# ----------------------------------------------------------------------------- history

def history_table(earnings_rows, closes, limit=12):
    """earnings_rows: [(datetime, eps surprise % or None)] newest first (yfinance earnings dates
    that have a reported EPS). Returns [{date, surprise, reaction, d5, d20, d60}] in %."""
    days = [d for d, _ in closes]
    price = dict(closes)
    out = []
    for ts, surprise in earnings_rows:
        hour = 'bmo' if ts.hour < 12 else 'amc'
        rd = ea.reaction_day(ts.date(), hour)
        after = [i for i, d in enumerate(days) if d >= rd]
        if not after or after[0] == 0:
            continue
        i = after[0]
        base, react = closes[i - 1][1], closes[i][1]
        row = {'date': ts.date().isoformat(), 'surprise': surprise, 'reaction': round((react / base - 1) * 100, 1)}
        for k in (5, 20, 60):
            row['d%d' % k] = round((closes[i + k][1] / react - 1) * 100, 1) if i + k < len(closes) else None
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def fit(table, surprise, reaction, exclude_date=None):
    """How this reaction compares with the past, and what followed similar ones."""
    past = [t for t in table if t['date'] != exclude_date]
    out = {'n': len(past)}
    if surprise is not None:
        same = [t for t in past if t['surprise'] is not None and (t['surprise'] >= 0) == (surprise >= 0)]
        out['same_sign'] = len(same)
        out['avg_reaction_same'] = _avg([t['reaction'] for t in same])
        out['up_share_same'] = (sum(1 for t in same if t['reaction'] > 0) / len(same)) if same else None
    if reaction is not None:
        similar = [t for t in past if (t['reaction'] <= -5 if reaction <= -5 else
                                       (t['reaction'] >= 5 if reaction >= 5 else -5 < t['reaction'] < 5))]
        out['similar_moves'] = len(similar)
        for k in (5, 20, 60):
            vals = [t['d%d' % k] for t in similar if t.get('d%d' % k) is not None]
            out['after_%d' % k] = _avg(vals)
            out['after_%d_up' % k] = (sum(1 for v in vals if v > 0) / len(vals)) if vals else None
            out['after_%d_n' % k] = len(vals)
    return out


# ----------------------------------------------------------------------------- the options

def options(shares, price, avg_cost, us_total, shield):
    """hold / trim half / sell all: proceeds, realised result, tax after the shield, weight after."""
    rows = []
    for name, frac in (('להחזיק', 0.0), ('לחתוך חצי', 0.5), ('למכור הכול', 1.0)):
        sold = shares * frac
        proceeds = sold * price
        realised = sold * (price - avg_cost)
        taxable = max(0.0, realised - max(0.0, shield)) if realised > 0 else 0.0
        weight = (shares - sold) * price / us_total if us_total else 0.0
        rows.append({'name': name, 'sold': sold, 'proceeds': proceeds, 'realised': realised,
                     'tax': taxable * TAX_RATE, 'shield_used': min(max(0.0, shield), max(0.0, realised)),
                     'shield_added': -realised if realised < 0 else 0.0, 'weight_after': weight})
    return rows


# ----------------------------------------------------------------------------- Claude

SCHEMA = {
    'type': 'object',
    'properties': {
        'report': {'type': 'array', 'items': {'type': 'string'}},
        'sentiment': {'type': 'string'}, 'macro': {'type': 'string'}, 'sector': {'type': 'string'},
        'micro': {'type': 'string'}, 'history': {'type': 'string'},
        'watch': {'type': 'array', 'items': {'type': 'string'}}},
    'required': ['report', 'sentiment', 'macro', 'sector', 'micro', 'history', 'watch'],
    'additionalProperties': False,
}
PROMPT = """You write an earnings debrief for the owner of {symbol}, in Hebrew, plain and short.
Inform -- do NOT tell them to buy, sell, hold, trim or where to move money; never phrase a recommendation.
Use only the data below; say "לא ידוע" where it is missing.

THE REPORT: {report}
PRICE REACTION: stock {reaction} on {reaction_day} · market (VTI) {market} · sector ETF(s) {sector_moves}
STOCK NOW: price {price}, forward P/E {fpe}, analyst mean target {target}, EPS estimate change for next year after the report: {revisions}
MACRO: VTI 1-month {vti_1m}; US 10-year yield {tnx} ({tnx_change} in a month); oil {oil}
HEADLINES since the report: {news}
HISTORY of its reports (surprise %, reaction %, then drift 5/20/60 trading days %): {table}
HOW THIS FITS: {fit}

Return: report (3-5 bullets: results vs expectations, guidance, what management stressed),
sentiment (one sentence: was the move about the stock, its sector or the whole market?),
macro (one sentence), sector (one sentence), micro (one sentence on valuation/estimates after the report),
history (1-2 sentences: does this reaction fit its past reports, and what followed similar moves -- numbers),
watch (2-3 things to watch next)."""


def ask(client, ctx):
    msg = client.messages.create(
        model=ea.MODEL, max_tokens=5000,
        output_config={'effort': 'medium', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
        messages=[{'role': 'user', 'content': PROMPT.format(**ctx)}])
    cost = (msg.usage.input_tokens * ea.PRICE_IN + msg.usage.output_tokens * ea.PRICE_OUT) / 1e6
    if msg.stop_reason in ('refusal', 'max_tokens'):
        raise ValueError('Claude did not finish (%s)' % msg.stop_reason)
    return json.loads(next((b.text for b in msg.content if b.type == 'text'), '{}')), cost


# ----------------------------------------------------------------------------- messages

def _p(x, sign=True):
    return '—' if x is None else (('%+.1f%%' if sign else '%.0f%%') % x)


def _clean(t):
    return str(t or '').replace('*', '').replace('_', ' ').replace('`', "'")


def format_debrief(symbol, a, f, reaction, verdict_text=None):
    lines = ['🔍 *תחקיר דוח — %s*' % symbol, '']
    lines += ['*מה הדוח אמר:*'] + ['• ' + _clean(x) for x in a.get('report') or []]
    lines += ['', '🌡 *סנטימנט:* ' + _clean(a.get('sentiment')),
              '🌍 *מאקרו:* ' + _clean(a.get('macro')),
              '🏭 *הסקטור:* ' + _clean(a.get('sector')),
              '🔬 *המניה:* ' + _clean(a.get('micro'))]
    lines += ['', '📜 *מול ההיסטוריה של הדוחות שלה*']
    if f.get('n'):
        if f.get('avg_reaction_same') is not None:
            lines.append('בדוחות עם הפתעה באותו כיוון (%d): תגובה ממוצעת %s, עלתה ב-%s מהפעמים' % (
                f['same_sign'], _p(f['avg_reaction_same']), _p((f.get('up_share_same') or 0) * 100, False)))
        if reaction is not None:
            lines.append('התגובה הפעם: *%s*' % _p(reaction))
        if f.get('similar_moves'):
            lines.append('אחרי %d תגובות דומות בעבר — בממוצע: 5 ימים %s · 20 ימים %s · 60 ימים %s' % (
                f['similar_moves'], _p(f.get('after_5')), _p(f.get('after_20')), _p(f.get('after_60'))))
            if f.get('after_20_n'):
                lines.append('_עלתה אחרי 20 יום ב-%s מהמקרים (%d מקרים) — מעט מקרים, אז זה רק רמז_' % (
                    _p((f.get('after_20_up') or 0) * 100, False), f['after_20_n']))
    lines.append(_clean(a.get('history')))
    if a.get('watch'):
        lines += ['', '👀 *לעקוב:*'] + ['• ' + _clean(x) for x in a['watch']]
    if verdict_text:
        lines += ['', verdict_text]
    lines.append('_מידע להחלטה שלך — לא המלצה._')
    return '\n'.join(lines)


def format_options(symbol, rows, price, shield, playbook=None, verdict=None, destinations=None):
    lines = ['🧮 *%s — האפשרויות במספרים*' % symbol, '_מחיר $%.2f · מגן מס זמין $%s_' % (price, format(round(shield), ','))]
    if playbook and any(playbook.values()):
        lines.append('')
        lines.append('📘 *התוכנית שכתבת מראש:*')
        for k, label in (('ok', '✅ אם התזה מחזיקה'), ('weak', '⚠️ אם נחלשת'), ('broken', '❌ אם נשברת')):
            if playbook.get(k):
                lines.append('%s%s: %s' % ('👉 ' if k == verdict else '', label, _clean(playbook[k])))
    elif playbook is not None:
        lines += ['', '_אין לך תוכנית כתובה למניה הזו — /thesis ← 📘_']
    lines.append('')
    for r in rows:
        if not r['sold']:
            lines.append('*%s* — משקל במניות ארה"ב: %s' % (r['name'], _p(r['weight_after'] * 100, False)))
            continue
        tax = ('מס משוער $%s' % format(round(r['tax']), ',')) if r['realised'] > 0 else (
            'הפסד → מגן מס +$%s' % format(round(r['shield_added']), ','))
        lines.append('*%s* — %.2f מניות, $%s · ממומש %s$%s · %s · משקל אחרי %s' % (
            r['name'], r['sold'], format(round(r['proceeds']), ','), '+' if r['realised'] >= 0 else '-',
            format(round(abs(r['realised'])), ','), tax, _p(r['weight_after'] * 100, False)))
    if destinations:
        lines += ['', '*אם מעבירים כסף — איך היעדים האפשריים התנהגו (נתונים, לא בחירה):*']
        for sym, name, s in destinations:
            lines.append('• %s (%s): 2022 %s · ירידה מקס׳ 5ש %s · צמיחה %s/שנה' % (
                sym, name, _p(None if s.get('fall_2022') is None else s['fall_2022'] * 100),
                _p(None if s.get('max_dd') is None else s['max_dd'] * 100),
                _p(None if s.get('growth') is None else s['growth'] * 100)))
    lines.append('_מס: 25% על רווח אחרי מגן המס — הערכה; לבדוק מול רו"ח. ההחלטה שלך._')
    return '\n'.join(lines)
