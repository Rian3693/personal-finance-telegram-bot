"""Watching the עו"ש between salaries, and last month's spending in review.

Spending alerts: once the עו"ש you started the pay period with (the balance /allocated
recorded after the salary) is 70 / 80 / 90 / 95% used, or this month's spending passes
last month's, the bot says so right after the purchase that crossed the line and then
every evening, until muted -- a mute lasts until the next salary. Each alert shows what
was spent, the days to the salary (it lands between the 5th and the 10th) and how much
a day is left to stay out of the minus.

Negative balance: the moment the עו"ש goes below zero, and then daily until muted (the
mute re-arms once the balance is back above zero), with what the overdraft interest costs.

Review: Claude goes over a closed month's purchases and marks each one needed or
avoidable, with the saving that was possible and a few tips.

State lives in wealth.json under "alerts" and "reviews".
"""

import json
from datetime import date, timedelta

import expenses as ex

LEVELS = (70, 80, 90, 95)
OVERDRAFT_RATE = 0.14          # a year, on the negative balance
SALARY_FIRST, SALARY_LAST = 5, 10


def money(amount):
    return ex.money(amount)


def _safe(text):
    return ''.join(ch for ch in str(text or '') if ch not in '*_`[]')


# ----------------------------------------------------------------------------- the pay period

def salary_window(today, paid_this_month):
    """(earliest, latest) day the next salary should arrive."""
    if paid_this_month or today.day > SALARY_LAST:
        y, m = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    else:
        y, m = today.year, today.month
    return date(y, m, SALARY_FIRST), date(y, m, SALARY_LAST)


def days_text(today, window):
    first, last = window
    a, b = (first - today).days, (last - today).days
    if b <= 0:
        return 'המשכורת אמורה להגיע בימים אלה'
    if a <= 0:
        return 'המשכורת אמורה להגיע עד %s (עוד %d ימים לכל היותר)' % (last.strftime('%d/%m'), b)
    return 'עוד %d–%d ימים למשכורת (%s–%s)' % (a, b, first.strftime('%d/%m'), last.strftime('%d/%m'))


def start_balance(plan):
    """(the עו"ש at the start of this pay period, its period key) -- what /allocated
    recorded after the latest salary; else the target left in the עו"ש."""
    payments = [p for p in plan.get('payments') or [] if p.get('month')]
    if not payments:
        return None, None
    p = payments[-1]
    checking = (p.get('actual') or {}).get('checking') or {}
    start = checking.get('actual') or p.get('float_target')
    return (float(start) if start else None), p['month']


def status(start, checking, cycle_total, last_total, today, window):
    used = max(0.0, start - checking) if start else 0.0
    pct = used / start * 100 if start else 0.0
    days_left = max(1, (window[1] - today).days)
    return {'start': start, 'checking': checking, 'used': round(used, 2), 'pct': round(pct, 1),
            'level': max([lv for lv in LEVELS if pct >= lv], default=0),
            'spent': round(cycle_total, 2), 'last': round(last_total, 2),
            'over_last': bool(last_total) and cycle_total > last_total,
            'days_left': days_left, 'per_day': round(max(0.0, checking) / days_left, 2)}


def format_spend_alert(s, today, window, top=None, first=False):
    head = ('⚠️ *העו"ש מתרוקן*' if s['level'] else '⚠️ *עברת את ההוצאות של החודש שעבר*')
    lines = [head, '']
    if s['start']:
        lines.append('💳 עו"ש: *%s* מתוך %s שהיו אחרי המשכורת — השתמשת ב-*%d%%*'
                     % (money(s['checking']), money(s['start']), round(s['pct'])))
    lines.append('🧾 הוצאת החודש: *%s*%s' % (money(s['spent']),
                                         (' — יותר מכל החודש שעבר (%s)' % money(s['last'])) if s['over_last']
                                         else ((' _(החודש שעבר: %s)_' % money(s['last'])) if s['last'] else '')))
    lines.append('📅 ' + days_text(today, window))
    if s['checking'] > 0:
        lines.append('🎯 כדי לא להיכנס למינוס: עד *%s ליום* עד המשכורת' % money(s['per_day']))
    if top:
        lines.append('🏷 הכי הרבה החודש: ' + ' · '.join('%s %s' % (_safe(c), money(v)) for c, v in top))
    lines += ['', '_מעכשיו — רק מה שבאמת צריך: אוכל בבית, תחבורה, חשבונות. בילויים, אוכל בחוץ וקניות שאפשר לדחות — אחרי המשכורת._']
    if not first:
        lines.append('_תזכורת יומית — 🔕 כדי להפסיק עד המשכורת הבאה_')
    return '\n'.join(lines)


def interest(balance, days):
    """What the overdraft costs for `days` days at OVERDRAFT_RATE a year."""
    return round(-min(0.0, balance) * OVERDRAFT_RATE / 365 * max(0, days), 2)


def format_negative_alert(checking, today, window, emergency=None, first=False):
    days = max(1, (window[1] - today).days)
    lines = ['🔴 *העו"ש במינוס: %s*' % money(checking) if first else '🔴 *תזכורת: העו"ש עדיין במינוס — %s*' % money(checking), '',
             '💸 ריבית מינוס %d%% בשנה: ~*%s ליום*' % (round(OVERDRAFT_RATE * 100), money(interest(checking, 1))),
             '📅 %s — עד אז זה יעלה ~*%s*' % (days_text(today, window), money(interest(checking, days))),
             '', '_הכי טוב: לא להוציא עד המשכורת חוץ מהכרחי, כדי שהמינוס לא יגדל._']
    if emergency:
        lines.append('_אפשרות אחרונה: להעביר %s מקרן החירום (/withdrawreserve) — חוסך ~%s, אבל מקטין את הקרן._'
                     % (money(-checking), money(interest(checking, days))))
    if not first:
        lines.append('_תזכורת יומית — 🔕 כדי להפסיק עד שהעו"ש יחזור לפלוס_')
    return '\n'.join(lines)


# ----------------------------------------------------------------------------- state

def state(data):
    return data.setdefault('alerts', {})


def spend_due(st, period, s):
    """Should the spending alert be on (crossed a level, or past last month), and not muted?"""
    if st.get('spend_muted') == period:
        return False
    return bool(s['level']) or s['over_last']


def new_spend_crossing(st, period, s):
    """True the first time a level (or 'over last month') is reached this period; marks it."""
    if st.get('period') != period:
        st.update({'period': period, 'level': 0, 'over_last': False})
    crossed = s['level'] > st.get('level', 0) or (s['over_last'] and not st.get('over_last'))
    st['level'] = max(st.get('level', 0), s['level'])
    st['over_last'] = st.get('over_last') or s['over_last']
    return crossed and st.get('spend_muted') != period


def negative_crossing(st, checking):
    """True when the balance has just gone below zero; re-arms (and unmutes) once it is back."""
    if checking >= 0:
        st['negative'] = False
        st['negative_muted'] = False
        return False
    if st.get('negative'):
        return False
    st['negative'] = True
    return True


# ----------------------------------------------------------------------------- the review

REVIEW_SCHEMA = {
    'type': 'object',
    'properties': {
        'verdict': {'type': 'string', 'enum': ['calm_down', 'ok', 'great']},
        'headline': {'type': 'string'},
        'items': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {'id': {'type': 'integer'}, 'need': {'type': 'string', 'enum': ['needed', 'avoidable']},
                           'reason': {'type': 'string'}},
            'required': ['id', 'need', 'reason'], 'additionalProperties': False}},
        'tips': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['verdict', 'headline', 'items', 'tips'], 'additionalProperties': False,
}
REVIEW_PROMPT = """You review one month of personal spending for a young person in Israel who saves
most of their salary and keeps a small checking balance (עו"ש) between salaries.

Month: {month} · total {total} over {count} purchases · the month before: {prev}
Net salary this period: {salary} · budgets per category: {budgets}

Purchases (JSON): {items}

For every purchase decide:
- "needed": groceries for home, transport to work, health, bills, rent, real necessities.
- "avoidable": could have been skipped, delayed or done much cheaper (eating out / delivery,
  cigarettes, impulse buys, convenience purchases, parking that a bus would avoid...).
Give each a very short Hebrew reason (max 8 words).
verdict: "calm_down" when spending is high or rising and the avoidable share is large;
"great" when it is low and mostly needed; else "ok".
headline: one short Hebrew sentence to the user, direct and kind.
tips: 2-3 short, concrete Hebrew tips based on these purchases (no investment advice).
Return every id exactly once."""
VERDICT = {'calm_down': '🛑 *כדאי להירגע עם ההוצאות*', 'ok': '🙂 *בסדר, אבל יש מה לשפר*', 'great': '🌟 *כל הכבוד — חודש חסכוני*'}
REVIEW_MODEL = 'claude-opus-5-5'
PRICE_IN, PRICE_OUT = 4.0, 20.0


def review(client, entries, month, total, prev_total, salary, budgets):
    """(result dict, cost $) from Claude for this month's purchases."""
    items = [{'id': i, 'date': e.get('date'), 'amount': e.get('amount'), 'description': e.get('description'),
              'category': e.get('category'), 'card': e.get('card')} for i, e in enumerate(entries)]
    message = client.messages.create(
        model=REVIEW_MODEL, max_tokens=8000,
        output_config={'effort': 'medium', 'format': {'type': 'json_schema', 'schema': REVIEW_SCHEMA}},
        messages=[{'role': 'user', 'content': REVIEW_PROMPT.format(
            month=month, total=money(total), count=len(entries), prev=money(prev_total) if prev_total else 'unknown',
            salary=money(salary) if salary else 'unknown', budgets=json.dumps(budgets, ensure_ascii=False) or '{}',
            items=json.dumps(items, ensure_ascii=False))}])
    cost = (message.usage.input_tokens * PRICE_IN + message.usage.output_tokens * PRICE_OUT) / 1e6
    if message.stop_reason in ('refusal', 'max_tokens'):
        raise ValueError('the review could not be completed (%s)' % message.stop_reason)
    text = next((b.text for b in message.content if b.type == 'text'), '')
    return json.loads(text), cost


def format_review(result, entries, month_label, rng, total, prev_total=None):
    needs = {it['id']: it for it in result.get('items') or [] if isinstance(it.get('id'), int)}
    needed = [(e, needs.get(i)) for i, e in enumerate(entries) if (needs.get(i) or {}).get('need') != 'avoidable']
    avoid = [(e, needs[i]) for i, e in enumerate(entries) if (needs.get(i) or {}).get('need') == 'avoidable']
    sum_of = lambda rows: sum(float(e.get('amount') or 0) for e, _ in rows)
    lines = ['🧐 *סקירת הוצאות — %s*' % month_label,
             '_%s · %s ב-%d רכישות%s_' % (rng, money(total), len(entries),
                                        (' · החודש שלפני: %s' % money(prev_total)) if prev_total else ''),
             '', VERDICT.get(result.get('verdict'), '🙂'), _safe(result.get('headline')), '']
    lines.append('💸 *מיותר — אפשר היה לחסוך %s* (%d)' % (money(sum_of(avoid)), len(avoid)))
    for e, it in sorted(avoid, key=lambda r: -float(r[0].get('amount') or 0))[:15]:
        lines.append('• %s — %s _(%s)_' % (money(e.get('amount')), _safe(e.get('description'))[:30], _safe(it.get('reason'))))
    if not avoid:
        lines.append('_אין — כל ההוצאות היו נחוצות_')
    lines += ['', '✅ *הכרחי: %s* (%d)' % (money(sum_of(needed)), len(needed))]
    for e, it in sorted(needed, key=lambda r: -float(r[0].get('amount') or 0))[:8]:
        lines.append('• %s — %s' % (money(e.get('amount')), _safe(e.get('description'))[:30]))
    if len(needed) > 8:
        lines.append('_+%d נוספות_' % (len(needed) - 8))
    if result.get('tips'):
        lines += ['', '💡 *טיפים*'] + ['• ' + _safe(t) for t in result['tips'][:3]]
    return '\n'.join(lines)
