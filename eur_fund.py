"""קרן כספית ליורו -- the EUR savings, held in shekels until the euros are needed.

Buying euros every month leaves them sitting idle while inflation eats their
buying power. So /setplan's 💶 share goes into a shekel money-market fund (קרן
כספית), whose yield is above the Israeli inflation, and is converted to euros
only when they are actually needed. Until then the fund counts toward the EUR
savings goal at today's rate, next to the euros already in the bank app and in
cash.

Only what /allocated records as really bought is added; /eurfund shows the
balance and corrects it (yield, a conversion to euros, a typo).

Stored in my_portfolio.json under "eur_fund" (the bot loads and saves the file):
  {"balance": 0.0, "log": [{"date", "amount", "balance_after", "note"}]}
"""

from datetime import date

KEY = 'eur_fund'
LABEL = 'קרן כספית ליורו'
EMOJI = '\U0001FA99'


def money(amount):
    value = round(float(amount or 0), 2)
    return '%s₪%s' % ('-' if value < 0 else '', format(abs(value), ',.2f'))


def load(data):
    """The fund's state from the portfolio dict (a fresh one if there is none)."""
    state = {'balance': 0.0, 'log': []}
    state.update((data or {}).get(KEY) or {})
    state['log'] = state.get('log') or []
    return state


def balance(data):
    return round(float(load(data).get('balance') or 0), 2)


def _log(state, amount, when, note):
    state['log'].append({'date': (when or date.today()).isoformat(), 'amount': round(float(amount), 2),
                         'balance_after': state['balance'], 'note': note})


def deposit(data, amount, when=None, note=''):
    """Add (or, negative, take out) shekels. Writes into `data`; the caller saves it."""
    state = load(data)
    state['balance'] = round(float(state['balance'] or 0) + float(amount), 2)
    _log(state, amount, when, note)
    data[KEY] = state
    return state


def set_balance(data, amount, when=None, note='עדכון יתרה'):
    """The balance as the bank shows it (e.g. after the fund's yield)."""
    state = load(data)
    diff = round(float(amount) - float(state['balance'] or 0), 2)
    state['balance'] = round(float(amount), 2)
    _log(state, diff, when, note)
    data[KEY] = state
    return state


def format_status(state, eur_bank, eur_cash, eurils, monthly_pct=None):
    fund = float(state.get('balance') or 0)
    in_eur = fund / eurils if eurils else 0.0
    total = eur_bank + eur_cash + in_eur
    lines = ['%s *%s*' % (EMOJI, LABEL),
             '_החלק של 💶 יורו ב-/setplan נקנה בשקלים בקרן כספית (תשואה מעל האינפלציה) ומומר ליורו רק כשצריך._', '',
             'יתרה: *%s*  _(≈ €%s לפי %.3f)_' % (money(fund), format(round(in_eur, 2), ',.2f'), eurils or 0), '',
             '\U0001F4B6 *כל החיסכון ליורו:*',
             '   🏦 יורו באפליקציה: €%s' % format(round(eur_bank, 2), ',.2f'),
             '   💵 יורו מזומן: €%s' % format(round(eur_cash, 2), ',.2f'),
             '   %s קרן כספית: %s (≈ €%s)' % (EMOJI, money(fund), format(round(in_eur, 2), ',.2f')),
             '   = *€%s*' % format(round(total, 2), ',.2f')]
    if monthly_pct:
        lines.append('_בתוכנית: %.0f%% מהחלוקה בכל חודש_' % monthly_pct)
    if state['log']:
        lines += ['', '*אחרונים:*']
        for e in state['log'][-5:][::-1]:
            lines.append('  `%s` %s%s → %s  _%s_' % (e['date'], '+' if e['amount'] >= 0 else '', money(e['amount']),
                                                    money(e['balance_after']), e.get('note') or ''))
    lines += ['', 'עדכון: `/eurfund add 500` · `/eurfund take 500` (המרת ליורו) · `/eurfund set 5230` (היתרה בבנק)']
    return '\n'.join(lines)
