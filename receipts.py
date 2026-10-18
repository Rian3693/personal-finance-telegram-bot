"""Receipts (חשבוניות): read a photo or PDF with Claude, keep every line item.

scan() sends the image to Claude Opus 5.5 and gets the receipt back as JSON
(structured output): the store, the date, each item with its quantity / weight
and price, the discounts, the VAT and the total. Price per kilo is worked out
here from the line total and the weight, so it can be compared across stores
later (/prices). Nothing here moves money: the bot records the purchase through
the normal /ilspend path once you say how you paid.
"""

import base64
import json
import os
import re

MODEL = 'claude-opus-5-5'
PRICE_IN, PRICE_OUT = 4.0, 20.0           # $ per million tokens
VAT_RATE = 0.18                           # Israel, from January 2025
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'receipts')

_NUM = {'type': ['number', 'null']}
_STR = {'type': ['string', 'null']}
SCHEMA = {
    'type': 'object',
    'properties': {
        'is_receipt': {'type': 'boolean'},
        'store_name': _STR,
        'store_branch': _STR,
        'is_grocery': {'type': 'boolean'},
        'date': _STR,
        'currency': {'type': 'string'},
        'items': {'type': 'array', 'items': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'generic_name': {'type': 'string'},
                'category': {'type': 'string'},
                'quantity': _NUM,
                'unit': {'type': 'string', 'enum': ['kg', 'g', 'unit', 'l', 'ml']},
                'weight_kg': _NUM,
                'unit_price': _NUM,
                'line_total': {'type': 'number'},
            },
            'required': ['name', 'generic_name', 'category', 'quantity', 'unit', 'weight_kg', 'unit_price', 'line_total'],
            'additionalProperties': False,
        }},
        'discounts': _NUM,
        'subtotal': _NUM,
        'vat': _NUM,
        'total': {'type': 'number'},
        'paid_with': {'type': 'string', 'enum': ['cash', 'card', 'unknown']},
        'expense_category': {'type': 'string'},
    },
    'required': ['is_receipt', 'store_name', 'store_branch', 'is_grocery', 'date', 'currency', 'items',
                 'discounts', 'subtotal', 'vat', 'total', 'paid_with', 'expense_category'],
    'additionalProperties': False,
}

PROMPT = """This is a photo of a shop receipt (חשבונית / קבלה), usually Israeli and in Hebrew.
Read it and return every purchased line.

- store_name: the shop or chain (e.g. שופרסל, רמי לוי, KSP); store_branch if printed.
- is_grocery: true for supermarkets, groceries, markets, bakeries, butchers.
- date: the purchase date as YYYY-MM-DD (Israeli receipts print DD/MM/YY), null if absent.
- For each item: name exactly as printed; generic_name = a short plain Hebrew name a person
  would search for (e.g. "עגבניות", "חלב 3%", "חזה עוף", "אוזניות"); category in Hebrew
  (ירקות, פירות, מוצרי חלב, בשר, ניקיון, אלקטרוניקה, ...).
- Weighed items (שקיל): unit "kg", quantity and weight_kg = the weight, unit_price = price per kg.
- Packaged items: unit "unit", quantity = how many; weight_kg = the total weight bought when the
  package size is printed or obvious from the name (e.g. "אורז 1 ק"ג" x2 -> 2.0), else null.
- line_total = what was paid for that line after its own discount. Put receipt-level discounts
  in `discounts` (a positive number).
- vat = the VAT (מע"מ) amount if printed, else null. total = the final amount paid.
- paid_with: "cash" / "card" if the receipt says (מזומן / אשראי), else "unknown".
- expense_category: what the whole purchase was for, in short Hebrew (e.g. סופר ומכולת, מסעדות
  ואוכל בחוץ, תחבורה, דלק ורכב, ביגוד והנעלה, בריאות ופארם, בית, אלקטרוניקה).
- If the image is not a receipt, set is_receipt false and leave items empty.
Do not invent lines you cannot read."""

MULTI = """These {n} images are parts of ONE receipt (e.g. top and bottom of a long one). Combine
them into a single receipt; where the parts overlap, list each line only once."""

CATEGORIES = """For expense_category, use one of the user's categories when one fits: {names}.
Only if none fits, give a new short Hebrew name."""


def media_type_of(filename, default='image/jpeg'):
    name = (filename or '').lower()
    for ext, kind in (('.png', 'image/png'), ('.webp', 'image/webp'), ('.gif', 'image/gif'),
                      ('.pdf', 'application/pdf'), ('.jpg', 'image/jpeg'), ('.jpeg', 'image/jpeg')):
        if name.endswith(ext):
            return kind
    return default


def _block(data, media_type):
    encoded = base64.standard_b64encode(bytes(data)).decode('utf-8')
    return ({'type': 'document', 'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': encoded}}
            if media_type == 'application/pdf' else
            {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': encoded}})


def scan(client, data, media_type='image/jpeg', categories=None, extra=()):
    """(receipt dict, cost in $). Raises ValueError when it cannot be read.

    extra: more (data, media_type) parts of the same receipt (a long one photographed
    in two). categories: the user's category names, so the suggestion uses them."""
    parts = [(data, media_type)] + list(extra or ())
    prompt = PROMPT
    if len(parts) > 1:
        prompt += '\n\n' + MULTI.format(n=len(parts))
    if categories:
        prompt += '\n\n' + CATEGORIES.format(names=', '.join(categories))
    content = [_block(d, t) for d, t in parts] + [{'type': 'text', 'text': prompt}]
    message = client.messages.create(
        model=MODEL, max_tokens=16000,
        output_config={'effort': 'medium', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
        messages=[{'role': 'user', 'content': content}])
    cost = (message.usage.input_tokens * PRICE_IN + message.usage.output_tokens * PRICE_OUT) / 1e6
    if message.stop_reason == 'refusal':
        raise ValueError('Claude declined to read this image')
    if message.stop_reason == 'max_tokens':
        raise ValueError('the receipt is too long to read in one go')
    text = next((b.text for b in message.content if b.type == 'text'), '')
    try:
        receipt = json.loads(text)
    except ValueError:
        raise ValueError('could not read the receipt')
    return enrich(receipt), cost


def enrich(receipt):
    """Price per kilo for every item with a known weight; VAT estimated when not printed."""
    for item in receipt.get('items') or []:
        weight = item.get('weight_kg')
        if not weight and item.get('unit') == 'g' and item.get('quantity'):
            weight = item['quantity'] / 1000.0
        if not weight and item.get('unit') == 'kg' and item.get('quantity'):
            weight = item['quantity']
        item['weight_kg'] = round(float(weight), 3) if weight else None
        item['price_per_kg'] = (round(float(item['line_total']) / item['weight_kg'], 2)
                                if item['weight_kg'] and item.get('line_total') else None)
    if receipt.get('vat') is None and receipt.get('total'):
        receipt['vat'] = round(float(receipt['total']) * VAT_RATE / (1 + VAT_RATE), 2)
        receipt['vat_estimated'] = True
    else:
        receipt['vat_estimated'] = False
    return receipt


def save_image(data, entry_id, media_type, part=1):
    """The photo next to the receipts; a second photo of the same one is <id>_2."""
    os.makedirs(DIR, exist_ok=True)
    ext = {'image/png': '.png', 'image/webp': '.webp', 'application/pdf': '.pdf', 'image/gif': '.gif'}.get(media_type, '.jpg')
    path = os.path.join(DIR, entry_id + ('' if part == 1 else '_%d' % part) + ext)
    with open(path, 'wb') as fh:
        fh.write(bytes(data))
    return path


def _money(amount):
    return ('-' if amount < 0 else '') + '₪{:,.2f}'.format(abs(float(amount)))


def _safe(text):
    return re.sub(r'[*_`\[\]]', '', str(text or ''))


def _qty(item):
    if item.get('unit') == 'kg' and item.get('quantity'):
        return '%.3g ק"ג' % item['quantity']
    if item.get('unit') == 'g' and item.get('quantity'):
        return '%g גר׳' % item['quantity']
    if item.get('unit') in ('l', 'ml') and item.get('quantity'):
        return '%g %s' % (item['quantity'], 'ל׳' if item['unit'] == 'l' else 'מ"ל')
    return '×%g' % (item.get('quantity') or 1)


def format_receipt(r, limit=40):
    """The scanned receipt, before you confirm how you paid."""
    head = '🧾 *%s*' % _safe(r.get('store_name') or 'חשבונית')
    if r.get('store_branch'):
        head += ' — %s' % _safe(r['store_branch'])
    lines = [head, '📅 %s%s' % (r.get('date') or 'בלי תאריך', ' · 🛒 מכולת/סופר' if r.get('is_grocery') else ''), '━' * 18]
    items = r.get('items') or []
    for item in items[:limit]:
        line = '• %s — %s · *%s*' % (_safe(item['name']), _qty(item), _money(item['line_total']))
        if item.get('price_per_kg'):
            line += '  _(%s לק"ג)_' % _money(item['price_per_kg'])
        lines.append(line)
    if len(items) > limit:
        lines.append('_+%d פריטים נוספים_' % (len(items) - limit))
    lines.append('━' * 18)
    if r.get('subtotal'):
        lines.append('סכום ביניים: %s' % _money(r['subtotal']))
    if r.get('discounts'):
        lines.append('הנחות: -%s' % _money(r['discounts']))
    if r.get('vat') is not None:
        lines.append('מע"מ: %s%s' % (_money(r['vat']),
                                    ' _(הערכה 18% — לא מופיע בחשבונית; פירות וירקות פטורים)_' if r.get('vat_estimated') else ''))
    lines.append('💰 *סה"כ: %s*  _(%d פריטים)_' % (_money(r['total']), len(items)))
    return '\n'.join(lines)


# ----------------------------------------------------------------------------- looking back

def receipts_in(entries):
    """(entry, receipt) for every logged purchase that came from a receipt, newest first."""
    rows = [(e, e['receipt']) for e in entries or [] if isinstance(e.get('receipt'), dict)
            and not e.get('cancelled')]
    return sorted(rows, key=lambda p: (p[0].get('date', ''), p[0].get('time', '')), reverse=True)


def format_receipts(entries, limit=10):
    rows = receipts_in(entries)
    if not rows:
        return '🧾 *חשבוניות*\n\n_אין עדיין. שלח צילום של חשבונית (או /receipt) והבוט יסרוק אותה._'
    lines = ['🧾 *חשבוניות אחרונות*', '']
    for n, (e, r) in enumerate(rows[:limit], 1):
        lines.append('*%d.* `%s` %s — *%s* _(%d פריטים)_' % (
            n, e.get('date', ''), _safe(r.get('store_name') or '?'), _money(e.get('amount', 0)), len(r.get('items') or [])))
    lines += ['', '_פירוט: /receipts 1 · מחירים לפי מוצר: /prices עגבניות_']
    return '\n'.join(lines)


def format_receipt_detail(entries, n):
    rows = receipts_in(entries)
    if not 1 <= n <= len(rows):
        return '❌ אין חשבונית מספר %d — /receipts' % n
    e, r = rows[n - 1]
    return format_receipt(r) + '\n_נרשם ב-%s · %s_' % (e.get('date', ''), e.get('card', ''))


def price_history(entries, query):
    """Every bought item matching `query` (in its plain or printed name)."""
    q = (query or '').strip().lower()
    out = []
    for e, r in receipts_in(entries):
        for item in r.get('items') or []:
            if q in (item.get('generic_name') or '').lower() or q in (item.get('name') or '').lower():
                out.append({'date': r.get('date') or e.get('date'), 'store': r.get('store_name') or '?',
                            'name': item.get('name'), 'generic': item.get('generic_name'),
                            'price_per_kg': item.get('price_per_kg'), 'line_total': item.get('line_total'),
                            'qty': _qty(item), 'unit_price': item.get('unit_price')})
    return out


def format_prices(entries, query):
    rows = price_history(entries, query)
    if not rows:
        return '🔎 *%s*\n\n_לא מצאתי את זה בחשבוניות שנסרקו._' % _safe(query)
    per_kg = sorted([r for r in rows if r['price_per_kg']], key=lambda r: r['price_per_kg'])
    lines = ['🔎 *%s* — %d קניות' % (_safe(query), len(rows))]
    if per_kg:
        lines += ['', '⚖️ *מחיר לק"ג, מהזול ליקר:*']
        for r in per_kg:
            lines.append('`%s` %s — *%s לק"ג* _(%s · %s)_' % (r['date'], _safe(r['store']), _money(r['price_per_kg']),
                                                          _safe(r['name']), r['qty']))
        prices = [r['price_per_kg'] for r in per_kg]
        lines.append('_הכי זול %s · ממוצע %s · הכי יקר %s_' % (
            _money(min(prices)), _money(sum(prices) / len(prices)), _money(max(prices))))
    other = [r for r in rows if not r['price_per_kg']]
    if other:
        lines += ['', '🏷 *לפי יחידה:*']
        for r in sorted(other, key=lambda r: (r['unit_price'] or r['line_total'] or 0)):
            lines.append('`%s` %s — *%s* _(%s · %s)_' % (r['date'], _safe(r['store']),
                                                      _money(r['unit_price'] or r['line_total']), _safe(r['name']), r['qty']))
    return '\n'.join(lines)


def match_candidates(entries, total, day=None, limit=3):
    """Logged purchases this receipt probably belongs to: (index in entries, entry).

    Same amount (within ₪1 or 2%), no receipt yet, not cancelled; when the receipt
    has a date, within 3 days of it. Closest first."""
    from datetime import datetime as _dt
    try:
        target = _dt.strptime(day, '%Y-%m-%d').date() if day else None
    except ValueError:
        target = None
    total = float(total or 0)
    found = []
    for index, entry in enumerate(entries or []):
        if entry.get('cancelled') or entry.get('kind') == 'investment' or isinstance(entry.get('receipt'), dict):
            continue
        try:
            amount = float(entry.get('amount') or 0)
            when = _dt.strptime(entry.get('date', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            continue
        gap = abs(amount - total)
        if gap > max(1.0, total * 0.02):
            continue
        days = abs((when - target).days) if target else 0
        if target and days > 3:
            continue
        found.append((days, gap, index, entry))
    found.sort(key=lambda f: (f[0], f[1]))
    return [(index, entry) for _, _, index, entry in found[:limit]]
