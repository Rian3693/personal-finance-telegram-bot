"""קרן השתלמות לעצמאיים -- the self-employed training fund.

Separate from the employee קרן השתלמות (keren.py): that one is fed by the
employer through payroll, while this one is a private fund you pay into yourself,
out of your own money. So its monthly deposit is part of /setplan and /payment
(taken off the top, before the percentage split), it is a step in /allocated,
and only what /allocated records as really deposited is added to its balance.

The tax-recognised ceiling is MAX_MONTHLY a month.

Stored in my_portfolio.json under "keren_self":
  {"balance": 0.0, "log": [{"date", "amount", "balance_after", "note"}]}
"""

import json
import os
from datetime import date

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my_portfolio.json')
KEY = 'keren_self'
MAX_MONTHLY = 1714.0
LABEL = 'קרן השתלמות לעצמאיים'
EMOJI = '\U0001F510'


def money(amount):
    return '₪%s' % format(round(float(amount or 0), 2), ',.2f')


def load(path=None):
    try:
        with open(path or PORTFOLIO_FILE, 'r', encoding='utf-8') as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        data = {}
    state = {'balance': 0.0, 'log': []}
    state.update(data.get(KEY) or {})
    state['log'] = state.get('log') or []
    return state


def save(state, path=None):
    path = path or PORTFOLIO_FILE
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data[KEY] = state
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return state


def parse_monthly(text):
    """The monthly deposit typed in /setplan: 0..MAX_MONTHLY ('-' = 0). ValueError otherwise."""
    cleaned = str(text or '').strip().replace(',', '').replace('₪', '')
    if cleaned in ('-', '', '0'):
        return 0.0
    value = float(cleaned)
    if value < 0:
        raise ValueError('negative')
    if value > MAX_MONTHLY:
        raise ValueError('over the ceiling')
    return round(value, 2)


def deposit(state, amount, when=None, note=''):
    amount = round(float(amount), 2)
    state['balance'] = round(float(state.get('balance') or 0) + amount, 2)
    state['log'].append({'date': (when or date.today()).isoformat(), 'amount': amount,
                         'balance_after': state['balance'], 'note': note})
    return state


def year_total(state, year):
    return round(sum(float(e['amount']) for e in state['log'] if str(e.get('date', '')).startswith(str(year))), 2)


def format_status(state, monthly=None, today=None):
    today = today or date.today()
    this_year = year_total(state, today.year)
    lines = ['%s *%s*' % (EMOJI, LABEL), '_קרן פרטית שאתה מפקיד אליה בעצמך — נפרדת מקרן ההשתלמות של העבודה_', '',
             'יתרה: *%s*' % money(state.get('balance')),
             'הופקד השנה: %s מתוך תקרה של %s' % (money(this_year), money(MAX_MONTHLY * 12))]
    if monthly is not None:
        lines.append('בתוכנית: %s לחודש%s' % (money(monthly), '' if monthly else ' _(לא מוגדר — /setplan)_'))
    for e in state['log'][-5:][::-1]:
        lines.append('  `%s` +%s → %s' % (e['date'], money(e['amount']), money(e['balance_after'])))
    return '\n'.join(lines)
