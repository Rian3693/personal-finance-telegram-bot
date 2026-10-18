"""/score: each spending month gets a score out of 100, and a streak of good months.

Four checks, each counted only when it applies to that month:
  1. allocated per plan -- /allocated recorded at least 95% of what /payment suggested
  2. budgets kept      -- every category with a /budget stayed within it
  3. no overdraft      -- the עו"ש never went below zero (checking log)
  4. spending in line  -- the month's spending within what /setplan expects (or last month's)
A month scoring 75+ keeps the streak going.
"""

from datetime import date

import categories as ecat
import expenses as ex

GOOD = 75


def month_checks(key, plan, entries, checking_log, cat_data, today):
    start, end = ex.cycle_range(key)
    checks = {}
    pays = [p for p in plan.get('payments') or [] if p.get('month') == key]
    if pays:
        actual = pays[-1].get('actual')
        checks['allocated'] = bool(actual) and actual['actual_total'] >= 0.95 * actual['suggested_total']
    if ecat.budgets(cat_data):
        rows = ecat.budget_status(cat_data, entries, key)
        checks['budgets'] = all(r[3] < 100 for r in rows)
    logged = [e for e in checking_log or [] if start.isoformat() <= str(e.get('date', ''))[:10] <= end.isoformat()]
    if logged:
        checks['no_overdraft'] = all(float(e.get('balance_after') or 0) >= 0 for e in logged)
    total = ex.month_summary(entries, key, cycle=True)['total']
    expected = float(plan.get('expected_spend') or 0)
    if not expected:
        expected = ex.month_summary(entries, ecat.previous_month(key), cycle=True)['total']
    if total and expected:
        checks['spending'] = total <= expected
    score = round(100 * sum(1 for v in checks.values() if v) / len(checks)) if checks else None
    return {'month': key, 'checks': checks, 'score': score, 'spent': total, 'expected': expected,
            'closed': end < today}


def history(plan, entries, checking_log, cat_data, today, months=6):
    key = ex.cycle_month_for(today)
    keys = [key]
    for _ in range(months - 1):
        keys.append(ecat.previous_month(keys[-1]))
    return [month_checks(k, plan, entries, checking_log, cat_data, today) for k in keys]


def streak(rows):
    n = 0
    for r in rows:
        if not r['closed']:
            continue
        if r['score'] is None or r['score'] < GOOD:
            break
        n += 1
    return n


LABEL = {'allocated': 'הקצאה לפי התוכנית', 'budgets': 'תקציבים נשמרו', 'no_overdraft': 'בלי מינוס בעו"ש',
         'spending': 'הוצאות בתוך הצפוי'}
HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']


def _money(x):
    return '₪{:,.0f}'.format(x or 0)


def format_score(rows):
    s = streak(rows)
    lines = ['🏆 *הציון החודשי שלך*', '🔥 רצף: *%d* חודשים ברצף עם ציון %d+' % (s, GOOD) if s else '🔥 _עוד אין רצף — חודש עם ציון %d+ מתחיל אותו_' % GOOD, '']
    for r in rows:
        name = '%s %s' % (HEB_MONTHS[int(r['month'][5:7]) - 1], r['month'][:4])
        if r['score'] is None:
            lines.append('*%s* — _אין מספיק נתונים_' % name)
            continue
        medal = '🥇' if r['score'] >= 90 else ('✅' if r['score'] >= GOOD else ('🟠' if r['score'] >= 50 else '🔴'))
        lines.append('%s *%s* — *%d*%s' % (medal, name, r['score'], '' if r['closed'] else ' _(עוד רץ)_'))
        lines.append('   ' + ' · '.join('%s %s' % ('✅' if v else '❌', LABEL[k]) for k, v in r['checks'].items()))
        if r.get('expected'):
            lines.append('   _הוצאות %s מתוך %s צפוי_' % (_money(r['spent']), _money(r['expected'])))
    lines.append('')
    lines.append('_כל בדיקה נספרת רק כשיש לה נתונים לחודש (תשלום, תקציבים, יומן עו"ש)._')
    return '\n'.join(lines)
