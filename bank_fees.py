"""Bank charges on ILS savings transfers.

Every movement into or out of the ILS bank savings costs a flat fee. The fee
comes out of the money being moved -- a deposit credits less than was sent, a
withdrawal delivers less than was taken -- so the balances stay honest instead of
quietly absorbing a charge nobody recorded.

Fees are kept in my_portfolio.json under 'ils_bank_fees' and reported in ILS.
They are deliberately NOT mixed into the stock commission totals, which are in
dollars; adding the two would produce a meaningless number.
"""

import json
import os
from datetime import datetime

ILS_BANK_FEE = 5.0
PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my_portfolio.json')
LOG_KEY = 'ils_bank_fees'

DEPOSIT = 'deposit'
WITHDRAW = 'withdraw'


def money(amount):
    return '₪%s' % format(round(float(amount or 0), 2), ',.2f')


def net_after_fee(amount, fee=ILS_BANK_FEE):
    """What actually lands after the bank takes its cut.

    A transfer smaller than the fee would otherwise credit a negative amount, so
    it floors at zero and the caller can see the whole thing was eaten.
    """
    return round(max(0.0, float(amount) - float(fee)), 2)


def fee_for(amount, fee=ILS_BANK_FEE):
    """The fee actually charged - never more than the transfer itself."""
    return round(min(float(fee), abs(float(amount))), 2)


def load(path=None):
    path = path or PORTFOLIO_FILE
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return (json.load(fh) or {}).get(LOG_KEY) or []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def entry_for(direction, gross, note='', fee=ILS_BANK_FEE, when=None):
    when = when or datetime.now()
    charged = fee_for(gross, fee)
    return {
        'date': when.strftime('%Y-%m-%d'),
        'time': when.strftime('%H:%M'),
        'direction': direction,
        'gross': round(abs(float(gross)), 2),
        'fee': charged,
        'net': round(abs(float(gross)) - charged, 2),
        'note': note,
    }


def append(data, direction, gross, note='', fee=ILS_BANK_FEE, when=None):
    """Add a fee to a portfolio dict the caller is about to save itself.

    `record` below writes the file directly, which is lost when the caller then
    saves its own in-memory copy over it -- so any code holding the data must
    use this instead.
    """
    entry = entry_for(direction, gross, note, fee, when)
    data.setdefault(LOG_KEY, []).append(entry)
    return entry


def record(direction, gross, note='', path=None, fee=ILS_BANK_FEE, when=None):
    """Append one fee to the log and return the entry.

    Only for callers that are NOT holding the portfolio dict; otherwise the
    write races with theirs. Use `append` in that case.
    """
    path = path or PORTFOLIO_FILE
    when = when or datetime.now()
    charged = fee_for(gross, fee)
    entry = {
        'date': when.strftime('%Y-%m-%d'),
        'time': when.strftime('%H:%M'),
        'direction': direction,
        'gross': round(abs(float(gross)), 2),
        'fee': charged,
        'net': round(abs(float(gross)) - charged, 2),
        'note': note,
    }
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        data = {}
    data.setdefault(LOG_KEY, []).append(entry)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return entry


def total(entries):
    return round(sum(float(e.get('fee', 0) or 0) for e in entries or []), 2)


def monthly_totals(entries):
    out = {}
    for entry in entries or []:
        key = (entry.get('date') or '')[:7]
        if key:
            out[key] = round(out.get(key, 0) + float(entry.get('fee', 0) or 0), 2)
    return out


def format_section(entries, limit_months=6):
    """The ILS block appended to /commission, kept separate from the $ totals."""
    if not entries:
        return ('\n\n\U0001F3E6 *ILS bank transfer fees*\n'
                '_None recorded yet._')

    by_month = monthly_totals(entries)
    lines = ['', '', '\U0001F3E6 *ILS BANK TRANSFER FEES*', '─' * 17,
             '\U0001F4B8 Total: *%s*  _(%d transfers)_' % (
                 money(total(entries)), len(entries)), '']

    for key in sorted(by_month, reverse=True)[:limit_months]:
        try:
            label = datetime.strptime(key, '%Y-%m').strftime('%B %Y')
        except ValueError:
            label = key
        count = sum(1 for e in entries if (e.get('date') or '').startswith(key))
        lines.append('\U0001F4C6 *%s*: %s  _(%d)_' % (label, money(by_month[key]), count))

    lines.append('')
    lines.append('_%s per transfer, taken from the amount moved._' % money(ILS_BANK_FEE))
    return '\n'.join(lines)
