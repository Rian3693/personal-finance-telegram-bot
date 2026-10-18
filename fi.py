"""/fi and /whatif: the long view and the bad-times view of the savings plan.

/fi -- financial independence: the FI number (yearly spending / 4%: a portfolio you could
live off), how far along you are, and the years to reach it at three REAL (after
inflation) returns, plus what ₪500 a month more would change. Rough by design.

/whatif -- income falls by X% for N months: savings lost, how much the emergency fund
pays for the gap, what is left of it, and how far the goals slip.
"""

import math

SWR = 0.04                      # the yearly withdrawal rate the FI number assumes
REAL_RETURNS = (0.03, 0.05, 0.07)


def fi_number(annual_spend, swr=SWR):
    return annual_spend / swr


def months_to(target, current, monthly, real_rate, cap=1200):
    """Months until current + monthly saving, growing at real_rate a year, reaches target."""
    if current >= target:
        return 0
    if monthly <= 0 and real_rate <= 0:
        return None
    r = (1 + real_rate) ** (1 / 12) - 1
    value = current
    for n in range(1, cap + 1):
        value = value * (1 + r) + monthly
        if value >= target:
            return n
    return None


def _money(x):
    return '₪{:,.0f}'.format(x or 0)


def _years(n):
    if n is None:
        return 'יותר מ-100 שנה'
    return '%.1f שנים' % (n / 12)


def format_fi(annual_spend, spend_basis, current, monthly, saving_basis, current_basis):
    target = fi_number(annual_spend)
    pct = current / target * 100 if target else 0
    lines = ['🏝 *עצמאות כלכלית — כמה רחוק*', '',
             '💸 הוצאה שנתית: *%s* _(%s)_' % (_money(annual_spend), spend_basis),
             '🎯 *המספר שלך: %s* _(הוצאה שנתית ÷ 4%%)_' % _money(target),
             '💼 יש לך היום: *%s* — *%.1f%%* מהדרך _(%s)_' % (_money(current), pct, current_basis),
             '💰 חיסכון חודשי: *%s* _(%s)_' % (_money(monthly), saving_basis), '',
             '*כמה זמן, לפי תשואה ריאלית (אחרי אינפלציה):*']
    for r in REAL_RETURNS:
        lines.append('• %d%% בשנה → *%s*' % (round(r * 100), _years(months_to(target, current, monthly, r))))
    base = months_to(target, current, monthly, 0.05)
    more = months_to(target, current, monthly + 500, 0.05)
    if base and more:
        lines.append('')
        lines.append('➕ עוד ₪500 בחודש מקצרים בערך *%.1f שנים* (בתשואה 5%%)' % ((base - more) / 12))
    lines += ['', '_"4%" = כלל אצבע: תיק בגודל פי 25 מההוצאה השנתית מאפשר למשוך ממנו לאורך זמן. הערכה גסה — '
                  'תשואות לא מובטחות, והמספר משתנה עם ההוצאות שלך._']
    return '\n'.join(lines)


def whatif(salary, spend, keren, emergency, drop_pct, months):
    """Income falls by drop_pct% for `months` months; keren deposits pause."""
    normal_saving = max(0.0, salary - spend - keren)
    income = salary * (1 - drop_pct / 100)
    reduced_saving = max(0.0, income - spend)
    gap = max(0.0, spend - income)                 # paid from the emergency fund
    lost = (normal_saving - reduced_saving) * months
    from_fund = gap * months
    left = emergency - from_fund
    return {'normal_saving': normal_saving, 'income': income, 'reduced_saving': reduced_saving,
            'gap': gap, 'lost': lost, 'from_fund': from_fund, 'fund_left': left,
            'fund_months_left': (left / spend) if spend and left > 0 else 0.0,
            'delay_months': (lost / normal_saving) if normal_saving else None,
            'runs_out_month': (math.ceil(emergency / gap) if gap and emergency < from_fund else None)}


def format_whatif(w, salary, spend, drop_pct, months, emergency):
    lines = ['🌧 *מה אם — ההכנסה יורדת ב-%d%% ל-%d חודשים*' % (round(drop_pct), months), '',
             'הכנסה: %s → *%s* בחודש · הוצאות: %s' % (_money(salary), _money(w['income']), _money(spend)),
             'חיסכון חודשי: %s → *%s*' % (_money(w['normal_saving']), _money(w['reduced_saving']))]
    if w['gap']:
        lines.append('🛟 חסר *%s* בחודש — יוצא מקרן החירום: *%s* בסך הכול' % (_money(w['gap']), _money(w['from_fund'])))
        if w['runs_out_month']:
            lines.append('🔴 *קרן החירום נגמרת בחודש %d* — לפני שהתקופה נגמרת' % w['runs_out_month'])
        else:
            lines.append('🛟 קרן החירום: %s → *%s* (מכסה עוד %.1f חודשים אחר כך)' % (
                _money(emergency), _money(w['fund_left']), w['fund_months_left']))
    else:
        lines.append('🟢 ההכנסה עדיין מכסה את ההוצאות — קרן החירום לא נוגעת')
    lines.append('📉 חיסכון שלא ייכנס: *%s*' % _money(w['lost']))
    if w['delay_months'] is not None:
        lines.append('⏳ היעדים יתעכבו בערך *%.1f חודשים*' % w['delay_months'])
    lines += ['', '_הנחות: ההוצאות לא משתנות, הפקדות קרן ההשתלמות נעצרות, בלי תשואה. אפשר: /whatif 50 6 (ירידה של 50%% ל-6 חודשים)._']
    return '\n'.join(lines)
