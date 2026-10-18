"""The ILS bank savings, split into two purposes.

The bank sees one account. This module tracks what that single balance is *for*:

  emergency  - untouched unless something goes wrong
  future     - planned purchases, and money that can come back to /ilcash

They are bookkeeping, not separate accounts, so one physical transfer still
costs one fee. The invariant that matters is that the two always add up to the
real bank balance; anything else and the split is lying about real money.
"""

import json
import os

PORTFOLIO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my_portfolio.json')

EMERGENCY = 'ILS_EMERGENCY'
FUTURE = 'ILS_FUTURE'
FUNDS = (EMERGENCY, FUTURE)

LABEL = {EMERGENCY: 'קרן חירום', FUTURE: 'הוצאות עתידיות / חיסכון'}
LABEL_EN = {EMERGENCY: 'Emergency fund', FUTURE: 'Future expenses'}
EMOJI = {EMERGENCY: '\U0001F6DF', FUTURE: '\U0001F3AF'}

STORE_KEY = {EMERGENCY: 'ILS_emergency', FUTURE: 'ILS_future'}


def money(amount):
    return '₪%s' % format(round(float(amount or 0), 2), ',.2f')


def read(reserves):
    """Both fund balances, seeded from the real bank balance on first use.

    Before the split existed, everything in the bank was effectively the
    emergency fund, so that is where an unseeded balance lands.
    """
    bank = float((reserves or {}).get('ILS', 0) or 0)
    has_split = STORE_KEY[EMERGENCY] in (reserves or {}) or STORE_KEY[FUTURE] in (reserves or {})
    if not has_split:
        return {EMERGENCY: round(bank, 2), FUTURE: 0.0}
    return {
        EMERGENCY: float(reserves.get(STORE_KEY[EMERGENCY], 0) or 0),
        FUTURE: float(reserves.get(STORE_KEY[FUTURE], 0) or 0),
    }


def write(reserves, funds):
    reserves[STORE_KEY[EMERGENCY]] = round(float(funds[EMERGENCY]), 2)
    reserves[STORE_KEY[FUTURE]] = round(float(funds[FUTURE]), 2)
    return reserves


def drift(reserves):
    """How far the two funds are from the real bank balance. Should be 0."""
    funds = read(reserves)
    bank = float((reserves or {}).get('ILS', 0) or 0)
    return round(funds[EMERGENCY] + funds[FUTURE] - bank, 2)


def apply_change(reserves, to_emergency=0.0, to_future=0.0, fee=0.0):
    """Move money into (or out of) the funds and keep the bank balance in step.

    The fee is charged once for the whole transfer, because that is what the
    bank actually does, and is taken from whichever fund received more.
    """
    funds = read(reserves)
    to_emergency = round(float(to_emergency or 0), 2)
    to_future = round(float(to_future or 0), 2)
    fee = round(float(fee or 0), 2)

    if fee:
        if to_emergency >= to_future:
            to_emergency = round(to_emergency - fee, 2)
        else:
            to_future = round(to_future - fee, 2)

    funds[EMERGENCY] = round(funds[EMERGENCY] + to_emergency, 2)
    funds[FUTURE] = round(funds[FUTURE] + to_future, 2)

    reserves['ILS'] = round(funds[EMERGENCY] + funds[FUTURE], 2)
    write(reserves, funds)
    return funds


def reconcile(reserves):
    """Force the split to match the real bank balance, adjusting the emergency
    fund. Used when the bank balance was changed by code that predates the
    split, so the two can never silently disagree."""
    funds = read(reserves)
    bank = float((reserves or {}).get('ILS', 0) or 0)
    gap = round(bank - (funds[EMERGENCY] + funds[FUTURE]), 2)
    if gap:
        funds[EMERGENCY] = round(funds[EMERGENCY] + gap, 2)
        write(reserves, funds)
    return funds, gap


RLM = '‏'   # forces the whole line to lay out right-to-left


def format_block(funds, indent='   '):
    """Each line starts with a right-to-left mark.

    Without it Telegram picks the paragraph direction from the first strong
    character, and an emoji is neutral -- so one Hebrew line would align right
    and the next left, purely by accident of what followed the emoji.
    """
    total = funds[EMERGENCY] + funds[FUTURE]
    return '\n'.join([
        '%s%s%s %s: *%s*' % (RLM, indent, EMOJI[EMERGENCY], LABEL[EMERGENCY],
                             money(funds[EMERGENCY])),
        '%s%s%s %s: *%s*' % (RLM, indent, EMOJI[FUTURE], LABEL[FUTURE],
                             money(funds[FUTURE])),
        '%s%s\U0001F3E6 סה"כ בבנק: *%s*' % (RLM, indent, money(total)),
    ])
