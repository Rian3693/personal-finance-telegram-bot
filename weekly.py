"""The week in US stocks: only what you held all week, day by day.

Built from portfolio_log, the snapshot the bot writes after every US close (each
stock's shares and price). The week is measured on the shares held from the last
close before Monday to now -- a stock sold or bought during the week is left out
(and listed apart), and of a position that was added to only the shares held all
week count. So a sale does not look like a loss, nor a purchase like a gain, and
each day is the same basket at that day's prices. Today can be added live.
"""

from datetime import date, timedelta

HEB_DAYS = ['שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'ראשון']


def week_start(today):
    """Monday of this week (on the weekend: of the week that just ended)."""
    return today - timedelta(days=today.weekday())


def _day(entry):
    try:
        return date.fromisoformat(str(entry.get('date'))[:10])
    except ValueError:
        return None


def _stocks(entry):
    """{symbol: (shares, price)} of one snapshot."""
    return {s['symbol']: (float(s.get('shares') or 0), float(s.get('price') or 0))
            for s in (entry or {}).get('stocks') or []}


def week(log, today):
    """{'monday', 'base': {sym: (shares, price)}, 'days': [{'date', 'stocks', 'moves'}]} -- None if nothing logged."""
    monday = week_start(today)
    dated = [(d, e) for d, e in ((_day(e), e) for e in log or []) if d]
    before = [e for d, e in dated if d < monday]
    days = [e for d, e in dated if monday <= d <= today]
    if not days and not before:
        return None
    if before:
        base = _stocks(before[-1])
    else:                                   # no close before Monday: Monday's previous close
        base = {s['symbol']: (float(s.get('shares') or 0), float(s.get('prev_close') or s.get('price') or 0))
                for s in days[0].get('stocks') or []}
    return {'monday': monday, 'base': base,
            'days': [{'date': _day(e), 'stocks': _stocks(e), 'moves': e.get('movements') or []} for e in days]}


def held(w, live=None):
    """{symbol: shares held all week} and the trades left out: [(symbol, shares before, shares now)]."""
    end = live['stocks'] if live else (w['days'][-1]['stocks'] if w['days'] else w['base'])
    kept, left_out = {}, []
    for sym in sorted(set(w['base']) | set(end)):
        before = w['base'].get(sym, (0.0, 0.0))[0]
        now = end.get(sym, (0.0, 0.0))[0]
        both = min(before, now)
        if both > 0:
            kept[sym] = both
        if abs(before - now) > 1e-9:
            left_out.append((sym, before, now))
    return kept, left_out


def _value(kept, prices, fallback):
    """The kept shares at these prices (a stock missing that day keeps its last price)."""
    total = 0.0
    for sym, shares in kept.items():
        price = (prices.get(sym) or (0.0, 0.0))[1] or fallback.get(sym, 0.0)
        total += shares * price
        if price:
            fallback[sym] = price
    return total


def series(w, live=None):
    """(start value, [(date, value, change, % change)], live row or None) for the kept shares."""
    kept, _ = held(w, live)
    last_price = {sym: p for sym, (_, p) in w['base'].items()}
    start = _value(kept, w['base'], dict(last_price))
    rows, prev = [], start
    for d in w['days']:
        value = _value(kept, d['stocks'], last_price)
        rows.append((d['date'], value, value - prev, (value / prev - 1) * 100 if prev else 0.0))
        prev = value
    live_row = None
    if live:
        value = _value(kept, live['stocks'], last_price)
        live_row = (value, value - prev, (value / prev - 1) * 100 if prev else 0.0)
    return start, rows, live_row


def movers(w, live=None):
    """[(symbol, $ change on the shares held all week, % change)] since the start, biggest first."""
    kept, _ = held(w, live)
    end = live['stocks'] if live else (w['days'][-1]['stocks'] if w['days'] else w['base'])
    out = []
    for sym, shares in kept.items():
        base, now = w['base'][sym][1], end.get(sym, (0, 0))[1]
        if base and now:
            out.append((sym, shares * (now - base), (now / base - 1) * 100))
    return sorted(out, key=lambda m: -abs(m[1]))


def _usd(amount, sign=False):
    amount = round(float(amount), 2)
    text = '${:,.2f}'.format(abs(amount))
    if sign:
        return ('+' if amount >= 0 else '-') + text
    return ('-' if amount < 0 else '') + text


def _ils(amount, rate, sign=False):
    amount = float(amount) * rate
    text = '₪{:,.0f}'.format(abs(amount))
    return (('+' if amount >= 0 else '-') + text) if sign else text


def format_week(w, usd_ils=None, live=None, today=None, auto=False):
    """Markdown: the start value, every day, today live, the trades left out, and the result."""
    today = today or date.today()
    friday = w['monday'] + timedelta(days=4)
    start, rows, live_row = series(w, live)
    _, left_out = held(w, live)
    lines = ['📅 *הרווח/הפסד השבועי — מניות ארה"ב*',
             '_%s – %s%s · רק מניות שהחזקת כל השבוע_' % (w['monday'].strftime('%d/%m'), min(today, friday).strftime('%d/%m'),
                                                         ' · סיכום סוף שבוע' if auto else ''), '',
             '🏁 שווי בתחילת השבוע (סגירה אחרונה לפני שני): *%s*' % _usd(start), '']
    for d, value, change, pct in rows:
        lines.append('%s *%s %s* — %s (%+.2f%%) → %s' % ('🟢' if change >= 0 else '🔴', HEB_DAYS[d.weekday()],
                                                       d.strftime('%d/%m'), _usd(change, True), pct, _usd(value)))
    if live_row:
        value, change, pct = live_row
        lines.append('%s *היום %s (חי, עד עכשיו)* — %s (%+.2f%%) → %s' % (
            '🟢' if change >= 0 else '🔴', today.strftime('%d/%m'), _usd(change, True), pct, _usd(value)))
    if not rows and not live_row:
        lines.append('_אין עדיין ימי מסחר השבוע._')
    end = live_row[0] if live_row else (rows[-1][1] if rows else start)
    total = end - start
    pct = (end / start - 1) * 100 if start else 0.0

    mv = movers(w, live)
    if mv:
        lines += ['', '*הכי זזו השבוע:*']
        for symbol, usd, p in mv[:5]:
            lines.append('• %s %s — %s (%+.1f%%)' % ('🟢' if usd >= 0 else '🔴', symbol, _usd(usd, True), p))
    if left_out:
        trades = {}
        for d in w['days']:
            for m in d['moves']:
                trades.setdefault(m.get('symbol'), []).append(m)
        lines += ['', '📤 *לא נכללו — נקנו/נמכרו השבוע:*']
        for sym, before, now in left_out:
            what = ('נמכרו %g' % (before - now)) if now < before else ('נקנו %g' % (now - before))
            detail = ' · '.join('%s @ $%.2f = %s' % ('מכירה' if m.get('type') == 'SELL' else 'קנייה',
                                                     float(m.get('price') or 0), _usd(m.get('total') or 0))
                                for m in trades.get(sym, []))
            lines.append('• %s — %s מניות%s' % (sym, what, (' (%s)' % detail) if detail else ''))

    word = 'רווח' if total >= 0 else 'הפסד'
    lines += ['', '━' * 16,
              '%s *סיכום השבוע: %s של %s (%+.2f%%)*' % ('📈' if total >= 0 else '📉', word, _usd(abs(total)), pct)]
    if usd_ils:
        lines.append('🇮🇱 *%s בשקלים: %s* _(לפי $1 = ₪%.3f)_' % (word, _ils(abs(total), usd_ils), usd_ils))
    lines.append('💼 %s → %s' % (_usd(start), _usd(end)))
    return '\n'.join(lines)
