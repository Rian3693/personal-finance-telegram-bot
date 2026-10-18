"""A record of shekels sent to and taken back from Interactive Brokers (/ibkr).

Documentation only: an entry here does not touch the עו"ש or any balance. It
keeps the date, the amount in ₪ and an optional note, so the net amount moved
to Interactive can always be read back.
"""

import json
import os
import re
from datetime import date, datetime, timedelta

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ibkr_transfers.json')
DEPOSIT, WITHDRAW = 'deposit', 'withdraw'
KIND = {DEPOSIT: ('➕', 'הפקדה ל-Interactive'), WITHDRAW: ('➖', 'משיכה מ-Interactive')}


def load():
    if not os.path.exists(FILE):
        return []
    with open(FILE, encoding='utf-8') as fh:
        return json.load(fh)


def save(entries):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(entries, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)


def add(kind, amount, day, note='', now=None):
    """Record one transfer; returns the entry."""
    if kind not in KIND:
        raise ValueError(kind)
    entries = load()
    entry = {'date': day.isoformat(), 'kind': kind, 'amount_ils': round(float(amount), 2),
             'note': note or '', 'recorded': (now or datetime.now()).strftime('%Y-%m-%d %H:%M')}
    entries.append(entry)
    save(entries)
    return entry


def parse_amount(text):
    """'5000' or '5,000 first deposit' -> (amount, note)."""
    raw = (text or '').replace('₪', ' ').strip()
    found = re.match(r'^\s*(\d[\d,]*(?:\.\d+)?)\s*(.*)$', raw)
    if not found:
        raise ValueError('שלח סכום בשקלים, למשל 5000 (אפשר להוסיף הערה אחריו)')
    amount = float(found.group(1).replace(',', ''))
    if amount <= 0:
        raise ValueError('הסכום חייב להיות חיובי')
    return amount, found.group(2).strip()


def parse_date(text, today):
    """'היום', 'אתמול', '6/10', '06/10/26', '06/10/2026' or '2026-10-06'. No future dates."""
    raw = (text or '').strip().lower()
    if raw in ('היום', 'today'):
        return today
    if raw in ('אתמול', 'yesterday'):
        return today - timedelta(days=1)
    try:
        found = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})', raw)
        if found:
            day = date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
        else:
            found = re.fullmatch(r'(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?', raw)
            if not found:
                raise ValueError
            year = found.group(3)
            year = today.year if not year else (2000 + int(year) if len(year) == 2 else int(year))
            day = date(year, int(found.group(2)), int(found.group(1)))
    except ValueError:
        raise ValueError('תאריך לא מובן — שלח למשל 6/10 או 06/10/2026')
    if day > today:
        raise ValueError('התאריך בעתיד')
    return day


def totals(entries):
    dep = round(sum(e['amount_ils'] for e in entries if e['kind'] == DEPOSIT), 2)
    wd = round(sum(e['amount_ils'] for e in entries if e['kind'] == WITHDRAW), 2)
    return {'deposited': dep, 'withdrawn': wd, 'net': round(dep - wd, 2)}


def _money(amount):
    return ('-' if amount < 0 else '') + '₪{:,.2f}'.format(abs(amount))


def _safe(text):
    return re.sub(r'[*_`\[\]]', '', text)


def format_log(entries, limit=20):
    t = totals(entries)
    lines = ['🌐 *יומן Interactive Brokers (₪)*',
             'הופקד: *%s* · נמשך: *%s* · נטו: *%s*' % (_money(t['deposited']), _money(t['withdrawn']), _money(t['net'])),
             '─' * 18]
    if not entries:
        return '\n'.join(lines + ['', '_אין עדיין העברות. לחץ על הפקדה או משיכה למטה._'])
    # Sorted by the transfer's date (then by when it was recorded), running net alongside.
    ordered = sorted(entries, key=lambda e: (e['date'], e.get('recorded', '')))
    running, rows = 0.0, []
    for e in ordered:
        running += e['amount_ils'] if e['kind'] == DEPOSIT else -e['amount_ils']
        rows.append((e, round(running, 2)))
    shown = rows if limit is None else rows[-limit:]
    for e, net in reversed(shown):
        emoji, name = KIND[e['kind']]
        y, m, d = e['date'].split('-')
        lines += ['', '%s *%s* · %s/%s/%s' % (emoji, name, d, m, y),
                  '   %s%s  ·  נטו אחרי: %s' % ('+' if e['kind'] == DEPOSIT else '-', _money(e['amount_ils']), _money(net))]
        if e.get('note'):
            lines.append('   📝 %s' % _safe(e['note']))
    if len(shown) < len(rows):
        lines += ['', '_מוצגות %d מתוך %d · /ibkr all — הכול_' % (len(shown), len(rows))]
    lines += ['', '_רישום בלבד — העו"ש לא משתנה._']
    return '\n'.join(lines)
