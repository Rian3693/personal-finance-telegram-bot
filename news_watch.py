"""Keep watching a stock after /shouldisell, and speak up only when it matters.

Every stock that has been researched with /shouldisell is watched until it is no
longer held. Each cycle:

  1. new headlines (Finnhub, free) and new analyst rating changes (Yahoo) are
     collected and de-duplicated against everything seen before;
  2. a large one-day price move is flagged on its own, without any AI;
  3. if anything new arrived, all of it -- every watched stock in one batch -- is
     handed to Claude Opus 5.5 together with the thesis from the last research
     (the call, its price levels and its sell triggers), and the model says which
     items are critical. Only severity 4-5 events reach the user.

Cost control: the AI runs only when there is something new, in one call for all
stocks, with low effort, and at most MAX_TRIAGE_PER_DAY times a day. Items that
arrive after the cap wait for the next day rather than being dropped. The first
look at a stock only records what is already out there: the research just read
those headlines, so repeating them would be noise.
"""

import json
import os
import re
import time
from datetime import date, datetime, timedelta

import requests

import stock_decision as sdec

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'news_watch.json')

CHECK_EVERY_MIN = 30
MAX_TRIAGE_PER_DAY = 30
NOTIFY_SEVERITY = 4            # 4 = material, 5 = thesis-changing
PRICE_SHOCK = 0.06             # a one-day move this large is reported even without news
LOOKBACK_DAYS = 3              # how far back each fetch looks; seen items are skipped
SEEN_KEEP = 500
PENDING_KEEP = 40
NOTIFIED_KEEP = 30


# --------------------------------------------------------------------------- state

def empty_state():
    return {'symbols': {}, 'triage': {'date': None, 'count': 0}}


def load(path=None):
    try:
        with open(path or STATE_FILE, 'r', encoding='utf-8') as fh:
            state = json.load(fh)
        if isinstance(state, dict) and isinstance(state.get('symbols'), dict):
            state.setdefault('triage', {'date': None, 'count': 0})
            return state
    except (FileNotFoundError, ValueError, OSError):
        pass
    return empty_state()


def save(state, path=None):
    with open(path or STATE_FILE, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, indent=1, ensure_ascii=False)


def thesis_from_result(result):
    """What the watcher needs to remember about the last research."""
    d, facts = result['decision'], result['facts']
    return {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'action': d['action'], 'confidence': d['confidence'], 'headline': d['headline'],
        'price': round(facts['price'], 2), 'take_profit': d['price_targets']['take_profit'],
        'add_below': d['price_targets']['add_below'], 'review_below': d['price_targets']['review_below'],
        'hold_until': d['hold_plan']['hold_until'], 'exit_triggers': d['hold_plan']['exit_triggers'][:4],
        'catalysts': [c['event'] for c in d['hold_plan']['catalysts']][:4],
    }


def watch(state, symbol, thesis=None, now=None):
    """Start (or refresh) watching. Refreshing keeps what has been seen, so a new
    research does not re-announce old news, but replaces the thesis it is judged
    against."""
    now = now or datetime.now()
    entry = state['symbols'].get(symbol)
    if entry is None:
        entry = {'since': now.strftime('%Y-%m-%d %H:%M'), 'seen': [], 'pending': [], 'notified': [],
                 'price_flags': {}, 'baseline_done': False, 'last_check': None}
        state['symbols'][symbol] = entry
    if thesis is not None:
        entry['thesis'] = thesis
    return entry


def unwatch(state, symbol):
    return state['symbols'].pop(symbol, None) is not None


def thesis_from_history(row):
    """A thesis rebuilt from a /shouldisell history entry. It has the call and the
    price levels, but not the sell triggers or catalysts, which history never kept."""
    targets = row.get('targets') or {}
    return {'date': (row.get('date') or '')[:10], 'action': row.get('action'), 'confidence': row.get('confidence'),
            'headline': row.get('headline', ''), 'price': row.get('price'),
            'take_profit': targets.get('take_profit') or [], 'add_below': targets.get('add_below'),
            'review_below': targets.get('review_below'), 'hold_until': '', 'exit_triggers': [], 'catalysts': []}


def seed_from_history(state, history_rows, held, now=None):
    """Once only: watch every stock researched before the watch existed, if still held.

    Recorded as done, so that a stock the user later stops watching is not added
    back on the next restart. Returns the symbols added."""
    if state.get('history_seeded'):
        return []
    latest = {}
    for row in history_rows or []:
        if row.get('symbol'):
            latest[row['symbol']] = row
    added = []
    for symbol, row in sorted(latest.items()):
        if symbol in held and symbol not in state['symbols']:
            watch(state, symbol, thesis_from_history(row), now)
            added.append(symbol)
    state['history_seeded'] = True
    return added


def item_key(item):
    """Same story, same key -- however many times it is re-fetched."""
    if item.get('id'):
        return '%s:%s' % (item.get('kind', 'news'), item['id'])
    text = re.sub(r'[^a-z0-9 ]', '', (item.get('headline') or '').lower())
    return '%s:%s' % (item.get('kind', 'news'), re.sub(r'\s+', ' ', text).strip()[:140])


def take_new(entry, items):
    """Queue what has not been seen before; return how many were queued.

    The very first look only records the current items as seen (the research
    that started the watch has just read them)."""
    seen = set(entry['seen'])
    fresh = []
    for item in sorted(items, key=lambda i: i.get('time') or ''):
        key = item_key(item)
        if key in seen:
            continue
        seen.add(key)
        entry['seen'].append(key)
        fresh.append(item)
    entry['seen'] = entry['seen'][-SEEN_KEEP:]
    if not entry.get('baseline_done'):
        entry['baseline_done'] = True
        return 0
    entry['pending'] = (entry.get('pending', []) + fresh)[-PENDING_KEEP:]
    return len(fresh)


def can_triage(state, today):
    t = state['triage']
    if t.get('date') != today:
        t['date'], t['count'] = today, 0
    return t['count'] < MAX_TRIAGE_PER_DAY


def count_triage(state, today):
    can_triage(state, today)
    state['triage']['count'] += 1


# --------------------------------------------------------------------------- collecting

def fetch_news(symbol, key, now=None, session=requests):
    if not key:
        return []
    now = now or datetime.now()
    response = session.get('https://finnhub.io/api/v1/company-news', timeout=20, params={
        'symbol': symbol, 'from': (now - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d'),
        'to': now.strftime('%Y-%m-%d'), 'token': key})
    response.raise_for_status()
    out = []
    for raw in response.json() or []:
        headline = (raw.get('headline') or '').strip()
        if not headline:
            continue
        out.append({'kind': 'news', 'id': raw.get('id'), 'headline': headline,
                    'summary': (raw.get('summary') or '').strip()[:400], 'source': raw.get('source') or '',
                    'url': raw.get('url') or '',
                    'time': datetime.fromtimestamp(raw.get('datetime') or 0).strftime('%Y-%m-%d %H:%M')})
    return out


def fetch_analyst_actions(symbol, now=None):
    """Rating changes as news items, so they are judged alongside the headlines."""
    import yfinance as yf
    now = now or datetime.now()
    table = yf.Ticker(symbol).upgrades_downgrades
    if table is None or getattr(table, 'empty', True):
        return []
    out = []
    for when, row in table.iterrows():
        try:
            stamp = when.to_pydatetime().replace(tzinfo=None)
        except Exception:
            continue
        if stamp < now - timedelta(days=LOOKBACK_DAYS):
            continue
        firm, action = str(row.get('Firm', '')), str(row.get('Action', ''))
        frm, to = str(row.get('FromGrade', '') or ''), str(row.get('ToGrade', '') or '')
        target = row.get('currentPriceTarget') if 'currentPriceTarget' in row else None
        prior = row.get('priorPriceTarget') if 'priorPriceTarget' in row else None
        text = '%s %s: %s%s' % (firm, action, ('%s -> ' % frm) if frm else '', to)
        if target:
            text += ', price target %s%s' % (('%s -> ' % prior) if prior else '', target)
        out.append({'kind': 'analyst', 'id': '%s|%s|%s' % (stamp.strftime('%Y-%m-%d'), firm, to),
                    'headline': 'Analyst: ' + text, 'summary': '', 'source': firm, 'url': '',
                    'time': stamp.strftime('%Y-%m-%d %H:%M')})
    return out


def fetch_items(symbol, finnhub_key, now=None):
    """Everything new-able for one stock. A failing source yields nothing rather than
    stopping the cycle."""
    items = []
    for fetch in (lambda: fetch_news(symbol, finnhub_key, now), lambda: fetch_analyst_actions(symbol, now)):
        try:
            items += fetch()
        except Exception:
            pass
    return items


def price_snapshot(symbol):
    """(last price, previous close) or (None, None)."""
    import yfinance as yf
    try:
        info = yf.Ticker(symbol).fast_info
        last, prev = float(info.last_price), float(info.previous_close)
        if last > 0 and prev > 0:
            return last, prev
    except Exception:
        pass
    return None, None


def price_shock(entry, last, prev, today):
    """A big one-day move, reported at most once per stock per day and direction."""
    if not last or not prev:
        return None
    move = last / prev - 1
    if abs(move) < PRICE_SHOCK:
        return None
    direction = 'up' if move > 0 else 'down'
    flags = entry.setdefault('price_flags', {})
    if flags.get(today) == direction:
        return None
    flags[today] = direction
    for old in sorted(flags)[:-7]:
        flags.pop(old, None)
    return {'move': move, 'last': last, 'prev': prev, 'direction': direction}


# --------------------------------------------------------------------------- judging

TRIAGE_SYSTEM = """You monitor news for ONE private investor's stock positions and decide what is worth \
interrupting them for. They get a Telegram message for every event you mark critical, so false alarms \
cost their attention and missed events cost money. Be strict.

Severity:
5 = thesis-changing: earnings miss/beat with a guidance change, M&A or takeover, fraud or accounting issue, \
major regulatory or legal action, CEO/CFO exit, large dilutive offering, bankruptcy risk, a big contract won/lost.
4 = material: likely to move the stock several percent, a notable analyst move (major firm, large target change, \
up/downgrade), or anything that directly hits one of the investor's stated sell triggers, price levels or catalysts.
3 = notable but not urgent.
1-2 = noise: price-move recaps, "stocks to watch" lists, promotional pieces, routine filings, repeats.

Rules:
- Judge each stock against ITS thesis below: what the investor was told to do and which triggers would change it.
- Group items that report the same story into ONE event.
- If an event repeats something already alerted (listed under "already alerted"), it is not new: severity at most 2.
- Never invent facts; use only what the items say.
- Output ONLY one JSON object, no prose, no fences:
{"events": [{"symbol": "SPOT", "items": ["SPOT-1", "SPOT-3"], "severity": 1-5, "direction": "good|bad|mixed",
  "title": "short factual title", "why_it_matters": "2-3 sentences tied to the thesis and levels",
  "suggested_action": "one sentence, e.g. re-run the research, nothing to do, watch the 435 level"}]}
List only events of severity 3 or more. Return {"events": []} if nothing qualifies."""


def build_batch(state, symbols=None):
    """Everything waiting to be judged, with short ids the model can refer to."""
    batch = {}
    for symbol, entry in state['symbols'].items():
        if symbols is not None and symbol not in symbols:
            continue
        pending = entry.get('pending') or []
        if not pending:
            continue
        items = []
        for i, item in enumerate(pending, 1):
            items.append(dict(item, ref='%s-%d' % (symbol, i)))
        batch[symbol] = {'thesis': entry.get('thesis'), 'items': items,
                         'already_alerted': [n['title'] for n in entry.get('notified', [])[-6:]]}
    return batch


def triage_prompt(batch, today=None):
    lines = ['TODAY: %s' % (today or date.today().isoformat()), '']
    for symbol, block in batch.items():
        t = block['thesis'] or {}
        lines.append('=== %s ===' % symbol)
        if t:
            lines.append('Last research %s: %s at $%s (%s%% confident). %s' % (
                t.get('date'), t.get('action'), t.get('price'), t.get('confidence'), t.get('headline')))
            lines.append('Levels: take profit %s | add below %s | re-examine below %s | hold until: %s' % (
                t.get('take_profit') or '-', t.get('add_below') or '-', t.get('review_below') or '-',
                t.get('hold_until') or '-'))
            if t.get('exit_triggers'):
                lines.append('Sell triggers: ' + '; '.join(t['exit_triggers']))
            if t.get('catalysts'):
                lines.append('Catalysts: ' + '; '.join(t['catalysts']))
        else:
            lines.append('No research thesis on record: judge on general materiality.')
        if block['already_alerted']:
            lines.append('Already alerted: ' + ' | '.join(block['already_alerted']))
        lines.append('New items:')
        for item in block['items']:
            lines.append('[%s] %s %s (%s): %s%s' % (item['ref'], item.get('time', ''), item.get('kind'),
                                                   item.get('source', ''), item['headline'],
                                                   (' -- ' + item['summary'][:300]) if item.get('summary') else ''))
        lines.append('')
    return '\n'.join(lines)


def ask_triage(client, batch, today=None):
    """One Opus call for the whole batch. Same leg shape as the research legs, so
    its cost lands in the same ledger."""
    leg = {'name': 'Claude Opus 5.5 (news watch)', 'ok': False, 'skipped': False, 'text': '', 'cost': 0.0,
           'seconds': 0.0, 'error': None, 'citations': [], 'detail': '', 'provider': 'anthropic'}
    started = time.time()
    try:
        kwargs = dict(model=sdec.OPUS_MODEL, max_tokens=3000, system=TRIAGE_SYSTEM,
                      messages=[{'role': 'user', 'content': triage_prompt(batch, today)}])
        try:
            message = client.messages.create(output_config={'effort': 'low'}, **kwargs)
        except Exception as first:
            if 'output_config' not in str(first).lower():
                raise
            message = client.messages.create(**kwargs)
        leg['text'] = ''.join(getattr(b, 'text', '') for b in message.content
                              if getattr(b, 'type', None) == 'text').strip()
        usage = message.usage
        leg['cost'] = (usage.input_tokens * sdec.OPUS_IN + usage.output_tokens * sdec.OPUS_OUT) / 1e6
        leg['detail'] = '%d in / %d out tokens' % (usage.input_tokens, usage.output_tokens)
        leg['ok'] = bool(leg['text'])
    except Exception as e:
        leg['error'] = '%s: %s' % (type(e).__name__, str(e)[:160])
    leg['seconds'] = round(time.time() - started, 1)
    return leg


def parse_triage(text, batch):
    """Events the model reported, checked against what it was actually shown."""
    parsed = sdec.extract_json(text)
    if not isinstance(parsed, dict):
        return None
    events = []
    for raw in parsed.get('events') or []:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get('symbol', '')).upper()
        if symbol not in batch:
            continue
        refs = {item['ref']: item for item in batch[symbol]['items']}
        items = [refs[r] for r in (raw.get('items') or []) if r in refs]
        if not items:
            continue                       # an event must point at something it was shown
        try:
            severity = max(1, min(5, int(round(float(raw.get('severity', 0))))))
        except (TypeError, ValueError):
            continue
        direction = str(raw.get('direction', '')).lower()
        events.append({
            'symbol': symbol, 'items': items, 'severity': severity,
            'direction': direction if direction in ('good', 'bad', 'mixed') else 'mixed',
            'title': str(raw.get('title') or items[0]['headline'])[:200],
            'why': str(raw.get('why_it_matters') or '')[:600],
            'action': str(raw.get('suggested_action') or '')[:250],
            'critical': severity >= NOTIFY_SEVERITY,
        })
    return events


def record_alert(entry, event, now=None):
    entry.setdefault('notified', []).append({
        'date': (now or datetime.now()).strftime('%Y-%m-%d %H:%M'), 'title': event['title'],
        'severity': event['severity'], 'direction': event['direction']})
    entry['notified'] = entry['notified'][-NOTIFIED_KEEP:]


# --------------------------------------------------------------------------- messages

DIRECTION_EMOJI = {'good': '\U0001F7E2', 'bad': '\U0001F534', 'mixed': '\U0001F7E1',
                   'up': '\U0001F7E2', 'down': '\U0001F534'}


def _thesis_line(thesis):
    if not thesis:
        return ''
    return '\U0001F9ED _Your last call (%s): %s at %s, %s%% confident_' % (
        thesis.get('date'), sdec.ACTION_LABEL.get(thesis.get('action'), thesis.get('action')),
        sdec.usd(thesis.get('price')), thesis.get('confidence'))


def format_event(event, thesis=None, price=None):
    symbol = event['symbol']
    lines = ['\U0001F6A8 %s *%s — %s news* (%d/5)' % (DIRECTION_EMOJI[event['direction']], symbol,
                                                           {'good': 'good', 'bad': 'bad', 'mixed': 'important'}[event['direction']],
                                                           event['severity']),
             '*%s*' % sdec.md(event['title'])]
    if event['why']:
        lines += ['', sdec.md(event['why'])]
    lines.append('')
    for item in event['items'][:3]:
        lines.append('\U0001F4F0 %s · %s: %s' % (sdec.md(item.get('source') or item.get('kind')),
                                                      item.get('time', '')[:16], sdec.md(item['headline'])))
    if price and price[0] and price[1]:
        lines.append('\U0001F4B5 Now %s (%s today)' % (sdec.usd(price[0]), sdec.pct(price[0] / price[1] - 1)))
    thesis_line = _thesis_line(thesis)
    if thesis_line:
        lines.append(thesis_line)
    if event['action']:
        lines.append('\U0001F449 %s' % sdec.md(event['action']))
    return '\n'.join(lines)


def format_price_shock(symbol, shock, thesis=None, latest=None):
    lines = ['⚡ %s *%s moved %s today*' % (DIRECTION_EMOJI[shock['direction']], symbol, sdec.pct(shock['move'])),
             'Now %s, previous close %s.' % (sdec.usd(shock['last']), sdec.usd(shock['prev']))]
    if latest:
        lines.append('\U0001F4F0 Latest headline: %s' % sdec.md(latest['headline']))
    else:
        lines.append('_No headline explains it yet. I will report one if it appears._')
    thesis_line = _thesis_line(thesis)
    if thesis_line:
        lines.append(thesis_line)
    if thesis and thesis.get('review_below') and shock['last'] < thesis['review_below']:
        lines.append('⛔ Below your re-examine level of %s.' % sdec.usd(thesis['review_below']))
    return '\n'.join(lines)


def format_list(state):
    if not state['symbols']:
        return ('\U0001F441 *News watch*\n\nNothing is being watched yet. Every stock you research with '
                '/shouldisell is watched automatically until you sell it.')
    t = state.get('triage', {})
    lines = ['\U0001F441 *News watch*', '_Checked every %d minutes; you hear only about severity 4-5 news '
             'and moves of %d%%+ in a day._' % (CHECK_EVERY_MIN, int(PRICE_SHOCK * 100)), '']
    for symbol in sorted(state['symbols']):
        e = state['symbols'][symbol]
        th = e.get('thesis') or {}
        last = e.get('notified', [])[-1:] or [None]
        lines.append('• *%s* since %s%s' % (symbol, e['since'][:10],
                                                 (' · call: %s' % sdec.ACTION_LABEL.get(th.get('action'), th.get('action'))) if th else ''))
        lines.append('   %d alert%s so far%s' % (len(e.get('notified', [])), '' if len(e.get('notified', [])) == 1 else 's',
                                                   (' · last: %s' % sdec.md(last[0]['title'][:60])) if last[0] else ''))
    lines += ['', 'AI checks today: %d of %d' % (t.get('count', 0) if t.get('date') == date.today().isoformat() else 0,
                                                 MAX_TRIAGE_PER_DAY),
              'Stop one: `/shouldisell unwatch SPOT`']
    return '\n'.join(lines)
