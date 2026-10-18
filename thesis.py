"""/thesis: why you hold each stock and what would break that reason -- written down
before the news, so an earnings report is judged against it rather than against the mood.

The day before a holding reports, the bot sends the date, the analysts' expectations and
your thesis; the day after, it asks whether the results kept the thesis (✅), weakened it
(⚠️) or broke it (❌). Each answer is kept in the stock's history.

Stored in thesis.json:
  {"stocks": {SYM: {"why", "breaks", "created", "updated", "reviews": [{"date", "verdict", "note"}]}},
   "earnings": {"fetched": date, "dates": {SYM: {"date", "eps", "revenue"}}},
   "reminded": {SYM: earnings date}, "asked": {SYM: earnings date}}
"""

import json
import os
import re
from datetime import date, timedelta

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'thesis.json')
VERDICTS = {'ok': '✅ עדיין מחזיק', 'weak': '⚠️ נחלש', 'broken': '❌ נשבר'}
MAX_TEXT = 600


def load():
    try:
        with open(FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault('stocks', {})
    data.setdefault('earnings', {})
    data.setdefault('reminded', {})
    data.setdefault('asked', {})
    return data


def save(data):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)


def clean(text):
    return re.sub(r'[*_`\[\]]', '', str(text or '')).strip()[:MAX_TEXT]


def set_thesis(data, symbol, why=None, breaks=None, today=None):
    today = (today or date.today()).isoformat()
    entry = data['stocks'].setdefault(symbol.upper(), {'why': '', 'breaks': '', 'created': today, 'reviews': []})
    if why is not None:
        entry['why'] = clean(why)
    if breaks is not None:
        entry['breaks'] = clean(breaks)
    entry['updated'] = today
    return entry


def review(data, symbol, verdict, today=None, note='', earnings_date=None):
    entry = data['stocks'].setdefault(symbol.upper(), {'why': '', 'breaks': '', 'created': (today or date.today()).isoformat(),
                                                       'reviews': []})
    entry['reviews'].append({'date': (today or date.today()).isoformat(), 'verdict': verdict,
                             'note': clean(note), 'earnings': earnings_date})
    return entry


# ----------------------------------------------------------------------------- earnings dates

def fetch_earnings(symbols):
    """{SYM: {'date', 'eps', 'revenue'}} from yfinance (blocking). Missing ones are left out."""
    import yfinance as yf
    out = {}
    for sym in symbols:
        try:
            cal = yf.Ticker(sym).calendar or {}
        except Exception:
            continue
        when = cal.get('Earnings Date')
        when = when[0] if isinstance(when, (list, tuple)) and when else when
        if not when:
            continue
        out[sym] = {'date': str(when)[:10], 'eps': cal.get('Earnings Average'), 'revenue': cal.get('Revenue Average')}
    return out


def due_reminders(data, today):
    """Holdings that report tomorrow and were not reminded for that report yet."""
    tomorrow = (today + timedelta(days=1)).isoformat()
    return [s for s, e in (data['earnings'].get('dates') or {}).items()
            if e.get('date') == tomorrow and data['reminded'].get(s) != tomorrow]


def due_reviews(data, today):
    """Holdings that reported yesterday (or today, after the fact) and were not asked about yet."""
    out = []
    for s, e in (data['earnings'].get('dates') or {}).items():
        d = e.get('date')
        if d and today - timedelta(days=3) <= date.fromisoformat(d) < today and data['asked'].get(s) != d:
            out.append(s)
    return out


# ----------------------------------------------------------------------------- messages

def _big(x):
    if x is None:
        return '—'
    x = float(x)
    for div, unit in ((1e9, 'B'), (1e6, 'M')):
        if abs(x) >= div:
            return '$%.2f%s' % (x / div, unit)
    return '$%.0f' % x


def format_thesis(symbol, entry, compact=False):
    if not entry or not (entry.get('why') or entry.get('breaks')):
        return '*%s* — _אין עדיין תזה. לחץ ✏️ כדי לכתוב_' % symbol
    lines = ['*%s*' % symbol,
             '💡 *למה אני מחזיק:* %s' % (entry.get('why') or '—'),
             '🧨 *מה ישבור את זה:* %s' % (entry.get('breaks') or '—')]
    reviews = entry.get('reviews') or []
    if reviews:
        last = reviews[-1]
        lines.append('🗂 בדיקה אחרונה %s: %s%s' % ('/'.join(reversed(last['date'].split('-'))), VERDICTS.get(last['verdict'], ''),
                                                 (' — ' + last['note']) if last.get('note') else ''))
        if not compact and len(reviews) > 1:
            for r in reviews[-5:-1][::-1]:
                lines.append('   ↳ %s %s' % ('/'.join(reversed(r['date'].split('-'))), VERDICTS.get(r['verdict'], '')))
    if not compact:
        lines.append('_עודכן %s_' % '/'.join(reversed((entry.get('updated') or '').split('-'))))
    return '\n'.join(lines)


def format_overview(data, holdings):
    lines = ['🧭 *התזות שלך*', '_למה אתה מחזיק כל מניה, ומה ישבור את הסיבה. לפני כל דוח הבוט יזכיר לך._', '']
    dates = data['earnings'].get('dates') or {}
    for sym in holdings:
        lines.append(format_thesis(sym, data['stocks'].get(sym), compact=True))
        if dates.get(sym):
            lines.append('📅 דוח הבא: %s' % '/'.join(reversed(dates[sym]['date'].split('-'))))
        lines.append('')
    missing = [s for s in holdings if not (data['stocks'].get(s) or {}).get('why')]
    if missing:
        lines.append('_חסרה תזה ל: %s_' % ', '.join(missing))
    return '\n'.join(lines).rstrip()


def format_reminder(symbol, earnings, entry):
    d = '/'.join(reversed(earnings['date'].split('-')))
    lines = ['📅 *%s מדווחת מחר (%s)*' % (symbol, d), '',
             '*הציפיות של האנליסטים:* EPS %s · הכנסות %s' % (
                 ('$%.2f' % earnings['eps']) if earnings.get('eps') is not None else '—', _big(earnings.get('revenue'))), '']
    if entry and entry.get('why'):
        lines += ['*התזה שלך:*', '💡 ' + entry['why'], '🧨 נשבר אם: ' + (entry.get('breaks') or '—'), '',
                  '_תחליט עכשיו, לפני הדוח, מה תעשה בכל תרחיש — לא תוך כדי התנודה._']
    else:
        lines.append('_אין לך תזה כתובה ל-%s. זה זמן טוב לכתוב אחת: /thesis %s_' % (symbol, symbol))
    lines.append('_מחר בערב אשאל אם הדוח שמר על התזה או שבר אותה._')
    return '\n'.join(lines)


def format_review_question(symbol, earnings_date, entry):
    d = '/'.join(reversed(earnings_date.split('-')))
    lines = ['🗂 *%s דיווחה (%s) — מה עם התזה?*' % (symbol, d), '']
    if entry and entry.get('why'):
        lines += ['💡 ' + entry['why'], '🧨 נשבר אם: ' + (entry.get('breaks') or '—'), '']
    lines.append('הדוח שמר על הסיבה שבגללה אתה מחזיק?')
    return '\n'.join(lines)
