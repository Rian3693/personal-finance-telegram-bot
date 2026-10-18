"""Day-to-day expense tracking for the /ilcash checking account.

Two cards draw on the same account but on different clocks. The debit card
leaves /ilcash the moment it is used. The Visa is collected in one lump on the
10th (the 2nd until October 2026), so those purchases sit as a pending claim
against a balance that still looks untouched -- which is exactly how people end
up short on the charge day.

Everything here is pure: it reads a list of spend records and reports on them.
Reading and writing balances stays in telegram_bot.py, so nothing in this file
can move money.

Records written before cards were tracked have no 'card' field. They were all
debit-style (already deducted), so they are treated as such and never show up as
pending Visa.
"""

from datetime import date, datetime, timedelta

DEBIT = 'debit'
VISA = 'visa'
# Cash is not a card, but it is a way you paid, so it belongs in the same list.
# It draws on physical cash on hand, never on the checking account.
CASH = 'cash'
CARDS = (DEBIT, VISA, CASH)
CARD_LABEL = {DEBIT: 'Debit', VISA: 'Visa', CASH: 'Cash'}
CARD_EMOJI = {DEBIT: '\U0001F4B3', VISA: '\U0001F7E6', CASH: '\U0001F4B5'}
CARD_BY_DIGIT = {'1': DEBIT, '2': VISA, '3': CASH}

INVESTMENT = 'investment'

VISA_CHARGE_DAY = 10            # the 2nd until 02/10/2026 (see the schedule below)
WARN_DAYS_BEFORE = 6
SHEKEL = '₪'


def money(amount):
    """₪1,234.50, and -₪500.00 (not ₪-500.00) once the עו"ש is in overdraft."""
    amount = round(float(amount or 0), 2)
    return '%s%s%s' % ('-' if amount < 0 else '', SHEKEL, format(abs(amount), ',.2f'))


# --------------------------------------------------------------------------- overdraft

# The bank lets the עו"ש go this far below zero. Spending is allowed into the
# overdraft and refused only past it.
OVERDRAFT_LIMIT = 3000.0


def room(checking, limit=OVERDRAFT_LIMIT):
    """How much can still leave the עו"ש: the balance plus what is left of the overdraft."""
    return round(float(checking or 0) + float(limit), 2)


def can_debit(checking, amount, limit=OVERDRAFT_LIMIT):
    return float(amount) <= room(checking, limit) + 0.005


def overdraft_line(balance, limit=OVERDRAFT_LIMIT):
    """One line for a confirmation once the balance is below zero, else ''."""
    balance = float(balance or 0)
    if balance >= 0:
        return ''
    left = round(limit + balance, 2)
    return ('🔴 העו"ש במינוס: %s (מתוך מסגרת של %s, נשארו %s)'
            % (money(balance), money(limit), money(max(0.0, left))))


def over_limit_text(checking, amount, limit=OVERDRAFT_LIMIT):
    """The refusal when a debit would go past the overdraft limit."""
    return ('❌ חורג ממסגרת המינוס!\n'
            'יתרה: %s\n'
            'מסגרת מינוס: %s\n'
            'אפשר להוציא עד: %s\n'
            'מבוקש: %s' % (money(checking), money(limit), money(max(0.0, room(checking, limit))),
                           money(amount)))


# --------------------------------------------------------------------------- records

def card_of(entry):
    """Legacy records predate card tracking and were all debit."""
    return entry.get('card') or DEBIT


def is_cancelled(entry):
    """A cancelled purchase (mistake or refund) stays in the file for the audit
    trail but must not count towards any total."""
    return bool(entry.get('cancelled'))


def is_investment(entry):
    """Buying EUR, USD or moving money to the bank savings drains /ilcash but is
    not spending - the money is still yours, just in another pocket. These are
    excluded from every spending total so the figures mean what they say."""
    return entry.get('kind') == INVESTMENT


def active(entries):
    """Records that genuinely count as spending."""
    return [e for e in entries or []
            if not is_cancelled(e) and not is_investment(e)]


def is_pending_visa(entry):
    if is_cancelled(entry) or is_investment(entry):
        return False
    return card_of(entry) == VISA and not entry.get('charged')


def is_reserved(entry):
    """A Visa purchase taken off the עו"ש the moment it was logged, so the charge
    day finds the money already set aside and must not deduct it again."""
    return card_of(entry) == VISA and bool(entry.get('reserved'))


def unreserved(entries):
    """The Visa purchases whose money still has to come off the עו"ש on the charge day."""
    return [e for e in entries or [] if not is_reserved(e)]


def entry_date(entry):
    try:
        return datetime.strptime(entry.get('date', ''), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def month_of(entry):
    raw = entry.get('date') or ''
    return raw[:7] if len(raw) >= 7 else ''


# Spending months follow the Visa: a month is everything one Visa charge collects.
#   until September 2026: the 3rd to the 2nd, collected on the 2nd (OLD_CHARGE_DAY)
#   October 2026 bridges: 03/10 – 09/11, collected on 10/11 (the charge moved to the 10th)
#   from November 2026:   the 10th to the 9th, collected on the 10th of the next month
OLD_CHARGE_DAY = 2
BRIDGE_MONTH = '2026-10'
BRIDGE_START = date(2026, 10, 3)            # first day of the bridge month
NEW_FROM = date(2026, 11, 10)               # first day of the first 10th-to-9th month
LAST_OLD_CHARGE = date(2026, 10, 2)         # the last collection on the 2nd


def _prev_month(day):
    return day.replace(day=1) - timedelta(days=1)


def _ym(day):
    return day.strftime('%Y-%m')


def _first(month_key):
    return datetime.strptime(month_key + '-01', '%Y-%m-%d').date()


def _next_month_day(month_key, day):
    first = _first(month_key)
    return (first.replace(day=28) + timedelta(days=4)).replace(day=day)


def charge_day_in(year, month):
    """The day of the month Visa collects: the 2nd until October 2026, then the 10th."""
    return OLD_CHARGE_DAY if (year, month) <= (2026, 10) else VISA_CHARGE_DAY


def cycle_month_for(day):
    """The spending month a purchase on `day` belongs to (see the schedule above)."""
    if day >= NEW_FROM:
        return _ym(day if day.day >= VISA_CHARGE_DAY else _prev_month(day))
    if day >= BRIDGE_START:
        return BRIDGE_MONTH
    return _ym(_prev_month(day) if day.day <= OLD_CHARGE_DAY else day)


def cycle_month_of(entry):
    day = entry_date(entry)
    return cycle_month_for(day) if day else month_of(entry)


def cycle_range(month_key):
    """(first day, last day) of a spending month."""
    if month_key > BRIDGE_MONTH:
        return _first(month_key).replace(day=VISA_CHARGE_DAY), _next_month_day(month_key, VISA_CHARGE_DAY - 1)
    if month_key == BRIDGE_MONTH:
        return BRIDGE_START, NEW_FROM - timedelta(days=1)
    return _first(month_key).replace(day=OLD_CHARGE_DAY + 1), _next_month_day(month_key, OLD_CHARGE_DAY)


def is_cycle_last_day(day):
    """True on a spending month's last day (when its summary goes out)."""
    return cycle_range(cycle_month_for(day))[1] == day


def _month_fn(cycle):
    return cycle_month_of if cycle else month_of


# --------------------------------------------------------------------------- the Visa clock

def charge_date_for(purchase_day):
    """When Visa collects a purchase: the 10th after its spending month ends.

    Purchases up to the last collection on the 2nd (02/10/2026) keep the old
    rule: the 1st was collected the next day, anything later on the 2nd of the
    month after. From then on a purchase waits for the charge that closes its
    spending month -- 10/11 for the bridge month, then the 10th of each month.
    """
    if purchase_day < LAST_OLD_CHARGE:
        year, month = purchase_day.year, purchase_day.month
        if purchase_day.day < OLD_CHARGE_DAY:
            return date(year, month, OLD_CHARGE_DAY)
        return date(year + (month // 12), month % 12 + 1, OLD_CHARGE_DAY)
    month = cycle_month_for(purchase_day) if purchase_day >= BRIDGE_START else BRIDGE_MONTH
    return _next_month_day(month, VISA_CHARGE_DAY)


CHARGE_HOUR = 10          # the bank collects during the morning of the charge day


def settle_cutoff(now):
    """The latest charge date that has really happened by `now`: today's charge
    counts from CHARGE_HOUR on, before that only yesterday's and earlier."""
    return now.date() if now.hour >= CHARGE_HOUR else now.date() - timedelta(days=1)


def format_visa_settled(result):
    """What the automatic Visa charge just did, for the Telegram notice."""
    def esc(text):
        return str(text or '').replace('_', ' ').replace('*', '').replace('`', "'")

    rows = result['rows']
    due_days = sorted({str(r.get('charge_date') or '')[5:].replace('-', '/') for r in rows if r.get('charge_date')})
    deducted = result.get('deducted', result['total'])
    already = round(result['total'] - deducted, 2)
    lines = ['✅ *Visa charged automatically*', '',
             '%s *%s* over %d purchase%s%s' % (CARD_EMOJI[VISA], money(result['total']), len(rows),
                                              '' if len(rows) == 1 else 's',
                                              (' (due %s)' % ', '.join(d.split('/')[1] + '/' + d.split('/')[0] for d in due_days)) if due_days else '')]
    if already:
        lines.append('✅ %s was already taken off the עו"ש when you bought' % money(already))
    if deducted:
        lines.append('%s /ilcash: %s → *%s*' % (CARD_EMOJI[DEBIT], money(result['before']), money(result['after'])))
    else:
        lines.append('%s /ilcash stays *%s* — nothing new comes off' % (CARD_EMOJI[DEBIT], money(result['after'])))
    if result['after'] < 0:
        lines.append(overdraft_line(result['after']))
        if result['after'] < -OVERDRAFT_LIMIT:
            lines.append('⛔ Past the overdraft limit — move money with /withdrawreserve.')
    lines.append('')
    for entry in sorted(rows, key=lambda e: str(e.get('date')))[:8]:
        lines.append('  %s — %s  _(%s)_' % (money(entry.get('amount')), esc(entry.get('description')), entry.get('date', '')))
    if len(rows) > 8:
        lines.append('  _+%d more_' % (len(rows) - 8))
    lines += ['', '_Wrong entry? Delete it in /ilspendhistory and the money comes back._']
    return '\n'.join(lines)


def recompute_charge_dates(entries):
    """Re-apply the charge rule to Visa purchases not yet charged. Returns the
    changes as (date, amount, old charge date, new charge date); charged ones and
    every other field are left exactly as they were."""
    changes = []
    for entry in entries or []:
        if not is_pending_visa(entry):
            continue
        try:
            day = datetime.strptime(entry.get('date', ''), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            continue
        new = charge_date_for(day).strftime('%Y-%m-%d')
        if entry.get('charge_date') != new:
            changes.append((entry.get('date'), entry.get('amount'), entry.get('charge_date'), new))
            entry['charge_date'] = new
    return changes


def next_charge_date(today=None):
    """The next Visa collection on or after today."""
    today = today or date.today()
    this_month = date(today.year, today.month, charge_day_in(today.year, today.month))
    if today <= this_month:
        return this_month
    nxt = _next_month_day(_ym(today), 1)
    return date(nxt.year, nxt.month, charge_day_in(nxt.year, nxt.month))


def warn_date(charge_day):
    return charge_day - timedelta(days=WARN_DAYS_BEFORE)


def is_warning_day(today=None):
    today = today or date.today()
    return today == warn_date(next_charge_date(today))


def pending_visa(entries, on_or_before=None):
    """Uncharged Visa records, optionally only those already due."""
    out = []
    for entry in entries or []:
        if not is_pending_visa(entry):
            continue
        if on_or_before is not None:
            due = entry.get('charge_date')
            try:
                due_day = datetime.strptime(due, '%Y-%m-%d').date() if due else None
            except (ValueError, TypeError):
                due_day = None
            if due_day and due_day > on_or_before:
                continue
        out.append(entry)
    return out


def total_of(entries):
    return round(sum(float(e.get('amount', 0) or 0) for e in entries or []), 2)


def shortfall(checking, due):
    """How far /ilcash falls short of covering a charge."""
    return round(max(0.0, float(due) - float(checking)), 2)


# --------------------------------------------------------------------------- summaries

def entries_for_month(entries, month_key, cycle=False):
    of = _month_fn(cycle)
    return [e for e in active(entries) if of(e) == month_key]


def entries_for_day(entries, day):
    stamp = day.strftime('%Y-%m-%d') if hasattr(day, 'strftime') else str(day)
    return [e for e in active(entries) if e.get('date') == stamp]


def month_summary(entries, month_key, cycle=False):
    rows = entries_for_month(entries, month_key, cycle)
    by_card = {c: round(sum(float(e.get('amount', 0) or 0)
                            for e in rows if card_of(e) == c), 2) for c in CARDS}
    biggest = max(rows, key=lambda e: float(e.get('amount', 0) or 0)) if rows else None
    return {
        'month': month_key, 'entries': rows, 'count': len(rows),
        'total': total_of(rows), 'by_card': by_card, 'biggest': biggest,
        'average': round(total_of(rows) / len(rows), 2) if rows else 0.0,
    }


def monthly_totals(entries, cycle=False):
    totals = {}
    of = _month_fn(cycle)
    for entry in active(entries):
        key = of(entry)
        if not key:
            continue
        totals[key] = round(totals.get(key, 0) + float(entry.get('amount', 0) or 0), 2)
    return totals


def predict(entries, upto_month, cycle=False):
    """Average of completed months. Deliberately not a forecast model.

    With one or two months of history an 'average' is barely information, so the
    caller is told how thin the basis is rather than being handed a number that
    looks more certain than it is.
    """
    totals = monthly_totals(entries, cycle)
    prior = [totals[m] for m in sorted(totals) if m < upto_month]
    if not prior:
        return {'ready': False, 'months': 0}

    average = round(sum(prior) / len(prior), 2)
    recent = prior[-3:]
    recent_average = round(sum(recent) / len(recent), 2)
    return {
        'ready': len(prior) >= 2, 'months': len(prior),
        'average': average, 'recent_average': recent_average,
        'last': prior[-1], 'highest': max(prior), 'lowest': min(prior),
        'trend': round(recent_average - average, 2),
    }


# --------------------------------------------------------------------------- messages

def format_daily_reminder(today_rows, checking, pending_total, today=None):
    today = today or date.today()
    lines = ['\U0001F319 *Log today’s spending*',
             '\U0001F4C5 %s' % today.strftime('%A, %d %B'), '']

    if today_rows:
        lines.append('Already logged today (%d):' % len(today_rows))
        for entry in today_rows:
            lines.append('  %s %s — %s' % (
                CARD_EMOJI[card_of(entry)], money(entry.get('amount')),
                entry.get('description', '')))
        lines.append('  *Total: %s*' % money(total_of(today_rows)))
    else:
        lines.append('_Nothing logged today yet._')

    lines.append('')
    lines.append('%s /ilcash: *%s*' % (CARD_EMOJI[DEBIT], money(checking)))
    if pending_total:
        lines.append('%s Visa pending: *%s*' % (CARD_EMOJI[VISA], money(pending_total)))
    lines.append('')
    lines.append('Add one with /ilspend')
    return '\n'.join(lines)


def format_visa_warning(charge_day, rows, checking, days_away):
    # Purchases already set aside are out of the עו"ש; only the rest still has to come off.
    due = total_of(unreserved(rows))
    already = round(total_of(rows) - due, 2)
    short = shortfall(checking, due)
    lines = ['⚠️ *VISA CHARGE IN %d DAYS*' % days_away,
             '\U0001F4C5 %s' % charge_day.strftime('%d %B %Y'), '',
             '%s Visa total: *%s*  _(%d purchases)_' % (
                 CARD_EMOJI[VISA], money(total_of(rows)), len(rows))]
    if already:
        lines.append('✅ %s already taken off the עו"ש — still to come off: *%s*' % (money(already), money(due)))
    lines += ['%s /ilcash now: *%s*' % (CARD_EMOJI[DEBIT], money(checking)), '']

    after = round(float(checking) - due, 2)
    if short and after < -OVERDRAFT_LIMIT:
        over = round(-OVERDRAFT_LIMIT - after, 2)
        lines.append('\U0001F534 *Past your overdraft limit by %s*' % money(over))
        lines.append('The charge would leave /ilcash at *%s*; the limit is %s.' % (money(after), money(-OVERDRAFT_LIMIT)))
        lines.append('')
        lines.append('Move at least *%s* from the ILS bank to /ilcash (*%s* to stay out of overdraft).'
                     % (money(over), money(short)))
        lines.append('Use `/withdrawreserve` — _do the bank transfer yourself._')
    elif short:
        lines.append('\U0001F7E0 *Goes into overdraft:* /ilcash would be *%s* after the charge' % money(after))
        lines.append('_Within your %s overdraft. To stay out of it, move %s from the ILS bank._'
                     % (money(OVERDRAFT_LIMIT), money(short)))
    else:
        lines.append('\U0001F7E2 Covered — *%s* left after the charge.' % money(
            round(float(checking) - due, 2)))

    if rows:
        lines.append('')
        lines.append('*Biggest this cycle:*')
        for entry in sorted(rows, key=lambda e: -float(e.get('amount', 0) or 0))[:5]:
            lines.append('  %s — %s  _(%s)_' % (
                money(entry.get('amount')), entry.get('description', ''),
                entry.get('date', '')))
    return '\n'.join(lines)


def format_visa_charge(rows, checking):
    due = total_of(rows)
    after = round(float(checking) - due, 2)
    lines = ['\U0001F7E6 *VISA CHARGED TODAY*', '',
             'Total: *%s*  _(%d purchases)_' % (money(due), len(rows)),
             '%s /ilcash: %s → *%s*' % (CARD_EMOJI[DEBIT], money(checking), money(after)), '']
    if after < 0:
        lines.append('\U0001F534 That would leave /ilcash *%s* overdrawn.' % money(abs(after)))
        lines.append('Top it up with `/withdrawreserve` before confirming.')
        lines.append('')
    lines.append('Tap below once the charge actually lands to update /ilcash.')
    return '\n'.join(lines)


def format_month_summary(entries, month_key, prediction=None, cycle=False):
    """cycle: the month is a Visa cycle -- 10th to the 9th (see cycle_month_for)."""
    summary = month_summary(entries, month_key, cycle)
    label = datetime.strptime(month_key, '%Y-%m').strftime('%B %Y')
    lines = ['\U0001F4CA *SPENDING — %s*' % label]
    if cycle:
        start, end = cycle_range(month_key)
        lines.append('_%s – %s_' % (start.strftime('%d/%m'), end.strftime('%d/%m')))
    lines += ['━' * 20, '']

    if not summary['count']:
        lines.append('_Nothing logged this month._')
        return '\n'.join(lines)

    lines.append('\U0001F4B8 Total: *%s*  _(%d purchases)_' % (
        money(summary['total']), summary['count']))
    lines.append('   %s Debit %s   %s Visa %s' % (
        CARD_EMOJI[DEBIT], money(summary['by_card'][DEBIT]),
        CARD_EMOJI[VISA], money(summary['by_card'][VISA])))
    lines.append('   Average purchase: %s' % money(summary['average']))
    lines.append('')

    big = summary['biggest']
    lines.append('\U0001F53A Most expensive: *%s* — %s  _(%s)_' % (
        money(big.get('amount')), big.get('description', ''), big.get('date', '')))
    lines.append('')

    lines.append('*Everything logged:*')
    for entry in sorted(summary['entries'], key=lambda e: (e.get('date', ''), e.get('time', ''))):
        lines.append('`%s` %s %s — %s' % (
            entry.get('date', '')[5:], CARD_EMOJI[card_of(entry)],
            money(entry.get('amount')), entry.get('description', '')))

    if prediction and prediction.get('months'):
        lines.append('')
        if prediction['ready']:
            lines.append('*Looking ahead*')
            lines.append('Average of your last %d months: *%s*' % (
                prediction['months'], money(prediction['average'])))
            lines.append('Last 3 months: *%s*' % money(prediction['recent_average']))
            delta = summary['total'] - prediction['average']
            lines.append('This month ran *%s* %s that average.' % (
                money(abs(delta)), 'above' if delta >= 0 else 'below'))
            lines.append('_An average of %d months, not a forecast._' % prediction['months'])
        else:
            lines.append('_Only %d month of history so far - no useful average yet._'
                         % prediction['months'])
    return '\n'.join(lines)


# --------------------------------------------------------------------------- history

def available_months(entries, include=None, cycle=False):
    """Months holding any record, oldest first, plus any month asked for."""
    of = _month_fn(cycle)
    months = {of(e) for e in entries or [] if of(e)}
    for extra in (include or []):
        if extra:
            months.add(extra)
    return sorted(months)


def neighbour_months(entries, month_key, include=None, cycle=False):
    """The months either side of this one, for the arrow buttons."""
    months = available_months(entries, include=list(include or []) + [month_key], cycle=cycle)
    index = months.index(month_key)
    return (months[index - 1] if index > 0 else None,
            months[index + 1] if index < len(months) - 1 else None)


def indexed_month_entries(entries, month_key, cycle=False):
    """(position in the full log, record) for one month, oldest first.

    The position is what a delete button carries. Cancelling marks rather than
    removes, so positions stay valid for the life of the message.
    """
    of = _month_fn(cycle)
    rows = [(i, e) for i, e in enumerate(entries or [])
            if of(e) == month_key
            and not is_cancelled(e) and not is_investment(e)]
    return sorted(rows, key=lambda pair: (pair[1].get('date', ''), pair[1].get('time', '')))


def checking_effect(entry):
    """(עו"ש before, עו"ש after, purchase as % of the before) -- or None if unknown.

    New entries store checking_before; older ones have only balance_after, from
    which a debit's before is after + amount (Visa and cash leave the עו"ש
    untouched at purchase time, so before = after). % is None when the עו"ש
    was at or below zero."""
    amount = float(entry.get('amount') or 0)
    before, after = entry.get('checking_before'), entry.get('balance_after')
    if before is None and after is None:
        return None
    debit = card_of(entry) == DEBIT or is_reserved(entry)
    if before is None:
        before = float(after) + amount if debit else float(after)
    if after is None:
        after = float(before) - amount if debit else float(before)
    before, after = round(float(before), 2), round(float(after), 2)
    return before, after, (amount / before * 100 if before > 0 else None)


def format_effect(effect, short=False):
    """'4.2% מהעו"ש · ₪3,140 → ₪3,074' (short rounds to whole shekels)."""
    if not effect:
        return ''
    before, after, pct = effect
    m = (lambda x: ('-' if x < 0 else '') + '₪{:,.0f}'.format(abs(x))) if short else money
    share = ('%.1f%% מהעו"ש' % pct) if pct is not None else 'העו"ש היה במינוס'
    return '%s · %s → %s' % (share, m(before), m(after))


RECURRING_MARK = {'active': ' 🔁', 'stopped': ' 🔁⛔'}


def format_history(entries, month_key, prediction=None, cycle=False, recurring=None):
    """One month's purchases, numbered, with a short comparison to the past.

    cycle: months run 3rd-to-2nd (see cycle_month_of). recurring(entry) gives
    'active' / 'stopped' for a recurring payment, so it can be marked 🔁."""
    of = _month_fn(cycle)
    rows = indexed_month_entries(entries, month_key, cycle)
    label = datetime.strptime(month_key, '%Y-%m').strftime('%B %Y')
    lines = ['\U0001F4D6 *%s*' % label]
    if cycle:
        start, end = cycle_range(month_key)
        lines.append('_%s – %s_' % (start.strftime('%d/%m'), end.strftime('%d/%m')))
    lines += ['━' * 18, '']

    marked = scanned = False
    if not rows:
        lines.append('_Nothing logged this month._')
    else:
        for number, (_, entry) in enumerate(rows, 1):
            pending = ''
            if card_of(entry) == VISA:
                pending = ' _(pending)_' if not entry.get('charged') else ''
            mark = RECURRING_MARK.get(recurring(entry), '') if recurring else ''
            marked = marked or bool(mark)
            if isinstance(entry.get('receipt'), dict):
                mark += ' 🧾'
                scanned = True
            day = entry.get('date') or ''
            # A day from another calendar month (the 1st-2nd) shows its month too.
            shown = day[8:10] if not cycle or day[:7] == month_key else '%s/%s' % (day[8:10], day[5:7])
            lines.append('*%d.* `%s` %s %s — %s%s%s' % (
                number, shown, CARD_EMOJI[card_of(entry)],
                money(entry.get('amount')), entry.get('description', ''), pending, mark))
            effect = format_effect(checking_effect(entry), short=True)
            label = ''.join(ch for ch in str(entry.get('category') or '') if ch not in '*_`[]')
            sub = ''.join(ch for ch in str(entry.get('subcategory') or '') if ch not in '*_`[]')
            if label and sub:
                label += ' › ' + sub
            if label:
                effect = (effect + ' · ' if effect else '') + '🏷 ' + label
            if effect:
                lines.append('      ↳ _%s_' % effect)

        summary = month_summary(entries, month_key, cycle)
        lines.append('')
        lines.append('\U0001F4B8 *Total: %s*  _(%d purchases)_' % (
            money(summary['total']), summary['count']))
        lines.append('   %s %s   %s %s' % (
            CARD_EMOJI[DEBIT], money(summary['by_card'][DEBIT]),
            CARD_EMOJI[VISA], money(summary['by_card'][VISA])))
        big = summary['biggest']
        if big:
            lines.append('\U0001F53A Biggest: %s — %s' % (
                money(big.get('amount')), big.get('description', '')))

    if marked:
        lines.append('🔁 _= חיוב חוזר: יחויב שוב בחודש הבא_ · 🔁⛔ _= הופסק_')
    if scanned:
        lines.append('🧾 _= יש חשבונית — לחץ על הכפתור למטה כדי לראות אותה_')

    cancelled = [e for e in entries or []
                 if of(e) == month_key and is_cancelled(e)]
    invested = [e for e in entries or []
                if of(e) == month_key and is_investment(e)]
    if cancelled:
        lines.append('')
        lines.append('_%d cancelled this month (%s), not counted._' % (
            len(cancelled), money(sum(float(e.get('amount', 0) or 0) for e in cancelled))))

    if invested:
        lines.append('')
        lines.append('_%d moved to savings this month (%s), not spending._' % (
            len(invested), money(sum(float(e.get('amount', 0) or 0) for e in invested))))

    if prediction and prediction.get('ready'):
        totals = monthly_totals(entries, cycle)
        this_total = totals.get(month_key, 0)
        delta = this_total - prediction['average']
        lines.append('')
        lines.append('_vs %s average of your other months: %s%s_' % (
            money(prediction['average']),
            '+' if delta >= 0 else '-', money(abs(delta))))
    return '\n'.join(lines)


def format_months_overview(entries, limit=12, cycle=False):
    """Totals per month, newest first."""
    totals = monthly_totals(entries, cycle)
    if not totals:
        return '\U0001F4CA *No spending recorded yet.*'

    lines = ['\U0001F4CA *MONTH BY MONTH*', '━' * 18, '']
    for key in sorted(totals, reverse=True)[:limit]:
        try:
            label = datetime.strptime(key, '%Y-%m').strftime('%b %Y')
        except ValueError:
            label = key
        count = len(entries_for_month(entries, key, cycle))
        lines.append('`%s`  *%s*  _(%d)_' % (label.ljust(8), money(totals[key]), count))

    values = list(totals.values())
    lines.append('')
    lines.append('Average: *%s* across %d months' % (
        money(round(sum(values) / len(values), 2)), len(values)))
    return '\n'.join(lines)
