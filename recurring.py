"""Recurring payments (חיוב חוזר): a purchase that will be charged again next month.

When /ilspend logs one, it can be marked recurring. RENEW_NOTICE_DAYS before
each renewal (the day of the month it started on) the bot asks whether it is
still in use; each answer is kept, so /recurring shows what is running, what it
costs a month and a year, and the history of those check-ins. A payment
answered "not using" is stopped and no longer asked about.

Stored in recurring.json:
  {"items": [{"id", "name", "amount", "card", "started", "status": "active"|"stopped",
              "asked_for": the renewal date last asked about, "stopped_on", "entries": [spend ids],
              "answers": [{"date", "answer": "using"|"stopped"}]}]}
"""

import json
import os
import re
import uuid
from calendar import monthrange
from datetime import date, timedelta

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recurring.json')
CHECK_DAYS = 15           # no longer used for asking; kept for old records
RENEW_NOTICE_DAYS = 5     # ask this many days before the subscription renews
ACTIVE, STOPPED = 'active', 'stopped'
USING, STOP = 'using', 'stopped'
ANSWER_TEXT = {USING: '✅ עדיין בשימוש', STOP: '⛔ לא בשימוש — הופסק'}


def load():
    if not os.path.exists(FILE):
        return {'items': []}
    with open(FILE, encoding='utf-8') as fh:
        data = json.load(fh)
    data.setdefault('items', [])
    return data


def save(data):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)


def _norm(name):
    return re.sub(r'\s+', ' ', (name or '').strip().lower())


def find(data, item_id):
    return next((i for i in data['items'] if i['id'] == item_id), None)


def find_active(data, name):
    """An active recurring payment with this name, if there is one."""
    key = _norm(name)
    return next((i for i in data['items'] if i['status'] == ACTIVE and _norm(i['name']) == key), None)


def mark(data, entry, today):
    """Mark a logged purchase as recurring: link it to the payment of the same name,
    or start a new one. Returns (item, created)."""
    item = find_active(data, entry.get('description'))
    created = item is None
    if created:
        item = {'id': uuid.uuid4().hex[:8], 'name': entry.get('description', ''),
                'amount': float(entry.get('amount', 0) or 0), 'card': entry.get('card'),
                'started': entry.get('date') or today.isoformat(), 'status': ACTIVE,
                'next_check': (today + timedelta(days=CHECK_DAYS)).isoformat(),
                'stopped_on': None, 'entries': [], 'answers': []}
        data['items'].append(item)
    else:
        item['amount'] = float(entry.get('amount', 0) or 0)     # the latest charge
    if entry.get('id') and entry['id'] not in item['entries']:
        item['entries'].append(entry['id'])
    return item, created


def renewal_day(item):
    """The day of the month it renews on: the day it was first charged."""
    try:
        return int(str(item.get('started'))[8:10])
    except (TypeError, ValueError):
        return 1


def _on(year, month, day):
    return date(year, month, min(day, monthrange(year, month)[1]))


def next_renewal(item, today):
    """The next renewal after today (a renewal today has already happened)."""
    day = renewal_day(item)
    this = _on(today.year, today.month, day)
    if this > today:
        return this
    y, m = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    return _on(y, m, day)


def due(data, today):
    """Active payments renewing within RENEW_NOTICE_DAYS that were not asked about
    for that renewal yet."""
    out = []
    for item in data['items']:
        if item['status'] != ACTIVE:
            continue
        renew = next_renewal(item, today)
        if (renew - today).days <= RENEW_NOTICE_DAYS and item.get('asked_for') != renew.isoformat():
            out.append(item)
    return out


def asked(item, today):
    """The question for the coming renewal went out: not asked again until the next one."""
    item['asked_for'] = next_renewal(item, today).isoformat()


def answer(item, using, today):
    item['answers'].append({'date': today.isoformat(), 'answer': USING if using else STOP})
    if using:
        item['asked_for'] = next_renewal(item, today).isoformat()
    else:
        item['status'], item['stopped_on'] = STOPPED, today.isoformat()


def status_of(data, entry):
    """'active' / 'stopped' for a logged purchase that is recurring, else None."""
    if not entry.get('recurring'):
        return None
    item = find(data, entry.get('recurring_id', ''))
    return item['status'] if item else ACTIVE


def _money(amount):
    return '₪{:,.2f}'.format(float(amount or 0))


def _safe(text):
    return re.sub(r'[*_`\[\]]', '', text or '')


def _d(iso):
    y, m, d = (iso or '----------')[:10].split('-')
    return '%s/%s/%s' % (d, m, y[2:])


def format_question(item, today=None):
    today = today or date.today()
    renew = next_renewal(item, today)
    days = (renew - today).days
    return ('🔁 *המנוי מתחדש בעוד %d ימים — עדיין בשימוש?*\n\n'
            '*%s* · %s לחודש (%s בשנה)\n📅 חיוב הבא: %s\n_מאז %s · אם לא — כדאי לבטל לפני החידוש_'
            % (days, _safe(item['name']), _money(item['amount']), _money(item['amount'] * 12),
               _d(renew.isoformat()), _d(item['started'])))


def format_list(data, today=None):
    today = today or date.today()
    active = [i for i in data['items'] if i['status'] == ACTIVE]
    stopped = [i for i in data['items'] if i['status'] == STOPPED]
    lines = ['🔁 *חיובים חוזרים*', '']
    if not data['items']:
        return '\n'.join(lines + ['_אין עדיין. כשתרשום הוצאה ב-/ilspend תישאל אם היא חוזרת כל חודש._'])
    monthly = sum(i['amount'] for i in active)
    lines.append('פעילים: *%d* · *%s* לחודש · *%s* בשנה' % (len(active), _money(monthly), _money(monthly * 12)))
    for title, group in (('✅ *פעילים*', active), ('⛔ *הופסקו*', stopped)):
        if not group:
            continue
        lines += ['', title]
        for i in sorted(group, key=lambda x: -x['amount']):
            line = '• *%s* — %s (%s בשנה) · מאז %s' % (_safe(i['name']), _money(i['amount']),
                                                       _money(i['amount'] * 12), _d(i['started']))
            if i['status'] == ACTIVE:
                line += ' · מתחדש %s' % _d(next_renewal(i, today).isoformat())
            else:
                line += ' · הופסק %s' % _d(i['stopped_on'])
            lines.append(line)
    log = sorted(((a['date'], i['name'], a['answer']) for i in data['items'] for a in i['answers']), reverse=True)
    if log:
        lines += ['', '📒 *יומן תשובות*']
        lines += ['`%s` %s — %s' % (_d(d), _safe(n), ANSWER_TEXT[a]) for d, n, a in log[:20]]
    return '\n'.join(lines)
