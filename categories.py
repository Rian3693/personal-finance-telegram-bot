"""Spending categories (קטגוריות): what each purchase was for.

A scanned receipt gets a category suggested by Claude; you keep it or pick /
write another, and a new one ("מונית", say) is offered as a button from then on.
The store's choice is remembered, so the next receipt from the same store starts
with it. Purchases with no category count as UNCATEGORISED. by_category() and
format_block() give a month's spending per category next to the month before,
for /expenses and the summary sent on the 10th.

Sub-categories live under a category ("תחבורה › מונית"): a purchase keeps the
category in entry['category'] and the sub-category in entry['subcategory'], and
what is remembered for a store or description is the whole path.

Stored in expense_categories.json: {"categories": [...], "subs": {category: [...]},
"stores": {store: path}, "descriptions": {description: path}}.
"""

import json
from datetime import datetime
import os
import re

import expenses as ex

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'expense_categories.json')
UNCATEGORISED = 'ללא קטגוריה'
DEFAULTS = ['סופר ומכולת', 'מסעדות ואוכל בחוץ', 'תחבורה', 'דלק ורכב', 'ביגוד והנעלה',
            'בריאות ופארם', 'בית', 'בילויים', 'מנויים', 'אלקטרוניקה', 'מתנות', 'אחר']
MAX_NAME = 30


def load():
    try:
        with open(FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault('categories', list(DEFAULTS))
    data.setdefault('subs', {})
    data.setdefault('stores', {})
    data.setdefault('descriptions', {})
    return data


def save(data):
    with open(FILE, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


def clean(name):
    """A category name as typed: trimmed, no Markdown/HTML marks, one line, short."""
    name = re.sub(r'[*_`\[\]<>]', '', str(name or '')).replace('\n', ' ')
    return re.sub(r'\s+', ' ', name).strip()[:MAX_NAME]


# What a receipt is called when no store name could be read: never learned or matched,
# or every unnamed receipt would inherit one purchase's category.
PLACEHOLDER_STORES = {'חשבונית', 'receipt', ''}


def _store_key(store):
    key = re.sub(r'\s+', ' ', str(store or '')).strip().lower()
    return '' if key in PLACEHOLDER_STORES else key


SEP = ' › '


def split_path(path):
    """'תחבורה › מונית' -> ('תחבורה', 'מונית'); 'תחבורה' -> ('תחבורה', None)."""
    text = str(path or '')
    for sep in (SEP, '›', '>'):
        if sep in text:
            top, sub = text.split(sep, 1)
            return clean(top), (clean(sub) or None)
    return clean(text), None


def join_path(category, sub=None):
    return category + SEP + sub if sub else category


def subs_of(data, category):
    return data.setdefault('subs', {}).get(category, [])


def add_sub(data, category, sub):
    """Make sure the sub-category exists under the category; its stored spelling."""
    category, sub = add(data, category), clean(sub)
    if not sub:
        raise ValueError('empty sub-category')
    subs = data.setdefault('subs', {}).setdefault(category, [])
    existing = next((s for s in subs if s.lower() == sub.lower()), None)
    if existing:
        return existing
    subs.append(sub)
    return sub


def add_path(data, path):
    """Create the category (and sub-category) a path names; the stored path."""
    top, sub = split_path(path)
    top = add(data, top)
    return join_path(top, add_sub(data, top, sub) if sub else None)


def assign(entry, path):
    """Put the purchase in this category / sub-category."""
    top, sub = split_path(path)
    entry['category'] = top
    if sub:
        entry['subcategory'] = sub
    else:
        entry.pop('subcategory', None)


def targets(data):
    """Every place a purchase can go: each category followed by its sub-categories."""
    out = []
    for cat in data['categories']:
        out.append(cat)
        out += [join_path(cat, s) for s in subs_of(data, cat)]
    return out


def find(data, name):
    """The existing category matching name (case/space-insensitive), else None."""
    key = clean(name).lower()
    return next((c for c in data['categories'] if c.lower() == key), None)


def add(data, name):
    """Make sure the category exists; returns its stored spelling."""
    name = clean(name)
    if not name:
        raise ValueError('empty category')
    existing = find(data, name)
    if existing:
        return existing
    data['categories'].append(name)
    return name


def suggest(data, store, claude_guess=None):
    """The store's remembered category first, then Claude's guess (mapped onto an
    existing category when it names one), else UNCATEGORISED."""
    remembered = data['stores'].get(_store_key(store))
    if remembered:
        return remembered
    guess = clean(claude_guess)
    if guess:
        return find(data, guess) or guess
    return UNCATEGORISED


def learn(data, store, category):
    """Remember the category (a path) for this store and keep it in the list."""
    category = add_path(data, category)
    if _store_key(store):
        data['stores'][_store_key(store)] = category
    return category


def category_of(entry):
    return clean(entry.get('category')) or UNCATEGORISED


def sub_of(entry):
    return clean(entry.get('subcategory')) or None


def path_of(entry):
    return join_path(category_of(entry), sub_of(entry))


def by_sub(entries, month_key, category, cycle=True):
    """{sub-category or None: total} inside one category for one month."""
    totals = {}
    for entry in ex.month_summary(entries, month_key, cycle)['entries']:
        if category_of(entry) == category:
            sub = sub_of(entry)
            totals[sub] = round(totals.get(sub, 0.0) + float(entry.get('amount', 0) or 0), 2)
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def by_category(entries, month_key, cycle=True):
    """{category: total} for one spending month, biggest first."""
    totals = {}
    for entry in ex.month_summary(entries, month_key, cycle)['entries']:
        cat = category_of(entry)
        totals[cat] = round(totals.get(cat, 0.0) + float(entry.get('amount', 0) or 0), 2)
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def previous_month(month_key):
    y, m = int(month_key[:4]), int(month_key[5:7])
    return '%04d-%02d' % ((y, m - 1) if m > 1 else (y - 1, 12))


def _esc(text):
    return re.sub(r'[*_`\[\]]', '', str(text or ''))


def format_block(entries, month_key, cycle=True):
    """Markdown: this month per category, each next to the month before it."""
    now = by_category(entries, month_key, cycle)
    prev_key = previous_month(month_key)
    before = by_category(entries, prev_key, cycle)
    total = sum(now.values())
    lines = ['🏷 *לפי קטגוריה*  _(מול %s)_' % datetime.strptime(prev_key, '%Y-%m').strftime('%b %Y')]
    if not now:
        lines.append('_אין הוצאות בחודש הזה._')
        return '\n'.join(lines)
    for cat in list(now) + [c for c in before if c not in now]:
        amount, last = now.get(cat, 0.0), before.get(cat, 0.0)
        share = ' · %d%%' % round(amount / total * 100) if total and amount else ''
        if not last:
            delta = ' _(חדש)_' if amount else ''
        elif not amount:
            delta = ' _(היה %s)_' % ex.money(last)
        else:
            diff = amount - last
            delta = ' _(%s%s, %s%d%%)_' % ('+' if diff >= 0 else '-', ex.money(abs(diff)),
                                          '+' if diff >= 0 else '-', round(abs(diff) / last * 100))
        lines.append('• %s: *%s*%s%s' % (_esc(cat), ex.money(amount), share, delta))
    if before:
        diff = total - sum(before.values())
        lines.append('_סה"כ מול החודש הקודם: %s%s_' % ('+' if diff >= 0 else '-', ex.money(abs(diff))))
    return '\n'.join(lines)


def format_trend(entries, months, cycle=True):
    """Markdown: the last few months side by side, total and top categories."""
    lines = ['📈 *חודש מול חודש*']
    for key in months:
        cats = by_category(entries, key, cycle)
        if not cats:
            continue
        top = ', '.join('%s %s' % (_esc(c), ex.money(v)) for c, v in list(cats.items())[:3])
        lines.append('`%s` *%s* — %s' % (key, ex.money(sum(cats.values())), top))
    return '\n'.join(lines) if len(lines) > 1 else ''


# ----------------------------------------------------------------------------- learning, AI classification

def _desc_key(text):
    return re.sub(r'\s+', ' ', str(text or '')).strip().lower()


def remembered(data, entry):
    """The category already learned for this store or this exact description, else None."""
    return (data['stores'].get(_store_key(entry.get('store')))
            or data.setdefault('descriptions', {}).get(_desc_key(entry.get('description'))))


def learn_description(data, description, category):
    category = add_path(data, category)
    if _desc_key(description):
        data.setdefault('descriptions', {})[_desc_key(description)] = category
    return category


CLASSIFY_MODEL = 'claude-opus-5-5'
PRICE_IN, PRICE_OUT = 4.0, 20.0           # $ per million tokens
CLASSIFY_SCHEMA = {
    'type': 'object',
    'properties': {'items': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'id': {'type': 'integer'}, 'category': {'type': 'string'}},
        'required': ['id', 'category'], 'additionalProperties': False}}},
    'required': ['items'], 'additionalProperties': False,
}
CLASSIFY_PROMPT = """These are personal expenses of someone in Israel, written by them (Hebrew or English).
Give each one a spending category.

Use one of these categories whenever one fits: {names}.
Only when none fits, make up a short, general Hebrew category name (2-3 words) that later
expenses of the same kind could share (e.g. "סיגריות וטבק", "חניה"). Delivery food (wolt,
וולט) and cafés go to the restaurants category. Unclear ones ("לא ידוע", a bank difference)
go to "אחר".

Expenses (JSON): {items}
Return every id exactly once."""


def classify(client, entries, categories):
    """{position in entries: category} from Claude, and the cost in $."""
    import json as _json
    items = [{'id': i, 'description': str(e.get('description') or ''), 'store': e.get('store'),
              'amount': e.get('amount')} for i, e in enumerate(entries)]
    message = client.messages.create(
        model=CLASSIFY_MODEL, max_tokens=4000,
        output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': CLASSIFY_SCHEMA}},
        messages=[{'role': 'user', 'content': CLASSIFY_PROMPT.format(
            names=', '.join(categories), items=_json.dumps(items, ensure_ascii=False))}])
    cost = (message.usage.input_tokens * PRICE_IN + message.usage.output_tokens * PRICE_OUT) / 1e6
    text = next((b.text for b in message.content if b.type == 'text'), '')
    out = {}
    for item in (_json.loads(text) if text else {}).get('items', []):
        name = clean(item.get('category'))
        if name and isinstance(item.get('id'), int) and 0 <= item['id'] < len(entries):
            out[item['id']] = name
    return out, cost


# ----------------------------------------------------------------------------- reports

def _share_lines(totals, limit=None):
    total = sum(totals.values())
    rows = list(totals.items())[:limit] if limit else list(totals.items())
    return ['• %s — *%s* · %d%%' % (_esc(c), ex.money(v), round(v / total * 100) if total else 0)
            for c, v in rows]


def _sub_lines(entries, month_key, category, cycle=True):
    subs = by_sub(entries, month_key, category, cycle)
    if not any(subs):
        return []
    return ['   ◦ %s — %s' % (_esc(s) if s else 'כללי', ex.money(v)) for s, v in subs.items()]


def _budget_note(spent, budget):
    """' · 🟢 מתוך ₪550.00 (60%)' -- the category against its /budget."""
    pct = spent / budget * 100 if budget else 0
    mark = '🔴' if pct >= 100 else ('🟠' if pct >= 80 else '🟢')
    note = ' · %s מתוך %s (%d%%' % (mark, ex.money(budget), round(pct))
    if spent > budget:
        note += ', חריגה %s' % ex.money(spent - budget)
    else:
        note += ', נשארו %s' % ex.money(budget - spent)
    return note + ')'


def share_block(entries, month_key, cycle=True, data=None):
    """Markdown for /ilspendhistory: the month per category (and sub-category), ₪ and %,
    and against its monthly budget where one is set (/budget)."""
    totals = by_category(entries, month_key, cycle)
    plan = budgets(data if data is not None else load())
    if not totals and not plan:
        return ''
    lines = ['🏷 *לפי קטגוריה:*']
    for line, cat in zip(_share_lines(totals), totals):
        lines.append(line + (_budget_note(totals[cat], plan[cat]) if cat in plan else ''))
        lines += _sub_lines(entries, month_key, cat, cycle)
    for cat, amount in plan.items():           # budgeted, nothing spent yet
        if cat not in totals:
            lines.append('• %s — *%s*%s' % (_esc(cat), ex.money(0), _budget_note(0.0, amount)))
    if plan:
        spent = sum(totals.get(c, 0.0) for c in plan)
        left = sum(max(0.0, amount - totals.get(c, 0.0)) for c, amount in plan.items())
        lines.append('💼 _בקטגוריות עם תקציב: %s מתוך %s — נשארו %s להוציא_'
                     % (ex.money(spent), ex.money(sum(plan.values())), ex.money(left)))
    lines.append('_לחץ על קטגוריה למטה כדי לראות ולהעביר הוצאות_')
    return '\n'.join(lines)


def uncategorised(entries, months, cycle=True):
    """Spending records in these months with no category: (index in entries, entry)."""
    keys = set(months)
    of = ex.cycle_month_of if cycle else ex.month_of
    return [(i, e) for i, e in enumerate(entries or [])
            if not ex.is_cancelled(e) and not ex.is_investment(e) and of(e) in keys and not clean(e.get("category"))]


def format_categories(entries, month_key, previous=3, cycle=True):
    """/categories: this month in full (₪, %, count, vs last month), then each of the
    previous months on its own."""
    def label(key):
        return datetime.strptime(key, '%Y-%m').strftime('%B %Y')

    lines = ['🏷 *הוצאות לפי קטגוריה*', '']
    start, end = ex.cycle_range(month_key)
    now = by_category(entries, month_key, cycle)
    last = by_category(entries, previous_month(month_key), cycle)
    total = sum(now.values())
    lines.append('📅 *%s* _(%s – %s, עד עכשיו)_' % (label(month_key), start.strftime('%d/%m'), end.strftime('%d/%m')))
    if not now:
        lines.append('_אין הוצאות עדיין._')
    rows = ex.month_summary(entries, month_key, cycle)['entries']
    for cat, amount in now.items():
        count = sum(1 for e in rows if category_of(e) == cat)
        was = last.get(cat, 0.0)
        vs = (' _(חודש שעבר %s)_' % ex.money(was)) if was else ''
        lines.append('• %s — *%s* · %d%% · %d רכישות%s' % (
            _esc(cat), ex.money(amount), round(amount / total * 100) if total else 0, count, vs))
        lines += _sub_lines(entries, month_key, cat, cycle)
    if now:
        lines.append('💸 *סה"כ: %s*' % ex.money(total))
    key = month_key
    for _ in range(previous):
        key = previous_month(key)
        totals = by_category(entries, key, cycle)
        start, end = ex.cycle_range(key)
        lines += ['', '📅 *%s* _(%s – %s)_' % (label(key), start.strftime('%d/%m'), end.strftime('%d/%m'))]
        if not totals:
            lines.append('_אין הוצאות._')
            continue
        lines += _share_lines(totals)
        lines.append('💸 סה"כ: *%s*' % ex.money(sum(totals.values())))
    return '\n'.join(lines)


# ----------------------------------------------------------------------------- budgets

ALERT_LEVELS = (80, 100)


def budgets(data):
    return data.setdefault('budgets', {})


def set_budget(data, category, amount):
    """amount 0 / None removes the budget. Returns the category's stored spelling."""
    category = add(data, category)
    if amount:
        budgets(data)[category] = round(float(amount), 2)
    else:
        budgets(data).pop(category, None)
    return category


def _bar(pct, width=10):
    filled = min(width, int(round(min(pct, 100) / 100 * width)))
    return '▓' * filled + '░' * (width - filled)


def budget_status(data, entries, month_key, cycle=True):
    """[(category, spent, budget, pct)] for every budgeted category, fullest first."""
    spent = by_category(entries, month_key, cycle)
    rows = [(cat, spent.get(cat, 0.0), amount, spent.get(cat, 0.0) / amount * 100 if amount else 0.0)
            for cat, amount in budgets(data).items()]
    return sorted(rows, key=lambda r: -r[3])


def format_budgets(data, entries, month_key, cycle=True):
    rows = budget_status(data, entries, month_key, cycle)
    start, end = ex.cycle_range(month_key)
    lines = ['💼 *תקציב לפי קטגוריה*', '_%s – %s_' % (start.strftime('%d/%m'), end.strftime('%d/%m')), '']
    if not rows:
        return '\n'.join(lines + ['_אין עדיין תקציבים. לחץ על קטגוריה למטה, או: /budget סופר 1500_'])
    for cat, spent, amount, pct in rows:
        mark = '🔴' if pct >= 100 else ('🟠' if pct >= 80 else '🟢')
        left = amount - spent
        lines.append('%s *%s* — %s מתוך %s' % (mark, _esc(cat), ex.money(spent), ex.money(amount)))
        lines.append('   `%s` %d%% · %s' % (_bar(pct), round(pct),
                                            ('נשארו %s' % ex.money(left)) if left >= 0 else ('חריגה של %s' % ex.money(-left))))
    total_b = sum(r[2] for r in rows)
    total_s = sum(r[1] for r in rows)
    lines += ['', '💸 בקטגוריות עם תקציב: %s מתוך %s' % (ex.money(total_s), ex.money(total_b))]
    return '\n'.join(lines)


def budget_alert(data, entries, month_key, category, cycle=True):
    """A warning the first time this month's spending in the category crosses 80% or
    100% of its budget (each level once a month), else None. Marks it as sent."""
    amount = budgets(data).get(category)
    if not amount:
        return None
    spent = by_category(entries, month_key, cycle).get(category, 0.0)
    pct = spent / amount * 100
    level = max([lv for lv in ALERT_LEVELS if pct >= lv], default=0)
    sent = data.setdefault('budget_alerts', {}).setdefault(month_key, {})
    if not level or sent.get(category, 0) >= level:
        return None
    sent[category] = level
    if level >= 100:
        return '🔴 *חרגת מהתקציב של %s*\nהוצאת %s מתוך %s (%d%%) — חריגה של %s' % (
            _esc(category), ex.money(spent), ex.money(amount), round(pct), ex.money(spent - amount))
    return '🟠 *%d%% מהתקציב של %s*\nהוצאת %s מתוך %s — נשארו %s עד סוף החודש' % (
        round(pct), _esc(category), ex.money(spent), ex.money(amount), ex.money(amount - spent))


def format_budget_summary(data, entries, month_key, cycle=True):
    """For the summary on the 10th: which budgets held and which went over."""
    rows = budget_status(data, entries, month_key, cycle)
    if not rows:
        return ''
    over = [r for r in rows if r[3] >= 100]
    lines = ['💼 *תקציבים*']
    for cat, spent, amount, pct in rows:
        lines.append('%s %s — %s / %s (%d%%)' % ('🔴' if pct >= 100 else '🟢', _esc(cat),
                                                ex.money(spent), ex.money(amount), round(pct)))
    lines.append('_%s_' % ('חריגה ב-%d קטגוריות' % len(over) if over else 'כל התקציבים נשמרו 👏'))
    return '\n'.join(lines)
