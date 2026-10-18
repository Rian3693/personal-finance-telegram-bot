"""The ILS bank savings, one transaction at a time: the balance before, what was
added or taken out, the balance after, and what it was for (/banklog).

The reserves log keeps the bank's balance after each deposit and withdrawal.
Bank -> עו"ש transfers are written from the עו"ש side (their balance_after is the
עו"ש), so for those the bank balance is carried forward from the entry before --
or read from 'bank_after', which newer transfers record. Where one entry's
"before" does not meet the previous entry's "after", the balance was changed
without a log entry, and the log says so rather than hiding it.
"""

import re

import ils_funds as ilf

# Early entries were saved with a broken encoding of the currency signs.
_MOJIBAKE = (('ג‚×', '₪'), ('ג‚¬', '€'), ('d2ac', '₪'))
_FEE = re.compile(r'(?:after ₪|\+ ₪|עמלה ₪)([\d,]+(?:\.\d+)?)')
_KIND = {'deposit': ('➕', 'הפקדה'), 'withdraw': ('➖', 'משיכה'), 'transfer': ('↪️', 'העברה לעו"ש'),
         'pl': ('📈', 'רווח/הפסד בקרן')}
PL_TYPE = 'PL'          # reserves-log type of a fund P/L update: growth, not a deposit


def _clean(text):
    for bad, good in _MOJIBAKE:
        text = text.replace(bad, good)
    return text


def _is_bank(entry):
    if entry.get('currency') != 'ILS':
        return False
    kind = entry.get('type')
    if kind in ('TRANSFER', PL_TYPE):
        return True
    # One early cash deposit was filed as BANK; its own text says Cash.
    return kind in (None, 'BANK') and '(Cash)' not in (entry.get('description') or '')


def _note(entry):
    note = (entry.get('note') or '').strip()
    if note:
        return note
    desc = _clean(entry.get('description') or '')
    found = re.search(r'—\s*(.+)$', desc)
    if not found and entry.get('type') == 'TRANSFER':
        found = re.search(r'\((.+)\)\s*$', desc)
    return found.group(1).strip() if found else ''


def _fee(entry):
    found = _FEE.search(_clean(entry.get('description') or ''))
    return float(found.group(1).replace(',', '')) if found else 0.0


def rows(log):
    """Oldest first: one row per bank transaction."""
    out, running = [], None
    for entry in log or []:
        if not _is_bank(entry):
            continue
        amount = float(entry.get('amount') or 0)
        if entry.get('type') == 'TRANSFER':
            kind, change = 'transfer', -abs(amount)
            if entry.get('bank_after') is not None:
                after = float(entry['bank_after'])
                before = round(after - change, 2)
            elif running is not None:
                before, after = running, round(running + change, 2)
            else:
                before = after = None
        else:
            if entry.get('type') == PL_TYPE:
                kind = 'pl'
            else:
                kind = 'deposit' if amount >= 0 else 'withdraw'
            change = amount
            after = float(entry.get('balance_after') or 0)
            before = round(after - change, 2)
        gap = 0.0
        if running is not None and before is not None and abs(before - running) >= 0.01:
            gap = round(before - running, 2)
        out.append({'date': entry.get('date', ''), 'kind': kind, 'before': before,
                    'change': round(change, 2), 'after': after, 'note': _note(entry),
                    'fee': _fee(entry), 'fund': entry.get('fund'),
                    'from_funds': entry.get('from_funds') or entry.get('funds_change'), 'gap': gap})
        if after is not None:
            running = round(after, 2)
    return out


def _money(amount):
    return ('-' if amount < 0 else '') + '₪{:,.2f}'.format(abs(amount))


def _signed(amount):
    return ('+' if amount >= 0 else '-') + '₪{:,.2f}'.format(abs(amount))


def _safe(text):
    """Notes are free text; keep them from breaking Telegram's Markdown."""
    return re.sub(r'[*_`\[\]]', '', text)


def _when(stamp):
    found = re.match(r'(\d{4})-(\d{2})-(\d{2})(?: (\d{2}:\d{2}))?', stamp or '')
    if not found:
        return stamp or '?'
    y, m, d, hm = found.groups()
    return '%s/%s/%s%s' % (d, m, y[2:], (' ' + hm) if hm else '')


def _fund_text(row):
    if row['fund'] in ilf.FUNDS:
        return ' · %s %s' % (ilf.EMOJI[row['fund']], ilf.LABEL[row['fund']])
    taken = row.get('from_funds') or {}
    show = _signed if row['kind'] == 'pl' else _money
    parts = ['%s %s' % (ilf.EMOJI[f], show(v)) for f, v in taken.items() if f in ilf.FUNDS and v]
    return (' · ' + ' + '.join(parts)) if parts else ''


def format_log(reserves, limit=15):
    all_rows = rows(reserves.get('log'))
    funds = ilf.read(reserves)
    total = float(reserves.get('ILS', 0) or 0)
    lines = ['\U0001F3E6 *יומן חיסכון בנקאי (₪)*',
             'יתרה: *%s*  (%s %s · %s %s)' % (
                 _money(total), ilf.EMOJI[ilf.EMERGENCY], _money(funds[ilf.EMERGENCY]),
                 ilf.EMOJI[ilf.FUTURE], _money(funds[ilf.FUTURE])),
             '─' * 18]
    if not all_rows:
        return '\n'.join(lines + ['', '_אין עדיין תנועות. הפקדה: /addreserve · משיכה: /withdrawreserve_'])

    last = all_rows[-1]['after']
    if last is not None and abs(total - last) >= 0.01:
        lines += ['', '✏️ _היתרה היום שונה מהתנועה האחרונה ב-%s (שינוי שלא נרשם ביומן)._' % _signed(total - last)]

    shown = all_rows if limit is None else all_rows[-limit:]
    pl_total = round(sum(r['change'] for r in all_rows if r['kind'] == 'pl'), 2)
    if pl_total:
        lines.insert(2, '📈 רווח/הפסד שנרשם בקרן: *%s*' % _signed(pl_total))

    for row in reversed(shown):
        emoji, name = _KIND[row['kind']]
        if row['kind'] == 'pl' and row['change'] < 0:
            emoji = '📉'
        lines += ['', '%s *%s* · %s%s' % (emoji, name, _when(row['date']), _fund_text(row))]
        if row['before'] is None:
            lines.append('   %s' % _signed(row['change']))
        else:
            lines.append('   %s → *%s*  (%s)' % (_money(row['before']), _money(row['after']), _signed(row['change'])))
        if row['fee']:
            lines[-1] = lines[-1][:-1] + ', עמלה %s)' % _money(row['fee'])
        if row['note']:
            lines.append('   \U0001F4DD %s' % _safe(row['note']))
        if row['gap']:
            lines.append('   ✏️ _לפני זה: שינוי שלא נרשם ביומן %s_' % _signed(row['gap']))

    lines += ['', '_%d תנועות%s · /banklog all — הכול · /banklog 30 — 30 אחרונות_' % (
        len(all_rows), '' if len(shown) == len(all_rows) else ' (מוצגות %d האחרונות)' % len(shown))]
    return '\n'.join(lines)


# ----------------------------------------------------------------- fund P/L (/bankpl)

def parse_pl(text):
    """What was typed: ('value', 25900.0, note) for the value shown in the app, or
    ('change', +120.0 / -45.0, note) when it carries a sign."""
    raw = (text or '').replace('₪', ' ').replace('−', '-').strip()
    found = re.match(r'^([+-])?\s*(\d[\d,]*(?:\.\d+)?)\s*(.*)$', raw)
    if not found:
        raise ValueError('שלח את השווי באפליקציה (למשל 25900) או שינוי עם סימן (+120 / -45)')
    number = float(found.group(2).replace(',', ''))
    note = found.group(3).strip()
    if found.group(1):
        return 'change', (number if found.group(1) == '+' else -number), note
    if number <= 0:
        raise ValueError('השווי חייב להיות חיובי')
    return 'value', number, note


def pl_change(mode, number, total):
    """The P/L to book: the change itself, or the app's value less the bot's balance."""
    return round(number if mode == 'change' else number - float(total), 2)


def pl_split(reserves, change):
    """Both funds sit in the same fund at the bank, so the P/L is shared by size."""
    funds = ilf.read(reserves)
    whole = funds[ilf.EMERGENCY] + funds[ilf.FUTURE]
    if whole <= 0:
        return {ilf.EMERGENCY: round(change, 2), ilf.FUTURE: 0.0}
    emergency = round(change * funds[ilf.EMERGENCY] / whole, 2)
    return {ilf.EMERGENCY: emergency, ilf.FUTURE: round(change - emergency, 2)}


def last_pl(reserves):
    """The most recent P/L update, or None."""
    for entry in reversed(reserves.get('log') or []):
        if entry.get('currency') == 'ILS' and entry.get('type') == PL_TYPE:
            return entry
    return None


def format_pl_prompt(reserves):
    funds = ilf.read(reserves)
    total = float(reserves.get('ILS', 0) or 0)
    lines = ['📈 *עדכון רווח/הפסד — חיסכון בנקאי (₪)*', '',
             'בבוט עכשיו: *%s*  (%s %s · %s %s)' % (_money(total), ilf.EMOJI[ilf.EMERGENCY], _money(funds[ilf.EMERGENCY]),
                                                  ilf.EMOJI[ilf.FUTURE], _money(funds[ilf.FUTURE]))]
    last = last_pl(reserves)
    if last:
        lines.append('_עדכון קודם: %s %s_' % (_when(last.get('date')), _signed(float(last['amount']))))
    lines += ['', 'שלח את *השווי הנוכחי* כמו שהוא באפליקציה, למשל `25900`',
              '_— ההפרש מהיתרה בבוט יירשם כרווח/הפסד (הכי מדויק, גם אחרי משיכות)._',
              'או את *השינוי* עם סימן: `+120` / `-45`',
              '_אפשר להוסיף הערה אחרי המספר. cancel לביטול._']
    return '\n'.join(lines)


def format_pl_preview(reserves, change, split, note=''):
    total = float(reserves.get('ILS', 0) or 0)
    funds = ilf.read(reserves)
    word = 'רווח' if change >= 0 else 'הפסד'
    lines = ['%s *%s בקרן: %s*' % ('📈' if change >= 0 else '📉', word, _signed(change)), '',
             '🏦 חיסכון בנקאי: %s → *%s*' % (_money(total), _money(total + change))]
    for fund in ilf.FUNDS:
        if split.get(fund):
            lines.append('   %s %s: %s → %s  (%s)' % (ilf.EMOJI[fund], ilf.LABEL[fund], _money(funds[fund]),
                                                     _money(funds[fund] + split[fund]), _signed(split[fund])))
    if note:
        lines.append('📝 %s' % _safe(note))
    lines += ['', '_העו"ש לא משתנה. זה רק עדכון שווי הקרן._']
    return '\n'.join(lines)


def pl_entry(change, split, total_after, note, stamp):
    """The reserves-log entry for a P/L update (shown by /banklog)."""
    word = 'רווח' if change >= 0 else 'הפסד'
    return {'date': stamp, 'currency': 'ILS', 'type': PL_TYPE, 'amount': round(change, 2),
            'description': '%s בקרן %s (עדכון לפי האפליקציה)' % (word, _signed(change)) + (' — %s' % note if note else ''),
            'note': note, 'balance_after': round(total_after, 2),
            'funds_change': {f: v for f, v in split.items() if v}}
