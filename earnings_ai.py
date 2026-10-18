"""Earnings, predicted and then checked -- so the bot learns from its own misses.

1. The day before a holding reports, Claude predicts: the chance of beating EPS, the
   stock's likely direction and move, what to watch. It sees the estimates, how this stock
   reacted to its past reports, recent news, your thesis -- and its own lessons from past
   predictions and its scorecard.
2. Once the results are out (Finnhub shows them the same day), a report: actual vs
   expected EPS and revenue, the early price reaction, the headlines -- and whether your
   thesis held.
3. After the first full trading session that reacted to the report, the prediction is
   graded against what happened, and Claude writes a lesson: one for this stock and one
   in general. Those lessons, and the running hit rate, go into every next prediction.

The model itself does not retrain; what grows is its written memory of its own mistakes,
and the scorecard shows whether it is really getting better.

Stored in earnings_ai.json:
  {"predictions": {"SYM:date": {...}}, "reports": {"SYM:date": {...}}, "grades": {"SYM:date": {...}},
   "lessons": [{"date", "symbol", "lesson", "general"}], "score": {...}, "checked": {"SYM:date": iso time}}
"""

import json
import math
import os
from datetime import date, datetime, timedelta

import requests

FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'earnings_ai.json')
MODEL = 'claude-opus-5-5'
PRICE_IN, PRICE_OUT = 4.0, 20.0
FLAT = 0.02                     # a reaction within ±2% counts as "flat"
DIR_HEB = {'up': '📈 עלייה', 'down': '📉 ירידה', 'flat': '➖ בלי תזוזה גדולה'}


def load():
    try:
        with open(FILE, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    for k in ('predictions', 'reports', 'grades', 'checked'):
        data.setdefault(k, {})
    data.setdefault('lessons', [])
    data.setdefault('score', {'graded': 0, 'beat_hits': 0, 'direction_hits': 0, 'abs_error_sum': 0.0})
    return data


def save(data):
    tmp = FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
    os.replace(tmp, FILE)


def key(symbol, day):
    return '%s:%s' % (symbol.upper(), day)


# ----------------------------------------------------------------------------- data

def finnhub_calendar(symbol, day, token):
    """The Finnhub earnings row for this symbol around `day` (estimates; actuals once out)."""
    if not token:
        return None
    d = date.fromisoformat(str(day))
    r = requests.get('https://finnhub.io/api/v1/calendar/earnings', timeout=20,
                     params={'from': str(d - timedelta(days=3)), 'to': str(d + timedelta(days=3)), 'symbol': symbol, 'token': token})
    rows = (r.json() or {}).get('earningsCalendar', []) if r.ok else []
    rows = [x for x in rows if x.get('symbol') == symbol.upper()]
    return min(rows, key=lambda x: abs((date.fromisoformat(x['date']) - d).days)) if rows else None


def finnhub_news(symbol, start, end, token, limit=12):
    if not token:
        return []
    r = requests.get('https://finnhub.io/api/v1/company-news', timeout=20,
                     params={'symbol': symbol, 'from': str(start), 'to': str(end), 'token': token})
    items = r.json() if r.ok else []
    seen, out = set(), []
    for it in sorted(items, key=lambda x: -x.get('datetime', 0)):
        h = (it.get('headline') or '').strip()
        if h and h.lower() not in seen:
            seen.add(h.lower())
            out.append({'date': date.fromtimestamp(it['datetime']).isoformat(), 'headline': h[:200],
                        'summary': (it.get('summary') or '')[:300]})
        if len(out) >= limit:
            break
    return out


def closes(symbol, days=800):
    import yfinance as yf
    h = yf.Ticker(symbol).history(period='%dd' % days, auto_adjust=False)
    return [(ts.date(), float(c)) for ts, c in h['Close'].items()]


def reaction_day(report_day, hour):
    """The session that first trades on the report: the same day if it came before the open,
    otherwise the next weekday."""
    d = date.fromisoformat(str(report_day))
    if hour == 'bmo':
        return d
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def reaction(rows, report_day, hour):
    """Close of the reacting session vs the close before it; None if not traded yet."""
    rd = reaction_day(report_day, hour)
    on = [c for d, c in rows if d == rd]
    before = [c for d, c in rows if d < rd]
    if not on or not before:
        return None
    return on[0] / before[-1] - 1


def past_reactions(symbol, rows, limit=8):
    """[(date, eps surprise %, price reaction)] for the stock's last reports (yfinance)."""
    import yfinance as yf
    try:
        ed = yf.Ticker(symbol).get_earnings_dates(limit=limit + 4)
    except Exception:
        return []
    out = []
    for ts, row in ed.iterrows():
        rep = row.get('Reported EPS')
        if rep is None or (isinstance(rep, float) and math.isnan(rep)):
            continue
        hour = 'bmo' if ts.hour < 12 else 'amc'
        r = reaction(rows, ts.date(), hour)
        sp = row.get('Surprise(%)')
        out.append({'date': ts.date().isoformat(), 'surprise_pct': None if sp is None or (isinstance(sp, float) and math.isnan(sp)) else round(float(sp), 1),
                    'reaction_pct': None if r is None else round(r * 100, 1)})
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------------------- Claude

PREDICT_SCHEMA = {
    'type': 'object',
    'properties': {
        'beat_prob': {'type': 'integer'}, 'direction': {'type': 'string', 'enum': ['up', 'down', 'flat']},
        'move_pct': {'type': 'number'}, 'confidence': {'type': 'string', 'enum': ['low', 'medium', 'high']},
        'key_points': {'type': 'array', 'items': {'type': 'string'}}, 'reasoning': {'type': 'string'}},
    'required': ['beat_prob', 'direction', 'move_pct', 'confidence', 'key_points', 'reasoning'],
    'additionalProperties': False,
}
REPORT_SCHEMA = {
    'type': 'object',
    'properties': {
        'summary': {'type': 'array', 'items': {'type': 'string'}}, 'guidance': {'type': 'string'},
        'thesis_verdict': {'type': 'string', 'enum': ['ok', 'weak', 'broken', 'unknown']},
        'thesis_reason': {'type': 'string'}},
    'required': ['summary', 'guidance', 'thesis_verdict', 'thesis_reason'], 'additionalProperties': False,
}
LESSON_SCHEMA = {
    'type': 'object',
    'properties': {'what_happened': {'type': 'string'}, 'lesson': {'type': 'string'}, 'general': {'type': 'string'}},
    'required': ['what_happened', 'lesson', 'general'], 'additionalProperties': False,
}


def _ask(client, prompt, schema, effort='medium'):
    msg = client.messages.create(
        model=MODEL, max_tokens=6000,
        output_config={'effort': effort, 'format': {'type': 'json_schema', 'schema': schema}},
        messages=[{'role': 'user', 'content': prompt}])
    cost = (msg.usage.input_tokens * PRICE_IN + msg.usage.output_tokens * PRICE_OUT) / 1e6
    if msg.stop_reason in ('refusal', 'max_tokens'):
        raise ValueError('Claude did not finish (%s)' % msg.stop_reason)
    text = next((b.text for b in msg.content if b.type == 'text'), '')
    return json.loads(text), cost


def lessons_for(data, symbol, n_symbol=5, n_general=10):
    own = [l for l in data['lessons'] if l.get('symbol') == symbol][-n_symbol:]
    general = [l for l in data['lessons'] if l.get('general')][-n_general:]
    return own, general


def scorecard(data):
    s = data['score']
    n = s.get('graded', 0)
    if not n:
        return {'graded': 0}
    return {'graded': n, 'beat_rate': s['beat_hits'] / n, 'direction_rate': s['direction_hits'] / n,
            'avg_error': s['abs_error_sum'] / n}


PREDICT_PROMPT = """You forecast how a US stock will do on its earnings report. Be calibrated, not bold:
a probability is a probability. Write `reasoning` and `key_points` in Hebrew (short).

Stock: {symbol} · reports {day} ({hour})
Estimates: EPS {eps_est} · revenue {rev_est}
Its last reports (EPS surprise %, next-session price reaction %): {history}
Recent moves: {moves}
Recent headlines: {news}
The owner's thesis: {thesis}

YOUR TRACK RECORD so far: {score}
YOUR LESSONS from past misses on this stock: {own_lessons}
YOUR GENERAL LESSONS: {general_lessons}
Apply the lessons. If your record shows overconfidence or a bias (e.g. calling "up" too often), correct it.

Return: beat_prob (0-100, chance EPS beats the estimate), direction of the next-session reaction
(up / down / flat = within ±2%), move_pct (your expected signed % move), confidence, 3-4 key_points
to watch, reasoning (2-3 sentences). This is analysis, not investment advice."""

REPORT_PROMPT = """{symbol} just reported. Summarise it for the owner in Hebrew, plainly.

Results: EPS {eps_act} vs {eps_est} expected · revenue {rev_act} vs {rev_est} expected · reported {hour}
Price reaction so far: {move}
Headlines since the report (with summaries): {news}
The owner's thesis: {thesis}

Return: summary (4-6 short Hebrew bullets: beat/miss, what drove it, notable numbers, what the market
seems to focus on), guidance (one Hebrew line on forward guidance if the headlines mention it, else "לא ידוע"),
thesis_verdict (ok = the thesis still holds, weak = weakened, broken = its stated break condition happened,
unknown = no thesis or not enough info), thesis_reason (one Hebrew sentence). No buy/sell advice."""

LESSON_PROMPT = """Grade your own earnings prediction honestly and learn from it.

Stock {symbol}, report {day}.
Your prediction: beat_prob {beat_prob}%, direction {direction}, move {move_pct}%, confidence {confidence}.
Your reasoning then: {reasoning}
What happened: EPS {eps_act} vs {eps_est} ({beat_word}); next-session price reaction {reaction}%.
Headlines: {news}
Your earlier lessons: {lessons}

Return in Hebrew: what_happened (one sentence: why the stock moved the way it did),
lesson (one concrete, reusable sentence for THIS stock's next report -- what to weigh differently),
general (one concrete sentence that applies to predicting any earnings reaction, or "" if nothing new).
Do not repeat an existing lesson; refine it instead."""


def _fmt_money(x):
    if x is None:
        return 'unknown'
    x = float(x)
    for div, unit in ((1e9, 'B'), (1e6, 'M')):
        if abs(x) >= div:
            return '$%.2f%s' % (x / div, unit)
    return '$%.2f' % x


def predict(client, data, symbol, day, cal, history, moves, news, thesis_text):
    own, general = lessons_for(data, symbol)
    prompt = PREDICT_PROMPT.format(
        symbol=symbol, day=day, hour=(cal or {}).get('hour') or 'unknown',
        eps_est=(cal or {}).get('epsEstimate'), rev_est=_fmt_money((cal or {}).get('revenueEstimate')),
        history=json.dumps(history, ensure_ascii=False), moves=moves,
        news=json.dumps(news[:10], ensure_ascii=False), thesis=thesis_text or 'none written',
        score=json.dumps(scorecard(data)), own_lessons=json.dumps([l['lesson'] for l in own], ensure_ascii=False),
        general_lessons=json.dumps([l['general'] for l in general], ensure_ascii=False))
    result, cost = _ask(client, prompt, PREDICT_SCHEMA)
    result['beat_prob'] = max(0, min(100, int(result['beat_prob'])))
    entry = dict(result, created=datetime.now().isoformat(timespec='minutes'), cost=round(cost, 4),
                 eps_estimate=(cal or {}).get('epsEstimate'), revenue_estimate=(cal or {}).get('revenueEstimate'),
                 hour=(cal or {}).get('hour'))
    data['predictions'][key(symbol, day)] = entry
    return entry, cost


def report(client, data, symbol, day, cal, move, news, thesis_text):
    prompt = REPORT_PROMPT.format(
        symbol=symbol, eps_act=cal.get('epsActual'), eps_est=cal.get('epsEstimate'),
        rev_act=_fmt_money(cal.get('revenueActual')), rev_est=_fmt_money(cal.get('revenueEstimate')),
        hour=cal.get('hour') or '', move=('%+.1f%%' % (move * 100)) if move is not None else 'not traded yet',
        news=json.dumps(news[:12], ensure_ascii=False), thesis=thesis_text or 'none written')
    result, cost = _ask(client, prompt, REPORT_SCHEMA)
    entry = dict(result, cal=cal, early_move=move, cost=round(cost, 4), at=datetime.now().isoformat(timespec='minutes'))
    data['reports'][key(symbol, day)] = entry
    return entry, cost


def grade(client, data, symbol, day, actual_reaction, news):
    """Score the prediction against what happened and keep the lesson. Returns (grade, cost)."""
    k = key(symbol, day)
    pred, rep = data['predictions'].get(k), data['reports'].get(k) or {}
    cal = rep.get('cal') or {}
    eps_act, eps_est = cal.get('epsActual'), cal.get('epsEstimate')
    beat = None if eps_act is None or eps_est is None else eps_act > eps_est
    actual_dir = 'flat' if abs(actual_reaction) < FLAT else ('up' if actual_reaction > 0 else 'down')
    g = {'reaction': actual_reaction, 'actual_direction': actual_dir, 'beat': beat}
    cost = 0.0
    if pred:
        g['beat_correct'] = None if beat is None else (pred['beat_prob'] >= 50) == beat
        g['direction_correct'] = pred['direction'] == actual_dir
        g['error'] = abs(pred['move_pct'] / 100 - actual_reaction)
        s = data['score']
        s['graded'] += 1
        s['beat_hits'] += 1 if g['beat_correct'] else 0
        s['direction_hits'] += 1 if g['direction_correct'] else 0
        s['abs_error_sum'] += g['error']
        own, _ = lessons_for(data, symbol)
        prompt = LESSON_PROMPT.format(
            symbol=symbol, day=day, beat_prob=pred['beat_prob'], direction=pred['direction'],
            move_pct=pred['move_pct'], confidence=pred['confidence'], reasoning=pred['reasoning'],
            eps_act=eps_act, eps_est=eps_est, beat_word='beat' if beat else ('miss' if beat is False else 'unknown'),
            reaction=round(actual_reaction * 100, 1), news=json.dumps(news[:10], ensure_ascii=False),
            lessons=json.dumps([l['lesson'] for l in own], ensure_ascii=False))
        lesson, cost = _ask(client, prompt, LESSON_SCHEMA, effort='medium')
        g.update(lesson)
        data['lessons'].append({'date': date.today().isoformat(), 'symbol': symbol, 'report': day,
                                'lesson': lesson['lesson'], 'general': lesson.get('general') or ''})
        g['cost'] = round(cost, 4)
    data['grades'][k] = g
    return g, cost


# ----------------------------------------------------------------------------- messages

def _usd(x):
    return '—' if x is None else _fmt_money(x)


def format_prediction(symbol, p):
    lines = ['🤖 *התחזית שלי ל-%s*' % symbol,
             'סיכוי להכות את תחזית ה-EPS: *%d%%* · כיוון צפוי: %s (*%+.1f%%*) · ביטחון: %s' % (
                 p['beat_prob'], DIR_HEB[p['direction']], p['move_pct'],
                 {'low': 'נמוך', 'medium': 'בינוני', 'high': 'גבוה'}[p['confidence']]),
             '_%s_' % p['reasoning'].replace('_', ' ').replace('*', '')]
    for k in p.get('key_points') or []:
        lines.append('• ' + k.replace('*', '').replace('_', ' '))
    return '\n'.join(lines)


def format_report(symbol, r, prediction=None):
    cal = r['cal']
    eps_a, eps_e = cal.get('epsActual'), cal.get('epsEstimate')
    rev_a, rev_e = cal.get('revenueActual'), cal.get('revenueEstimate')
    def vs(a, e, money=False):
        if a is None or e is None:
            return '%s (צפי %s)' % (_usd(a) if money else a, _usd(e) if money else e)
        pct = (a / e - 1) * 100 if e else 0
        return '%s מול צפי %s — %s %+.1f%%' % (_usd(a) if money else '$%.2f' % a, _usd(e) if money else '$%.2f' % e,
                                              '✅' if a >= e else '❌', pct)
    lines = ['📣 *%s פרסמה דוח*' % symbol, '',
             'EPS: ' + vs(eps_a, eps_e), 'הכנסות: ' + vs(rev_a, rev_e, money=True)]
    if r.get('early_move') is not None:
        lines.append('תגובה ראשונית במחיר: *%+.1f%%*' % (r['early_move'] * 100))
    lines += [''] + ['• ' + s.replace('*', '').replace('_', ' ') for s in r['summary']]
    if r.get('guidance') and r['guidance'] != 'לא ידוע':
        lines.append('🔭 תחזית קדימה: ' + r['guidance'].replace('*', '').replace('_', ' '))
    verdict = {'ok': '✅ נראה שהתזה שלך מחזיקה', 'weak': '⚠️ נראה שהתזה נחלשה', 'broken': '❌ נראה שתנאי השבירה קרה',
               'unknown': '❔ אין מספיק כדי לשפוט את התזה'}[r['thesis_verdict']]
    lines += ['', '🧭 %s — _%s_' % (verdict, r['thesis_reason'].replace('_', ' ').replace('*', ''))]
    if prediction:
        lines.append('🤖 התחזית שלי הייתה: %d%% להכות, %s %+.1f%% — הציון יגיע אחרי המסחר הבא' % (
            prediction['beat_prob'], DIR_HEB[prediction['direction']], prediction['move_pct']))
    lines.append('_אשר את התזה בכפתורים:_')
    return '\n'.join(lines)


def format_grade(symbol, g, prediction, data):
    lines = ['📊 *ציון לתחזית שלי — %s*' % symbol,
             'בפועל: %s, המחיר %s *%+.1f%%*' % ('הכתה' if g.get('beat') else ('פספסה' if g.get('beat') is False else '?'),
                                                 DIR_HEB[g['actual_direction']], g['reaction'] * 100)]
    if prediction:
        lines.append('חזיתי: %d%% להכות %s · %s %+.1f%% %s' % (
            prediction['beat_prob'], '✅' if g.get('beat_correct') else '❌',
            DIR_HEB[prediction['direction']], prediction['move_pct'], '✅' if g.get('direction_correct') else '❌'))
        lines.append('_%s_' % (g.get('what_happened') or '').replace('_', ' ').replace('*', ''))
        lines.append('📝 *לקח ל-%s:* %s' % (symbol, (g.get('lesson') or '').replace('*', '').replace('_', ' ')))
        if g.get('general'):
            lines.append('📝 *לקח כללי:* %s' % g['general'].replace('*', '').replace('_', ' '))
    sc = scorecard(data)
    if sc.get('graded'):
        lines.append('🏁 עד עכשיו: %d תחזיות · כיוון נכון %.0f%% · הכה/פספס נכון %.0f%% · טעות ממוצעת %.1f%%' % (
            sc['graded'], sc['direction_rate'] * 100, sc['beat_rate'] * 100, sc['avg_error'] * 100))
    return '\n'.join(lines)


def format_scoreboard(data):
    sc = scorecard(data)
    lines = ['🏁 *התחזיות שלי לדוחות — כמה אני צודק*', '']
    if not sc.get('graded'):
        lines.append('_עוד אין תחזיות שנבדקו. אחרי הדוח הראשון של מניה שלך יופיע כאן הציון._')
    else:
        lines.append('נבדקו *%d* · כיוון נכון *%.0f%%* · הכה/פספס נכון *%.0f%%* · טעות ממוצעת בתנועה *%.1f%%*' % (
            sc['graded'], sc['direction_rate'] * 100, sc['beat_rate'] * 100, sc['avg_error'] * 100))
        lines.append('_לשם השוואה: ניחוש אקראי של כיוון ≈ 33% (עלייה/ירידה/בלי תזוזה)_')
    graded = sorted(data['grades'].items(), key=lambda kv: kv[0].split(':')[1], reverse=True)[:8]
    if graded:
        lines += ['', '*אחרונות:*']
        for k, g in graded:
            p = data['predictions'].get(k) or {}
            lines.append('`%s` %s %+.1f%% (חזיתי %s %s)' % (k, DIR_HEB[g['actual_direction']], g['reaction'] * 100,
                                                          DIR_HEB.get(p.get('direction'), '—'), '✅' if g.get('direction_correct') else '❌'))
    lessons = data['lessons'][-8:]
    if lessons:
        lines += ['', '*מה למדתי:*'] + ['• %s: %s' % (l['symbol'], l['lesson'].replace('*', '').replace('_', ' ')) for l in lessons[::-1]]
    return '\n'.join(lines)
