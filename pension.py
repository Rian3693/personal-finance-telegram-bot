"""/pension: the pension fund (קרן פנסיה) -- balance, monthly deposit and a rough projection.

Updated by hand from the quarterly statement (the bot reminds you on the 15th of
January, April, July and October). The projection grows the balance and the deposits at
three REAL returns until the retirement age; the monthly pension is the balance divided
by a conversion factor (~200 in Israeli funds). Rough by design -- the fund's own
statement is the real figure.

Stored in pension.json: {"balance", "monthly", "birth_year", "retire_age", "updated", "log", "reminded"}
"""

import json
import os
from datetime import date

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pension.json')
LABEL = 'קרן פנסיה'
FACTOR = 200.0
REAL_RETURNS = (0.03, 0.04, 0.05)
REMIND_MONTHS = (1, 4, 7, 10)
REMIND_DAY = 15


def load():
    try:
        with open(FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault('balance', None)
    data.setdefault('monthly', None)
    data.setdefault('birth_year', None)
    data.setdefault('retire_age', 67)
    data.setdefault('log', [])
    return data


def save(data):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)


def set_balance(data, amount, today=None):
    today = (today or date.today()).isoformat()
    data['balance'] = round(float(amount), 2)
    data['updated'] = today
    data['log'].append({'date': today, 'balance': data['balance']})
    return data


def project(balance, monthly, years, real_rate):
    r = (1 + real_rate) ** (1 / 12) - 1
    value = float(balance or 0)
    for _ in range(int(round(years * 12))):
        value = value * (1 + r) + float(monthly or 0)
    return value


def due_reminder(data, today):
    quarter = '%d-Q%d' % (today.year, (today.month - 1) // 3 + 1)
    return today.month in REMIND_MONTHS and today.day >= REMIND_DAY and data.get('reminded') != quarter, quarter


def _money(x):
    return '₪{:,.0f}'.format(x or 0)


def format_status(data, today=None):
    today = today or date.today()
    lines = ['🏦 *%s*' % LABEL, '']
    if data.get('balance') is None:
        lines += ['_עוד לא הוזנה יתרה._', '',
                  'הזנה מהדוח הרבעוני:', '`/pension 85000` — היתרה', '`/pension monthly 1800` — ההפקדה החודשית (עובד+מעסיק)',
                  '`/pension born 1999` — שנת לידה (לתחזית)']
        return '\n'.join(lines)
    lines.append('יתרה: *%s* _(עודכן %s)_' % (_money(data['balance']), '/'.join(reversed((data.get('updated') or '').split('-')))))
    if data.get('monthly'):
        lines.append('הפקדה חודשית: *%s*' % _money(data['monthly']))
    if len(data['log']) > 1:
        prev = data['log'][-2]
        lines.append('מאז העדכון הקודם (%s): *%s ₪*' % ('/'.join(reversed(prev['date'].split('-'))),
                                                        '{:+,.0f}'.format(data['balance'] - prev['balance'])))
    if data.get('birth_year'):
        age = today.year - int(data['birth_year'])
        years = max(0, int(data['retire_age']) - age)
        lines += ['', '*תחזית לגיל %d (בעוד %d שנים, בכסף של היום):*' % (data['retire_age'], years)]
        for r in REAL_RETURNS:
            total = project(data['balance'], data.get('monthly'), years, r)
            lines.append('• %d%% ריאלי → צבירה *%s* · קצבה ~*%s* לחודש' % (round(r * 100), _money(total), _money(total / FACTOR)))
        lines.append('_קצבה = צבירה ÷ ~200 (מקדם המרה). הערכה גסה — הדוח של הקרן הוא המספר האמיתי._')
    else:
        lines += ['', '_לתחזית: /pension born 1999_']
    return '\n'.join(lines)
