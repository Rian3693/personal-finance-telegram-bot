"""Future expenses (הוצאות עתידיות): things you expect to pay for, with a cost, a rough
date and a category.

/futureexpenses (also /planned) lists them by date: when each one comes, how many
months away it is, its category (picked by Claude from the description, changeable),
and how much to put aside each month to have it ready on time. The totals are set
against the future-expenses fund. One is ticked off when bought (kept in a short
history) or deleted. Nothing here moves money -- the purchase itself is logged with
/ilspend as usual.

Stored in planned_expenses.json:
  {"items": [{"id", "name", "cost", "added", "when": "YYYY-MM-DD" | null,
              "when_precision": "month" | "day", "category"}], "done": [...]}
"""

import json
import os
import re
import uuid
from calendar import monthrange
from datetime import date

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'planned_expenses.json')
MAX_NAME = 40
HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר',
              'אוקטובר', 'נובמבר', 'דצמבר']
SKIP_WORDS = ('skip', 'לא יודע', 'לא ידוע', 'אין', '-', 'דלג')


def load():
    try:
        with open(FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault('items', [])
    data.setdefault('done', [])
    return data


def save(data):
    with open(FILE, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def clean(name):
    name = re.sub(r'[*_`\[\]<>]', '', str(name or '')).replace('\n', ' ')
    return re.sub(r'\s+', ' ', name).strip()[:MAX_NAME]


def parse_cost(text):
    """'4,500' / '₪4500' / '4500.50' -> 4500.5; None when it is not a positive number."""
    try:
        value = float(str(text).replace(',', '').replace('₪', '').strip())
    except ValueError:
        return None
    return round(value, 2) if value > 0 else None


def parse_line(text):
    """'מקרר חדש 4500' -> ('מקרר חדש', 4500.0); the cost is the last word. None if not."""
    words = str(text or '').split()
    if len(words) < 2:
        return None
    cost = parse_cost(words[-1])
    name = clean(' '.join(words[:-1]))
    return (name, cost) if cost and name else None


# ----------------------------------------------------------------------------- when

def add_months(day, months):
    m = day.month - 1 + months
    y, m = day.year + m // 12, m % 12 + 1
    return date(y, m, min(day.day, monthrange(y, m)[1]))


def _year(text, today):
    y = int(text)
    return y + 2000 if y < 100 else y


def parse_when(text, today):
    """When it will be paid: (date, 'month' | 'day'), or None if not understood.

    '6' = in 6 months · '03/2027' or '3/27' or '2027-03' or 'מרץ 2027' = that month ·
    '15/03/2027' or '2027-03-15' = that day. A month with no year is the next one."""
    t = str(text or '').strip().replace('.', '/').replace('\\', '/')
    if re.fullmatch(r'\d{1,3}', t):
        n = int(t)
        if 0 < n <= 240:
            return add_months(today, n).replace(day=1), 'month'
        return None
    try:
        m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', t)
        if m:
            return date(_year(m.group(3), today), int(m.group(2)), int(m.group(1))), 'day'
        m = re.fullmatch(r'(\d{1,2})/(\d{2,4})', t)
        if m:
            return date(_year(m.group(2), today), int(m.group(1)), 1), 'month'
        m = re.fullmatch(r'(\d{4})-(\d{1,2})(?:-(\d{1,2}))?', t)
        if m:
            if m.group(3):
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), 'day'
            return date(int(m.group(1)), int(m.group(2)), 1), 'month'
    except ValueError:
        return None
    for n, name in enumerate(HEB_MONTHS, 1):
        if t.startswith(name):
            rest = t[len(name):].strip()
            if rest:
                if not re.fullmatch(r'\d{2,4}', rest):
                    return None
                return date(_year(rest, today), n, 1), 'month'
            y = today.year if n > today.month else today.year + 1
            return date(y, n, 1), 'month'
    return None


def months_until(when, today):
    """Whole months from this month to that one (0 = this month or already past)."""
    return max(0, (when.year - today.year) * 12 + when.month - today.month)


def when_text(item):
    if not item.get('when'):
        return 'ללא תאריך'
    d = date.fromisoformat(item['when'])
    if item.get('when_precision') == 'day':
        return d.strftime('%d/%m/%Y')
    return '%s %d' % (HEB_MONTHS[d.month - 1], d.year)


def monthly_need(item, today):
    """What to put aside each month to have it by then (all of it if due now)."""
    if not item.get('when'):
        return None
    months = months_until(date.fromisoformat(item['when']), today)
    return round(float(item['cost']) / max(1, months), 2)


# ----------------------------------------------------------------------------- the list

def add(data, name, cost, today=None, when=None, precision='month', category=None):
    item = {'id': uuid.uuid4().hex[:8], 'name': clean(name), 'cost': round(float(cost), 2),
            'added': (today or date.today()).isoformat(),
            'when': when.isoformat() if when else None, 'when_precision': precision if when else None,
            'category': category}
    data['items'].append(item)
    return item


def find(data, item_id):
    return next((i for i in data['items'] if i['id'] == item_id), None)


def remove(data, item_id):
    item = find(data, item_id)
    if item:
        data['items'].remove(item)
    return item


def mark_done(data, item_id, today=None):
    item = remove(data, item_id)
    if item:
        item['done'] = (today or date.today()).isoformat()
        data['done'] = ([item] + data['done'])[:20]
    return item


def total(data):
    return round(sum(float(i['cost']) for i in data['items']), 2)


def ordered(data):
    """By date, the ones with no date last."""
    return sorted(data['items'], key=lambda i: (i.get('when') is None, i.get('when') or '', i['added']))


def _money(amount):
    amount = round(float(amount or 0), 2)
    return ('-' if amount < 0 else '') + '₪{:,.2f}'.format(abs(amount))


def _safe(text):
    return re.sub(r'[*_`\[\]]', '', str(text or ''))


def format_list(data, fund=None, today=None):
    """Markdown: every future expense by date, what to set aside a month, the totals
    per category, and what the future fund covers."""
    today = today or date.today()
    lines = ['🗓 *הוצאות עתידיות*', '']
    items = ordered(data)
    if not items:
        lines.append('_אין עדיין. הוסף עם ➕ (תיאור → סכום → מתי)._')
    for n, item in enumerate(items, 1):
        lines.append('*%d.* %s — *%s*' % (n, _safe(item['name']), _money(item['cost'])))
        detail = ['📅 ' + when_text(item)]
        if item.get('when'):
            months = months_until(date.fromisoformat(item['when']), today)
            detail[0] += ' (%s)' % ('הגיע הזמן' if months == 0 else 'בעוד %d חודשים' % months)
        if item.get('category'):
            detail.append('🏷 ' + _safe(item['category']))
        need = monthly_need(item, today)
        if need is not None:
            detail.append('לשים בצד %s לחודש' % _money(need))
        lines.append('   ' + ' · '.join(detail))
    if items:
        planned = total(data)
        monthly = sum(monthly_need(i, today) or 0 for i in items)
        lines += ['', '💰 *סה"כ: %s*  _(%d)_' % (_money(planned), len(items))]
        if monthly:
            lines.append('📆 לשים בצד: *%s לחודש* _(לכל מה שיש לו תאריך)_' % _money(monthly))
        cats = {}
        for i in items:
            key = i.get('category') or 'ללא קטגוריה'
            cats[key] = cats.get(key, 0.0) + float(i['cost'])
        if len(cats) > 1:
            lines.append('🏷 ' + ' · '.join('%s %s' % (_safe(c), _money(v))
                                            for c, v in sorted(cats.items(), key=lambda kv: -kv[1])))
        if fund is not None:
            lines.append('🎯 בקרן הוצאות עתידיות: *%s*' % _money(fund))
            if fund >= planned:
                lines.append('🟢 הקרן מכסה הכול — יישאר %s' % _money(fund - planned))
            else:
                lines.append('🟠 חסר %s (הקרן מכסה %d%%)' % (_money(planned - fund),
                                                              round(max(fund, 0) / planned * 100)))
    if data['done']:
        lines += ['', '_נקנו לאחרונה:_']
        for item in data['done'][:5]:
            lines.append('  ✅ %s — %s _(%s)_' % (_safe(item['name']), _money(item['cost']),
                                                 '/'.join(reversed(item.get('done', '').split('-')[1:]))))
    return '\n'.join(lines)
