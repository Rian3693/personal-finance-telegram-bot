"""What the salary has to be for the plan's goals to be met.

The plan splits each month's pay by fixed percentages and projects where every
bucket ends up. Run that projection backwards and you get a salary: the smallest
monthly pay at which each goal -- the total target and every bucket goal -- is
reached by the end of the planned period.

Everything the plan knows is net, because that is what lands in the bank. A job
is negotiated in gross, so the gross figure comes from an Israeli tax model. It
is an ESTIMATE: pay slips carry deductions this model cannot see. One real
number from a pay slip (`/salarytogoal gross <amount>`) calibrates it, after
which the estimate is scaled to match what the user actually takes home.

Tax parameters are the 2026 figures: income tax brackets and credit-point value
from the Tax Authority schedule, insurance rates and thresholds from the
National Insurance Institute (btl.gov.il, in force from 1 January 2026).
"""

import json
import os
from datetime import datetime

import savings_planner as sp

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'salary_goal.json')

TAX_YEAR = 2026

# Monthly income tax brackets: (upper limit, rate). The last band is 47% plus
# the 3% surtax on high incomes.
BRACKETS = ((7010.0, 0.10), (10060.0, 0.14), (19000.0, 0.20), (25100.0, 0.31),
            (46690.0, 0.35), (60130.0, 0.47), (float('inf'), 0.50))
CREDIT_POINT = 242.0                      # NIS per point per month
PENSION_CREDIT_RATE = 0.35                # credit on the employee's pension deposit

# National insurance + health tax, employee side. Reduced rate up to 60% of the
# average wage, full rate above it, nothing above the ceiling.
NI_THRESHOLD = 7703.0
NI_CEILING = 51910.0
NI_LOW = 0.0104 + 0.0323
NI_HIGH = 0.07 + 0.0517

DEFAULTS = {
    'points': 2.25,        # every resident; +0.5 for women, more for children
    'pension': 0.06,       # employee pension deposit, share of gross
    'keren': 0.0,          # employee study-fund deposit, share of gross
    'gross_now': None,     # calibration: the real current gross ...
    'net_now': None,       # ... and the net it produced
    # What the headline salary is computed against. 'auto' uses the total target
    # when the plan has one, which is what "the goal" means in practice; 'all'
    # demands every bucket goal too. At a fixed split a small bucket share makes
    # its goal enormously expensive in salary terms (a €11,000 goal fed by 5% of
    # pay needs a far larger salary than the whole target does), so 'all' can
    # return a number that says more about the split than about the goal.
    'basis': 'auto',
}

# A salary this close to the goal counts as having met it. Pay never lands on the
# exact shekel the model asked for, so demanding equality would make "reached"
# unattainable.
TOLERANCE = 50.0

REACHED, ABOVE, BELOW = 'reached', 'above', 'below'
STATUS_EMOJI = {REACHED: '✅', ABOVE: '\U0001F7E2', BELOW: '\U0001F534'}
STATUS_LABEL = {REACHED: 'reached the goal', ABOVE: 'above the goal',
                BELOW: 'below the goal'}

TARGET_KEY = 'TARGET'


def money(amount):
    return sp.money(amount, 'ILS')


def _signed(amount):
    return ('+' if amount >= 0 else '-') + money(abs(amount))


# --------------------------------------------------------------------------- gross <-> net

def income_tax(gross, points, pension):
    tax, floor = 0.0, 0.0
    for ceiling, rate in BRACKETS:
        if gross > floor:
            tax += (min(gross, ceiling) - floor) * rate
        floor = ceiling
    credits = points * CREDIT_POINT + PENSION_CREDIT_RATE * pension * gross
    return max(0.0, tax - credits)


def insurance(gross):
    low = min(gross, NI_THRESHOLD)
    high = max(0.0, min(gross, NI_CEILING) - NI_THRESHOLD)
    return low * NI_LOW + high * NI_HIGH


def _model_net(gross, cfg):
    gross = max(0.0, float(gross))
    return (gross - income_tax(gross, cfg['points'], cfg['pension'])
            - insurance(gross) - gross * cfg['pension'] - gross * cfg['keren'])


def calibration(cfg):
    """How far the real pay slip sits from the model, as a multiplier on net."""
    gross, net = cfg.get('gross_now'), cfg.get('net_now')
    if gross and net:
        model = _model_net(gross, cfg)
        if model > 0:
            return float(net) / model
    return 1.0


def net_from_gross(gross, cfg=None):
    cfg = merged(cfg)
    return round(_model_net(gross, cfg) * calibration(cfg), 2)


def gross_from_net(net, cfg=None):
    """Invert the model. Take-home rises with gross at every income level, so a
    plain bisection is exact enough."""
    cfg = merged(cfg)
    net = float(net)
    if net <= 0:
        return 0.0
    lo, hi = net, max(net * 4, 20000.0)
    while net_from_gross(hi, cfg) < net and hi < 5e6:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        if net_from_gross(mid, cfg) < net:
            lo = mid
        else:
            hi = mid
    return round(hi, 2)


def merged(cfg):
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    return out


# --------------------------------------------------------------------------- the goals, run backwards

def _specs(plan, fx):
    """Every end-of-period condition the plan sets, each with a test on the
    projected final state."""
    specs = []
    target = plan.get('target') or {}
    if target.get('amount'):
        goal = sp.target_in_ils(plan, fx)          # inflation-adjusted when /inflation is on
        # The ILS bank fund grows with the CPI by itself, so that growth counts too.
        specs.append({'key': TARGET_KEY, 'label': 'Total target', 'emoji': '\U0001F3AF',
                      'goal': goal, 'ccy': 'ILS',
                      'value': lambda end: end['total_ils'] + sp.inflation_credit(plan, end['balances'])})
    for bucket, goal in sp.goals_of(plan).items():
        if goal:
            specs.append({'key': bucket, 'label': sp.BUCKET_LABEL[bucket],
                          'emoji': sp.BUCKET_EMOJI[bucket], 'goal': goal,
                          'ccy': sp.BUCKET_CCY[bucket],
                          'value': (lambda end, b=bucket: end['balances'][b])})
    return specs


def _end_state(plan, balances, fx, months, net):
    trial = dict(plan)
    trial['salary'] = {'amount': float(net), 'currency': 'ILS'}
    # The question is one salary for every month: /setplan's per-month incomes would
    # otherwise override the salary being tried, and every trial would look the same.
    trial.pop('month_income', None)
    steps = sp.project_timeline(trial, balances, fx, months)
    return steps[-1] if steps else None


def _need(plan, balances, fx, months, spec):
    """Smallest net salary at which this one goal is met, or None if no salary
    gets there at the current split (its share of pay is zero)."""
    def met(net):
        end = _end_state(plan, balances, fx, months, net)
        return end is not None and spec['value'](end) >= spec['goal'] - 0.005

    if met(0.0):
        return 0.0
    hi = max(1000.0, float((plan.get('salary') or {}).get('amount') or 0))
    while not met(hi):
        hi *= 2
        if hi > 5e6:
            return None
    lo = 0.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if met(mid):
            hi = mid
        else:
            lo = mid
    # Whole shekels, rounded up so the figure given really does clear the goal.
    need = float(int(hi) + (0 if hi == int(hi) else 1))
    return need if met(need) else need + 1.0


def compute(plan, balances, fx, cfg=None, from_month=None):
    """The salary the plan needs, per goal and overall. None when there is
    nothing to compute against (no planned months, or no goals at all)."""
    cfg = merged(cfg)
    months = [m for m in sorted(plan.get('months') or {}) if plan['months'][m]]
    if from_month:
        months = [m for m in months if m >= from_month]
    specs = _specs(plan, fx)
    if not months or not specs:
        return None

    current_net = float((plan.get('salary') or {}).get('amount') or 0)
    now_end = _end_state(plan, balances, fx, months, current_net)

    goals = []
    for spec in specs:
        need = _need(plan, balances, fx, months, spec)
        projected = spec['value'](now_end) if now_end else 0.0
        goals.append({
            'key': spec['key'], 'label': spec['label'], 'emoji': spec['emoji'],
            'goal': spec['goal'], 'ccy': spec['ccy'],
            'projected': projected,
            'short': round(max(0.0, spec['goal'] - projected), 2),
            'need_net': need,
            'need_gross': gross_from_net(need, cfg) if need is not None else None,
        })

    use_target = (cfg.get('basis', 'auto') == 'auto'
                  and any(g['key'] == TARGET_KEY for g in goals))
    for goal in goals:
        goal['headline'] = (goal['key'] == TARGET_KEY) if use_target else True
    counted = [g for g in goals if g['headline'] and g['need_net'] is not None]
    binding = max(counted, key=lambda g: g['need_net']) if counted else None
    need_net = binding['need_net'] if binding else None

    if cfg.get('gross_now') and cfg.get('net_now'):
        gross_now = float(cfg['gross_now'])
    else:
        gross_now = gross_from_net(current_net, cfg) if current_net else 0.0

    return {
        'months': months, 'from': months[0], 'to': months[-1], 'count': len(months),
        'current_net': current_net, 'current_gross': gross_now,
        'goals': goals, 'binding': binding['key'] if binding else None,
        'need_net': need_net,
        'need_gross': gross_from_net(need_net, cfg) if need_net is not None else None,
        'unreachable': [g['key'] for g in goals if g['need_net'] is None],
        'basis': 'target' if use_target else 'all',
        'calibrated': bool(cfg.get('gross_now') and cfg.get('net_now')),
        'computed_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        # The target as entered (today's money) when /inflation has grown it.
        'target_real': ((plan.get('target') or {}).get('amount')
                        if (plan.get('target') or {}).get('amount_nominal') else None),
    }


# --------------------------------------------------------------------------- state: month goals + log

def load_state(path=None):
    path = path or STATE_FILE
    state = {'config': dict(DEFAULTS), 'months': {}, 'log': []}
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            stored = json.load(fh) or {}
        state['config'] = merged(stored.get('config'))
        state['months'] = stored.get('months') or {}
        state['log'] = stored.get('log') or []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return state


def save_state(state, path=None):
    path = path or STATE_FILE
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)


def remember_month_goal(state, month, result):
    """Pin the figure announced on the 1st, so the payment is judged against
    what the user was told rather than against a number that has since moved."""
    if not result or result.get('need_net') is None:
        return None
    state['months'][month] = {
        'net': result['need_net'], 'gross': result['need_gross'],
        'binding': result['binding'], 'set_on': result['computed_at'],
        'source': 'reminder',
    }
    return state['months'][month]


def judge(paid, goal_net, tolerance=TOLERANCE):
    diff = round(float(paid) - float(goal_net), 2)
    if abs(diff) <= tolerance:
        return REACHED, diff
    return (ABOVE if diff > 0 else BELOW), diff


def record_payment(state, month, paid, fallback=None, cfg=None):
    """Compare a received payment with that month's salary goal and log it.

    The goal is the one announced on the 1st when there is one; otherwise the
    caller's freshly computed `fallback` is used and the entry says so. Returns
    the log entry, or None when there is no goal to compare against (no goals
    set in the plan) -- in which case nothing is logged rather than inventing a
    verdict.
    """
    cfg = merged(cfg or state.get('config'))
    goal = state['months'].get(month)
    source = 'announced'
    if not goal and fallback and fallback.get('need_net') is not None:
        goal = {'net': fallback['need_net'], 'gross': fallback['need_gross'],
                'binding': fallback['binding']}
        source = 'computed at payment'
    if not goal:
        return None

    # A month can be paid in more than one go (salary, then a bonus). The goal is
    # for the month, so the verdict is on what has arrived so far this month, not
    # on each transfer against the whole figure.
    prior = round(sum(float(e.get('paid_net', 0) or 0) for e in state['log']
                      if e.get('month') == month), 2)
    total = round(prior + float(paid), 2)
    status, diff = judge(total, goal['net'])
    entry = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'month': month,
        'paid_net': round(float(paid), 2),
        'month_total': total,
        'paid_gross_est': gross_from_net(total, cfg),
        'goal_net': goal['net'], 'goal_gross': goal.get('gross'),
        'diff': diff,
        'diff_pct': round(diff / goal['net'] * 100, 1) if goal['net'] else 0.0,
        'status': status, 'binding': goal.get('binding'), 'source': source,
    }
    state['log'].append(entry)
    return entry


def drop_payment(state, month, paid, stamp=None):
    """Take a replaced payment out of the log, so the month total stops counting it.

    Entries carry the /payment stamp they belong to ('payment'); older ones do
    not, and are matched by month and amount instead. The newest match goes.
    Returns the removed entry, or None.
    """
    log = state['log']
    for index in range(len(log) - 1, -1, -1):
        entry = log[index]
        if entry.get('month') != month:
            continue
        if entry.get('payment'):
            match = entry['payment'] == stamp
        else:
            match = abs(float(entry.get('paid_net', 0) or 0) - float(paid)) < 0.01
        if match:
            return log.pop(index)
    return None


# --------------------------------------------------------------------------- messages

def _goal_name(goal):
    return '%s %s' % (goal['emoji'], goal['label'])


def _goal_amount(goal):
    return sp.money(goal['goal'], goal['ccy'])


def _calibration_note(result):
    if result.get('calibrated'):
        return '_Gross estimate calibrated to your real pay slip._'
    return ('_Gross is an estimate (Israeli %d tax model). For a tighter figure send '
            'your current gross: /salarytogoal gross 8200_' % TAX_YEAR)


def format_block(result):
    """The compact version written onto /plan."""
    if not result:
        return ''
    lines = ['\U0001F4BC *SALARY NEEDED FOR YOUR GOALS*',
             '_%s by %s (%d months)_' % (_basis_text(result), result['to'],
                                         result['count'])]
    if result['need_net'] is None:
        lines.append('   ⚠️ _No salary reaches them at this split._')
    else:
        delta = result['need_net'] - result['current_net']
        pct = (delta / result['current_net'] * 100) if result['current_net'] else None
        lines.append('   Net: *%s* / month  _(now %s, %s%s)_' % (
            money(result['need_net']), money(result['current_net']), _signed(delta),
            (' · %+.1f%%' % pct) if pct is not None else ''))
        lines.append('   Gross: *≈ %s*  _(now ≈ %s)_' % (
            money(result['need_gross']), money(result['current_gross'])))
        binding = next((g for g in result['goals'] if g['key'] == result['binding']), None)
        if binding and result['basis'] == 'all' and len(result['goals']) > 1:
            lines.append('   Decided by: %s' % _goal_name(binding))
    others = [g for g in result['goals'] if not g['headline']]
    for goal in others:
        lines.append(_other_goal_line(goal, result))
    return '\n'.join(lines)


def _basis_text(result):
    if result['basis'] == 'target':
        goal = next((g for g in result['goals'] if g['key'] == TARGET_KEY), None)
        text = 'to reach your %s target' % (_goal_amount(goal) if goal else '')
        if result.get('target_real'):
            # No underscores: the caller already sets this whole line in italics.
            text += ' (%s in today\'s money + inflation)' % sp.money(result['target_real'], 'ILS')
        return text
    return 'to hit every goal'


def _other_goal_line(goal, result):
    """A bucket goal that is NOT what the headline is computed against: what it
    alone would cost, so a lopsided split is visible instead of hidden."""
    if goal['need_net'] is None:
        return '   %s %s — _unreachable: 0%% of pay goes to it_' % (
            goal['emoji'], _goal_amount(goal))
    line = '   %s %s alone: net %s · gross ≈ %s' % (
        goal['emoji'], _goal_amount(goal),
        money(goal['need_net']), money(goal['need_gross']))
    if result['need_net'] and goal['need_net'] > result['need_net'] * 1.5:
        line += '  ⚠️ _its share of pay is small_'
    return line


def format_report(result):
    """The full /salarytogoal answer."""
    if not result:
        return ('\U0001F4BC *SALARY TO GOAL*\n\n_Nothing to calculate: the plan needs '
                'planned months and at least one goal or a target. Use /setplan, '
                '/plantarget._')
    lines = ['\U0001F4BC *SALARY TO GOAL*', '━' * 20, '',
             '_What you need to earn each month, from %s to %s (%d months), %s._'
             % (result['from'], result['to'], result['count'], _basis_text(result)), '']
    if result['need_net'] is None:
        lines.append('⚠️ No salary reaches it at the current split.')
    else:
        delta = result['need_net'] - result['current_net']
        lines.append('\U0001F4B0 *Net per month:* *%s*' % money(result['need_net']))
        lines.append('\U0001F4C4 *Gross per month:* *≈ %s*' % money(result['need_gross']))
        lines.append('')
        if delta > 0:
            pct = (delta / result['current_net'] * 100) if result['current_net'] else 0
            lines.append('Now: net %s (gross ≈ %s)' % (
                money(result['current_net']), money(result['current_gross'])))
            lines.append('\U0001F4C8 You need *%s* more net (%+.1f%%)' % (money(delta), pct))
        else:
            lines.append('Now: net %s (gross ≈ %s)' % (
                money(result['current_net']), money(result['current_gross'])))
            lines.append('✅ Your current pay already covers it, with %s to spare.'
                         % money(-delta))

    lines += ['', '*Goal by goal:*']
    for goal in result['goals']:
        lines.append('%s *%s*' % (_goal_name(goal), _goal_amount(goal)))
        if goal['short'] > 0:
            lines.append('   At your current pay you end %s short.'
                         % sp.money(goal['short'], goal['ccy']))
        else:
            lines.append('   Already covered at your current pay.')
        if goal['need_net'] is None:
            lines.append('   ⚠️ _Unreachable: this goal gets 0%% of pay in the '
                         'plan._')
        else:
            tag = ('  ⬅️ _the headline_' if goal['key'] == result['binding']
                   else ('' if goal['headline'] else '  _(not in the headline)_'))
            lines.append('   Needs net %s · gross ≈ %s%s' % (
                money(goal['need_net']), money(goal['need_gross']), tag))
            if (not goal['headline'] and result['need_net']
                    and goal['need_net'] > result['need_net'] * 1.5):
                lines.append('   ⚠️ _Its share of your pay is small, so only a much '
                             'bigger salary would fund it. Raising its % in /setplan costs '
                             'far less than raising your pay._')
    if result['basis'] == 'target':
        lines += ['', '_The headline covers the total target. To demand every bucket '
                  'goal as well: /salarytogoal basis all_']
    else:
        lines += ['', '_The headline demands every goal. For the total target only: '
                  '/salarytogoal basis target_']
    lines += ['', '_Same split every month as in /plan, contributions only, no market '
              'growth. Net is what lands in the bank._', _calibration_note(result)]
    return '\n'.join(lines)


def format_reminder(month, result, current_net):
    """The 1st-of-month nudge: what this month's pay has to be."""
    if not result or result['need_net'] is None:
        return ''
    lines = ['\U0001F4BC *SALARY GOAL — %s*' % month, '',
             'To stay on track for your goals by %s you need:' % result['to'], '',
             '\U0001F4B0 Net: *%s*' % money(result['need_net']),
             '\U0001F4C4 Gross: *≈ %s*' % money(result['need_gross'])]
    if current_net:
        delta = result['need_net'] - current_net
        word = 'above' if delta > 0 else 'below'
        lines.append('\U0001F4CA %s %s your usual %s' % (
            money(abs(delta)), word, money(current_net)))
    binding = next((g for g in result['goals'] if g['key'] == result['binding']), None)
    if binding:
        lines.append('\U0001F3AF Goal: %s %s' % (binding['label'], _goal_amount(binding)))
    lines += ['', '_Log your pay with /payment and I\'ll tell you how it compares._']
    return '\n'.join(lines)


def format_verdict(entry):
    """Shown straight after /payment."""
    emoji = STATUS_EMOJI[entry['status']]
    lines = ['%s *Salary goal for %s: %s*' % (emoji, entry['month'],
                                              STATUS_LABEL[entry['status']]), '']
    total = entry.get('month_total', entry['paid_net'])
    if abs(total - entry['paid_net']) > 0.005:
        lines.append('Received now: *%s*' % money(entry['paid_net']))
        lines.append('This month so far: *%s*  _(gross ≈ %s)_' % (
            money(total), money(entry['paid_gross_est'])))
    else:
        lines.append('Received: *%s*  _(gross ≈ %s)_' % (
            money(entry['paid_net']), money(entry['paid_gross_est'])))
    lines.append('Goal: *%s*  _(gross ≈ %s)_' % (
        money(entry['goal_net']), money(entry['goal_gross'] or 0)))
    if entry['status'] == REACHED:
        lines.append('Difference: %s' % _signed(entry['diff']))
    else:
        lines.append('Difference: *%s*  _(%+.1f%%)_' % (_signed(entry['diff']),
                                                         entry['diff_pct']))
    if entry['source'] != 'announced':
        lines.append('_The goal was calculated now: no 1st-of-month figure was saved._')
    return '\n'.join(lines)


def format_log(state, limit=12):
    log = state.get('log') or []
    if not log:
        return ('\U0001F4D2 *SALARY GOAL LOG*\n\n_Empty. Each time you log a payment with '
                '/payment it is compared with that month\'s goal and recorded here._')

    # One verdict per month: when a month was paid in several parts, only its last
    # entry (the running total) counts, or one month would be tallied twice.
    last_of_month = {}
    for entry in log:
        last_of_month[entry['month']] = entry
    log = sorted(last_of_month.values(), key=lambda e: e['month'])
    recent = log[-limit:]
    counts = {s: sum(1 for e in log if e['status'] == s) for s in (REACHED, ABOVE, BELOW)}
    lines = ['\U0001F4D2 *SALARY GOAL LOG*', '─' * 18, '',
             '%s %d reached  %s %d above  %s %d below  _(%d months)_' % (
                 STATUS_EMOJI[REACHED], counts[REACHED], STATUS_EMOJI[ABOVE],
                 counts[ABOVE], STATUS_EMOJI[BELOW], counts[BELOW], len(log)),
             '\U0001F4CA Net result vs goals: *%s*' % _signed(
                 round(sum(e['diff'] for e in log), 2)), '']
    for entry in reversed(recent):
        lines.append('%s `%s`  %s vs goal %s' % (
            STATUS_EMOJI[entry['status']], entry['month'],
            money(entry.get('month_total', entry['paid_net'])), money(entry['goal_net'])))
        lines.append('      %s%s' % (STATUS_LABEL[entry['status']],
                                     '' if entry['status'] == REACHED
                                     else ' by %s' % money(abs(entry['diff']))))
    if len(log) > limit:
        lines.append('')
        lines.append('_Showing the latest %d of %d._' % (limit, len(log)))
    return '\n'.join(lines)


# --------------------------------------------------------------------------- what if the pay changes

WHATIF_STEPS = (-20, -15, -10, -5, 0, 5, 10, 15, 20)


def what_if(plan, balances, fx, cfg=None, steps=WHATIF_STEPS, base_net=None):
    """Where the period ends if the monthly pay were `steps` percent different
    from `base_net` (the current pay unless given).

    A preview only: it runs the same projection as /plan with a different salary
    and changes nothing. Same split, same float, same fees; contributions only.
    Each row's 'vs_now' is measured against the base pay's own ending.
    """
    cfg = merged(cfg)
    months = [m for m in sorted(plan.get('months') or {}) if plan['months'][m]]
    current = float((plan.get('salary') or {}).get('amount') or 0)
    base = float(base_net) if base_net is not None else current
    if not months or base <= 0 or (base_net is None and current <= 0):
        return None
    specs = _specs(plan, fx)
    now_end = _end_state(plan, balances, fx, months, base)
    start_total = sum(sp.to_ils(balances.get(b, 0), sp.BUCKET_CCY[b], fx) for b in sp.BUCKETS)

    rows = []
    for step in steps:
        net = round(base * (1 + step / 100.0), 2)
        end = _end_state(plan, balances, fx, months, net)
        goals = []
        for spec in specs:
            value = spec['value'](end)
            goals.append({'key': spec['key'], 'emoji': spec['emoji'], 'label': spec['label'], 'ccy': spec['ccy'],
                          'goal': spec['goal'], 'value': value, 'gap': round(spec['goal'] - value, 2),
                          'met': value >= spec['goal'] - 0.005})
        rows.append({
            'step': step, 'net': net, 'gross': gross_from_net(net, cfg),
            'end_total': round(end['total_ils'], 2),
            'vs_now': round(end['total_ils'] - now_end['total_ils'], 2),
            'gain': round(end['total_ils'] - start_total, 2),
            'goals': goals, 'target': next((g for g in goals if g['key'] == TARGET_KEY), None),
            # each pot at the end, in its own currency
            'buckets': {b: round(float(end['balances'][b]), 2) for b in sp.BUCKETS},
        })
    # Where the target is actually reached, which the fixed steps may not show at all.
    target_spec = next((s for s in specs if s['key'] == TARGET_KEY), None)
    target_need = _need(plan, balances, fx, months, target_spec) if target_spec else None
    return {'months': months, 'from': months[0], 'to': months[-1], 'count': len(months),
            'current_net': current, 'base_net': base, 'start_total': round(start_total, 2), 'rows': rows,
            'start_buckets': {b: round(float(balances.get(b, 0) or 0), 2) for b in sp.BUCKETS},
            'target_need_net': target_need,
            'target_need_pct': ((target_need / current - 1) * 100
                                if target_need is not None and current > 0 else None),
            'target_need_gross': gross_from_net(target_need, cfg) if target_need else None}


# --------------------------------------------------------------------------- "what if I earn X"

def earn(plan, balances, fx, net, months, cfg=None):
    """Earning `net` a month over `months`: what goes into each pot every month
    (by the plan's split), where each pot and the total end, and each goal's
    share -- the same projection /plan runs, nothing saved."""
    cfg = merged(cfg)
    months = [m for m in months if (plan.get('months') or {}).get(m)]
    net = float(net)
    if not months or net <= 0:
        return None
    trial = dict(plan)
    trial['salary'] = {'amount': net, 'currency': 'ILS'}
    trial.pop('month_income', None)          # "if I earn X" means X every month
    # By payday the עו"ש is spent down to (target - monthly spend), as /showplan
    # assumes -- so the first month is not skewed by today's balance.
    float_cfg = sp.float_config(plan)
    balances = dict(balances)
    balances[sp.CHECKING] = round(float_cfg['target'] - float_cfg['monthly_spend'], 2)
    steps = sp.project_timeline(trial, balances, fx, months)
    if not steps:
        return None
    end = steps[-1]
    current = float((plan.get('salary') or {}).get('amount') or 0)
    now_end = _end_state(plan, balances, fx, months, current) if current > 0 else None
    goals = []
    for spec in _specs(plan, fx):
        value = spec['value'](end)
        goals.append({'key': spec['key'], 'emoji': spec['emoji'], 'label': spec['label'], 'ccy': spec['ccy'],
                      'goal': spec['goal'], 'value': value, 'gap': round(spec['goal'] - value, 2),
                      'pct': value / spec['goal'] * 100 if spec['goal'] else 0.0,
                      'met': value >= spec['goal'] - 0.005})
    start_total = sum(sp.to_ils(balances.get(b, 0), sp.BUCKET_CCY[b], fx) for b in sp.BUCKETS)
    return {'net': net, 'gross': gross_from_net(net, cfg), 'current_net': current,
            'months': months, 'from': months[0], 'to': months[-1], 'count': len(months),
            'steps': steps, 'end': end, 'goals': goals,
            'start': {b: float(balances.get(b, 0) or 0) for b in sp.BUCKETS},
            'start_total': round(start_total, 2), 'end_total': round(end['total_ils'], 2),
            'vs_now': round(end['total_ils'] - now_end['total_ils'], 2) if now_end else None,
            'target_real': ((plan.get('target') or {}).get('amount')
                            if (plan.get('target') or {}).get('amount_nominal') else None)}


def _mmyy(key):
    return '%s/%s' % (key[5:7], key[2:4])


def _deposit_line(step):
    return ' · '.join('%s %s' % (sp.BUCKET_EMOJI[b], sp.money(step['added_native'][b], sp.BUCKET_CCY[b]))
                      for b in sp.BUCKETS if step['added_native'].get(b))


def format_earn(r):
    if not r:
        return '❌ אין חודשים מתוכננים קדימה — בנה תוכנית עם /setplan.'
    lines = ['\U0001F4AD *אם תרוויח %s נטו בחודש*  _(≈ %s ברוטו)_' % (money(r['net']), money(r['gross']))]
    if r['current_net']:
        d = r['net'] - r['current_net']
        lines.append('_עכשיו %s · %s%s (%+.1f%%)_' % (money(r['current_net']), '+' if d >= 0 else '-',
                                                    money(abs(d)), d / r['current_net'] * 100))
    lines += ['_%s – %s (%d חודשים), לפי החלוקה בתוכנית_' % (sp.heb_month(r['from']), sp.heb_month(r['to']), r['count']),
              '━' * 20, '', '\U0001F4C5 *כמה נכנס לכל דבר, כל חודש:*']
    # Consecutive months that deposit the same amounts are shown once.
    groups = []
    for step in r['steps']:
        line = _deposit_line(step)
        if groups and groups[-1][2] == line:
            groups[-1][1] = step['month']
            groups[-1][3] += 1
        else:
            groups.append([step['month'], step['month'], line, 1])
    for first, last, line, n in groups:
        when = _mmyy(first) if n == 1 else '%s–%s (×%d)' % (_mmyy(first), _mmyy(last), n)
        lines.append('`%s` %s' % (when, line))

    lines += ['', '\U0001F3C1 *בסוף %s:*' % sp.heb_month(r['to'])]
    goal_of = {g['key']: g for g in r['goals']}
    for b in sp.BUCKETS:
        ccy = sp.BUCKET_CCY[b]
        start, finish = r['start'][b], float(r['end']['balances'][b])
        line = '%s %s: %s → *%s* (+%s)' % (sp.BUCKET_EMOJI[b], sp.HEB_BUCKET[b], sp.money(start, ccy),
                                            sp.money(finish, ccy), sp.money(finish - start, ccy))
        g = goal_of.get(b)
        if g:
            line += '\n      🎯 %s: *%.0f%%*%s' % (sp.money(g['goal'], ccy), g['pct'],
                                                  ' ✅' if g['met'] else ' — חסר %s' % sp.money(g['gap'], ccy))
        lines.append(line)
    gain = r['end_total'] - r['start_total']
    lines += ['', '\U0001F4B0 *סה"כ:* %s → *%s* (+%s · +%.1f%%)' % (
        money(r['start_total']), money(r['end_total']), money(gain), gain / r['start_total'] * 100 if r['start_total'] else 0)]
    if r['vs_now'] is not None and r['current_net']:
        lines.append('   _לעומת המשכורת הנוכחית: %s%s_' % ('+' if r['vs_now'] >= 0 else '-', money(abs(r['vs_now']))))
    t = goal_of.get(TARGET_KEY)
    if t:
        label = ' (%s של היום + אינפלציה)' % money(r['target_real']) if r['target_real'] else ''
        lines.append('\U0001F3AF *יעד כולל %s*%s: *%.1f%%*%s' % (
            money(t['goal']), label, t['pct'],
            ' ✅ מושג (+%s מעל)' % money(-t['gap']) if t['met'] else ' — חסר *%s* (%.1f%%)' % (money(t['gap']), t['gap'] / t['goal'] * 100)))
    lines += ['', '_הפקדות בלבד, בלי תשואה בשוק. החיסכון הבנקאי ₪ צמוד מדד ונספר ביעד._']
    return '\n'.join(lines)


# --------------------------------------------------------------------------- around the pay the goal needs

GOAL_STEPS = (-30, -25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30)


def around_goal(plan, balances, fx, cfg=None, steps=GOAL_STEPS):
    """The pay the goal needs (the /salarytogoal headline), and what happens to the
    goal if the pay lands 5-30% either side of it. A preview: nothing is saved."""
    result = compute(plan, balances, fx, cfg)
    if not result or result['need_net'] is None:
        return {'result': result, 'preview': None}
    if result['need_net'] <= 0:
        return {'result': result, 'preview': None, 'already': True}
    preview = what_if(plan, balances, fx, cfg, steps, base_net=result['need_net'])
    return {'result': result, 'preview': preview}


POTS_LEGEND = ('_\U0001F3E6 ILS bank savings (emergency + future funds) · \U0001F4B6 EUR (bank + cash) '
               '· \U0001F4C8 US stocks (holdings + cash)_')


def _pot(amount, ccy):
    return sp.money(amount, ccy).split('.')[0]


def _pots_line(buckets, goals=None):
    """Where each savings pot stands, with the goal set on it (if any) marked:
    \U0001F3E6 ₪45,914 (\U0001F6DF❌) · \U0001F4B6 €8,790 ❌ · \U0001F4C8 $32,832"""
    marks = {g['key']: ('✅' if g['met'] else '❌') for g in goals or []}
    ils = buckets['ILS_EMERGENCY'] + buckets['ILS_FUTURE']
    # A goal on one fund is judged on that fund alone, so show that fund's own amount
    # beside its mark: the combined figure can pass a goal that the fund itself misses.
    ils_marks = ' '.join('%s %s %s' % (sp.BUCKET_EMOJI[k], _whole(buckets[k]), marks[k])
                         for k in ('ILS_EMERGENCY', 'ILS_FUTURE') if k in marks)
    return ' · '.join([
        '\U0001F3E6 %s%s' % (_whole(ils), (' (%s)' % ils_marks) if ils_marks else ''),
        '\U0001F4B6 %s%s' % (_pot(buckets['EUR'], 'EUR'), (' ' + marks['EUR']) if 'EUR' in marks else ''),
        '\U0001F4C8 %s' % _pot(buckets['USD_STOCKS'], 'USD'),
    ])


def _outcome(goal):
    """'reached, +X over' or 'X short (NN% of it)', in the goal's own currency."""
    ccy = goal['ccy']
    if goal['met']:
        surplus = -goal['gap']
        return '✅ reached' + (', %s over' % sp.money(surplus, ccy).split('.')[0] if surplus >= 1 else '')
    share = goal['value'] / goal['goal'] * 100 if goal['goal'] else 0
    return '❌ %s short (%.0f%% of it)' % (sp.money(goal['gap'], ccy).split('.')[0], share)


def format_around_goal(bundle):
    result = (bundle or {}).get('result')
    title = '\U0001F3AF *THE PAY YOUR GOAL NEEDS*  _(preview)_'
    if not result:
        return title + ('\n\n_Nothing to calculate: the plan needs planned months and a goal or a target. '
                        'Use /setplan, /plantarget._')
    if bundle.get('already'):
        return title + '\n\n✅ Your goals are reached by your savings and the plan as it stands, whatever you earn.'
    w = bundle.get('preview')
    if not w:
        return title + '\n\n⚠️ No salary reaches it at the current split: a goal gets 0% of your pay.'

    binding = next((g for g in result['goals'] if g['key'] == result['binding']), None)
    goal_name = '%s %s' % (binding['label'].lower(), sp.money(binding['goal'], binding['ccy']).split('.')[0]) if binding else 'goals'
    need, gross = result['need_net'], result['need_gross']
    lines = [title,
             '_Preview only — nothing is saved. To reach your %s by %s (%d months), same split as /plan._'
             % (goal_name, w['to'], w['count']), '',
             '\U0001F4B0 Net *%s* / month' % _whole(need),
             '\U0001F4C4 Gross ≈ *%s* / month' % _whole(gross)]
    if w['current_net'] > 0:
        lines.append('_That is %+.1f%% vs your net now (%s)._' % ((need / w['current_net'] - 1) * 100,
                                                                   _whole(w['current_net'])))
    lines += ['', '*Today:* ' + _pots_line(w['start_buckets'])]
    lines += ['', '*If the pay lands 5–30% either side of that:*']
    for row in w['rows']:
        if row['step'] == 0:
            head = '\U0001F3AF *goal pay* · net %s · gross ≈ %s' % (_whole(row['net']), _whole(row['gross']))
        else:
            head = '%s *%+d%%* · net %s · gross ≈ %s' % (
                '\U0001F53A' if row['step'] > 0 else '\U0001F53B', row['step'], _whole(row['net']), _whole(row['gross']))
        lines.append(head)
        key_goal = next((g for g in row['goals'] if binding and g['key'] == binding['key']), None)
        detail = '      ends with *%s*' % _whole(row['end_total'])
        if key_goal:
            detail += ' · ' + _outcome(key_goal)
        lines.append(detail)
        others = [g for g in row['goals'] if not binding or g['key'] != binding['key']]
        lines.append('      ' + _pots_line(row['buckets'], others))
    legend = ' · '.join('%s %s %s' % (g['emoji'], g['label'], sp.money(g['goal'], g['ccy']).split('.')[0])
                             for g in w['rows'][0]['goals'] if not binding or g['key'] != binding['key'])
    lines.append('')
    lines.append(POTS_LEGEND)
    if legend:
        lines.append('_Other goals: %s_' % legend)
    lines.append('_Contributions only, no market growth. Gross is an estimate: /salarytogoal gross <yours> to calibrate._')
    return '\n'.join(lines)


def _whole(amount):
    """Shekels without the agorot: a projection is not accurate to the agora."""
    amount = float(amount or 0)
    return ('-' if amount < 0 else '') + '₪' + format(abs(round(amount)), ',')


def _signed_whole(amount):
    return ('+' if amount >= 0 else '-') + _whole(abs(amount))


def format_what_if(w):
    if not w:
        return ('\U0001F4CA *WHAT IF MY SALARY CHANGES?*\n\n_Nothing to preview: the plan needs a salary '
                '(/salary) and planned months (/setplan)._')
    now = next(r for r in w['rows'] if r['step'] == 0)
    lines = ['\U0001F4CA *WHAT IF MY SALARY CHANGES?*',
             '_Preview only — nothing is saved. Same split as /plan, %d months to %s._' % (w['count'], w['to']),
             '',
             'Today you have *%s*. At your current pay you end with *%s*.' % (_whole(w['start_total']),
                                                                                _whole(now['end_total'])),
             '*Today:* ' + _pots_line(w['start_buckets']),
             '']
    for row in w['rows']:
        if row['step'] == 0:
            head = '▶️ *now* · net %s · gross ≈ %s' % (_whole(row['net']), _whole(row['gross']))
        else:
            head = '%s *%+d%%* · net %s · gross ≈ %s' % (
                '\U0001F53A' if row['step'] > 0 else '\U0001F53B', row['step'], _whole(row['net']), _whole(row['gross']))
        lines.append(head)
        detail = '      ends with *%s*' % _whole(row['end_total'])
        if row['step'] != 0:
            detail += ' (%s vs now)' % _signed_whole(row['vs_now'])
        t = row['target']
        if t:
            detail += ' · ' + ('✅ target reached' if t['met'] else '%s short' % _whole(t['gap']))
        lines.append(detail)
        lines.append('      ' + _pots_line(row['buckets'], [g for g in row['goals'] if g['key'] != TARGET_KEY]))
    if w.get('target_need_net') is not None:
        need, pct_need = w['target_need_net'], w['target_need_pct']
        if pct_need <= 0:
            lines += ['', '🎯 *Your current pay already reaches the target* (it needs net %s, %.1f%% less).'
                      % (_whole(need), abs(pct_need))]
        else:
            beyond = ' — beyond this range' if pct_need > max(WHATIF_STEPS) else ''
            lines += ['', '🎯 *The target needs net %s* (%+.1f%%, gross ≈ %s)%s' % (
                _whole(need), pct_need, _whole(w['target_need_gross']), beyond)]
    legend = ' · '.join('%s %s %s' % (g['emoji'], g['label'], sp.money(g['goal'], g['ccy']))
                             for g in w['rows'][0]['goals'])
    lines += ['', POTS_LEGEND]
    if legend:
        lines.append('_%s_' % legend)
    lines.append('_Contributions only, no market growth. The exact pay needed: /salarytogoal_')
    return '\n'.join(lines)
