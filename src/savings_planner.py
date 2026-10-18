"""Monthly savings allocation planner.

Plans what share of each month's pay goes to the three savings buckets, projects
where the balances land when the plan runs out, and works out the split for a
payment that actually arrived.

This module only ever *reports* numbers. Writing balances stays with the existing
/addreserve, /ilcash and portfolio commands, so a typo here cannot corrupt the
ledger. The allocations are the user's own decision -- nothing here suggests a
split -- and the projection counts contributions only, with no market growth
assumed, so the stocks bucket is projected at money-in rather than at a guessed
return.
"""

import json
import os
import re
from datetime import datetime

PLAN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'savings_plan.json')

BUCKETS = ('ILS_EMERGENCY', 'ILS_FUTURE', 'EUR', 'USD_STOCKS')
BUCKET_LABEL = {'ILS_EMERGENCY': 'Emergency fund', 'ILS_FUTURE': 'Future expenses',
                'EUR': 'EUR savings', 'USD_STOCKS': 'USD stocks'}
BUCKET_CCY = {'ILS_EMERGENCY': 'ILS', 'ILS_FUTURE': 'ILS',
              'EUR': 'EUR', 'USD_STOCKS': 'USD'}
BUCKET_EMOJI = {'ILS_EMERGENCY': '\U0001F6DF', 'ILS_FUTURE': '\U0001F3AF',
                'EUR': '\U0001F4B6', 'USD_STOCKS': '\U0001F4C8'}

# Both funds live in one bank account, so a month that feeds either one is a
# single physical transfer and carries a single fee.
ILS_FUNDS = ('ILS_EMERGENCY', 'ILS_FUTURE')

# Plans written before the split stored one combined ILS bucket.
LEGACY_BUCKET = 'ILS_BANK'
KEREN_SELF_EMOJI = '\U0001F510'

# The 💶 share is not bought as euros each month: it goes into a shekel קרן כספית
# kept for euros (its yield beats inflation; idle euros lose buying power) and is
# converted only when needed. The bucket's balance stays in euros -- bank, cash and
# the fund at today's rate -- so the EUR goal reads the same; the fund's own
# shekels travel alongside under this key.
EUR_FUND = 'EUR_FUND_ILS'
EUR_FUND_LABEL = 'קרן כספית ליורו'
EUR_FUND_EMOJI = '\U0001FA99'
SYMBOL = {'ILS': '₪', 'EUR': '€', 'USD': '$'}

# The /ilcash checking account is not a savings bucket -- it is a float kept at a
# target balance for living expenses. It is topped up from pay BEFORE the savings
# percentages apply, because the percentages are a share of what is left to save.
CHECKING = 'ILS_CHECKING'
CHECKING_LABEL = 'Checking (/ilcash)'
CHECKING_EMOJI = '\U0001F4B3'
DEFAULT_FLOAT_TARGET = 3000.0
DEFAULT_MONTHLY_SPEND = 2000.0

# Every move into the ILS bank savings is charged a flat fee, taken out of the
# transfer. Planning without it quietly overstates what actually lands there.
ILS_TRANSFER_FEE = 5.0

ALIASES = {
    'emg': 'ILS_EMERGENCY', 'emergency': 'ILS_EMERGENCY', 'chirum': 'ILS_EMERGENCY',
    'ils': 'ILS_EMERGENCY', 'bank': 'ILS_EMERGENCY', 'ils_bank': 'ILS_EMERGENCY',
    'fut': 'ILS_FUTURE', 'future': 'ILS_FUTURE', 'savings': 'ILS_FUTURE',
    'expenses': 'ILS_FUTURE',
    'eur': 'EUR', 'euro': 'EUR',
    'usd': 'USD_STOCKS', 'usd_stocks': 'USD_STOCKS', 'stocks': 'USD_STOCKS',
    'stock': 'USD_STOCKS', 'invest': 'USD_STOCKS', 'investments': 'USD_STOCKS',
}

PLAN_HORIZON = 12

# Only these two carry a target; the stocks bucket is deliberately open-ended.
GOAL_BUCKETS = ('ILS_EMERGENCY', 'ILS_FUTURE', 'EUR')


# --------------------------------------------------------------------------- storage

def empty_plan():
    return {'salary': None, 'target': None, 'goals': {}, 'months': {}, 'payments': [],
            'created': datetime.now().strftime('%Y-%m-%d %H:%M'), 'updated': None}


def load_plan(path=None):
    path = path or PLAN_FILE
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            plan = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return empty_plan()
    base = empty_plan()
    base.update(plan or {})
    base['months'] = base.get('months') or {}
    base['payments'] = base.get('payments') or []
    base['goals'] = base.get('goals') or {}
    _strip_derived(base)
    return _migrate_legacy(base)


# Worked out on every load by the bot (inflation), never stored: a saved copy
# would go stale and outlive /inflation off.
DERIVED_TARGET_KEYS = ('amount_nominal', 'inflation')


def _strip_derived(plan):
    for key in DERIVED_TARGET_KEYS:
        (plan.get('target') or {}).pop(key, None)
    return plan


def _migrate_legacy(plan):
    """Plans predating the emergency/future split kept one ILS bucket.

    That money was all sitting in the bank untouched, which is the emergency
    fund's job, so it carries over there rather than being guessed at.
    """
    for alloc in (plan.get('months') or {}).values():
        if LEGACY_BUCKET in alloc:
            alloc['ILS_EMERGENCY'] = float(alloc.get('ILS_EMERGENCY', 0) or 0) \
                + float(alloc.pop(LEGACY_BUCKET) or 0)
            alloc.setdefault('ILS_FUTURE', 0.0)

    goals = plan.get('goals') or {}
    if LEGACY_BUCKET in goals:
        goals.setdefault('ILS_EMERGENCY', goals.pop(LEGACY_BUCKET))
    return plan


def save_plan(plan, path=None):
    path = path or PLAN_FILE
    plan['updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    stored = dict(plan)
    if plan.get('target'):
        stored['target'] = {k: v for k, v in plan['target'].items() if k not in DERIVED_TARGET_KEYS}
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(stored, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)          # atomic; never leaves a half-written plan behind
    return plan


# --------------------------------------------------------------------------- months

def month_key(when=None):
    return (when or datetime.now()).strftime('%Y-%m')


def shift_month(key, n):
    year, month = (int(part) for part in key.split('-'))
    total = year * 12 + (month - 1) + n
    return '%04d-%02d' % (total // 12, total % 12 + 1)


def upcoming_months(count=PLAN_HORIZON, start=None):
    start = start or month_key()
    return [shift_month(start, i) for i in range(count)]


def month_name(key):
    return datetime.strptime(key, '%Y-%m').strftime('%B %Y')


def plan_months(count=PLAN_HORIZON, now=None):
    """The months a fresh plan covers, starting with the current month.

    If this month's pay has already been split by the time the plan is drawn up,
    the wizard's "Skip month" leaves it out, so it is not counted twice in the
    projection.
    """
    return upcoming_months(count, month_key(now))


# --------------------------------------------------------------------------- goals

def inflation_credit(plan, end_balances):
    """The ILS bank savings (emergency + future) sit in a fund that tracks the CPI,
    so by the plan's end they have grown with the inflation still to come. That
    part of the target keeps its buying power without extra saving, so it is
    counted alongside the projected total. 0 when /inflation is off."""
    adj = (plan.get('target') or {}).get('inflation')
    if not adj:
        return 0.0
    ils = sum(float((end_balances or {}).get(b, 0) or 0) for b in ILS_FUNDS)
    return round(ils * float(adj.get('ahead_pct', 0)) / 100, 2)


def target_in_ils(plan, fx):
    """The overall target in shekels at the plan's end: the inflation-adjusted
    figure when /inflation has set one (amount_nominal, refreshed on every load),
    else the amount as entered. None when no target is set."""
    target = plan.get('target') or {}
    if not target.get('amount'):
        return None
    if target.get('amount_nominal'):
        return float(target['amount_nominal'])
    return to_ils(target['amount'], target.get('currency', 'ILS'), fx)


def goals_of(plan):
    """Target balance per bucket, in that bucket's own currency. 0 means none."""
    stored = (plan or {}).get('goals') or {}
    return {bucket: float(stored.get(bucket) or 0) for bucket in GOAL_BUCKETS}


def goal_progress(goal, current):
    goal = float(goal or 0)
    current = float(current or 0)
    if not goal:
        return None
    return {
        'goal': goal, 'current': current,
        'remaining': round(max(0.0, goal - current), 2),
        'pct': (current / goal * 100) if goal else 0.0,
        'done': current >= goal,
    }


def monthly_contribution(plan, bucket, fx, month=None):
    """What one planned month puts into `bucket`, in that bucket's currency.

    Uses the named month, or the last planned month when it is past the end of
    the plan -- assuming the current pace continues is honest; assuming saving
    stops is not.
    """
    months = sorted(plan.get('months') or {})
    if not months:
        return 0.0
    key = month if month in plan.get('months', {}) else months[-1]
    salary = (plan.get('salary') or {}).get('amount') or 0
    if not salary:
        return 0.0

    # The float refill is not known without a live checking balance, so the
    # steady-state refill (one month's spend) is used - the same assumption the
    # projection makes for every month after the first.
    cfg = float_config(plan)
    breakdown = payment_breakdown(salary, plan['months'][key],
                                  cfg['target'] - cfg['monthly_spend'], cfg)
    return from_ils(breakdown['split'].get(bucket, 0), BUCKET_CCY[bucket], fx)


def months_until(plan, balances, fx, bucket, target, horizon=120):
    """Months until `bucket` reaches `target` at the planned pace.

    Returns 0 when it is already there and None when the pace never gets there,
    rather than inventing a date.
    """
    current = float(balances.get(bucket, 0) or 0)
    target = float(target or 0)
    if current >= target:
        return 0

    months = sorted(plan.get('months') or {})
    if not months:
        return None

    start = month_key()
    for step in range(1, horizon + 1):
        key = shift_month(start, step)
        current += monthly_contribution(plan, bucket, fx, key)
        if current >= target:
            return step
    return None


def deposit_progress(plan, bucket, balances, added):
    """What a deposit just did to its goal, and what is still missing.

    Reports the contribution as a share of the goal, not of the balance, so the
    number answers 'how much closer am I' rather than 'how much bigger is the
    pot' -- those differ once the pot is large.
    """
    goal = goals_of(plan).get(bucket, 0)
    if not goal or not added:
        return None
    current = float(balances.get(bucket, 0) or 0)
    ccy = BUCKET_CCY[bucket]
    before = current - float(added)
    return {
        'bucket': bucket, 'ccy': ccy, 'goal': goal, 'current': current,
        'added': float(added),
        'added_pct': float(added) / goal * 100,
        'pct_before': max(0.0, before) / goal * 100,
        'pct_now': current / goal * 100,
        'remaining': round(max(0.0, goal - current), 2),
        'remaining_pct': max(0.0, goal - current) / goal * 100,
        'done': current >= goal,
    }


def format_deposit_progress(row):
    if not row:
        return ''
    ccy = row['ccy']
    lines = ['%s *%s*' % (BUCKET_EMOJI[row['bucket']], BUCKET_LABEL[row['bucket']]),
             '   ➕ הופקד: *%s*  _(%.1f%% מהיעד)_' % (
                 money(row['added'], ccy), row['added_pct']),
             '   \U0001F4C8 התקדמות: %.1f%% → *%.1f%%*' % (
                 row['pct_before'], row['pct_now'])]
    if row['done']:
        lines.append('   \U0001F389 *היעד הושג!* (%s מתוך %s)' % (
            money(row['current'], ccy), money(row['goal'], ccy)))
    else:
        lines.append('   \U0001F3AF נשאר: *%s*  _(%.1f%% מהיעד)_' % (
            money(row['remaining'], ccy), row['remaining_pct']))
        lines.append('   _%s מתוך %s_' % (
            money(row['current'], ccy), money(row['goal'], ccy)))
    return '\n'.join(lines)


def withdraw_progress(plan, bucket, balances, taken):
    """What a withdrawal cost in goal terms.

    `balances` is read AFTER the money left, so the previous balance is derived
    rather than passed -- the caller cannot accidentally report a stale figure.
    Two different denominators matter here and are kept apart: the share of the
    balance that walked out, and the share of the goal that was given up.
    """
    taken = abs(float(taken or 0))
    current = float(balances.get(bucket, 0) or 0)
    before = round(current + taken, 2)
    row = {
        'bucket': bucket,
        'ccy': BUCKET_CCY.get(bucket, 'ILS'),
        'taken': taken,
        'before': before,
        'current': current,
        # Of what was there a moment ago. Zero before means there is no share to
        # report, not a division by zero.
        'taken_pct_of_before': (taken / before * 100) if before > 0 else 0.0,
    }
    goal = goals_of(plan).get(bucket, 0)
    if goal:
        pct_before = max(0.0, before) / goal * 100
        pct_now = max(0.0, current) / goal * 100
        row.update({
            'goal': goal,
            'pct_before': pct_before,
            'pct_now': pct_now,
            'lost_pct': pct_before - pct_now,
            'taken_pct_of_goal': taken / goal * 100,
            'remaining': round(max(0.0, goal - current), 2),
            'remaining_pct': max(0.0, goal - current) / goal * 100,
            'done': current >= goal,
        })
    return row


def format_withdraw_progress(row):
    """How far the goal slipped, and how much of the pot it was."""
    if not row:
        return ''
    ccy = row['ccy']
    label = BUCKET_LABEL.get(row['bucket'], row['bucket'])
    emoji = BUCKET_EMOJI.get(row['bucket'], '\U0001F4B0')
    lines = ['%s *%s*' % (emoji, label)]
    lines.append('   ➖ ירד: *%s*  _(%.1f%% ממה '
                 'שהיה לך)_'
                 % (money(row['taken'], ccy), row['taken_pct_of_before']))
    lines.append('   %s → *%s*' % (money(row['before'], ccy),
                                        money(row['current'], ccy)))

    if not row.get('goal'):
        lines.append('   _אין יעד '
                     'מוגדר — /setplan_')
        return '\n'.join(lines)

    lines.append('   \U0001F4C9 התקדמות: '
                 '%.1f%% → *%.1f%%*  _(-%.1f%%)_'
                 % (row['pct_before'], row['pct_now'], row['lost_pct']))
    if row.get('done'):
        lines.append('   ✅ _עדיין '
                     'מעל היעד_')
    else:
        lines.append('   \U0001F3AF נשאר: *%s*  _(%.1f%% '
                     'מהיעד)_'
                     % (money(row['remaining'], ccy), row['remaining_pct']))
    lines.append('   _%s מתוך %s_'
                 % (money(row['current'], ccy), money(row['goal'], ccy)))
    return '\n'.join(lines)


def goal_lines(plan, balances, indent='   '):
    """One line per bucket that has a target, saying what is still missing."""
    goals = goals_of(plan)
    lines = []
    for bucket in GOAL_BUCKETS:
        progress = goal_progress(goals[bucket], balances.get(bucket, 0))
        if not progress:
            continue
        ccy = BUCKET_CCY[bucket]
        if progress['done']:
            lines.append('%s%s %s: \U0001F389 *reached* (%s of %s)' % (
                indent, BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket],
                money(progress['current'], ccy), money(progress['goal'], ccy)))
        else:
            lines.append('%s%s %s: *%s to go* (%s of %s, %.0f%%)' % (
                indent, BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket],
                money(progress['remaining'], ccy), money(progress['current'], ccy),
                money(progress['goal'], ccy), progress['pct']))
    return lines


# --------------------------------------------------------------------------- allocations

def parse_allocation(tokens):
    """Parse 'emg=30 fut=20 eur=20 usd=30' or a bare '30/20/20/30' into a dict."""
    if not tokens:
        raise ValueError('No allocation given.')
    text = ' '.join(tokens).replace(',', ' ').strip()

    if '=' not in text:
        parts = [p for p in text.replace('/', ' ').split() if p]
        if len(parts) != len(BUCKETS):
            raise ValueError('Give four numbers as emergency/future/EUR/USD, e.g. 30/20/20/20')
        return validate_allocation(dict(zip(BUCKETS, (_pct(p) for p in parts))))

    alloc = {}
    for token in text.split():
        if '=' not in token:
            raise ValueError('Use name=percent, e.g. emg=30 fut=20 eur=20 usd=30')
        name, _, value = token.partition('=')
        bucket = ALIASES.get(name.strip().lower())
        if not bucket:
            raise ValueError('Unknown bucket "%s". Use emg, fut, eur or usd.' % name)
        alloc[bucket] = _pct(value)
    return validate_allocation(alloc)


def _pct(raw):
    try:
        value = float(str(raw).strip().rstrip('%'))
    except ValueError:
        raise ValueError('"%s" is not a number.' % raw)
    if value < 0:
        raise ValueError('Percentages cannot be negative.')
    return value


def validate_allocation(alloc):
    full = {b: float(alloc.get(b, 0) or 0) for b in BUCKETS}
    total = sum(full.values())
    if total > 100.0001:
        raise ValueError('Allocations add up to %.1f%% - that is more than your pay.' % total)
    if total <= 0:
        raise ValueError('Allocations are all zero.')
    return full


def allocated_pct(alloc):
    return sum(float(alloc.get(b, 0) or 0) for b in BUCKETS)


# --------------------------------------------------------------------------- money

def split_amount(amount, alloc):
    """Split a payment by allocation.

    Bucket amounts sum exactly to the allocated part; rounding residue lands on
    the largest bucket instead of quietly disappearing.
    """
    amount = float(amount)
    split = {b: round(amount * float(alloc.get(b, 0) or 0) / 100.0, 2) for b in BUCKETS}

    target_total = round(amount * allocated_pct(alloc) / 100.0, 2)
    drift = round(target_total - sum(split.values()), 2)
    if drift and any(split.values()):
        biggest = max(BUCKETS, key=lambda b: split[b])
        split[biggest] = round(split[biggest] + drift, 2)

    unallocated = round(amount - sum(split.values()), 2)
    return split, unallocated


def to_ils(amount, currency, fx):
    if currency == 'ILS':
        return float(amount)
    rate = fx.get(currency + 'ILS')
    if not rate:
        raise ValueError('Missing %s->ILS rate.' % currency)
    return float(amount) * float(rate)


def from_ils(amount_ils, currency, fx):
    if currency == 'ILS':
        return float(amount_ils)
    rate = fx.get(currency + 'ILS')
    if not rate:
        raise ValueError('Missing %s->ILS rate.' % currency)
    return float(amount_ils) / float(rate)


def money(amount, currency):
    value = round(float(amount), 2)
    sign = '-' if value < 0 else ''          # -₪235.65, not ₪-235.65
    return '%s%s%s' % (sign, SYMBOL.get(currency, ''), format(abs(value), ',.2f'))


# --------------------------------------------------------------------------- projection

# --------------------------------------------------------------------------- messages

def _alloc_line(alloc):
    parts = []
    for bucket in BUCKETS:
        pct = float(alloc.get(bucket, 0) or 0)
        if pct:
            parts.append('%s %.0f%%' % (BUCKET_EMOJI[bucket], pct))
    left = 100 - allocated_pct(alloc)
    if left > 0.01:
        parts.append('\U0001F4B8 %.0f%% free' % left)
    return '  '.join(parts) if parts else '-'


def format_plan(plan, balances, fx, snapshot=None, salary_text=None):
    """The /plan view. Shares the timeline maths with the wizard summary so the
    checking float is handled identically in both.

    With a `snapshot` the short balance list is replaced by the full current
    situation -- cash, the pending Visa charge, the locked fund, measured
    spending, fees, goal pace, purchases and any running trip -- so the
    projection is read against reality rather than four numbers.
    """
    cfg = float_config(plan)
    salary = (plan.get('salary') or {}).get('amount')
    months = sorted(plan.get('months') or {})

    header = ['\U0001F4C5 *SAVINGS PLAN*', '━' * 20, '']
    if snapshot:
        header += [format_situation(snapshot, plan, balances, fx), '']
    else:
        header += ['*Today:*', _balance_block(balances, fx, target=cfg['target']), '']
    header.append('\U0001F4BC Pay: *%s* / month' % money(salary, 'ILS') if salary
                  else '\U0001F4BC Pay: _not set_ - use /salary')
    header.append('%s Checking float: *%s* (%s)' % (
        CHECKING_EMOJI, money(cfg['target'], 'ILS'), float_basis_text(cfg)))
    target = plan.get('target') or {}
    if not target.get('amount'):
        header.append('\U0001F3AF Target: _not set_ - use /plantarget')
    header.append('')

    # The salary the goals above require, written onto the plan itself so the
    # projection and what it asks of you sit on one page.
    if salary_text:
        header += [salary_text, '']

    if not months:
        header.append('_No months planned yet._')
        header.append('Run /setplan to build them step by step.')
        return '\n'.join(header)

    return '\n'.join(header) + '\n' + format_summary(plan, balances, fx, months)


def format_payment(month, breakdown, alloc, fx):
    """The /payment view: what to move where, in the order the money moves."""
    bd = breakdown
    inside = bd.get('in_checking')
    lines = ['\U0001F4B0 *PAYMENT — %s*' % month_name(month), '━' * 20, '',
             'Received: *%s*' % money(bd['amount'], 'ILS')]
    if inside:
        # The payment is already sitting in the עו"ש: what counts is the balance without it.
        lines.append('%s /ilcash now: *%s* — without this payment *%s*' % (
            CHECKING_EMOJI, money(bd['checking_shown'], 'ILS'), money(bd['checking_before'], 'ILS')))
    else:
        lines.append('%s /ilcash now: *%s*' % (CHECKING_EMOJI, money(bd['checking_before'], 'ILS')))
    lines.append('')

    step = 1
    if bd['refill']:
        lines.append(('*%d. Leave %s of it in /ilcash*' if inside else '*%d. Top up /ilcash — %s*')
                     % (step, money(bd['refill'], 'ILS')))
        lines.append('   %s → brings it to *%s*' % (
            money(bd['checking_before'], 'ILS'), money(bd['checking_after'], 'ILS')))
        step += 1
    else:
        lines.append('%s Already at %s — no top-up needed.' % (
            CHECKING_EMOJI, money(bd['target'], 'ILS')))

    if bd['excess']:
        lines.append('')
        lines.append('*%d. Unused expense budget → future expenses*' % step)
        lines.append('   %s *%s*  _(budgeted %s, only %s needed)_' % (
            BUCKET_EMOJI['ILS_FUTURE'], money(bd['excess'], 'ILS'),
            money(bd['budget'], 'ILS'), money(bd['refill'], 'ILS')))
        step += 1

    if bd['short']:
        lines.append('')
        lines.append('⚠️ The whole payment went to /ilcash - nothing left to save.')
        lines.append('')
        lines.append('_Nothing was recorded._ Log it with /addreserve, /ilcash or /addcash.')
        return '\n'.join(lines)

    if bd.get('keren_self'):
        lines.append('')
        lines.append('*%d. %s קרן השתלמות לעצמאיים — %s*' % (step, KEREN_SELF_EMOJI, money(bd['keren_self'], 'ILS')))
        lines.append('   _סכום קבוע מהתוכנית (תקרה ₪1,714 לחודש), לפני החלוקה באחוזים_')
        step += 1

    lines.append('')
    lines.append('*%d. Split the remaining %s*' % (step, money(bd['base'], 'ILS')))

    for bucket in BUCKETS:
        pct = float(alloc.get(bucket, 0) or 0)
        if not pct:
            continue
        # The recorded split, so the bank fee taken off an ILS fund shows here too
        # (the future-expenses line is only its share; the unused budget is listed apart).
        allocated = round(bd['split'][bucket] - (bd['excess'] if bucket == 'ILS_FUTURE' else 0), 2)
        ccy = BUCKET_CCY[bucket]
        row = '   %s *%s* — %s  _(%.0f%%)_' % (
            BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket], money(allocated, 'ILS'), pct)
        if bucket == 'EUR':
            row += ('\n      → buy *%s* in shekels (≈ %s at today’s rate) — '
                    'convert to € only when you need it' % (EUR_FUND_LABEL, money(from_ils(allocated, ccy, fx), ccy)))
        elif ccy != 'ILS':
            row += '\n      ≈ *%s* at today’s rate' % money(
                from_ils(allocated, ccy, fx), ccy)
        lines.append(row)

    if bd['unallocated'] > 0.01:
        lines.append('   \U0001F4B8 Left over: *%s*' % money(bd['unallocated'], 'ILS'))

    if bd.get('fee'):
        lines.append('')
        lines.append('\U0001F3E6 _ILS bank transfer fee %s already deducted above._'
                     % money(bd['fee'], 'ILS'))

    if bd['excess']:
        lines.append('')
        lines.append('%s *Future expenses total: %s*  _(%s unused budget + %s allocation)_' % (
            BUCKET_EMOJI['ILS_FUTURE'], money(bd['split']['ILS_FUTURE'], 'ILS'),
            money(bd['excess'], 'ILS'),
            money(bd['split']['ILS_FUTURE'] - bd['excess'], 'ILS')))

    lines.append('')
    if inside:
        lines.append('_Move the rest out of the עו"ש; what stays there is the %s above._'
                     % money(bd['refill'], 'ILS') if bd['refill'] else
                     '_Move all of it out of the עו"ש._')
    lines.append('_Nothing was recorded._ Log it with /addreserve, /ilcash or /addcash.')
    return '\n'.join(lines)


def format_reminder(month, alloc, salary, index, total, fx, topup=0, target=None):
    """One of the month-start nudges."""
    lines = ['\U0001F514 *ALLOCATION REMINDER* (%d/%d)' % (index, total),
             '\U0001F4C5 %s' % month_name(month), '']

    if salary:
        base = max(0.0, round(float(salary) - float(topup or 0), 2))
        split, unallocated = split_amount(base, alloc)
        if topup:
            lines.append('%s First refill checking: *%s*%s' % (
                CHECKING_EMOJI, money(topup, 'ILS'),
                (' (back to %s)' % money(target, 'ILS')) if target else ''))
            lines.append('')
            lines.append('Then from the remaining %s:' % money(base, 'ILS'))
        else:
            lines.append('On your usual %s:' % money(salary, 'ILS'))
        for bucket in BUCKETS:
            if not float(alloc.get(bucket, 0) or 0):
                continue
            ccy = BUCKET_CCY[bucket]
            extra = ''
            if bucket == 'EUR':
                extra = ' → %s' % EUR_FUND_LABEL
            elif ccy != 'ILS':
                try:
                    extra = ' (≈%s)' % money(from_ils(split[bucket], ccy, fx), ccy)
                except ValueError:
                    extra = ''
            lines.append('%s *%s* — %s%s' % (
                BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket], money(split[bucket], 'ILS'), extra))
        if unallocated > 0.01:
            lines.append('\U0001F4B8 Left over: %s' % money(unallocated, 'ILS'))
    else:
        lines.append('This month’s split: %s' % _alloc_line(alloc))

    lines.append('')
    lines.append('Run `/payment <amount>` when your pay lands.')
    return '\n'.join(lines)


# --------------------------------------------------------------------------- wizard

# Shortcut buttons for the step-by-step planner. These are input conveniences,
# not suggestions -- any split can be typed instead.
PRESETS = [
    (30, 20, 20, 20), (40, 10, 20, 20), (25, 25, 25, 25),
    (50, 10, 20, 20), (20, 30, 20, 20), (20, 20, 10, 40),
]


def preset_label(triple):
    return '/'.join(str(int(x)) for x in triple)


def preset_alloc(triple):
    return dict(zip(BUCKETS, (float(x) for x in triple)))


FLOAT_AUTO = 'last_month'          # target = last month's real spending + a buffer
DEFAULT_FLOAT_BUFFER = 1000.0


def float_config(plan):
    """Checking-float settings, with defaults when never configured.

    In the automatic mode the target follows real spending: last month's total
    plus a buffer. The bot fills in 'last_month_spend' from the expense log each
    time it loads the plan (this module never reads the log itself); until it
    has, the fixed figures below stand in.
    """
    cfg = (plan or {}).get('float') or {}
    # the self-employed keren deposit rides along: every payment_breakdown() caller gets it
    keren = float((plan or {}).get('keren_self_monthly') or 0)
    if cfg.get('mode') == FLOAT_AUTO and cfg.get('last_month_spend') is not None:
        spend = round(float(cfg['last_month_spend']), 2)
        buffer = float(cfg.get('buffer', DEFAULT_FLOAT_BUFFER) or 0)
        return {'target': round(spend + buffer, 2), 'monthly_spend': spend, 'mode': FLOAT_AUTO,
                'buffer': buffer, 'basis_month': cfg.get('basis_month'), 'basis': cfg.get('basis', 'last_month'),
                'keren_self': keren}
    return {
        'target': float(cfg.get('target', DEFAULT_FLOAT_TARGET) or 0),
        'monthly_spend': float(cfg.get('monthly_spend', DEFAULT_MONTHLY_SPEND) or 0),
        'mode': 'fixed', 'keren_self': keren,
    }


def planning_config(plan):
    """float_config() for projections: with the monthly spending you expect (set in /setplan,
    plan['expected_spend']) instead of last month's, so every planned month first sets that
    spending aside. The real /payment keeps using float_config()."""
    cfg = float_config(plan)
    spend = float((plan or {}).get('expected_spend') or 0)
    if spend:
        cfg = dict(cfg, monthly_spend=spend, target=max(cfg['target'], spend), planned_spend=spend)
    return cfg


def float_basis_text(cfg):
    """One line saying where the float target comes from."""
    if cfg.get('mode') != FLOAT_AUTO:
        return '%s spend + %s buffer, fixed' % (money(cfg['monthly_spend'], 'ILS'),
                                                money(cfg['target'] - cfg['monthly_spend'], 'ILS'))
    month = cfg.get('basis_month')
    label = month_name(month) if month else 'last month'
    if cfg.get('basis') == 'average':
        return ('%s average spend (nothing logged in %s) + %s buffer'
                % (money(cfg['monthly_spend'], 'ILS'), label, money(cfg['buffer'], 'ILS')))
    return '%s spent in %s + %s buffer' % (money(cfg['monthly_spend'], 'ILS'), label, money(cfg['buffer'], 'ILS'))


# --------------------------------------------------------------------------- what a payment is made of

def parse_sources(text):
    """'7000 salary, 2000 refund, 1500 selling something' -> amounts with labels.

    Parts are separated by commas, semicolons or new lines; a comma inside a
    number (4,000) is not a separator. The amount may come before or after its
    label. Raises ValueError with a readable reason.
    """
    parts = re.split(r'\n|;|,(?!\d{3}(?!\d))', text or '')
    out = []
    for raw in parts:
        part = raw.replace('₪', ' ').replace('ש"ח', ' ').strip(' .\t')
        if not part:
            continue
        numbers = list(re.finditer(r'(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w,])', part))
        if not numbers:
            raise ValueError('no amount in "%s"' % part.strip())
        # A number at the start or the end is the amount; one buried in the middle
        # of the label ("iphone 12 sold 2100") is not.
        chosen = numbers[0]
        if chosen.start() > 0:
            chosen = numbers[-1] if part[numbers[-1].end():].strip() == '' else numbers[0]
        amount = float(chosen.group(1).replace(',', ''))
        if amount <= 0:
            raise ValueError('"%s" is not a positive amount' % chosen.group(1))
        label = (part[:chosen.start()] + part[chosen.end():]).strip(' -–:=')
        out.append({'amount': round(amount, 2), 'label': re.sub(r'\s+', ' ', label) or 'other'})
    if not out:
        raise ValueError('nothing to read')
    return out


def format_sources(sources, total=None):
    """The breakdown, shown above the allocation."""
    total = total if total is not None else sum(s['amount'] for s in sources)
    lines = ['\U0001F9FE *What the payment is made of:*']
    for s in sorted(sources, key=lambda s: -s['amount']):
        share = (' _(%.0f%%)_' % (s['amount'] / total * 100)) if total else ''
        lines.append('   • %s — %s%s' % (money(s['amount'], 'ILS'),
                                                     s['label'].replace('*', '').replace('_', ' '), share))
    return '\n'.join(lines)


def topup_needed(current, target):
    """What it takes to bring the checking account back up to its float target."""
    return max(0.0, round(float(target) - float(current), 2))


def payment_breakdown(amount, alloc, checking_now, cfg):
    """Work out one payment, in the order the money actually moves.

    1. Refill /ilcash to its target -- however much that happens to need today.
    2. Any part of the month's checking budget that was NOT needed (you underspent
       last month) goes 100% to the ILS bank, not spread across the percentages.
    3. The self-employed keren deposit (a fixed amount, cfg['keren_self']), if set.
    4. Whatever is still left is split by the allocation.

    Step 2 is what keeps a frugal month from quietly inflating the EUR and stock
    contributions: the leftover was budgeted as spending money, so it lands in the
    bank rather than being treated as new savings capacity.
    """
    amount = float(amount)
    target = float(cfg.get('target', DEFAULT_FLOAT_TARGET) or 0)
    budget = float(cfg.get('monthly_spend', DEFAULT_MONTHLY_SPEND) or 0)

    refill = min(topup_needed(checking_now, target), amount)
    remaining = round(amount - refill, 2)

    excess = round(max(0.0, min(budget - refill, remaining)), 2)
    keren = round(max(0.0, min(float(cfg.get('keren_self') or 0), remaining - excess)), 2)
    base = round(remaining - excess - keren, 2)

    if base > 0:
        split, unallocated = split_amount(base, alloc)
    else:
        base = max(base, 0.0)
        split, unallocated = {b: 0.0 for b in BUCKETS}, 0.0

    split = dict(split)
    # Unused expense budget was spending money, so it joins the fund you can pull
    # back to /ilcash rather than the one meant to stay untouched.
    split['ILS_FUTURE'] = round(split['ILS_FUTURE'] + excess, 2)

    # Both ILS funds sit in one bank account, so funding either is a single
    # transfer and a single fee, taken off whichever receives more.
    ils_total = round(sum(split[b] for b in ILS_FUNDS), 2)
    fee = round(min(ILS_TRANSFER_FEE, ils_total), 2) if ils_total > 0 else 0.0
    if fee:
        bigger = max(ILS_FUNDS, key=lambda b: split[b])
        split[bigger] = round(split[bigger] - fee, 2)

    return {
        'amount': amount, 'refill': refill, 'excess': excess, 'base': base, 'keren_self': keren,
        'fee': fee, 'split': split, 'unallocated': unallocated,
        'checking_before': float(checking_now),
        'checking_after': round(float(checking_now) + refill, 2),
        'short': remaining <= 0,
        'target': target, 'budget': budget,
    }


def project_timeline(plan, balances, fx, months):
    """Running balance after each planned month. Contributions only, no growth.

    Each month the checking float is refilled to its target first, and only what
    is left over is split by the allocation. Within the month the expected spend
    draws the float back down, so it settles at target-minus-spend and the next
    refill is the spend itself.
    """
    running = {b: float(balances.get(b, 0) or 0) for b in BUCKETS}
    checking = float(balances.get(CHECKING, 0) or 0)
    eur_fund = float(balances.get(EUR_FUND, 0) or 0)
    cfg = planning_config(plan)
    salary = (plan.get('salary') or {}).get('amount') or 0
    steps = []

    for key in months:
        alloc = (plan.get('months') or {}).get(key)
        if not alloc:
            continue

        # Same routine a real /payment runs, so projection and reality agree. A month can
        # carry its own expected income (asked month by month in /setplan).
        income = float((plan.get('month_income') or {}).get(key) or salary)
        bd = payment_breakdown(income, alloc, checking, cfg)

        added = {}
        for bucket in BUCKETS:
            native = from_ils(bd['split'][bucket], BUCKET_CCY[bucket], fx)
            added[bucket] = native
            running[bucket] += native

        checking = round(bd['checking_after'] - cfg['monthly_spend'], 2)
        eur_fund = round(eur_fund + bd['split']['EUR'], 2)

        steps.append({
            'month': key, 'alloc': alloc, 'split_ils': bd['split'], 'added_native': added,
            'balances': dict(running, **{EUR_FUND: eur_fund}), 'eur_fund': eur_fund,
            'unallocated': bd['unallocated'],
            'topup': bd['refill'], 'excess': bd['excess'], 'base': bd['base'],
            'fee': bd['fee'], 'keren_self': bd.get('keren_self', 0.0),
            'checking_filled': bd['checking_after'], 'checking_end': checking,
            'short': bd['short'],
            'total_ils': sum(to_ils(running[b], BUCKET_CCY[b], fx) for b in BUCKETS),
        })
    return steps


def _balance_block(balances, fx, indent='   ', target=None):
    """Checking float first (it is spending money, not savings), then the buckets."""
    lines = []
    if CHECKING in balances:
        line = '%s%s %s: *%s*' % (indent, CHECKING_EMOJI, CHECKING_LABEL,
                                  money(balances.get(CHECKING, 0), 'ILS'))
        if target:
            short = topup_needed(balances.get(CHECKING, 0), target)
            line += (' — _%s short of %s_' % (money(short, 'ILS'), money(target, 'ILS'))
                     if short else ' — _at target_')
        lines.append(line)

    for bucket in BUCKETS:
        line = '%s%s %s: *%s*' % (
            indent, BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket],
            money(balances.get(bucket, 0), BUCKET_CCY[bucket]))
        if bucket == 'EUR' and EUR_FUND in balances:
            line += ' _(incl. %s %s)_' % (EUR_FUND_LABEL, money(balances[EUR_FUND], 'ILS'))
        lines.append(line)
    total = sum(to_ils(balances.get(b, 0), BUCKET_CCY[b], fx) for b in BUCKETS)
    lines.append('%s\U0001F4B0 Savings total: *%s*' % (indent, money(total, 'ILS')))
    return '\n'.join(lines)


HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט',
              'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']


def heb_month(key):
    y, m = str(key).split('-')[:2]
    return '%s %s' % (HEB_MONTHS[int(m) - 1], y)


HEB_BUCKET = {'ILS_EMERGENCY': 'קרן חירום', 'ILS_FUTURE': 'הוצאות עתידיות',
              'EUR': 'חיסכון ביורו', 'USD_STOCKS': 'מניות (דולר)'}


def next_month_preview(plan, balances, fx, month):
    """What next month's payment does, by the plan: the same routine /payment
    runs, with the עו"ש assumed spent down to (target - monthly spend) by payday
    -- the way every later month is projected. None if the month has no plan."""
    if not (plan.get('months') or {}).get(month):
        return None
    cfg = planning_config(plan)
    start = dict(balances)
    start[CHECKING] = round(cfg['target'] - cfg['monthly_spend'], 2)
    steps = project_timeline(plan, start, fx, [month])
    return steps[0] if steps else None


def format_next_month(plan, balances, fx, month, step, salary=None):
    """/showplan's live top section: next month's split, what each goal gains
    (₪ and % of today's), how far each goal and the overall target remain, and
    the pay the target needs -- inflation included."""
    pay = (plan.get('salary') or {}).get('amount') or 0
    lines = ['\U0001F4C5 *ההקצאה המתוכננת — %s* _(מחושב עכשיו)_' % heb_month(month),
             '_לפי המשכורת בתוכנית: %s · %s להשלמת העו"ש (להוצאות)_' % (
                 money(pay, 'ILS'), money(step['topup'], 'ILS')),
             '━' * 20]
    goals = goals_of(plan)
    for b in BUCKETS:
        pct = float(step['alloc'].get(b, 0) or 0)
        now = float(balances.get(b, 0) or 0)
        add = float(step['added_native'].get(b, 0) or 0)
        after = now + add
        ccy = BUCKET_CCY[b]
        lines += ['', '%s *%s* · %.0f%%' % (BUCKET_EMOJI[b], HEB_BUCKET[b], pct)]
        grow = (' (+%.1f%% מהקיים)' % (add / now * 100)) if now > 0 else ''
        extra = ('  _(%s)_' % money(step['split_ils'][b], 'ILS')) if ccy != 'ILS' else ''
        if b == 'EUR' and 'eur_fund' in step:
            extra = '  _(%s ל%s → %s)_' % (money(step['split_ils'][b], 'ILS'), EUR_FUND_LABEL, money(step['eur_fund'], 'ILS'))
        lines.append('   ➕ *%s*%s → %s%s' % (money(add, ccy), extra, money(after, ccy), grow))
        goal = goals.get(b)
        if goal:
            left = max(0.0, goal - after)
            lines.append('   🎯 יעד %s — %s' % (
                money(goal, ccy), ('חסר *%s* (%.1f%% מהיעד) · הושלם %.1f%%' % (money(left, ccy), left / goal * 100, after / goal * 100))
                if left > 0 else '✅ הושג'))
    if step.get('excess'):
        lines.append('   _+%s תקציב הוצאות שלא נוצל → הוצאות עתידיות_' % money(step['excess'], 'ILS'))
    if step.get('fee'):
        lines.append('   _🏦 עמלת העברה %s כבר בחשבון_' % money(step['fee'], 'ILS'))

    now_total = sum(to_ils(float(balances.get(b, 0) or 0), BUCKET_CCY[b], fx) for b in BUCKETS)
    after_total = step['total_ils']
    lines += ['', '\U0001F4B0 *סה"כ:* %s → *%s* (+%s · +%.1f%%)' % (
        money(now_total, 'ILS'), money(after_total, 'ILS'), money(after_total - now_total, 'ILS'),
        (after_total - now_total) / now_total * 100 if now_total else 0)]
    target = target_in_ils(plan, fx)
    if target:
        real = (plan.get('target') or {}).get('amount')
        label = (' (%s של היום + אינפלציה)' % money(real, 'ILS')) if (plan.get('target') or {}).get('amount_nominal') else ''
        for name, value in (('עכשיו', now_total), ('אחרי %s' % heb_month(month), after_total)):
            left = max(0.0, target - value)
            lines.append('\U0001F3AF יעד כולל %s%s — %s: חסר *%s* (%.1f%%)' % (
                money(target, 'ILS'), label if name == 'עכשיו' else '', name, money(left, 'ILS'), left / target * 100))
    if salary and salary.get('need_net') is not None:
        diff = salary['need_net'] - salary['current_net']
        lines += ['', '\U0001F4BC *המשכורת שהיעד דורש עד %s* _(כולל אינפלציה משוערת)_' % heb_month(salary['to']),
                  '   נטו: *%s* לחודש  _(עכשיו %s, %s%s)_' % (
                      money(salary['need_net'], 'ILS'), money(salary['current_net'], 'ILS'),
                      '+' if diff >= 0 else '-', money(abs(diff), 'ILS')),
                  '   ברוטו: *≈ %s*  _(עכשיו ≈ %s)_' % (money(salary['need_gross'], 'ILS'), money(salary['current_gross'], 'ILS'))]
    return '\n'.join(lines)


def format_wizard_intro(balances, fx, salary, total_steps, cfg=None, start=None):
    """start: the first planned month -- next month once this month's
    allocation is recorded (/allocated)."""
    cfg = cfg or {'target': DEFAULT_FLOAT_TARGET, 'monthly_spend': DEFAULT_MONTHLY_SPEND}
    start = start or month_key()
    lines = ['\U0001F4C5 *SAVINGS PLANNER*', '━' * 20, '',
             '*Where you stand today:*',
             _balance_block(balances, fx, target=cfg['target']), '']
    if salary:
        lines.append('\U0001F4BC Monthly pay: *%s*' % money(salary, 'ILS'))
    else:
        lines.append('⚠️ No pay set yet - run /salary first, '
                     'otherwise months project as zero.')
    lines.append('%s Checking kept at *%s* (%s), '
                 'refilled before anything is saved.' % (
                     CHECKING_EMOJI, money(cfg['target'], 'ILS'), float_basis_text(cfg)))
    if cfg.get('mode') == FLOAT_AUTO:
        lines.append('_Automatic: last month\'s spending + %s — not part of the plan._'
                     % money(cfg.get('buffer', DEFAULT_FLOAT_BUFFER), 'ILS'))
    else:
        lines.append('_Change it with_ `/ilfloat 3000 2000` _or make it automatic:_ `/ilfloat auto`')
    lines.append('')
    if start == month_key():
        lines.append('I’ll ask you month by month for %d months, starting this month (%s).'
                     % (total_steps, month_name(start)))
        lines.append('_Already split this month’s pay? Tap “Skip month” on it so it isn’t counted twice._')
    else:
        lines.append('I’ll ask you month by month for %d months, starting %s — '
                     '%s’s allocation is already recorded.' % (total_steps, month_name(start), month_name(month_key())))
    return '\n'.join(lines)


def format_wizard_prompt(month, index, total, running, fx, cfg=None, plan=None, salary=None):
    """The question asked for one month, with the balances it starts from -- and, when the
    expected income is known, the money itself: what is left to split and what each
    preset button would send where."""
    cfg = cfg or {'target': DEFAULT_FLOAT_TARGET}
    if salary:
        return _wizard_prompt_with_income(month, index, total, running, fx, cfg, plan, float(salary))
    topup = topup_needed(running.get(CHECKING, 0), cfg['target'])
    lines = ['\U0001F4C5 *Step %d of %d — %s*' % (index, total, month_name(month)), '',
             '*Starting from:*',
             _balance_block(running, fx, target=cfg['target']), '']

    goals = goal_lines(plan or {}, running) if plan else []
    if goals:
        lines.append('*Still to go:*')
        lines.extend(goals)
        lines.append('')
    if topup:
        lines.append('%s Refill checking first: *%s*' % (CHECKING_EMOJI, money(topup, 'ILS')))
        lines.append('')
    if cfg.get('keren_self'):
        lines.append('%s Then קרן השתלמות לעצמאיים: *%s* _(fixed, before the split)_'
                     % (KEREN_SELF_EMOJI, money(cfg['keren_self'], 'ILS')))
        lines.append('')
    lines.append('How should the rest of this month’s pay be split?')
    lines.append('_Buttons are 🛟emergency/🎯future/💶EUR (קרן כספית)/📈stocks percentages._')
    return '\n'.join(lines)


def _wizard_prompt_with_income(month, index, total, running, fx, cfg, plan, salary):
    bd = payment_breakdown(salary, {b: 0 for b in BUCKETS}, running.get(CHECKING, 0), dict(cfg))
    lines = ['\U0001F4C5 *Step %d of %d — %s*' % (index, total, month_name(month)), '',
             '*Starting from:*', _balance_block(running, fx, target=cfg['target']), '']
    goals = goal_lines(plan or {}, running) if plan else []
    if goals:
        lines += ['*Still to go:*'] + goals + ['']
    lines.append('\U0001F4BC *Expected income: %s*' % money(salary, 'ILS'))
    if bd['refill']:
        lines.append('   %s %s: -%s' % (CHECKING_EMOJI, 'Expected spending (stays in the עו"ש)' if cfg.get('planned_spend')
                                       else 'Refill checking', money(bd['refill'], 'ILS')))
    if bd['excess']:
        lines.append('   %s Unused expense budget → future expenses: -%s' % (BUCKET_EMOJI['ILS_FUTURE'], money(bd['excess'], 'ILS')))
    if bd.get('keren_self'):
        lines.append('   %s קרן השתלמות לעצמאיים: -%s' % (KEREN_SELF_EMOJI, money(bd['keren_self'], 'ILS')))
    lines.append('   \U0001F4B5 *Left to split: %s*' % money(bd['base'], 'ILS'))
    need = float(cfg.get('future_need') or 0)
    if need:
        lines.append('   \U0001F5D3 /futureexpenses need *%s/month* in 🎯 future expenses' % money(need, 'ILS'))
    if bd['base'] > 0:
        lines += ['', '*What each button invests (₪):*']
        for triple in PRESETS:
            parts = ['%s%s' % (BUCKET_EMOJI[b], format(round(bd['base'] * p / 100), ',')) for b, p in zip(BUCKETS, triple) if p]
            spare = bd['base'] * (100 - sum(triple)) / 100
            future = bd['base'] * triple[BUCKETS.index('ILS_FUTURE')] / 100 + bd['excess']
            lines.append('`%s` %s%s%s' % (preset_label(triple), ' '.join(parts),
                                          (' · 💸%s' % format(round(spare), ',')) if spare >= 1 else '',
                                          ' ⚠️' if need and future < need else ''))
        if need:
            lines.append('_⚠️ = 🎯 below what your future expenses need_')
    else:
        lines.append('⚠️ The income does not cover the refill — nothing left to invest this month.')
    lines += ['', 'How should it be split?',
              '_Buttons are 🛟emergency/🎯future/💶EUR (קרן כספית)/📈stocks percentages; 💸 = stays unallocated._']
    return '\n'.join(lines)


def format_month_done(step, fx, plan=None):
    """What that month does, shown right after it is chosen."""
    lines = ['✅ *%s* — %s' % (month_name(step['month']), _alloc_line(step['alloc']))]

    if step.get('topup'):
        lines.append('   %s Checking +%s → *%s*' % (
            CHECKING_EMOJI, money(step['topup'], 'ILS'), money(step['checking_filled'], 'ILS')))
    if step.get('excess'):
        lines.append('   %s Unused expense budget → future expenses: *%s*' % (
            BUCKET_EMOJI['ILS_FUTURE'], money(step['excess'], 'ILS')))
    if step.get('short'):
        lines.append('   ⚠️ Pay does not cover the refill - nothing left to save.')
    if step.get('keren_self'):
        lines.append('   %s קרן השתלמות לעצמאיים: *+%s*' % (KEREN_SELF_EMOJI, money(step['keren_self'], 'ILS')))
    lines.append('   \U0001F4B5 Left to split: *%s*' % money(step.get('base', 0), 'ILS'))
    if step.get('fee'):
        lines.append('   \U0001F3E6 Bank transfer fee: *-%s*' % money(step['fee'], 'ILS'))

    for bucket in BUCKETS:
        added = step['added_native'][bucket]
        if abs(added) < 0.005:
            continue
        ccy = BUCKET_CCY[bucket]
        ils = (step.get('split_ils') or {}).get(bucket)
        if bucket == 'EUR' and 'eur_fund' in step:
            lines.append('   %s +%s → %s *%s*  _(EUR savings ≈ %s)_' % (
                BUCKET_EMOJI[bucket], money(ils or 0, 'ILS'), EUR_FUND_LABEL,
                money(step['eur_fund'], 'ILS'), money(step['balances'][bucket], 'EUR')))
            continue
        lines.append('   %s +%s%s → *%s*' % (
            BUCKET_EMOJI[bucket], money(added, ccy),
            (' (%s)' % money(ils, 'ILS')) if ccy != 'ILS' and ils else '', money(step['balances'][bucket], ccy)))
    lines.append('   \U0001F4B0 Savings total: *%s*' % money(step['total_ils'], 'ILS'))
    need = float((plan or {}).get('future_need') or 0)
    if need:
        got = float((step.get('split_ils') or {}).get('ILS_FUTURE') or 0)
        lines.append('   \U0001F5D3 Future expenses: %s %s of the %s/month they need' % (
            '✅' if got >= need else '⚠️', money(got, 'ILS'), money(need, 'ILS')))

    for line in goal_lines(plan or {}, step['balances']) if plan else []:
        lines.append(line)
    return '\n'.join(lines)


def format_summary(plan, balances, fx, months):
    """Final view: month by month, then today vs the end, in value and percent."""
    steps = project_timeline(plan, balances, fx, months)
    if not steps:
        return '\n'.join(['\U0001F4C8 *YOUR PLAN*', '━' * 20, '',
                          '_Nothing planned - every month was skipped._'])

    # Count planned months, not the horizon: skipped months are not in the plan.
    lines = ['\U0001F4C8 *YOUR %d-MONTH PLAN*' % len(steps), '━' * 20, '']

    cfg = float_config(plan)
    lines.append('*Month by month:*')
    for step in steps:
        refill = ('  %s%s' % (CHECKING_EMOJI, money(step['topup'], 'ILS'))
                  if step.get('topup') else '')
        lines.append('`%s`  %s%s' % (step['month'], _alloc_line(step['alloc']), refill))
        lines.append('    → %s' % money(step['total_ils'], 'ILS'))
    lines.append('')

    total_fees = round(sum(s.get('fee', 0) for s in steps), 2)
    if total_fees:
        lines.append('\U0001F3E6 Bank transfer fees over the period: *-%s*  '
                     '_(%s x %d deposits)_' % (
                         money(total_fees, 'ILS'), money(ILS_TRANSFER_FEE, 'ILS'),
                         sum(1 for s in steps if s.get('fee'))))
        lines.append('')

    total_refill = sum(s.get('topup', 0) for s in steps)
    if total_refill:
        lines.append('%s Into checking over the period: *%s* '
                     '(kept at %s for living costs)' % (
                         CHECKING_EMOJI, money(total_refill, 'ILS'),
                         money(cfg['target'], 'ILS')))
        lines.append('')

    end = steps[-1]['balances']
    lines.append('*Today → after %d months:*' % len(steps))
    for bucket in BUCKETS:
        ccy = BUCKET_CCY[bucket]
        start = float(balances.get(bucket, 0) or 0)
        finish = end[bucket]
        delta = finish - start
        pct = (delta / start * 100) if start else None
        pct_text = ('  _(%+.1f%%)_' % pct) if pct is not None else ''
        lines.append('%s *%s*' % (BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket]))
        lines.append('   %s → *%s*' % (money(start, ccy), money(finish, ccy)))
        lines.append('   %s%s' % (('+' if delta >= 0 else '') + money(delta, ccy), pct_text))
        if bucket == 'EUR':
            lines.append('   %s %s: %s → *%s*' % (EUR_FUND_EMOJI, EUR_FUND_LABEL, money(balances.get(EUR_FUND, 0) or 0, 'ILS'),
                                                money(steps[-1]['eur_fund'], 'ILS')))
    lines.append('')

    start_total = sum(to_ils(balances.get(b, 0), BUCKET_CCY[b], fx) for b in BUCKETS)
    end_total = steps[-1]['total_ils']
    delta_total = end_total - start_total
    pct_total = (delta_total / start_total * 100) if start_total else 0
    lines.append('\U0001F4B0 *Total: %s → %s*' % (
        money(start_total, 'ILS'), money(end_total, 'ILS')))
    lines.append('   *+%s*  _(%+.1f%%)_' % (money(delta_total, 'ILS'), pct_total))

    ending = goal_lines(plan, end)
    if ending:
        lines.append('')
        lines.append('\U0001F3AF *Goals after %d months:*' % len(steps))
        lines.extend(ending)

    target = plan.get('target') or {}
    if target.get('amount'):
        target_ils = target_in_ils(plan, fx)
        credit = inflation_credit(plan, end)
        gap = target_ils - end_total - credit
        lines.append('')
        if target.get('amount_nominal'):
            lines.append('\U0001F4C8 _Target %s in today\'s money = %s with inflation (/inflation)_' % (
                money(target['amount'], 'ILS'), money(target_ils, 'ILS')))
        if credit:
            lines.append('\U0001F3E6 _The ILS bank fund tracks the CPI: +%s of inflation growth counted_' % money(credit, 'ILS'))
        if gap > 0:
            lines.append('\U0001F3AF Target %s — *%s short* (%.0f%% there)' % (
                money(target_ils, 'ILS'), money(gap, 'ILS'), (end_total + credit) / target_ils * 100))
        else:
            lines.append('\U0001F3AF Target %s — *cleared by %s*' % (
                money(target_ils, 'ILS'), money(-gap, 'ILS')))

    lines.append('')
    lines.append('_Contributions only - no market rise or fall assumed._')
    lines.append('_Rates: $1=%s  €1=%s_' % (
        money(fx.get('USDILS', 0), 'ILS'), money(fx.get('EURILS', 0), 'ILS')))
    return '\n'.join(lines)


# --------------------------------------------------------------------------- current situation
# /plan used to show four bucket balances and a projection, which left most of
# what the bot now tracks out of the picture: physical cash, a Visa charge
# already committed, the locked study fund, measured spending, fees paid, goal
# pace, purchase goals and a running trip. The snapshot is assembled by the
# caller -- this module stays free of the ledger modules -- and reported here.


def situation_totals(snap, fx):
    """Spendable, savings, locked and net worth from one snapshot.

    Returned rather than printed so the header totals and the blocks below them
    cannot drift apart on the arithmetic.
    """
    checking = float(snap.get('checking', 0) or 0)
    cash = float(snap.get('cash', 0) or 0)
    pending = float(snap.get('pending_visa', 0) or 0)

    savings_ils = (float(snap.get('emergency', 0) or 0)
                   + float(snap.get('future', 0) or 0)
                   + to_ils(float(snap.get('eur_bank', 0) or 0)
                            + float(snap.get('eur_cash', 0) or 0), 'EUR', fx)
                   + float(snap.get('eur_fund', 0) or 0)
                   + to_ils(float(snap.get('usd_holdings', 0) or 0)
                            + float(snap.get('usd_free', 0) or 0), 'USD', fx))
    spendable = round(checking + cash, 2)
    locked = float((snap.get('keren') or {}).get('balance', 0) or 0)
    liquid = round(spendable + savings_ils, 2)
    return {
        'spendable': spendable,
        'available': round(spendable - pending, 2),
        'pending': pending,
        'savings': round(savings_ils, 2),
        'liquid': liquid,
        'locked': round(locked, 2),
        'net_worth': round(liquid + locked, 2),
    }


def _situation_spendable(snap, plan, tot):
    cfg = float_config(plan)
    lines = [u'\U0001F4B3 *SPENDABLE NOW*']
    lines.append(u'   Checking: *%s*  _(‏עו"ש)_'
                 % money(snap.get('checking', 0), 'ILS'))
    if snap.get('cash'):
        lines.append(u'   Cash on hand: *%s*' % money(snap.get('cash', 0), 'ILS'))

    if tot['pending'] > 0:
        when = snap.get('visa_charge_date')
        label = (u' on %s' % when.strftime('%d/%m')) if when else u''
        lines.append(u'   ➖ Visa pending%s: *%s*'
                     % (label, money(tot['pending'], 'ILS')))
        flag = u'  ⚠️ *not covered*' if tot['available'] < 0 else u''
        lines.append(u'   = After the charge: *%s*%s'
                     % (money(tot['available'], 'ILS'), flag))

    short = topup_needed(tot['available'], cfg['target'])
    if short:
        lines.append(u'   \U0001F3AF Float target %s → *%s* to refill'
                     % (money(cfg['target'], 'ILS'), money(short, 'ILS')))
    else:
        lines.append(u'   \U0001F3AF Float target %s — _at target_'
                     % money(cfg['target'], 'ILS'))
    return lines


def _situation_savings(snap, fx, tot):
    lines = [u'\U0001F3E6 *SAVINGS*']
    for bucket in ('ILS_EMERGENCY', 'ILS_FUTURE'):
        key = 'emergency' if bucket == 'ILS_EMERGENCY' else 'future'
        lines.append(u'   %s %s: *%s*' % (BUCKET_EMOJI[bucket], BUCKET_LABEL[bucket],
                                          money(snap.get(key, 0), 'ILS')))

    eur_bank = float(snap.get('eur_bank', 0) or 0)
    eur_cash = float(snap.get('eur_cash', 0) or 0)
    eur_line = u'   %s %s: *%s*' % (BUCKET_EMOJI['EUR'], BUCKET_LABEL['EUR'],
                                    money(eur_bank + eur_cash, 'EUR'))
    if eur_bank and eur_cash:
        eur_line += u'  _(bank %s + cash %s)_' % (money(eur_bank, 'EUR'),
                                                  money(eur_cash, 'EUR'))
    lines.append(eur_line)
    lines.append(u'      _= %s at %.3f_' % (
        money(to_ils(eur_bank + eur_cash, 'EUR', fx), 'ILS'), fx.get('EURILS', 0)))
    eur_fund = float(snap.get('eur_fund', 0) or 0)
    if eur_fund:
        lines.append(u'   %s %s: *%s*  _(≈ %s, for euros)_' % (
            EUR_FUND_EMOJI, EUR_FUND_LABEL, money(eur_fund, 'ILS'), money(from_ils(eur_fund, 'EUR', fx), 'EUR')))

    holdings = float(snap.get('usd_holdings', 0) or 0)
    free = float(snap.get('usd_free', 0) or 0)
    lines.append(u'   %s %s: *%s*' % (BUCKET_EMOJI['USD_STOCKS'],
                                      BUCKET_LABEL['USD_STOCKS'],
                                      money(holdings + free, 'USD')))
    detail = u'      _holdings %s' % money(holdings, 'USD')
    pl = snap.get('usd_pl')
    if pl is not None:
        detail += u' (%s%s)' % (u'+' if pl >= 0 else u'-', money(abs(pl), 'USD'))
    detail += u' + cash %s_' % money(free, 'USD')
    lines.append(detail)
    lines.append(u'      _= %s at %.3f_' % (
        money(to_ils(holdings + free, 'USD', fx), 'ILS'), fx.get('USDILS', 0)))

    lines.append(u'   \U0001F4B0 Savings total: *%s*' % money(tot['savings'], 'ILS'))
    return lines


def _situation_locked(snap):
    keren = snap.get('keren') or {}
    balance = float(keren.get('balance', 0) or 0)
    if not balance:
        return []
    lines = [u'\U0001F512 *LOCKED* — ‏קרן השתלמות']
    monthly = float(keren.get('monthly', 0) or 0)
    line = u'   Balance: *%s*' % money(balance, 'ILS')
    if monthly:
        line += u'  _(+%s/mo)_' % money(monthly, 'ILS')
    lines.append(line)
    unlock = keren.get('unlock')
    left = keren.get('months_left') or 0
    if unlock:
        tail = u'  _(%d months)_' % left if left else u''
        lines.append(u'   Unlocks %s%s' % (unlock, tail))
        if monthly and left:
            lines.append(u'   At this pace: *%s* by then'
                         % money(balance + monthly * left, 'ILS'))
    return lines


def _situation_networth(tot):
    lines = [u'\U0001F4CA *NET WORTH*']
    lines.append(u'   Spendable + savings: *%s*' % money(tot['liquid'], 'ILS'))
    if tot['locked']:
        lines.append(u'   + locked: *%s*' % money(tot['locked'], 'ILS'))
        lines.append(u'   *Total: %s*' % money(tot['net_worth'], 'ILS'))
    return lines


def _situation_spending(snap, plan):
    cfg = float_config(plan)
    lines = [u'\U0001F9FE *SPENDING*']
    month = snap.get('spend_month_key') or ''
    count = int(snap.get('spend_count', 0) or 0)
    lines.append(u'   This month%s: *%s*%s' % (
        (u' (%s)' % month) if month else u'',
        money(snap.get('spend_month', 0), 'ILS'),
        u'  _%d entries_' % count if count else u''))

    pred = snap.get('spend_predict') or {}
    if pred.get('months'):
        lines.append(u'   Average of %d past month%s: *%s*' % (
            pred['months'], u'' if pred['months'] == 1 else u's',
            money(pred.get('average', 0), 'ILS')))
        if pred.get('months', 0) >= 3:
            trend = pred.get('trend', 0) or 0
            lines.append(u'   Last 3 months: *%s*  _(trend %s%s)_' % (
                money(pred.get('recent_average', 0), 'ILS'),
                u'+' if trend >= 0 else u'-', money(abs(trend), 'ILS')))

        # The float target is only as good as the spend figure behind it. If
        # measured spending has drifted from the planned assumption the whole
        # projection is off, so say so rather than projecting quietly.
        measured = pred.get('recent_average') or pred.get('average') or 0
        assumed = cfg['monthly_spend']
        if cfg.get('mode') == FLOAT_AUTO:
            # Automatic: it already follows last month's real spending.
            lines.append(u'   💳 עו"ש target: *%s* — automatic (%s)'
                         % (money(cfg['target'], 'ILS'), float_basis_text(cfg)))
        elif measured and assumed:
            gap = measured - assumed
            if abs(gap) >= max(100.0, assumed * 0.15):
                buffer_ils = cfg['target'] - assumed
                lines.append(u'   ⚠️ Plan assumes *%s*/mo, you spend *%s*'
                             % (money(assumed, 'ILS'), money(measured, 'ILS')))
                lines.append(u'      _a matching float would be %s — /setplan_'
                             % money(round(measured + buffer_ils, 2), 'ILS'))
            else:
                lines.append(u'   ✅ Matches the planned %s/mo'
                             % money(assumed, 'ILS'))
    else:
        lines.append(u'   _Not enough history yet for an average._')

    fees = snap.get('fees') or {}
    if fees.get('total'):
        line = u'   \U0001F3E6 Bank transfer fees: *%s*' % money(fees['total'], 'ILS')
        if fees.get('count'):
            line += u'  _(%d transfers)_' % fees['count']
        lines.append(line)
        if fees.get('month'):
            lines.append(u'      _%s this month_' % money(fees['month'], 'ILS'))
    return lines


def _situation_goals(plan, balances, fx):
    goals = dict((k, v) for k, v in goals_of(plan).items() if v)
    if not goals:
        return [u'\U0001F3AF *GOALS*',
                u'   _None set — /setplan asks for them._']

    lines = [u'\U0001F3AF *GOALS*']
    for bucket in GOAL_BUCKETS:
        goal = goals.get(bucket)
        if not goal:
            continue
        ccy = BUCKET_CCY[bucket]
        current = float(balances.get(bucket, 0) or 0)
        prog = goal_progress(goal, current)
        lines.append(u'   %s %s: *%.1f%%*' % (BUCKET_EMOJI[bucket],
                                              BUCKET_LABEL[bucket], prog['pct']))
        if prog['remaining'] <= 0:
            lines.append(u'      ✅ _reached — %s of %s_'
                         % (money(current, ccy), money(goal, ccy)))
            continue
        lines.append(u'      _%s of %s — %s left_' % (
            money(current, ccy), money(goal, ccy), money(prog['remaining'], ccy)))
        eta = months_until(plan, balances, fx, bucket, goal)
        if eta:
            lines.append(u'      ⏳ ~%d month%s at the planned pace'
                         % (eta, u'' if eta == 1 else u's'))
        else:
            lines.append(u'      ⚠️ _the plan never gets there — '
                         u'raise this bucket’s share_')
    return lines


def _situation_purchases(snap, balances, plan, fx):
    rows = snap.get('purchases') or []
    if not rows:
        return []
    fund = float(balances.get('ILS_FUTURE', 0) or 0)
    lines = [u'\U0001F6CD *PURCHASE GOALS*  _(future-expenses fund)_']
    for row in rows:
        cost = float(row.get('cost', 0) or 0)
        name = row.get('name', 'item')
        if fund >= cost > 0:
            lines.append(u'   ✅ *%s* — %s, affordable now'
                         % (name, money(cost, 'ILS')))
            continue
        gap = money(round(cost - fund, 2), 'ILS')
        eta = months_until(plan, balances, fx, 'ILS_FUTURE', cost)
        if eta:
            lines.append(u'   ⏳ *%s* — %s, %s short, ~%d month%s'
                         % (name, money(cost, 'ILS'), gap, eta,
                            u'' if eta == 1 else u's'))
        else:
            lines.append(u'   ⚠️ *%s* — %s, %s short, _not on this plan_'
                         % (name, money(cost, 'ILS'), gap))
    return lines


def _situation_trip(snap):
    trip = snap.get('trip')
    if not trip:
        return []
    lines = [u'✈️ *TRIP — %s*' % trip.get('name', '')]
    if trip.get('spent_ils'):
        lines.append(u'   Spent so far: *%s*' % money(trip['spent_ils'], 'ILS'))
    if trip.get('cash_left'):
        lines.append(u'   %s cash left: *%s*'
                     % (trip.get('currency', ''), format(trip['cash_left'], ',.2f')))
    if trip.get('eur_left') is not None:
        lines.append(u'   EUR bank: *%s*' % money(trip['eur_left'], 'EUR'))
    if trip.get('days_left') is not None:
        lines.append(u'   _%d day(s) to go_' % trip['days_left'])
    return lines


def format_situation(snap, plan, balances, fx):
    """Everything true right now, before the projection says what comes next."""
    tot = situation_totals(snap, fx)
    blocks = [
        _situation_spendable(snap, plan, tot),
        _situation_savings(snap, fx, tot),
        _situation_locked(snap),
        _situation_networth(tot),
        _situation_spending(snap, plan),
        _situation_goals(plan, balances, fx),
        _situation_purchases(snap, balances, plan, fx),
        _situation_trip(snap),
    ]
    return u'\n\n'.join(u'\n'.join(b) for b in blocks if b)
