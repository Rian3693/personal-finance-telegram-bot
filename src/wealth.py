"""Savings health: savings rate, emergency months, net-worth snapshots, fees.

- savings rate: of each month's net payment (/payment), how much went to savings --
  what /allocated recorded, or the plan's split while nothing is recorded yet.
- emergency months: the emergency fund divided by your real average spending.
- net worth: one snapshot a month (the /horizons split), kept to see the trend.
- fees: commissions, transfer fees and an estimate of the fund's management fee,
  this year and over the last 12 months.

Settings and snapshots live in wealth.json:
  {"emergency_months": 6, "fund_fee_pct": 0.19, "snapshots": [...]}
"""

import json
import os
from datetime import date, datetime, timedelta

import expenses as ex

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'wealth.json')
STEP_EMOJI = {'ILS_EMERGENCY': '🛟', 'ILS_FUTURE': '🎯', 'EUR': '💶', 'USD_STOCKS': '💵'}
STEP_NAME = {'ILS_EMERGENCY': 'חירום', 'ILS_FUTURE': 'עתידיות', 'EUR': 'יורו', 'USD_STOCKS': 'מניות $'}
HEB_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר',
              'אוקטובר', 'נובמבר', 'דצמבר']


def load():
    try:
        with open(FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    data.setdefault('emergency_months', None)
    data.setdefault('fund_fee_pct', None)
    data.setdefault('snapshots', [])
    return data


def save(data):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, FILE)


def money(amount):
    return ex.money(amount)


def month_label(key):
    return '%s %s' % (HEB_MONTHS[int(key[5:7]) - 1], key[:4])


# ----------------------------------------------------------------------------- savings rate

def savings_rows(plan):
    """One row per month with a payment: received, saved, rate %, where it went."""
    months = {}
    for p in plan.get('payments') or []:
        key = p.get('month')
        if not key:
            continue
        row = months.setdefault(key, {'month': key, 'payment': 0.0, 'saved': 0.0, 'items': {},
                                      'actual': True, 'sources': []})
        row['payment'] += float(p.get('amount') or 0)
        row['sources'] += [s.get('label') for s in p.get('sources') or [] if s.get('label')]
        if p.get('actual'):
            items = {k: float(v.get('ils') or 0) for k, v in p['actual']['items'].items()}
        else:
            items = {k: float(v or 0) for k, v in (p.get('split') or {}).items()}
            row['actual'] = False
        for k, v in items.items():
            row['items'][k] = row['items'].get(k, 0.0) + v
            row['saved'] += v
    rows = []
    for key in sorted(months):
        row = months[key]
        row['payment'], row['saved'] = round(row['payment'], 2), round(row['saved'], 2)
        row['rate'] = round(row['saved'] / row['payment'] * 100, 1) if row['payment'] else 0.0
        rows.append(row)
    return rows


def format_savings_rate(plan, limit=12):
    rows = savings_rows(plan)
    lines = ['💰 *שיעור חיסכון לפי חודש*', '_כמה מכל תשלום נטו הלך לחיסכון (חירום, עתידיות, יורו, מניות)_', '']
    if not rows:
        return '\n'.join(lines + ['_אין עדיין תשלומים. אחרי /payment ו-/allocated זה יתמלא._'])
    prev = None
    for row in rows[-limit:]:
        trend = ''
        if prev is not None:
            d = row['rate'] - prev['rate']
            trend = '  %s%.1f נק׳' % ('▲ +' if d >= 0 else '▼ ', d)
        lines.append('📆 *%s* — *%.1f%%*%s' % (month_label(row['month']), row['rate'], trend))
        lines.append('   תשלום %s · לחיסכון %s%s' % (money(row['payment']), money(row['saved']),
                                                     '' if row['actual'] else ' _(לפי התוכנית — עוד אין /allocated)_'))
        parts = ['%s %s' % (STEP_EMOJI.get(k, '•'), money(v)) for k, v in row['items'].items() if v]
        if parts:
            lines.append('   ' + ' · '.join(parts))
        if row['sources']:
            lines.append('   _מקורות: %s_' % ', '.join(ex_safe(s) for s in row['sources']))
        prev = row
    shown = rows[-limit:]
    if len(shown) > 1:
        total_pay = sum(r['payment'] for r in shown)
        total_saved = sum(r['saved'] for r in shown)
        lines += ['', '📊 ממוצע %d חודשים: *%.1f%%* (%s מתוך %s)' % (
            len(shown), total_saved / total_pay * 100 if total_pay else 0, money(total_saved), money(total_pay))]
    return '\n'.join(lines)


def savings_line(plan):
    """One line for /showplan: the latest month's rate."""
    rows = savings_rows(plan)
    if not rows:
        return ''
    last = rows[-1]
    return '💰 שיעור חיסכון %s: *%.1f%%* (%s מתוך %s) · /savingsrate' % (
        month_label(last['month']), last['rate'], money(last['saved']), money(last['payment']))


def ex_safe(text):
    return ''.join(ch for ch in str(text or '') if ch not in '*_`[]')


# ----------------------------------------------------------------------------- emergency months

def average_spending(entries, today, months=3):
    """Average of the last `months` complete spending months (Visa cycles) that have
    any spending. Returns (average, [month keys used])."""
    totals = ex.monthly_totals(entries, cycle=True)
    key = ex.cycle_month_for(today)
    used = []
    for _ in range(12):
        y, m = int(key[:4]), int(key[5:7])
        key = '%04d-%02d' % ((y, m - 1) if m > 1 else (y - 1, 12))
        if totals.get(key):
            used.append(key)
        if len(used) == months:
            break
    if not used:
        return 0.0, []
    return round(sum(totals[k] for k in used) / len(used), 2), used


def format_emergency(fund, entries, today, target_months=None):
    avg, used = average_spending(entries, today)
    lines = ['🛟 *קרן חירום — כמה חודשים היא מכסה*', '',
             '🏦 בקרן: *%s*' % money(fund)]
    if not avg:
        return '\n'.join(lines + ['', '_אין עדיין מספיק הוצאות רשומות כדי לחשב ממוצע._'])
    months = fund / avg
    lines.append('💸 הוצאה חודשית ממוצעת: *%s* _(%s)_' % (money(avg), ', '.join(month_label(k) for k in used)))
    lines.append('⏳ הקרן מכסה *%.1f חודשים* של הוצאות' % months)
    if target_months:
        need = avg * target_months
        lines += ['', '🎯 יעד: *%g חודשים* = %s' % (target_months, money(need))]
        if fund >= need:
            lines.append('🟢 היעד מכוסה — עודף של %s' % money(fund - need))
        else:
            lines.append('🟠 חסרים %s (%.0f%% מהיעד)' % (money(need - fund), fund / need * 100))
    else:
        lines += ['', '_קבע יעד בחודשים: /emergency 6_']
    lines.append('_הממוצע מתעדכן לבד לפי ההוצאות שלך (3 החודשים האחרונים שנסגרו)._')
    return '\n'.join(lines)


def emergency_line(fund, entries, today):
    avg, _ = average_spending(entries, today)
    return ('🛟 קרן החירום מכסה *%.1f חודשים* של הוצאות · /emergency' % (fund / avg)) if avg else ''


# ----------------------------------------------------------------------------- net worth

BUCKET_NAME = {'short': '🛟 קצר', 'medium': '📈 בינוני', 'long': '🌳 ארוך', 'other': '💵 מזומן'}


def snapshot(result, usd_ils, eur_ils, today):
    return {'month': today.strftime('%Y-%m'), 'date': today.isoformat(),
            'total': round(result['total'], 2), 'liquid': round(result['liquid'], 2),
            'locked': round(result['locked'], 2),
            'buckets': {k: round(v['ils'], 2) for k, v in result['buckets'].items()},
            'usd_ils': round(usd_ils, 4), 'eur_ils': round(eur_ils, 4)}


def add_snapshot(data, snap):
    """Keep one snapshot per month (the newest wins)."""
    data['snapshots'] = [s for s in data['snapshots'] if s['month'] != snap['month']] + [snap]
    data['snapshots'].sort(key=lambda s: s['month'])
    return snap


def _change(now, before):
    diff = now - before
    pct = (diff / before * 100) if before else 0.0
    return '%s%s (%s%.1f%%)' % ('+' if diff >= 0 else '-', money(abs(diff)), '+' if diff >= 0 else '-', abs(pct))


def format_snapshot(snap, prev=None, title='📸 *שווי נקי — צילום חודשי*'):
    lines = [title, '📅 %s' % '/'.join(reversed(snap['date'].split('-'))), '',
             '💎 סה"כ: *%s*' % money(snap['total'])]
    if prev:
        lines.append('   מול %s: *%s*' % (month_label(prev['month']), _change(snap['total'], prev['total'])))
    lines.append('')
    for key in ('short', 'medium', 'long', 'other'):
        value = snap['buckets'].get(key, 0.0)
        if not value and not (prev and prev['buckets'].get(key)):
            continue
        line = '%s: %s' % (BUCKET_NAME[key], money(value))
        if prev and prev['buckets'].get(key) is not None:
            line += '  _(%s)_' % _change(value, prev['buckets'][key])
        lines.append(line)
    lines.append('_שער $ %.3f · € %.3f_' % (snap['usd_ils'], snap['eur_ils']))
    return '\n'.join(lines)


def format_history(snaps, current=None, limit=12):
    """Text chart of the monthly snapshots, then the live figure if given."""
    lines = ['💎 *שווי נקי לאורך זמן*', '']
    rows = snaps[-limit:]
    if not rows and not current:
        return '\n'.join(lines + ['_אין עדיין צילומים. הראשון יילקח ב-10 לחודש (או: /networth save)._'])
    top = max([s['total'] for s in rows] + ([current['total']] if current else [])) or 1
    prev = None
    for s in rows:
        bar = '█' * max(1, round(s['total'] / top * 12))
        change = ('  ' + _change(s['total'], prev['total'])) if prev else ''
        lines.append('`%s` %s *%s*%s' % (s['month'], bar, money(s['total']), change))
        prev = s
    if current:
        lines += ['', format_snapshot(current, rows[-1] if rows else None, title='🔴 *עכשיו (חי)*')]
    lines += ['', '_צילום אוטומטי ב-10 לכל חודש · צילום עכשיו: /networth save_']
    return '\n'.join(lines)


# ----------------------------------------------------------------------------- fees

def _day(text):
    try:
        return datetime.strptime(str(text)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def fee_rows(portfolio):
    """(date or None, kind, amount, currency) for every fee the records hold."""
    rows = []
    for s in portfolio.get('sold_history') or []:
        if s.get('buy_commission'):
            rows.append((_day(s.get('buy_date')), 'trade', float(s['buy_commission']), 'USD'))
        if s.get('sell_commission'):
            rows.append((_day(s.get('sell_date')), 'trade', float(s['sell_commission']), 'USD'))
    for h in portfolio.get('holdings') or []:
        if h.get('commission'):
            rows.append((_day(h.get('purchase_date')), 'trade', float(h['commission']), 'USD'))
    for c in portfolio.get('cash_log') or []:
        if c.get('fx_commission'):
            rows.append((_day(c.get('date')), 'fx', float(c['fx_commission']), 'USD'))
    for f in portfolio.get('ils_bank_fees') or []:
        if f.get('fee'):
            rows.append((_day(f.get('date')), 'bank', float(f['fee']), 'ILS'))
    return rows


FEE_KIND = {'trade': '📈 עמלות קנייה/מכירה של מניות', 'fx': '💱 עמלות המרה ב-IBKR',
            'bank': '🏦 עמלות העברה לחיסכון ₪', 'mgmt': '📉 דמי ניהול הקרן (הערכה)'}


def fee_summary(portfolio, usd_ils, today, fund_fee_pct=None):
    rows = fee_rows(portfolio)
    year_start = date(today.year, 1, 1)
    last12 = today - timedelta(days=365)
    out = {'year': {}, 'last12': {}, 'undated': {}}

    def add(bucket, kind, ils):
        out[bucket][kind] = round(out[bucket].get(kind, 0.0) + ils, 2)
    for day, kind, amount, ccy in rows:
        ils = amount * usd_ils if ccy == 'USD' else amount
        if day is None:
            add('undated', kind, ils)
            continue
        if day >= year_start:
            add('year', kind, ils)
        if day >= last12:
            add('last12', kind, ils)
    bank = float((portfolio.get('reserves') or {}).get('ILS', 0) or 0)
    if fund_fee_pct:
        annual = bank * fund_fee_pct / 100
        out['year']['mgmt'] = round(annual * ((today - year_start).days + 1) / 365, 2)
        out['last12']['mgmt'] = round(annual, 2)
    out['bank_balance'] = bank
    return out


def format_fees(summary, invested, fund_fee_pct=None, usd_ils=None):
    lines = ['🧾 *עמלות ודמי ניהול*', '']
    for key, title in (('year', '📅 *השנה*'), ('last12', '🗓 *12 החודשים האחרונים*')):
        part = summary[key]
        total = sum(part.values())
        lines.append('%s — *%s*%s' % (title, money(total),
                                      (' · %.2f%% מהכסף המושקע' % (total / invested * 100)) if invested else ''))
        for kind in ('trade', 'fx', 'bank', 'mgmt'):
            if part.get(kind):
                lines.append('   %s: %s' % (FEE_KIND[kind], money(part[kind])))
        if not part:
            lines.append('   _אין עמלות רשומות_')
        lines.append('')
    if summary['undated']:
        lines.append('_ועוד %s עמלות קנייה של החזקות שתאריך הקנייה שלהן לא שמור (מניות "Combined")._'
                     % money(sum(summary['undated'].values())))
    if fund_fee_pct:
        lines.append('_דמי ניהול: %g%% בשנה על החיסכון הבנקאי (%s). לשינוי: /fees rate 0.19_'
                     % (fund_fee_pct, money(summary['bank_balance'])))
    else:
        lines.append('_דמי הניהול של הקרן לא נספרים — קבע אחוז: /fees rate 0.19_')
    if invested:
        lines.append('_הכסף המושקע: ~%s (מניות לפי השווי האחרון + החיסכון הבנקאי)%s_'
                     % (money(invested), (' · $ לפי %.3f' % usd_ils) if usd_ils else ''))
    return '\n'.join(lines)


# ----------------------------------------------------------------------------- what if I spend X a month

def _until(today, months):
    """The month the money would last until, roughly."""
    day = today + timedelta(days=int(months * 30.44))
    return '%s %s' % (HEB_MONTHS[day.month - 1], day.year)


def format_runway(spend, emergency, future, today, snapshot=None, average=0.0):
    """How many months of `spend` a month the savings cover: the emergency fund, both
    ILS funds, and everything liquid (from the latest net-worth snapshot)."""
    lines = ['💭 *אם אני מוציא %s בחודש*' % money(spend), '']
    rows = [('🛟 קרן חירום', emergency),
            ('🏦 חירום + הוצאות עתידיות', emergency + future)]
    if snapshot:
        rows.append(('💎 כל החיסכון הנזיל (צילום %s)' % '/'.join(reversed(snapshot['date'].split('-')))[:5],
                     float(snapshot.get('liquid') or 0)))
    for label, amount in rows:
        months = amount / spend if spend else 0
        lines.append('%s — %s' % (label, money(amount)))
        lines.append('   ⏳ *%.1f חודשים*%s' % (months, ('  _(בערך עד %s)_' % _until(today, months)) if months >= 1 else ''))
    if not snapshot:
        lines.append('_לכל החיסכון (מניות, יורו, מזומן): /networth save_')
    if average:
        diff = spend - average
        lines += ['', '_ההוצאה הממוצעת שלך: %s — זה %s %s ממנה_' % (
            money(average), money(abs(diff)), 'יותר' if diff > 0 else 'פחות')]
    lines.append('_חישוב בלבד: בלי הכנסה, בלי ריבית ובלי אינפלציה._')
    return '\n'.join(lines)
