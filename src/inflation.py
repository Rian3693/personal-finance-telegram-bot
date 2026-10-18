"""Israel's inflation (CBS consumer price index) and what it does to the savings target.

The /plantarget amount is in today's money. To keep that buying power at the end
of the plan, the target grows by
  - the inflation that has already happened since the base month (actual CPI), and
  - the inflation still to come until the plan ends, at an assumed yearly rate
    (the latest 12-month figure unless one is set by hand).

CBS publishes the index around the 15th, for the month before. The bot checks
daily from the 14th until the new month appears, then tells you what changed.

State in inflation.json:
  {"enabled", "base_month", "rate_override", "fetched", "notified_month",
   "series": [{"month": "YYYY-MM", "value", "base", "pct_month", "pct_year"}]}
"""

import json
import os
from datetime import date

import requests

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inflation.json')
CPI_URL = 'https://api.cbs.gov.il/index/data/price'
CPI_ID = 120010                 # מדד המחירים לצרכן - כללי
CHECK_FROM_DAY = 14             # the index comes out around the 15th
HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט',
              'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']


def load():
    if not os.path.exists(FILE):
        return {'enabled': True, 'base_month': None, 'rate_override': None,
                'fetched': None, 'notified_month': None, 'series': []}
    with open(FILE, encoding='utf-8') as fh:
        return json.load(fh)


def save(state):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)


def fetch_series(months=36, session=None):
    """The last `months` published months, oldest first."""
    get = (session or requests).get
    reply = get(CPI_URL, params={'id': CPI_ID, 'format': 'json', 'download': 'false', 'last': months},
                timeout=20)
    reply.raise_for_status()
    rows = []
    for block in reply.json().get('month') or []:
        for d in block.get('date') or []:
            base = d.get('currBase') or {}
            rows.append({'month': '%04d-%02d' % (int(d['year']), int(d['month'])),
                         'value': float(base.get('value')), 'base': base.get('baseDesc'),
                         'pct_month': float(d.get('percent') or 0), 'pct_year': float(d.get('percentYear') or 0)})
    if not rows:
        raise ValueError('CBS returned no index data')
    return sorted({r['month']: r for r in rows}.values(), key=lambda r: r['month'])


def refresh(state, today, session=None):
    """Fetch and merge. Returns the months that were not known before."""
    known = {r['month'] for r in state.get('series') or []}
    fresh = fetch_series(session=session)
    merged = {r['month']: r for r in (state.get('series') or []) + fresh}
    state['series'] = sorted(merged.values(), key=lambda r: r['month'])
    state['fetched'] = today.isoformat()
    if not state.get('base_month'):
        state['base_month'] = state['series'][-1]['month']     # "today's money" = the latest index
    return [r['month'] for r in fresh if r['month'] not in known]


def expected_latest(today):
    """The newest month that should be published by `today`."""
    back = 1 if today.day >= CHECK_FROM_DAY else 2
    y, m = today.year, today.month - back
    while m <= 0:
        y, m = y - 1, m + 12
    return '%04d-%02d' % (y, m)


def needs_check(state, today):
    """True when a newer month should be out and was not fetched today already."""
    series = state.get('series') or []
    latest = series[-1]['month'] if series else ''
    return latest < expected_latest(today) and state.get('fetched') != today.isoformat()


def latest(state):
    series = state.get('series') or []
    return series[-1] if series else None


def _row(state, month):
    return next((r for r in state.get('series') or [] if r['month'] == month), None)


def since(state, month):
    """Price growth from `month` to the latest index, as a factor (1.012 = +1.2%)."""
    rows = [r for r in state.get('series') or [] if r['month'] >= month]
    if len(rows) < 2:
        return 1.0
    first, last = rows[0], rows[-1]
    if first['base'] == last['base'] and first['value']:
        return last['value'] / first['value']
    factor = 1.0                       # the index was re-based: chain the monthly changes
    for r in rows[1:]:
        factor *= 1 + r['pct_month'] / 100
    return factor


def annual_rate(state):
    """The yearly rate assumed for the months still to come, in %."""
    if state.get('rate_override') is not None:
        return float(state['rate_override'])
    row = latest(state)
    return float(row['pct_year']) if row else 0.0


def months_between(a, b):
    ya, ma = map(int, a.split('-'))
    yb, mb = map(int, b.split('-'))
    return (yb - ya) * 12 + (mb - ma)


def adjust(state, real_amount, end_month):
    """What a target of `real_amount` (base-month money) is in shekels of `end_month`."""
    row = latest(state)
    if not row or not state.get('enabled', True) or not state.get('base_month'):
        return None
    done = since(state, state['base_month'])
    ahead_months = max(0, months_between(row['month'], end_month))
    rate = annual_rate(state)
    ahead = (1 + rate / 100) ** (ahead_months / 12)
    nominal = round(real_amount * done * ahead, 2)
    return {'real': round(real_amount, 2), 'nominal': nominal, 'extra': round(nominal - real_amount, 2),
            'done_pct': round((done - 1) * 100, 2), 'ahead_pct': round((ahead - 1) * 100, 2),
            'rate': rate, 'ahead_months': ahead_months, 'base_month': state['base_month'],
            'latest_month': row['month'], 'end_month': end_month}


def month_label(key):
    y, m = key.split('-')
    return '%s %s' % (HEB_MONTHS[int(m) - 1], y)


def _money(amount):
    return '₪{:,.2f}'.format(amount)


def format_adjustment(adj):
    return ('🎯 יעד %s בכוח קנייה של %s = *%s* ב-%s\n'
            '   _(+%.2f%% אינפלציה שכבר הייתה · +%.2f%% צפויה: %.1f%% לשנה × %d חודשים)_'
            % (_money(adj['real']), month_label(adj['base_month']), _money(adj['nominal']),
               month_label(adj['end_month']), adj['done_pct'], adj['ahead_pct'], adj['rate'], adj['ahead_months']))


def format_report(state, adj=None, months_left=None, limit=12, ils_credit=0.0):
    """ils_credit: inflation growth the CPI-linked ILS bank fund covers by itself."""
    row = latest(state)
    if not row:
        return '📈 *אינפלציה בישראל*\n\n_אין עדיין נתונים — נסה שוב בעוד רגע._'
    lines = ['📈 *אינפלציה בישראל (מדד המחירים לצרכן)*', '',
             'אחרון: *%s* — החודש *%+.1f%%* · 12 חודשים *%+.1f%%*' % (
                 month_label(row['month']), row['pct_month'], row['pct_year']),
             '_מדד %.1f (בסיס %s). המדד הבא מתפרסם בסביבות ה-15._' % (row['value'], row['base']), '',
             '📅 *12 החודשים האחרונים:*']
    for r in reversed((state.get('series') or [])[-limit:]):
        lines.append('`%s`  %+.1f%%   _(שנתי %+.1f%%)_' % (r['month'], r['pct_month'], r['pct_year']))
    lines.append('')
    if not state.get('enabled', True):
        lines.append('⏸ _ההתאמה לתוכנית כבויה — /inflation on להפעלה._')
    elif adj:
        lines.append(format_adjustment(adj))
        need = max(0.0, adj['extra'] - (ils_credit or 0))
        if ils_credit:
            lines.append('   🏦 החיסכון הבנקאי ₪ בקרן צמודת מדד — מכסה לבד ≈%s מהתוספת' % _money(ils_credit))
        if months_left:
            lines.append('   💡 כדי לשמור על כוח הקנייה: עוד *≈%s לחודש* לחיסכון (%s ÷ %d חודשים)' % (
                _money(need / months_left), _money(need), months_left))
        lines.append('_/plan ו-/salarytogoal כבר מחשבים לפי היעד המותאם._')
    else:
        lines.append('_אין יעד כולל ב-₪ — /plantarget._')
    rate_src = 'שהגדרת' if state.get('rate_override') is not None else 'לפי 12 החודשים האחרונים'
    lines += ['', '⚙️ שיעור לעתיד: %.1f%% (%s) · בסיס: %s' % (annual_rate(state), rate_src,
                                                          month_label(state['base_month']) if state.get('base_month') else '—'),
              '_/inflation rate 2.5 · /inflation rate auto · /inflation base 2026-08 · /inflation off_']
    return '\n'.join(lines)
