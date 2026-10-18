"""/rebalance: what to buy and sell, in how many steps, to bring the US stocks to a chosen
VTI share. The other stocks keep their weights relative to each other. A calculator only.

Each sale's realised gain or loss is estimated from the average cost; the tax line uses
Israel's 25% capital-gains rate on the net gain (losses offset gains). An estimate --
check the real figure with an accountant.
"""

import math

VTI = 'VTI'
TAX_RATE = 0.25


def plan(positions, vti_pct, steps=1, new_money=0.0):
    """positions: {sym: {'shares', 'price', 'cost'}} (cost = average cost per share).
    Returns {'total', 'target', 'moves': {sym: $ change}, 'steps': [[(sym, $, shares)]], 'realised', 'tax'}."""
    value = {s: p['shares'] * p['price'] for s, p in positions.items()}
    total = sum(value.values()) + float(new_money or 0)
    vti_target = total * vti_pct / 100
    others = {s: v for s, v in value.items() if s != VTI}
    others_total = sum(others.values())
    target = {VTI: vti_target}
    for s, v in others.items():
        target[s] = (total - vti_target) * (v / others_total) if others_total else 0.0
    moves = {s: target[s] - value.get(s, 0.0) for s in target}
    steps = max(1, int(steps))
    per_step = []
    for _ in range(steps):
        row = []
        for s, m in sorted(moves.items(), key=lambda kv: kv[1]):
            if abs(m) < 1:
                continue
            usd = m / steps
            price = positions.get(s, {}).get('price') or 0
            row.append((s, usd, usd / price if price else 0.0))
        per_step.append(row)
    realised = {}
    for s, m in moves.items():
        if m < 0 and s in positions:
            shares_sold = -m / positions[s]['price']
            realised[s] = shares_sold * (positions[s]['price'] - positions[s]['cost'])
    net = sum(realised.values())
    return {'total': total, 'value': value, 'target': target, 'moves': moves, 'steps': per_step,
            'realised': realised, 'net_realised': net, 'tax': max(0.0, net) * TAX_RATE}


def _usd(x, sign=False):
    t = '${:,.0f}'.format(abs(x))
    return (('+' if x >= 0 else '-') + t) if sign else (('-' if x < 0 else '') + t)


def format_plan(p, vti_pct, steps, new_money=0.0):
    total = p['total']
    now_vti = p['value'].get(VTI, 0.0) / (total - new_money) * 100 if total - new_money else 0
    lines = ['⚖️ *איזון לתיק: %d%% VTI / %d%% שאר המניות*' % (round(vti_pct), round(100 - vti_pct)),
             '_עכשיו VTI %.0f%% · שווי %s%s_' % (now_vti, _usd(total - new_money),
                                                  (' + כסף חדש %s' % _usd(new_money)) if new_money else ''), '',
             '*היעד לכל מניה:*']
    for s, t in sorted(p['target'].items(), key=lambda kv: -kv[1]):
        m = p['moves'][s]
        lines.append('`%-5s` %s → %s  (%s)' % (s, _usd(p['value'].get(s, 0.0)), _usd(t),
                                               'קנייה ' + _usd(m) if m > 1 else ('מכירה ' + _usd(-m) if m < -1 else 'בלי שינוי')))
    if len(p['steps']) > 1:
        lines += ['', '*בכל אחד מ-%d השלבים:*' % len(p['steps'])]
    else:
        lines += ['', '*הפעולות:*']
    for s, usd, sh in p['steps'][0]:
        lines.append('• %s %s — %s (~%.2f מניות)' % ('🟢 לקנות' if usd > 0 else '🔴 למכור', s, _usd(abs(usd)), abs(sh)))
    if p['realised']:
        lines += ['', '*אם מוכרים — רווח/הפסד ממומש (לפי מחיר קנייה ממוצע):*']
        for s, r in sorted(p['realised'].items(), key=lambda kv: kv[1]):
            lines.append('• %s: %s' % (s, _usd(r, True)))
        lines.append('סה"כ: *%s* · מס משוער (25%% על רווח נטו): *%s*' % (_usd(p['net_realised'], True), _usd(p['tax'])))
        if p['net_realised'] < 0:
            lines.append('_הפסד נטו — אין מס, וההפסד יכול לקזז רווחים עתידיים (מגן מס)._')
    lines += ['', '_מחשבון בלבד — לא המלצה. מס ועמלות: לבדוק מול רו"ח/הברוקר._']
    return '\n'.join(lines)
