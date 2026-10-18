"""What /payment suggested, against what was actually moved.

/payment works out a split and stops there: the money is moved by hand, at the
bank and the exchange, and rarely to the shekel. /allocated asks, destination by
destination, what really went where (and, for euros and dollars, at what rate),
and keeps both side by side on the payment record, so each month can be read
back as "planned X, did Y, at these rates".

It records; it does not move balances. Deposits are still logged with
/addreserve and /addcash, so nothing is counted twice.
"""

import re
from datetime import datetime

import savings_planner as sp

CHECKING = 'CHECKING'
KEREN_SELF = 'KEREN_SELF'
STEP_LABEL = {CHECKING: '\U0001F4B3 עו"ש (/ilcash)', KEREN_SELF: '\U0001F510 קרן השתלמות לעצמאיים',
              'ILS_EMERGENCY': '\U0001F6DF קרן חירום',
              'ILS_FUTURE': '\U0001F3AF הוצאות עתידיות', 'EUR': '\U0001F4B6 יורו → קרן כספית (₪)',
              'USD_STOCKS': '\U0001F4C8 מניות (דולר)'}
# The euro share is bought in shekels, as a קרן כספית kept for euros (savings_planner.EUR_FUND),
# so it is a shekel step with no rate to ask.
STEP_CCY = {CHECKING: 'ILS', KEREN_SELF: 'ILS', 'ILS_EMERGENCY': 'ILS', 'ILS_FUTURE': 'ILS', 'EUR': 'ILS', 'USD_STOCKS': 'USD'}
FX_KEY = {'EUR': 'EURILS', 'USD': 'USDILS'}
RATE_RANGE = (2.0, 8.0)                  # shekels per euro/dollar that are believable


def money(amount, ccy='ILS'):
    return sp.money(amount, ccy)


def latest_payment(plan, month=None):
    """(index, payment) for `month`, or the most recent payment of all; (None, None)."""
    payments = plan.get('payments') or []
    for index in range(len(payments) - 1, -1, -1):
        if month is None or payments[index].get('month') == month:
            return index, payments[index]
    return None, None


def find_payment(plan, stamp):
    """The payment with this 'date' stamp, wherever it now sits in the list."""
    for index, payment in enumerate(plan.get('payments') or []):
        if payment.get('date') == stamp:
            return index, payment
    return None, None


def breakdown_from_record(payment):
    """The /payment breakdown, rebuilt from what was stored with the payment, so it
    can be shown again exactly as suggested (even if the plan changed since)."""
    split = {b: float(v or 0) for b, v in (payment.get('split') or {}).items()}
    refill = float(payment.get('refill') or 0)
    excess = float(payment.get('excess') or 0)
    before = float(payment.get('checking_before') or 0)
    ils = sum(split.get(b, 0) for b in sp.ILS_FUNDS)
    bd = {
        'amount': float(payment['amount']), 'refill': refill, 'excess': excess,
        'base': float(payment.get('base') or 0), 'split': split,
        'keren_self': float(payment.get('keren_self') or 0),
        'unallocated': float(payment.get('unallocated') or 0),
        'fee': sp.ILS_TRANSFER_FEE if ils > 0 else 0.0,
        'checking_before': before, 'checking_after': round(before + refill, 2),
        'target': float(payment.get('float_target') or round(before + refill, 2)),
        'budget': round(refill + excess, 2), 'short': float(payment['amount']) - refill <= 0,
    }
    if payment.get('in_checking'):
        bd['in_checking'] = True
        bd['checking_shown'] = round(before + float(payment['amount']), 2)
    return bd


def suggestion_steps(payment):
    """The destinations /payment proposed. What stays in the עו"ש is not a step: it
    is worked out at the end from what really went out (see checking_left)."""
    split = payment.get('split') or {}
    steps = []
    if float(payment.get('keren_self') or 0) > 0:
        steps.append({'key': KEREN_SELF, 'ils': round(float(payment['keren_self']), 2)})
    steps.append({'key': 'ILS_EMERGENCY', 'ils': round(float(split.get('ILS_EMERGENCY', 0) or 0), 2)})
    # /payment has already folded the unused expense budget into this figure and
    # taken the bank fee off it: it is exactly the "Future expenses total" shown.
    steps.append({'key': 'ILS_FUTURE', 'ils': round(float(split.get('ILS_FUTURE', 0) or 0), 2)})
    steps.append({'key': 'EUR', 'ils': round(float(split.get('EUR', 0) or 0), 2)})
    steps.append({'key': 'USD_STOCKS', 'ils': round(float(split.get('USD_STOCKS', 0) or 0), 2)})
    for step in steps:
        step['ccy'] = STEP_CCY[step['key']]
        step['label'] = STEP_LABEL[step['key']]
    return steps


def _check_rate(rate):
    if not RATE_RANGE[0] <= rate <= RATE_RANGE[1]:
        raise ValueError('שער %.4g לא נראה נכון (צפוי בין %g ל-%g)' % (rate, RATE_RANGE[0], RATE_RANGE[1]))
    return rate


def parse_amount(text, step):
    """One typed answer to a step.

    Shekel steps: the finished entry. Euro and dollar steps: a partial entry --
    the shekels spent ("394"), or the foreign amount marked with €/$ ("€115"),
    with the rate if it was typed too ("394 3.40"); with_rate() completes it.
    Raises ValueError with a readable reason.
    """
    raw = (text or '').strip()
    numbers = [float(n.replace(',', '')) for n in re.findall(r'\d[\d,]*(?:\.\d+)?', raw)]
    if not numbers:
        raise ValueError('לא מצאתי סכום')
    if '-' in raw.replace(' ', '')[:1]:
        raise ValueError('סכום לא יכול להיות שלילי')
    if step['ccy'] == 'ILS':
        return {'ils': round(numbers[0], 2), 'foreign': None, 'rate': None, 'rate_source': None}
    foreign_first = bool(re.search(r'[€$]|\b(eur|usd|euro|dollar)\b|יורו|דולר', raw, re.I))
    rate = _check_rate(numbers[1]) if len(numbers) > 1 else None
    return {'value': numbers[0], 'foreign_first': foreign_first, 'rate': rate}


def parse_rate(text):
    """A typed exchange rate ("3.42")."""
    numbers = re.findall(r'\d+(?:\.\d+)?', (text or '').replace(',', '.'))
    if not numbers:
        raise ValueError('לא מצאתי שער — שלח מספר, למשל 3.42')
    return _check_rate(float(numbers[0]))


def with_rate(partial, rate, source):
    """Complete a euro/dollar entry with the rate it was converted at."""
    rate = float(rate)
    if partial['foreign_first']:
        foreign, ils = partial['value'], partial['value'] * rate
    else:
        ils, foreign = partial['value'], (partial['value'] / rate if rate else 0.0)
    return {'ils': round(ils, 2), 'foreign': round(foreign, 2), 'rate': round(rate, 4), 'rate_source': source}


def parse_actual(text, step, market_rate=None):
    """One answer in a single go: the typed rate if given, else the market rate."""
    got = parse_amount(text, step)
    if step['ccy'] == 'ILS':
        return got
    if got['rate'] is not None:
        return with_rate(got, got['rate'], 'yours')
    if market_rate is None:
        raise ValueError('צריך גם את השער, למשל: 394 3.40')
    return with_rate(got, _check_rate(market_rate), 'market')


def suggested_partial(step):
    """'As suggested' on a euro/dollar step: the suggested shekels, rate still to ask."""
    return {'value': step['ils'], 'foreign_first': False, 'rate': None}


def as_suggested(step, market_rate=None):
    if step['ccy'] == 'ILS':
        return {'ils': step['ils'], 'foreign': None, 'rate': None, 'rate_source': None}
    rate = market_rate or 0.0
    return {'ils': step['ils'], 'foreign': round(step['ils'] / rate, 2) if rate else None,
            'rate': round(rate, 4) if rate else None, 'rate_source': 'market'}


def checking_left(payment, steps, actual):
    """What should be left in the עו"ש after the moves: the balance with the payment
    in it, less everything that went out and the bank fee for the ILS transfer."""
    start = round(float(payment.get('checking_before') or 0) + float(payment['amount']), 2)
    moved = round(sum(actual[s['key']]['ils'] for s in steps), 2)
    to_bank = sum(actual[s['key']]['ils'] for s in steps if s['key'] in sp.ILS_FUNDS)
    fee = sp.ILS_TRANSFER_FEE if to_bank > 0 else 0.0
    target = round(float(payment.get('checking_before') or 0) + float(payment.get('refill') or 0), 2)
    return {'start': start, 'moved': moved, 'fee': fee, 'expected': round(start - moved - fee, 2),
            'target': target}


def parse_balance(text):
    """The עו"ש balance as typed; may be negative (overdraft)."""
    raw = (text or '').replace(',', '').replace('₪', '').strip()
    match = re.search(r'-?\d+(?:\.\d+)?', raw)
    if not match:
        raise ValueError('לא מצאתי סכום — שלח את היתרה, למשל 2500')
    return round(float(match.group()), 2)


def nothing(step):
    return {'ils': 0.0, 'foreign': 0.0 if step['ccy'] != 'ILS' else None, 'rate': None, 'rate_source': None}


def record(payment, steps, actual, fx, now=None, checking=None):
    """Attach the actual allocation to the payment record (replacing an earlier one).
    `checking` is checking_left() plus the balance you reported ('actual')."""
    now = now or datetime.now()
    items = {}
    for step in steps:
        got = actual[step['key']]
        items[step['key']] = dict(got, suggested=step['ils'], diff=round(got['ils'] - step['ils'], 2))
    rates = {}
    for ccy, key in (('USD', 'USD_STOCKS'), ('EUR', 'EUR')):
        got = items.get(key) or {}
        rates[ccy] = {'yours': got.get('rate') if got.get('rate_source') == 'yours' else None,
                      'market': round(float(fx.get(FX_KEY[ccy], 0) or 0), 4)}
    payment['actual'] = {
        'recorded': now.strftime('%Y-%m-%d %H:%M'), 'items': items, 'rates': rates,
        'suggested_total': round(sum(s['ils'] for s in steps), 2),
        'actual_total': round(sum(actual[s['key']]['ils'] for s in steps), 2),
    }
    if checking is not None:
        checking = dict(checking)
        checking['diff'] = round(checking['actual'] - checking['expected'], 2)
        payment['actual']['checking'] = checking
    return payment['actual']


def _signed(amount):
    return ('+' if amount >= 0 else '-') + money(abs(amount))


def format_step(step, index, total, month, market_rate=None):
    lines = ['\U0001F4DD *הקצאה בפועל — %s* (%d/%d)' % (sp.month_name(month), index, total), '',
             '*%s*' % step['label']]
    if step['ccy'] == 'ILS':
        lines.append('הומלץ: *%s*' % money(step['ils']))
        lines += ['', 'כמה העברת בפועל? שלח סכום, או לחץ:']
    else:
        foreign = step['ils'] / market_rate if market_rate else 0
        lines.append('הומלץ: *%s* (≈ %s לפי שער היום %.4g)' % (money(step['ils']), money(foreign, step['ccy']), market_rate or 0))
        symbol = '€' if step['ccy'] == 'EUR' else '$'
        lines += ['', 'כמה ₪ המרת? (השער — בשאלה הבאה)',
                  '_או בסכום ב%s: `%s115`. אפשר גם הכול יחד: `394 3.40`._' % (step['ccy'], symbol)]
    return '\n'.join(lines)


def format_rate_step(step, partial, market_rate=None):
    """Asked after a euro/dollar amount that came without its rate."""
    what = (money(partial['value'], step['ccy']) if partial['foreign_first'] else money(partial['value']))
    name = 'היורו' if step['ccy'] == 'EUR' else 'הדולר'
    lines = ['\U0001F4B1 *באיזה שער המרת?* (%s)' % step['label'], '',
             'המרת: *%s*' % what, 'שלח את שער %s שקיבלת, למשל `%.4g`' % (name, market_rate or 3.4)]
    if market_rate:
        lines.append('_או לחץ על שער השוק של היום._')
    return '\n'.join(lines)


def format_checking_step(month, calc, steps, actual, index, total):
    """The last question: how much is really left in the עו"ש."""
    lines = ['\U0001F4DD *הקצאה בפועל — %s* (%d/%d)' % (sp.month_name(month), index, total), '',
             '\U0001F4B3 *כמה נשאר בעו"ש?*', '',
             'עו"ש עם התשלום: %s' % money(calc['start'])]
    for step in steps:
        got = actual[step['key']]
        if got['ils']:
            lines.append('− %s: %s' % (step['label'], money(got['ils'])))
    if calc['fee']:
        lines.append('− עמלת העברה לבנק: %s' % money(calc['fee']))
    lines += ['= *צפוי להישאר: %s*' % money(calc['expected']),
              '_(היעד היה %s)_' % money(calc['target']), '',
              'כמה יש בעו"ש בפועל? שלח סכום, או לחץ:',
              '_העו"ש בבוט יתעדכן ליתרה הזו — כדאי לרשום קודם את ההעברות ב-/addreserve וב-/addcash._']
    return '\n'.join(lines)


def format_summary(month, actual, steps):
    items = actual['items']
    lines = ['✅ *ההקצאה של %s נרשמה*' % sp.month_name(month), '']
    for step in steps:
        got = items[step['key']]
        line = '%s: הומלץ %s · בפועל *%s*' % (step['label'], money(step['ils']), money(got['ils']))
        if got.get('foreign') is not None and got['ils']:
            line += ' (%s' % money(got['foreign'], step['ccy'])
            if got.get('rate'):
                line += ' @ %.4g%s' % (got['rate'], '' if got['rate_source'] == 'yours' else ' שוק')
            line += ')'
        if abs(got['diff']) >= 0.01:
            line += '  _%s_' % _signed(got['diff'])
        lines.append(line)
    diff = round(actual['actual_total'] - actual['suggested_total'], 2)
    lines += ['', '\U0001F4B0 סה"כ: הומלץ %s · בפועל *%s*%s' % (
        money(actual['suggested_total']), money(actual['actual_total']),
        ('  _(%s)_' % _signed(diff)) if abs(diff) >= 0.01 else '  ✅ בדיוק')]
    r = actual['rates']
    eur_rate = (items.get('EUR') or {}).get('rate')
    lines.append('\U0001F4B1 שער הדולר: %s' % _rate_text(r['USD'])
                 + (' · שער היורו: %s' % _rate_text(r['EUR']) if eur_rate else ''))
    if actual.get('checking'):
        lines.append(_checking_text(actual['checking'], '*%s*'))
    lines += ['', '_ההעברות עצמן נרשמות ב-/addreserve וב-/addcash; כאן רק העו"ש מתעדכן ליתרה שדיווחת._',
              '_היסטוריה: /allocated log · /showplan_']
    return '\n'.join(lines)


def _checking_text(c, bold='%s'):
    line = '\U0001F4B3 עו"ש: צפוי %s · בפועל %s' % (money(c['expected']), bold % money(c['actual']))
    if abs(c.get('diff', 0)) >= 0.01:
        line += ' (%s)' % _signed(c['diff'])
    return line + ' · יעד %s' % money(c['target'])


def _rate_text(rate):
    if rate.get('yours'):
        return '*%.4g* (שלך; שוק %.4g)' % (rate['yours'], rate['market'])
    return '%.4g (שוק)' % rate['market']


def format_log(plan, limit=12):
    done = [p for p in plan.get('payments') or [] if p.get('actual')]
    if not done:
        return ('\U0001F4D2 *יומן הקצאות*\n\n_ריק. אחרי /payment, כשהעברת את הכסף בפועל, שלח /allocated '
                'כדי לרשום מה הלך לאן._')
    lines = ['\U0001F4D2 *יומן הקצאות*', '─' * 18]
    for p in done[-limit:][::-1]:
        a = p['actual']
        diff = round(a['actual_total'] - a['suggested_total'], 2)
        lines += ['', '\U0001F4C6 *%s* · תשלום %s · נרשם %s' % (sp.month_name(p['month']), money(p['amount']), a['recorded'][:10]),
                  '   הומלץ %s · בפועל *%s*%s' % (money(a['suggested_total']), money(a['actual_total']),
                                                      (' (%s)' % _signed(diff)) if abs(diff) >= 0.01 else ' ✅'),
                  '   \U0001F4B1 דולר %s · יורו %s' % (_rate_text(a['rates']['USD']), _rate_text(a['rates']['EUR']))]
        if a.get('checking'):
            lines.append('   ' + _checking_text(a['checking']))
        for key, item in a['items'].items():
            if abs(item['diff']) >= 0.01:
                lines.append('   %s: %s' % (STEP_LABEL[key], _signed(item['diff'])))
    return '\n'.join(lines)


# --------------------------------------------------------------------------- /showplan history

def on_plan(item):
    """Close enough to the suggestion: within ₪10 or 2% of it."""
    return abs(item['diff']) <= max(10.0, abs(item.get('suggested', 0)) * 0.02)


def _safe(text):
    return re.sub(r'[*_`\[\]]', '', str(text or ''))


def format_history(plan, current_month=None, limit=6):
    """Past months from the records: the plan's split, the net payment received
    (and what it was made of), what really went to each goal, and whether that
    followed the suggestion."""
    current_month = current_month or sp.month_key()
    by_month = {}
    for p in plan.get('payments') or []:
        by_month.setdefault(p.get('month'), []).append(p)
    months = sorted((m for m in by_month if m and m <= current_month), reverse=True)[:limit]
    if not months:
        return ''
    lines = ['━' * 20, '\U0001F4DC *PAST MONTHS* _(from your /payment and /allocated records)_']
    for month in months:
        payments = by_month[month]
        net = sum(float(p.get('amount') or 0) for p in payments)
        lines += ['', '\U0001F4C6 *%s* — net received *%s*' % (sp.month_name(month), money(net))]
        parts = [s for p in payments for s in (p.get('sources') or [])]
        if parts:
            lines.append('   _%s_' % ' · '.join('%s %s' % (money(s['amount']), _safe(s['label'])) for s in parts))
        alloc = payments[-1].get('alloc') or (plan.get('months') or {}).get(month) or {}
        if alloc:
            lines.append('   Plan: ' + '  '.join('%s %.0f%%' % (sp.BUCKET_EMOJI[b], float(alloc.get(b, 0) or 0))
                                              for b in sp.BUCKETS if alloc.get(b)))
        for p in payments:
            a = p.get('actual')
            if not a:
                lines.append('   ⏳ _%s — no allocation recorded yet: /allocated_' % money(p['amount']))
                continue
            off = []
            for key, item in a['items'].items():
                mark = '✅' if on_plan(item) else '⚠️'
                if not on_plan(item):
                    off.append(STEP_LABEL[key])
                line = '   %s %s: %s → *%s*' % (mark, STEP_LABEL[key], money(item['suggested']), money(item['ils']))
                if abs(item['diff']) >= 0.01:
                    line += ' (%s)' % _signed(item['diff'])
                lines.append(line)
            if a.get('checking'):
                lines.append('   ' + _checking_text(a['checking']))
            lines.append('   ' + ('✅ *Allocated as planned*' if not off
                                  else '⚠️ *Off the plan:* %s' % ', '.join(off)))
    return '\n'.join(lines)
