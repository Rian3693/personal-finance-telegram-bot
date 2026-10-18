"""Travel spending, billed to the EUR bank reserve.

A purchase abroad reaches the euro account through a chain, not a single rate,
and each link costs something:

  1. local currency -> USD at Visa's rate (their calculator, 0% added fee)
  2. USD -> EUR the way CAL actually bills it: via the Bank of Israel
     representative rates, USD x (ILS-per-USD / ILS-per-EUR). This is NOT
     Visa's direct USD->EUR rate, and the two differ.
  3. CAL's foreign-currency fee, applied once (3% unless told otherwise)

      EUR debit = USD x (ILS_per_USD / ILS_per_EUR) x (1 + fee)

Visa publishes its rate through a calculator page rather than an API, so the
market rate stands in as an estimate and every figure derived from it is
labelled as such. Setting the real Visa rate for a trip replaces it.

Bank of Israel rates are used from the same publication date for both
currencies; if nothing was published on the conversion day, the latest
available publication is used, which is what the billing rules assume.
"""

import json
import os
import urllib.request
from datetime import date, datetime, timedelta

TRIP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trips.json')

BOI_URL = 'https://boi.org.il/PublicApi/GetExchangeRates?asJson=true'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
TIMEOUT = 15

DEFAULT_FEE = 0.03          # CAL foreign-currency transaction fee
BASE = 'EUR'                # trips are billed to the euro reserve
REMIND_HOUR = 22            # nightly "log today's spending"
SUMMARY_HOUR = 9            # morning-after wrap-up

_rate_cache = {}


def money(amount, currency='EUR'):
    symbol = {'EUR': '€', 'USD': '$', 'ILS': '₪'}.get(currency, '')
    if symbol:
        return '%s%s' % (symbol, format(round(float(amount or 0), 2), ',.2f'))
    return '%s %s' % (format(round(float(amount or 0), 2), ',.2f'), currency)


# --------------------------------------------------------------------------- rates

def boi_rates(force=False):
    """Bank of Israel representative rates: ILS per USD and ILS per EUR.

    Both come from one response, so they always share a publication date --
    mixing dates across currencies would silently distort the cross rate.
    """
    if not force and 'boi' in _rate_cache:
        return _rate_cache['boi']

    request = urllib.request.Request(BOI_URL, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.load(response)

    rates = {}
    published = None
    for row in payload.get('exchangeRates', []):
        key = row.get('key')
        if key in ('USD', 'EUR'):
            unit = float(row.get('unit') or 1) or 1
            rates[key] = float(row['currentExchangeRate']) / unit
            published = published or (row.get('lastUpdate') or '')[:10]

    if 'USD' not in rates or 'EUR' not in rates:
        raise ValueError('Bank of Israel response missing USD or EUR')

    result = {'ils_per_usd': rates['USD'], 'ils_per_eur': rates['EUR'],
              'published': published}
    _rate_cache['boi'] = result
    return result


def market_usd_rate(currency, force=False):
    """Units of `currency` per 1 USD, from market data. A stand-in for Visa."""
    currency = currency.upper()
    if currency == 'USD':
        return 1.0
    key = 'mkt:' + currency
    if not force and key in _rate_cache:
        return _rate_cache[key]

    import yfinance as yf
    value = None
    for symbol in ('%s=X' % currency, 'USD%s=X' % currency):
        try:
            info = yf.Ticker(symbol).info
            value = info.get('regularMarketPrice') or info.get('previousClose')
            if value:
                break
        except Exception:
            continue
    if not value:
        raise ValueError('No market rate for USD/%s' % currency)

    _rate_cache[key] = float(value)
    return float(value)


def usd_rate_for(trip, force=False):
    """Local-currency-per-USD for this trip, and where it came from."""
    override = (trip or {}).get('visa_rate')
    if override:
        return float(override), 'visa'
    return market_usd_rate((trip or {}).get('currency', 'USD'), force), 'market'


# --------------------------------------------------------------------------- conversion

def convert(amount_local, per_usd, boi, fee=DEFAULT_FEE):
    """Run the billing chain and show every step, so the figure can be checked."""
    amount_local = float(amount_local)
    per_usd = float(per_usd)
    if per_usd <= 0:
        raise ValueError('Rate must be positive.')

    usd = amount_local / per_usd
    cross = float(boi['ils_per_usd']) / float(boi['ils_per_eur'])
    eur_before_fee = usd * cross
    total = eur_before_fee * (1 + float(fee))

    return {
        'local': round(amount_local, 2),
        'per_usd': per_usd,
        'usd': round(usd, 4),
        'cross': cross,
        'ils_per_usd': float(boi['ils_per_usd']),
        'ils_per_eur': float(boi['ils_per_eur']),
        'eur_net': round(eur_before_fee, 2),
        'fee_pct': float(fee),
        'fee_eur': round(total - eur_before_fee, 2),
        'eur_total': round(total, 2),
        # What the charge is worth in shekels, at the same BOI rate used above.
        'ils_total': round(total * float(boi['ils_per_eur']), 2),
        'boi_published': boi.get('published'),
    }


def value_in_ils(amount, currency, boi, per_usd=None, fee=DEFAULT_FEE):
    """What an amount is worth in shekels. Nothing is charged or moved.

    EUR goes straight through the Bank of Israel rate. Anything else routes via
    USD, the same path a card charge takes, so the two figures are comparable.
    The card cost is reported separately because the fee is a cost, not value.
    """
    amount = float(amount)
    currency = currency.upper()
    ils_per_eur = float(boi['ils_per_eur'])
    ils_per_usd = float(boi['ils_per_usd'])

    if currency == 'EUR':
        eur = amount
        usd = amount * (ils_per_eur / ils_per_usd)
    elif currency == 'USD':
        usd = amount
        eur = amount * (ils_per_usd / ils_per_eur)
    else:
        if not per_usd:
            raise ValueError('Need a %s/USD rate.' % currency)
        usd = amount / float(per_usd)
        eur = usd * (ils_per_usd / ils_per_eur)

    ils = eur * ils_per_eur
    return {
        'amount': round(amount, 2), 'currency': currency,
        'usd': round(usd, 2), 'eur': round(eur, 2), 'ils': round(ils, 2),
        'ils_with_fee': round(ils * (1 + float(fee)), 2),
        'fee_pct': float(fee), 'per_usd': per_usd,
        'boi_published': boi.get('published'),
    }


def format_value(row):
    lines = ['\U0001F4B1 *%s %s*' % (format(row['amount'], ',.2f'), row['currency']), '',
             '₪ *%s*' % format(row['ils'], ',.2f')]
    if row['currency'] != 'EUR':
        lines.append('€ %s' % format(row['eur'], ',.2f'))
    if row['currency'] != 'USD':
        lines.append('$ %s' % format(row['usd'], ',.2f'))
    lines.append('')
    lines.append('_בכרטיס (עם %.0f%% עמלת קאל): ₪%s_' % (
        row['fee_pct'] * 100, format(row['ils_with_fee'], ',.2f')))
    lines.append('_בנק ישראל, פרסום %s_' % (row.get('boi_published') or '?'))
    if row.get('per_usd'):
        lines.append('_שער %s/USD: %.4f_' % (row['currency'], float(row['per_usd'])))
    lines.append('')
    lines.append('_בדיקה בלבד — לא ירד כלום._')
    return '\n'.join(lines)


# --------------------------------------------------------------------------- storage

CARD = 'card'
CASH = 'cash'


def empty_trip(name, currency, start, end, start_eur=0.0):
    return {'name': name, 'currency': currency.upper(),
            'start': start, 'end': end,
            'start_eur': round(float(start_eur), 2),
            'visa_rate': None, 'fee': DEFAULT_FEE,
            'cash': 0.0, 'cash_log': [],
            'expenses': [], 'closed': False,
            'created': datetime.now().strftime('%Y-%m-%d %H:%M')}


def cash_balance(trip):
    return round(float((trip or {}).get('cash', 0) or 0), 2)


def add_cash(trip, amount, note=''):
    """Cash brought on the trip. It comes from outside the tracked accounts, so
    nothing is deducted anywhere -- it is simply declared."""
    amount = float(amount)
    trip['cash'] = round(cash_balance(trip) + amount, 2)
    trip.setdefault('cash_log', []).append({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'time': datetime.now().strftime('%H:%M'),
        'amount': round(amount, 2),
        'balance_after': trip['cash'],
        'note': note,
    })
    return trip['cash']


def method_of(expense):
    """Older records predate the split and were all card purchases."""
    return expense.get('method') or CARD


def load_all(path=None):
    path = path or TRIP_FILE
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {'trips': []}
    data['trips'] = data.get('trips') or []
    return data


def save_all(data, path=None):
    path = path or TRIP_FILE
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return data


def _as_date(value):
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def active_trip(data, today=None):
    """The trip covering today, if any."""
    today = today or date.today()
    for trip in data.get('trips', []):
        if trip.get('closed'):
            continue
        start, end = _as_date(trip.get('start')), _as_date(trip.get('end'))
        if start and end and start <= today <= end:
            return trip
    return None


def latest_trip(data):
    trips = data.get('trips') or []
    return trips[-1] if trips else None


def trip_ending(data, today=None):
    """A trip whose last day was yesterday and that has not been wrapped up."""
    today = today or date.today()
    for trip in data.get('trips', []):
        if trip.get('closed'):
            continue
        end = _as_date(trip.get('end'))
        if end and end < today:
            return trip
    return None


def expenses_on(trip, day):
    stamp = day.strftime('%Y-%m-%d') if hasattr(day, 'strftime') else str(day)
    return [e for e in trip.get('expenses', []) if e.get('date') == stamp]


def totals(trip):
    """Card and cash are kept apart: only card spending leaves the euro account,
    and only card spending carries the CAL fee."""
    rows = trip.get('expenses', [])
    card_rows = [e for e in rows if method_of(e) == CARD]
    cash_rows = [e for e in rows if method_of(e) == CASH]

    spent = round(sum(float(e.get('eur_total', 0) or 0) for e in card_rows), 2)
    net = round(sum(float(e.get('eur_net', 0) or 0) for e in card_rows), 2)
    return {
        'count': len(rows),
        'eur_total': spent, 'eur_net': net, 'eur_fees': round(spent - net, 2),
        'card_count': len(card_rows),
        'card_local': round(sum(float(e.get('local', 0) or 0) for e in card_rows), 2),
        'cash_count': len(cash_rows),
        'cash_local': round(sum(float(e.get('local', 0) or 0) for e in cash_rows), 2),
        'cash_eur_value': round(sum(float(e.get('eur_total', 0) or 0) for e in cash_rows), 2),
        'local_total': round(sum(float(e.get('local', 0) or 0) for e in rows), 2),
        # Shekels are summed from each record's own stored figure, so a rate that
        # moved between purchases is preserved rather than re-applied to all.
        'card_ils': round(sum(float(e.get('ils_total', 0) or 0) for e in card_rows), 2),
        'cash_ils': round(sum(float(e.get('ils_total', 0) or 0) for e in cash_rows), 2),
        'ils_total': round(sum(float(e.get('ils_total', 0) or 0) for e in rows), 2),
    }


def format_overall(trip, eur_now):
    """Everything about the trip so far: cash left, every purchase, the totals."""
    running = totals(trip)
    currency = trip['currency']
    lines = ['\U0001F9F3 *%s — מצב נוכחי*' % trip['name'],
             '━' * 20,
             '\U0001F4C5 %s → %s' % (trip.get('start'), trip.get('end')), '']

    lines.append('\U0001F4B5 *מזומן שנותר: %s %s*' % (
        format(cash_balance(trip), ',.2f'), currency))
    added = round(sum(float(c.get('amount', 0) or 0)
                      for c in trip.get('cash_log', [])), 2)
    if added:
        lines.append('   _הוכנס %s %s, הוצא %s %s_' % (
            format(added, ',.2f'), currency,
            format(running['cash_local'], ',.2f'), currency))
    lines.append('\U0001F4B6 יתרת אירו: *%s*' % money(eur_now))
    lines.append('')

    if not running['count']:
        lines.append('_עדיין לא נרשמו הוצאות._')
        return '\n'.join(lines)

    lines.append('*כל ההוצאות:*')
    for row in sorted(trip['expenses'], key=lambda e: (e.get('date', ''), e.get('time', ''))):
        icon = '\U0001F4B5' if method_of(row) == CASH else '\U0001F4B3'
        lines.append('`%s` %s %s %s → %s  _%s_' % (
            (row.get('date') or '')[5:], icon,
            format(row['local'], ',.2f'), currency,
            money(row['eur_total']), row.get('description', '')))
    lines.append('')

    lines.append('\U0001F4CA *סיכום*')
    lines.append('   \U0001F4B3 בכרטיס: *%s %s* → %s  _(%s)_  _(%d)_' % (
        format(running['card_local'], ',.2f'), currency,
        money(running['eur_total']), money(running['card_ils'], 'ILS'),
        running['card_count']))
    if running['eur_fees']:
        lines.append('      _מתוכם עמלות קאל: %s_' % money(running['eur_fees']))
    lines.append('   \U0001F4B5 במזומן: *%s %s* → %s  _(%d)_' % (
        format(running['cash_local'], ',.2f'), currency,
        money(running['cash_ils'], 'ILS'), running['cash_count']))
    lines.append('   \U0001F9FE סה"כ הוצאות: *%s %s*' % (
        format(running['local_total'], ',.2f'), currency))
    lines.append('')
    lines.append('₪ *סה"כ בשקלים: %s*' % money(running['ils_total'], 'ILS'))
    lines.append('_כולל עמלות קאל על הכרטיס; מזומן ללא עמלה._')
    return '\n'.join(lines)


# --------------------------------------------------------------------------- messages

def format_conversion(row, currency):
    """Show every link of the chain, so the number can be checked by hand.

    A cash purchase has no CAL fee, so that step is left out entirely rather
    than printed as a zero -- and the shekel figure leads, since with no card
    involved the shekel cost is the number that matters.
    """
    source = 'Visa' if row.get('source') == 'visa' else 'שער שוק (הערכה)'
    is_cash = not row.get('fee_pct')
    ils = money(row.get('ils_total', 0), 'ILS')

    if is_cash:
        head = '%s %s  →  *%s*  _(%s)_' % (
            format(row['local'], ',.2f'), currency, ils, money(row['eur_total']))
    else:
        head = '%s %s  →  *%s*  _(≈ %s)_' % (
            format(row['local'], ',.2f'), currency, money(row['eur_total']), ils)

    lines = [head, '',
             '_1. %s %s ÷ %.4f = $%.2f_  (%s)' % (
                 format(row['local'], ',.2f'), currency, row['per_usd'],
                 row['usd'], source),
             '_2. $%.2f × (%.4f ÷ %.4f) = %s_' % (
                 row['usd'], row['ils_per_usd'], row['ils_per_eur'],
                 money(row['eur_net']))]
    if is_cash:
        lines.append('_3. %s × %.4f = %s_  (ללא עמלה — מזומן)' % (
            money(row['eur_net']), row['ils_per_eur'], ils))
    else:
        lines.append('_3. + %.0f%% עמלת קאל = %s_' % (
            row['fee_pct'] * 100, money(row['fee_eur'])))
    lines.append('_בנק ישראל, פרסום %s_' % (row.get('boi_published') or '?'))
    return '\n'.join(lines)


def indexed_expenses(trip):
    """(position, record) oldest first, for the delete buttons."""
    rows = list(enumerate(trip.get('expenses') or []))
    return sorted(rows, key=lambda pair: (pair[1].get('date', ''), pair[1].get('time', '')))


def format_log(trip):
    """Every action on this trip, numbered, ready to pick one to delete."""
    rows = indexed_expenses(trip)
    currency = trip['currency']
    lines = ['\U0001F4DC *%s — יומן הוצאות*' % trip['name'], '━' * 20, '']

    if not rows:
        lines.append('_לא נרשמו הוצאות._')
        return '\n'.join(lines)

    for number, (_, row) in enumerate(rows, 1):
        icon = '\U0001F4B5' if method_of(row) == CASH else '\U0001F4B3'
        shown = (money(row.get('ils_total', 0), 'ILS') if method_of(row) == CASH
                 else money(row.get('eur_total', 0)))
        lines.append('*%d.* `%s %s` %s %s %s → %s' % (
            number, (row.get('date') or '')[5:], row.get('time', ''), icon,
            format(row.get('local', 0), ',.2f'), currency, shown))
        lines.append('     _%s_' % row.get('description', ''))

    running = totals(trip)
    lines.append('')
    lines.append('\U0001F4B3 כרטיס: *%s* _(%d)_   \U0001F4B5 מזומן: *%s %s* _(%d)_' % (
        money(running['eur_total']), running['card_count'],
        format(running['cash_local'], ',.2f'), currency, running['cash_count']))
    lines.append('\U0001F4B5 נותר מזומן: *%s %s*' % (
        format(cash_balance(trip), ',.2f'), currency))
    return '\n'.join(lines)


def format_nightly(trip, day, eur_balance):
    rows = expenses_on(trip, day)
    lines = ['\U0001F303 *%s — %s*' % (trip['name'], day.strftime('%d/%m')), '']
    if rows:
        lines.append('היום נרשמו %d הוצאות:' % len(rows))
        for row in rows:
            lines.append('  %s %s → %s  _%s_' % (
                format(row['local'], ',.2f'), trip['currency'],
                money(row['eur_total']), row.get('description', '')))
        lines.append('  *סה"כ היום: %s*' % money(
            sum(float(r['eur_total']) for r in rows)))
    else:
        lines.append('_עדיין לא נרשמו הוצאות היום._')

    running = totals(trip)
    lines.append('')
    lines.append('\U0001F4B6 יתרת אירו: *%s*' % money(eur_balance))
    lines.append('\U0001F9FE סה"כ בטיול: *%s* (%d הוצאות)' % (
        money(running['eur_total']), running['count']))
    lines.append('')
    lines.append('להוספה: `/tripspend 120 ארוחת ערב`')
    return '\n'.join(lines)


def format_summary(trip, eur_now):
    running = totals(trip)
    start = float(trip.get('start_eur', 0) or 0)
    lines = ['\U0001F9F3 *סיכום טיול — %s*' % trip['name'],
             '━' * 20,
             '\U0001F4C5 %s → %s' % (trip.get('start'), trip.get('end')), '']

    if not running['count']:
        lines.append('_לא נרשמו הוצאות._')
        return '\n'.join(lines)

    lines.append('\U0001F4B6 *יתרת אירו*')
    lines.append('   לפני: *%s*' % money(start))
    lines.append('   אחרי: *%s*' % money(eur_now))
    lines.append('   ירד: *%s*' % money(round(start - eur_now, 2)))
    lines.append('')
    lines.append('\U0001F4B8 *מתוך זה*')
    lines.append('   קניות נטו: *%s*' % money(running['eur_net']))
    lines.append('   עמלות קאל: *%s*  _(%.0f%%)_' % (
        money(running['eur_fees']), float(trip.get('fee', DEFAULT_FEE)) * 100))
    lines.append('   סה"כ חיוב: *%s*' % money(running['eur_total']))
    # Cash never touched the euro account, so it is reported apart from the
    # euro movement above rather than folded into it.
    if running['cash_count']:
        lines.append('')
        lines.append('\U0001F4B5 *במזומן (לא נגע באירו)*')
        lines.append('   %s %s  _(%d הוצאות, שווי %s)_' % (
            format(running['cash_local'], ',.2f'), trip['currency'],
            running['cash_count'], money(running['cash_eur_value'])))
        lines.append('   נותר מזומן: *%s %s*' % (
            format(cash_balance(trip), ',.2f'), trip['currency']))

    lines.append('')
    lines.append('\U0001F4CA %d הוצאות, %s %s סה"כ' % (
        running['count'], format(running['local_total'], ',.2f'), trip['currency']))

    biggest = max(trip['expenses'], key=lambda e: float(e.get('eur_total', 0) or 0))
    lines.append('\U0001F53A הגדולה ביותר: *%s* — %s' % (
        money(biggest['eur_total']), biggest.get('description', '')))
    lines.append('')
    lines.append('*כל ההוצאות:*')
    for row in sorted(trip['expenses'], key=lambda e: (e.get('date', ''), e.get('time', ''))):
        icon = '\U0001F4B5' if method_of(row) == CASH else '\U0001F4B3'
        lines.append('`%s` %s %s %s → %s  _%s_' % (
            (row.get('date') or '')[5:], icon, format(row['local'], ',.2f'),
            trip['currency'], money(row['eur_total']), row.get('description', '')))
    return '\n'.join(lines)
