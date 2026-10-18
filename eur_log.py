"""Deposit and withdrawal history for the euro account.

Every euro movement has always been written to `reserves['log']`, but nothing
read it back: there was no way to ask what went into the account, what came out
and why. This module is that reader. It stores nothing of its own, so the whole
history -- 2026 included -- is available immediately rather than starting from
the day a new log was introduced.

Bank and cash are kept apart throughout. They are separate pots with separate
balances, and summing them in a statement would invent a balance neither one
ever had.
"""

from datetime import datetime

BANK = 'BANK'
CASH = 'CASH'

DEPOSIT = 'deposit'
WITHDRAW = 'withdraw'

# Old entries were written through a console that mangled the euro sign; the
# bytes are still in the file, so they are repaired on the way out rather than
# by rewriting history.
_MOJIBAKE = {'ג‚¬': '€', 'â‚¬': '€'}

# Trip purchases hit the euro bank through the card, so they belong in the
# statement, but they are not someone deciding to move savings around.
TRIP_MARKERS = ('רומניה:',)


def money(amount):
    return '€%s' % format(round(float(amount or 0), 2), ',.2f')


def clean(text):
    out = str(text or '')
    for bad, good in _MOJIBAKE.items():
        out = out.replace(bad, good)
    return out.strip()


def _account_of(entry):
    """Which pot moved. The earliest entries predate the type field."""
    kind = (entry.get('type') or '').upper()
    return CASH if kind == CASH else BANK


def is_trip(entry):
    text = clean(entry.get('description'))
    return any(marker in text for marker in TRIP_MARKERS)


def _date_of(entry):
    raw = (entry.get('date') or '').strip()
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(raw[:len(fmt) + 2].strip(), fmt)
        except ValueError:
            continue
    return None


def rows(reserves, year=None, account=None, kind=None):
    """Every euro movement, newest last, as plain dicts ready to print."""
    out = []
    for entry in (reserves or {}).get('log', []) or []:
        if (entry.get('currency') or '').upper() != 'EUR':
            continue
        amount = float(entry.get('amount', 0) or 0)
        if not amount:
            continue
        when = _date_of(entry)
        row = {
            'date': (entry.get('date') or '')[:10],
            'time': (entry.get('date') or '')[11:16],
            'when': when,
            'year': (entry.get('date') or '')[:4],
            'month': (entry.get('date') or '')[:7],
            'account': _account_of(entry),
            'kind': DEPOSIT if amount > 0 else WITHDRAW,
            'amount': abs(round(amount, 2)),
            'signed': round(amount, 2),
            'balance_after': float(entry.get('balance_after', 0) or 0),
            'description': clean(entry.get('description')),
            'note': clean(entry.get('note')),
            'trip': is_trip(entry),
        }
        if year and row['year'] != str(year):
            continue
        if account and row['account'] != account:
            continue
        if kind and row['kind'] != kind:
            continue
        out.append(row)
    return out


def years(reserves):
    return sorted({r['year'] for r in rows(reserves) if r['year']}, reverse=True)


def totals(entries):
    deposits = [r for r in entries if r['kind'] == DEPOSIT]
    withdrawals = [r for r in entries if r['kind'] == WITHDRAW]
    deposited = round(sum(r['amount'] for r in deposits), 2)
    withdrawn = round(sum(r['amount'] for r in withdrawals), 2)
    return {
        'count': len(entries),
        'deposit_count': len(deposits),
        'withdraw_count': len(withdrawals),
        'deposited': deposited,
        'withdrawn': withdrawn,
        'net': round(deposited - withdrawn, 2),
        'bank_in': round(sum(r['amount'] for r in deposits if r['account'] == BANK), 2),
        'bank_out': round(sum(r['amount'] for r in withdrawals if r['account'] == BANK), 2),
        'cash_in': round(sum(r['amount'] for r in deposits if r['account'] == CASH), 2),
        'cash_out': round(sum(r['amount'] for r in withdrawals if r['account'] == CASH), 2),
        'trip_out': round(sum(r['amount'] for r in withdrawals if r['trip']), 2),
        # A cancelled trip purchase puts the euros back; it is a refund, not
        # someone choosing to deposit, so it is reported apart from "In".
        'trip_back': round(sum(r['amount'] for r in deposits if r['trip']), 2),
        'biggest_in': max(deposits, key=lambda r: r['amount']) if deposits else None,
        'biggest_out': max(withdrawals, key=lambda r: r['amount']) if withdrawals else None,
    }


def gaps(entries):
    """Changes the log never recorded.

    Every entry stores the balance it left behind, so the previous balance plus
    the movement must equal it. When it does not, the pot changed some other way
    -- an edit made outside the bot, an old command that did not log -- and the
    difference is returned here instead of being silently absorbed. Without this
    the totals add up logged movements only and quietly disagree with the real
    balance.
    """
    last_balance, last_date, out = {}, {}, []
    for row in entries:
        account = row['account']
        if account in last_balance:
            expected = last_balance[account] + row['signed']
            if abs(expected - row['balance_after']) > 0.005:
                out.append({
                    'date': row['date'], 'month': row['month'], 'account': account,
                    'amount': round(row['balance_after'] - expected, 2),
                    'since': last_date[account],
                    'row': row,
                })
        last_balance[account] = row['balance_after']
        last_date[account] = row['date']
    return out


def reconcile(entries):
    """Opening + logged movements + unlogged changes = closing, per the log.

    Opening is what each pot held before its first movement in the selection and
    closing is the balance the last one left behind, so the equation is checked
    rather than assumed.
    """
    first, last = {}, {}
    for row in entries:
        first.setdefault(row['account'], row)
        last[row['account']] = row
    opening = round(sum(r['balance_after'] - r['signed'] for r in first.values()), 2)
    closing = round(sum(r['balance_after'] for r in last.values()), 2)
    unlogged = round(sum(g['amount'] for g in gaps(entries)), 2)
    logged = round(sum(r['signed'] for r in entries), 2)
    return {'opening': opening, 'closing': closing, 'logged': logged,
            'unlogged': unlogged,
            'balanced': abs(opening + logged + unlogged - closing) < 0.01}


def monthly(entries, gap_list=None):
    """Per-month in/out, oldest first, for the summary table."""
    out = {}
    for row in entries:
        key = row['month']
        if not key:
            continue
        bucket = out.setdefault(key, {'in': 0.0, 'out': 0.0, 'count': 0, 'gap': 0.0})
        bucket['count'] += 1
        bucket['in' if row['kind'] == DEPOSIT else 'out'] += row['amount']
    for gap in gap_list or []:
        if gap['month'] in out:
            out[gap['month']]['gap'] += gap['amount']
    for bucket in out.values():
        bucket['in'] = round(bucket['in'], 2)
        bucket['out'] = round(bucket['out'], 2)
        bucket['gap'] = round(bucket['gap'], 2)
        bucket['net'] = round(bucket['in'] - bucket['out'] + bucket['gap'], 2)
    return dict(sorted(out.items()))


def _month_label(key):
    try:
        return datetime.strptime(key, '%Y-%m').strftime('%B %Y')
    except ValueError:
        return key


def _reason(row):
    """The description, with the stock 'Added €x (Cash)' boilerplate dropped --
    it only repeats the amount and the column it is already in."""
    note = row['note']
    if note:
        return note
    text = row['description']
    for prefix in ('Added ', 'Withdrew '):
        if text.startswith(prefix):
            tail = text.split('—', 1)
            return tail[1].strip() if len(tail) > 1 else ''
    return text


def _live_balance(reserves, account=None):
    """What the account holds right now, for the pot(s) being shown."""
    reserves = reserves or {}
    try:
        bank = float(reserves.get('EUR', 0) or 0)
        cash = float(reserves.get('EUR_cash', 0) or 0)
    except (TypeError, ValueError):
        return None
    if account == BANK:
        return round(bank, 2)
    if account == CASH:
        return round(cash, 2)
    return round(bank + cash, 2)


def format_log(reserves, year=None, account=None, kind=None):
    """The /eurlog view: totals, a month table, then every movement with its
    reason."""
    entries = rows(reserves, year=year, account=account, kind=kind)
    scope = []
    if year:
        scope.append(str(year))
    if account:
        scope.append('Bank' if account == BANK else 'Cash')
    if kind:
        scope.append('deposits' if kind == DEPOSIT else 'withdrawals')
    title = '\U0001F4B6 *EURO ACCOUNT LOG*'
    if scope:
        title += '  _(%s)_' % ' · '.join(scope)

    if not entries:
        available = years(reserves)
        tail = ('\n_Years on record: %s_' % ', '.join(available)) if available else ''
        return '%s\n%s\n\n_Nothing recorded for this selection._%s' % (
            title, '─' * 18, tail)

    tot = totals(entries)
    lines = [title, '─' * 18, '']
    lines.append('\U0001F7E2 In: *%s*  _(%d)_' % (money(tot['deposited']),
                                                  tot['deposit_count']))
    lines.append('\U0001F534 Out: *%s*  _(%d)_' % (money(tot['withdrawn']),
                                                   tot['withdraw_count']))
    sign = '+' if tot['net'] >= 0 else '-'
    lines.append('\U0001F4CA Net of logged movements: *%s%s*' % (sign, money(abs(tot['net']))))

    # In and out only cover what was logged. If a pot also changed in a way the
    # log never saw, the net above is not the balance, so the difference is
    # shown and the equation closed against the real balance rather than leaving
    # a number that quietly disagrees with it.
    gap_list = gaps(entries) if not kind else []
    if gap_list:
        for gap in gap_list:
            lines.append('⚠️ *Not in the log:* %s%s  _(%s, between %s and %s)_' % (
                '+' if gap['amount'] >= 0 else '-', money(abs(gap['amount'])),
                'cash' if gap['account'] == CASH else 'bank',
                gap['since'][5:], gap['date'][5:]))
        rec = reconcile(entries)
        live = _live_balance(reserves, account)
        lines.append('\U0001F9EE Opening %s %s%s %s%s = *%s*' % (
            money(rec['opening']),
            '+' if rec['logged'] >= 0 else '-', money(abs(rec['logged'])),
            '+' if rec['unlogged'] >= 0 else '-', money(abs(rec['unlogged'])),
            money(rec['closing'])))
        if live is not None and abs(live - rec['closing']) < 0.01:
            lines.append('✅ _matches your balance now (%s)_' % money(live))
        elif live is not None:
            lines.append('⚠️ _balance now is %s_' % money(live))
    lines.append('')
    lines.append('\U0001F3E6 Bank: +%s / -%s' % (money(tot['bank_in']),
                                                 money(tot['bank_out'])))
    lines.append('\U0001F4B5 Cash: +%s / -%s' % (money(tot['cash_in']),
                                                 money(tot['cash_out'])))
    if tot['trip_out'] or tot['trip_back']:
        line = '✈️ _trips: %s spent' % money(tot['trip_out'])
        if tot['trip_back']:
            line += ', %s refunded (both included above)' % money(tot['trip_back'])
        lines.append(line + '_')

    months = monthly(entries, gap_list)
    if len(months) > 1:
        lines.append('')
        lines.append('*By month:*')
        for key, bucket in months.items():
            lines.append('`%s`  +%-9s -%-9s = %s%s%s' % (
                key, format(bucket['in'], ',.0f'), format(bucket['out'], ',.0f'),
                '+' if bucket['net'] >= 0 else '-',
                format(abs(bucket['net']), ',.0f'),
                ' ⚠️' if bucket['gap'] else ''))

    lines.append('')
    lines.append('*Every movement:*')
    current_month = None
    gap_before = {id(g['row']): g for g in gap_list}
    for row in entries:
        if row['month'] != current_month:
            current_month = row['month']
            lines.append('')
            lines.append('\U0001F4C6 *%s*' % _month_label(current_month))
        gap = gap_before.get(id(row))
        if gap:
            lines.append('⚠️ %s *%s%s*  _not in the log (%s)_' % (
                '\U0001F4B5' if gap['account'] == CASH else '\U0001F3E6',
                '+' if gap['amount'] >= 0 else '-', money(abs(gap['amount'])),
                'cash' if gap['account'] == CASH else 'bank'))
        mark = '\U0001F7E2' if row['kind'] == DEPOSIT else '\U0001F534'
        where = '\U0001F3E6' if row['account'] == BANK else '\U0001F4B5'
        if row['trip']:
            where = '✈️'
        head = '%s %s `%s`  *%s%s*' % (
            mark, where, row['date'][5:], '+' if row['kind'] == DEPOSIT else '-',
            money(row['amount']))
        lines.append(head)
        reason = _reason(row)
        if reason:
            lines.append('      _%s_' % reason)
        lines.append('      → %s balance %s' % (
            'cash' if row['account'] == CASH else 'bank', money(row['balance_after'])))

    lines.append('')
    lines.append('_/eurlog 2026 · /eurlog bank · /eurlog cash · '
                 '/eurlog in · /eurlog out_')
    return '\n'.join(lines)


def parse_args(args, reserves=None):
    """`/eurlog 2026 bank out` in any order; unknown words are ignored."""
    year = account = kind = None
    for raw in args or []:
        word = str(raw).strip().lower()
        if word.isdigit() and len(word) == 4:
            year = word
        elif word in ('bank', 'בנק'):
            account = BANK
        elif word in ('cash', 'מזומן'):
            account = CASH
        elif word in ('in', 'deposit', 'deposits', 'הפקדות'):
            kind = DEPOSIT
        elif word in ('out', 'withdraw', 'withdrawals', 'משיכות'):
            kind = WITHDRAW
        elif word == 'all':
            year = 'all'
    if year == 'all':
        return {'year': None, 'account': account, 'kind': kind}
    if year is None:
        # Default to the current year, falling back to the newest year on record
        # so an empty January does not look like an empty history.
        available = years(reserves or {})
        this_year = datetime.now().strftime('%Y')
        year = this_year if this_year in available else (available[0] if available else this_year)
    return {'year': year, 'account': account, 'kind': kind}
