"""/taxyear: the year's tax picture so far -- information to check with an accountant.

From the sales log: realised gains and losses this year and the tax already withheld;
the tax shield (losses carried, usable against gains); paper losses in the stocks held
now (they become usable only if sold before 31/12); and how much of the self-employed
keren's yearly ceiling is left. Israel's 25% rate on real capital gains, in dollars here
-- the real calculation is in shekels with inflation adjustments.
"""

from datetime import date

TAX_RATE = 0.25


def summary(portfolio, prices, year):
    sales = [s for s in portfolio.get('sold_history') or [] if str(s.get('sell_date', '')).startswith(str(year))]
    gains = sum(float(s.get('profit_loss') or 0) for s in sales if float(s.get('profit_loss') or 0) > 0)
    losses = sum(float(s.get('profit_loss') or 0) for s in sales if float(s.get('profit_loss') or 0) < 0)
    withheld = sum(float(s.get('tax_withheld') or 0) for s in sales)
    paper = []
    for h in portfolio.get('holdings') or []:
        sym, sh, cost = h['symbol'], float(h.get('shares') or 0), float(h.get('purchase_price') or 0)
        price = prices.get(sym)
        if sh and price and cost and price < cost:
            paper.append((sym, sh * (price - cost)))
    return {'sales': len(sales), 'gains': gains, 'losses': losses, 'net': gains + losses, 'withheld': withheld,
            'shield': float(portfolio.get('tax_shield_balance') or 0), 'paper': sorted(paper, key=lambda p: p[1])}


def _usd(x, sign=False):
    t = '${:,.0f}'.format(abs(x))
    return (('+' if x >= 0 else '-') + t) if sign else (('-' if x < 0 else '') + t)


def format_summary(s, year, today, keren_ytd=None, keren_ceiling=None):
    days_left = (date(year, 12, 31) - today).days
    lines = ['🧾 *סיכום מס %d — עד עכשיו*' % year, '_עוד %d ימים לסוף שנת המס_' % days_left, '',
             '*מימושים השנה (%d מכירות):*' % s['sales'],
             'רווחים %s · הפסדים %s · *נטו %s*' % (_usd(s['gains'], True), _usd(s['losses'], True), _usd(s['net'], True)),
             'מס שכבר נוכה: %s' % _usd(s['withheld']),
             '🛡 מגן מס זמין (הפסדים שנצברו): *%s*' % _usd(s['shield'])]
    if s['net'] > 0:
        lines.append('מס משוער על הרווח הנטו אחרי המגן: ~%s' % _usd(max(0.0, s['net'] - s['shield']) * TAX_RATE))
    if s['paper']:
        total = sum(v for _, v in s['paper'])
        lines += ['', '📉 *הפסדי נייר במניות שאתה מחזיק:* %s' % _usd(total, True)]
        for sym, v in s['paper'][:6]:
            lines.append('• %s %s' % (sym, _usd(v, True)))
        lines.append('_הפסד נייר הופך למגן מס רק אם מוכרים — ומכירה היא החלטה עם השלכות נוספות. לבדוק מול רו"ח._')
    if keren_ytd is not None and keren_ceiling:
        lines += ['', '🔐 *קרן השתלמות לעצמאיים:* הופקד השנה ₪{:,.0f} מתוך תקרה ₪{:,.0f} — נשאר *₪{:,.0f}*'.format(
            keren_ytd, keren_ceiling, max(0.0, keren_ceiling - keren_ytd))]
    lines += ['', '_הערכה בדולרים בלבד: המס בישראל מחושב בשקלים, על רווח ריאלי. רק מידע — לבדוק מול רו"ח._']
    return '\n'.join(lines)
