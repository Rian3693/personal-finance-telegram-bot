"""Everything /total counts, sorted by when the money is meant to be used (/horizons).

  short  — emergency money: the ILS bank savings (both funds) and the EUR savings
  medium — 2-5 years: every stock except VTI (US at both brokers, and Israeli)
  long   — VTI and the קרן השתלמות (locked, so it is long term by nature)
  other  — what /total counts but fits none of them (₪ cash in hand, USD cash)

The liquid part is the same total /total shows; with the locked fund added the
shares are of the whole net worth, as /total's "including locked" line.
"""

import re

import brokers as brk
import ils_funds as ilf

LONG_SYMBOLS = ('VTI',)
ORDER = ('short', 'medium', 'long', 'other')
TITLE = {'short': '🛟 *טווח קצר — חירום*', 'medium': '📈 *טווח בינוני — 2–5 שנים*',
         'long': '🌳 *טווח ארוך*', 'other': '⚪ *לא מסווג*'}


def compute(portfolio, il_portfolio, price_of, usd_ils, eur_ils, locked=None):
    """{'buckets': {name: {'ils', 'pct', 'items': [(label, ils, detail)]}}, 'total', 'liquid', 'locked'}.

    price_of(holding) -> USD price; il_portfolio is the Israeli portfolio file;
    locked is (label, ils) of the קרן השתלמות, counted in the long term."""
    reserves = portfolio.get('reserves') or {}
    buckets = {name: {'ils': 0.0, 'items': []} for name in ORDER}

    def put(name, label, ils, detail=''):
        if abs(ils) < 0.005:
            return
        buckets[name]['items'].append((label, round(ils, 2), detail))
        buckets[name]['ils'] += ils

    # Short: the ILS bank (both funds) and the euros, bank and cash.
    funds = ilf.read(reserves)
    put('short', '🏦 חיסכון בנקאי ₪', float(reserves.get('ILS', 0) or 0),
        '%s %s · %s %s' % (ilf.EMOJI[ilf.EMERGENCY], _ils(funds[ilf.EMERGENCY]),
                           ilf.EMOJI[ilf.FUTURE], _ils(funds[ilf.FUTURE])))
    eur_bank = float(reserves.get('EUR', 0) or 0)
    eur_cash = float(reserves.get('EUR_cash', 0) or 0)
    put('short', '💶 חיסכון ביורו', (eur_bank + eur_cash) * eur_ils,
        '€{:,.2f} (בנק €{:,.2f} · מזומן €{:,.2f})'.format(eur_bank + eur_cash, eur_bank, eur_cash))

    # Medium and long: the US stocks, one line per symbol, by value.
    rows = []
    for holding in portfolio.get('holdings') or []:
        price = float(price_of(holding) or 0)
        usd = float(holding.get('shares') or 0) * price
        where = brk.where(holding)
        tag = ' · '.join(brk.SHORT[b] for b in where) if where else ''
        name = 'long' if holding['symbol'].upper() in LONG_SYMBOLS else 'medium'
        rows.append((usd, name, holding['symbol'], tag, float(holding.get('shares') or 0), price))
    for usd, name, symbol, tag, shares, price in sorted(rows, reverse=True):
        put(name, symbol, usd * usd_ils, '{:g} × ${:,.2f} = ${:,.2f}{}'.format(
            round(shares, 4), price, usd, (' · ' + tag) if tag else ''))

    # The locked training funds: long term.
    locked_ils = 0.0
    # locked: (label, ils) or a list of them (the employee keren and the self-employed one)
    for label, ils in ([locked] if locked and isinstance(locked[0], str) else (locked or [])):
        locked_ils += float(ils or 0)
        put('long', '🔒 ' + label, float(ils or 0), 'נעול')

    # Israeli stocks are medium term too.
    for stock, data in sorted((il_portfolio.get('manual_prices') or {}).items(),
                              key=lambda kv: -float(kv[1].get('current_value', 0) or 0)):
        put('medium', '🇮🇱 ' + stock, float(data.get('current_value', 0) or 0))

    # Other: counted by /total but in no horizon.
    put('other', '💵 מזומן ₪', float(reserves.get('ILS_cash', 0) or 0))
    for b, usd in brk.cash(portfolio).items():
        put('other', '💵 מזומן $ ' + brk.SHORT[b], usd * usd_ils, '${:,.2f}'.format(usd))

    total = round(sum(b['ils'] for b in buckets.values()), 2)
    for b in buckets.values():
        b['ils'] = round(b['ils'], 2)
        b['pct'] = (b['ils'] / total * 100) if total else 0.0
    return {'buckets': buckets, 'total': total, 'locked': round(locked_ils, 2),
            'liquid': round(total - locked_ils, 2)}


def _ils(amount):
    return ('-' if amount < 0 else '') + '₪{:,.2f}'.format(abs(amount))


def _bar(pct, width=12):
    filled = int(round(pct / 100 * width))
    return '▓' * filled + '░' * (width - filled)


def _safe(text):
    return re.sub(r'[*_`\[\]]', '', text)


def format_report(result, usd_ils, eur_ils):
    lines = ['📆 *הנכסים לפי טווח זמן*',
             'שווי כולל: *%s*' % _ils(result['total'])]
    if result.get('locked'):
        lines.append('_(נזיל %s כמו ב-/total + נעול %s)_' % (_ils(result['liquid']), _ils(result['locked'])))
    lines.append('━' * 20)
    for name in ORDER:
        b = result['buckets'][name]
        if name == 'other' and not b['items']:
            continue
        lines += ['', '%s' % TITLE[name],
                  '*%s* · *%.1f%%*  %s' % (_ils(b['ils']), b['pct'], _bar(b['pct']))]
        for label, ils, detail in b['items']:
            lines.append('   %s: %s%s' % (_safe(label), _ils(ils), ('  _(%s)_' % _safe(detail)) if detail else ''))
        if not b['items']:
            lines.append('   _אין כרגע_')
    lines += ['', '━' * 20, '📊 *סיכום:*']
    for name in ORDER:
        b = result['buckets'][name]
        if name == 'other' and not b['items']:
            continue
        lines.append('%s %s · %.1f%%' % (TITLE[name].split(' ')[0], _ils(b['ils']), b['pct']))
    lines.append('💱 USD/ILS %.4f · EUR/ILS %.4f' % (usd_ils, eur_ils))
    return '\n'.join(lines)
