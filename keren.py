"""קרן השתלמות - the locked training fund.

Money here is real but cannot be touched until the lock date, so it must never
be mixed into a liquid total. Every figure this module produces is labelled as
locked, and the totals it offers come in two flavours: liquid (everything you
could actually use today) and total including the fund.

Contributions are payroll-side: the monthly deposit does not come out of
/ilcash, it simply appears. So adding one credits the fund and touches nothing
else.
"""

import json
import os
from datetime import date, datetime

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my_portfolio.json')
KEY = 'keren'

DEFAULT_BALANCE = 24483.0
DEFAULT_MONTHLY = 800.0
DEFAULT_LOCKED_UNTIL = '2030-05-01'
PROMPT_DAY = 26

LABEL = 'קרן השתלמות'
EMOJI = '\U0001F512'


def money(amount):
    return '₪%s' % format(round(float(amount or 0), 2), ',.2f')


def default_state():
    return {'balance': DEFAULT_BALANCE, 'monthly': DEFAULT_MONTHLY,
            'locked_until': DEFAULT_LOCKED_UNTIL, 'log': []}


def load(path=None):
    """Current fund state, seeded on first use with the known balance."""
    path = path or PORTFOLIO_FILE
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default_state()

    state = default_state()
    state.update(data.get(KEY) or {})
    state['log'] = state.get('log') or []
    return state


def save(state, path=None):
    path = path or PORTFOLIO_FILE
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data[KEY] = state
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return state


def unlock_date(state):
    try:
        return datetime.strptime(state.get('locked_until', DEFAULT_LOCKED_UNTIL),
                                 '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return datetime.strptime(DEFAULT_LOCKED_UNTIL, '%Y-%m-%d').date()


def is_locked(state, today=None):
    return (today or date.today()) < unlock_date(state)


def months_until_unlock(state, today=None):
    today = today or date.today()
    target = unlock_date(state)
    if today >= target:
        return 0
    return (target.year - today.year) * 12 + (target.month - today.month)


def contributed_this_month(state, today=None):
    """Has the monthly deposit already been recorded for this month?"""
    today = today or date.today()
    stamp = today.strftime('%Y-%m')
    return any((entry.get('date') or '').startswith(stamp) for entry in state.get('log', []))


def add_contribution(state, amount=None, when=None, note=''):
    """Credit the fund. Nothing else moves -- this is payroll money."""
    when = when or date.today()
    amount = float(state.get('monthly', DEFAULT_MONTHLY) if amount is None else amount)
    state['balance'] = round(float(state.get('balance', 0) or 0) + amount, 2)
    state.setdefault('log', []).append({
        'date': when.strftime('%Y-%m-%d'),
        'amount': round(amount, 2),
        'balance_after': state['balance'],
        'note': note,
    })
    return state


def split_totals(liquid_ils, state):
    """Liquid vs liquid-plus-locked, so the two are never conflated."""
    locked = float(state.get('balance', 0) or 0)
    return {'liquid': round(float(liquid_ils), 2),
            'locked': round(locked, 2),
            'combined': round(float(liquid_ils) + locked, 2)}


# --------------------------------------------------------------------------- messages

def format_status(state, today=None):
    today = today or date.today()
    target = unlock_date(state)
    lines = ['%s *%s*' % (EMOJI, LABEL), '━' * 18, '',
             '\U0001F4B0 יתרה: *%s*' % money(state.get('balance')),
             '\U0001F4C5 נעול עד: *%s*' % target.strftime('%d/%m/%Y')]

    if is_locked(state, today):
        months = months_until_unlock(state, today)
        lines.append('⏳ עוד *%d חודשים* (%d שנים בערך)' % (months, round(months / 12)))
        lines.append('_לא נכלל בכסף הנזיל._')
    else:
        lines.append('\U0001F513 *הכסף שוחרר - זמין למשיכה*')

    lines.append('')
    lines.append('\U0001F4C8 הפקדה חודשית: *%s*' % money(state.get('monthly')))
    if contributed_this_month(state, today):
        lines.append('✅ ההפקדה של החודש כבר נרשמה')
    else:
        lines.append('⚠️ ההפקדה של החודש טרם נרשמה')

    log = state.get('log') or []
    if log:
        lines.append('')
        lines.append('*הפקדות אחרונות:*')
        for entry in log[-5:]:
            lines.append('  `%s`  +%s → %s' % (
                entry.get('date', ''), money(entry.get('amount')),
                money(entry.get('balance_after'))))
    return '\n'.join(lines)


def format_prompt(state, today=None):
    today = today or date.today()
    return ('%s *%s*\n\n'
            'הפקדת *%s* לקרן החודש?\n\n'
            '\U0001F4B0 יתרה נוכחית: *%s*\n'
            '_ההפקדה לא יורדת מהעו"ש._' % (
                EMOJI, LABEL, money(state.get('monthly')), money(state.get('balance'))))


def format_totals(totals, state):
    """The liquid / locked / combined block for /total and /reserves."""
    return '\n'.join([
        '\U0001F4A7 נזיל: *%s*' % money(totals['liquid']),
        '%s %s (נעול): *%s*' % (EMOJI, LABEL, money(totals['locked'])),
        '\U0001F4CA סה"כ כולל נעול: *%s*' % money(totals['combined']),
    ])
