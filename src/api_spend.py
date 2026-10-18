"""What the AI features have cost, and an estimate of what is left.

Neither Anthropic nor Perplexity lets an ordinary API key read its remaining
balance: Anthropic exposes spend history only through organization admin keys and
shows the balance in its console, and Perplexity has no endpoint for it at all.
So the only honest way to answer "how much is left?" from inside the bot is to
count what the bot itself spends and subtract it from a balance the user states.

Two things follow, and every message built here says so:
  * the result is an ESTIMATE, accurate only for what has been counted;
  * it counts only what is recorded through `record_spend`. Anything else that
    uses the same keys is invisible to it.

Each record comes from a call's own usage figures (Perplexity reports its exact
cost; Anthropic's is computed from the tokens it reports), never from a guess.
"""

import json
import os
from datetime import datetime

SPEND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_spend.json')
CREDITS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_credits.json')

ANTHROPIC, PERPLEXITY = 'anthropic', 'perplexity'
PROVIDERS = (ANTHROPIC, PERPLEXITY)
LABEL = {ANTHROPIC: 'Anthropic — Claude Opus 5.5', PERPLEXITY: 'Perplexity — finance + Deep Research'}
EMOJI = {ANTHROPIC: '\U0001F9E0', PERPLEXITY: '\U0001F50E'}
CONSOLE = {ANTHROPIC: 'Claude Console → Billing', PERPLEXITY: 'perplexity.ai → Settings → API'}
ALIASES = {'anthropic': ANTHROPIC, 'claude': ANTHROPIC, 'opus': ANTHROPIC,
           'perplexity': PERPLEXITY, 'pplx': PERPLEXITY, 'sonar': PERPLEXITY}

KEEP_ROWS = 5000
RUNS_FOR_AVERAGE = 10
# Microseconds, so "spent since the balance was stated" has an exact cutoff: with
# whole seconds, a run finishing in the same second as the statement was counted
# against a balance that already excluded it.
NOW_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def money(amount):
    amount = float(amount or 0)
    return ('-' if amount < 0 else '') + '$' + format(abs(amount), ',.2f')


def _read(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError, OSError):
        return None


def provider_of(leg):
    """Which account a call was billed to: stated on the leg, else read from its name."""
    stated = (leg.get('provider') or '').lower()
    if stated in PROVIDERS:
        return stated
    name = (leg.get('name') or '').lower()
    if 'claude' in name or 'opus' in name:
        return ANTHROPIC
    if 'perplexity' in name or 'sonar' in name:
        return PERPLEXITY
    return None


# --------------------------------------------------------------------------- the ledger

def load_spend(path=None):
    rows = _read(path or SPEND_FILE)
    return rows if isinstance(rows, list) else []


def record_spend(legs, label, path=None, now=None):
    """Append what a batch of calls cost, one row per call. Calls with no cost or
    no recognisable provider are skipped. Returns the rows written."""
    now = now or datetime.now()
    run = '%s-%s' % (now.strftime('%Y%m%d%H%M%S'), label)
    rows = []
    for leg in legs:
        provider, cost = provider_of(leg), float(leg.get('cost') or 0)
        if provider and cost > 0:
            rows.append({'date': now.strftime(NOW_FORMAT), 'provider': provider, 'usd': round(cost, 5),
                         'what': leg.get('name', ''), 'label': label, 'run': run})
    if rows:
        existing = load_spend(path)
        with open(path or SPEND_FILE, 'w', encoding='utf-8') as fh:
            json.dump((existing + rows)[-KEEP_ROWS:], fh, indent=1, ensure_ascii=False)
    return rows


# --------------------------------------------------------------------------- the balances the user states

def load_credits(path=None):
    stored = _read(path or CREDITS_FILE)
    return stored if isinstance(stored, dict) else {}


def parse_provider(word):
    return ALIASES.get((word or '').strip().lower())


def set_balance(provider, amount, path=None, now=None):
    """Record what the user says they have right now. Spend is counted from this
    moment, so a top-up is handled by simply stating the new balance."""
    if provider not in PROVIDERS:
        raise ValueError('provider must be one of: %s' % ', '.join(PROVIDERS))
    amount = float(amount)
    if amount < 0:
        raise ValueError('a balance cannot be negative')
    credits = load_credits(path)
    credits[provider] = {'balance': round(amount, 2),
                         'as_of': (now or datetime.now()).strftime(NOW_FORMAT)}
    with open(path or CREDITS_FILE, 'w', encoding='utf-8') as fh:
        json.dump(credits, fh, indent=1)
    return credits[provider]


# --------------------------------------------------------------------------- the picture

def status(provider, spend_path=None, credits_path=None, now=None):
    now = now or datetime.now()
    rows = [r for r in load_spend(spend_path) if r.get('provider') == provider]
    month = now.strftime('%Y-%m')

    # Average cost of a whole run: sum each run's calls, then average the runs.
    by_run = {}
    for row in rows:
        by_run[row.get('run')] = by_run.get(row.get('run'), 0.0) + float(row.get('usd', 0))
    recent = list(by_run.values())[-RUNS_FOR_AVERAGE:]
    average = sum(recent) / len(recent) if recent else 0.0

    out = {
        'provider': provider, 'runs': len(by_run),
        'total': round(sum(float(r['usd']) for r in rows), 4),
        'month': round(sum(float(r['usd']) for r in rows if str(r.get('date', '')).startswith(month)), 4),
        'average_run': round(average, 4), 'balance': None, 'as_of': None, 'spent_since': None,
        'estimate': None, 'runs_left': None,
    }
    stated = load_credits(credits_path).get(provider)
    if stated:
        since = round(sum(float(r['usd']) for r in rows if str(r.get('date', '')) >= stated['as_of']), 4)
        estimate = round(stated['balance'] - since, 2)
        out.update(balance=stated['balance'], as_of=stated['as_of'], spent_since=since, estimate=estimate,
                   runs_left=int(estimate // average) if average > 0 and estimate > 0 else (0 if estimate <= 0 else None))
    return out


def format_status(spend_path=None, credits_path=None, now=None):
    """The full /shouldisell credits answer."""
    lines = ['\U0001F4B3 *API CREDITS*  _(an estimate)_', '━' * 18, '']
    for provider in PROVIDERS:
        s = status(provider, spend_path, credits_path, now)
        lines.append('%s *%s*' % (EMOJI[provider], LABEL[provider]))
        if s['estimate'] is None:
            lines.append('   Balance not set. Tell me what you have:')
            lines.append('   `/shouldisell credits %s 20`' % provider)
        else:
            lines.append('   ≈ *%s left*' % money(s['estimate']))
            lines.append('   _you said %s on %s; %s counted since_' % (
                money(s['balance']), s['as_of'][:10], money(s['spent_since'])))
            if s['estimate'] <= 0:
                lines.append('   ⚠️ Estimated empty: top up, then re-state the balance.')
            elif s['runs_left'] is not None and s['average_run'] > 0:
                lines.append('   ≈ %d more runs at about %s each' % (s['runs_left'], money(s['average_run'])))
        lines.append('   Spent this month: %s · all counted: %s · %d runs' % (
            money(s['month']), money(s['total']), s['runs']))
        lines.append('')
    lines.append('_Only /shouldisell is counted. Other features that use the same keys, or anything '
                 'run outside the bot, are not, so treat the figure as an upper bound on what is left._')
    lines.append('_The exact balance is only in the consoles: %s; %s._' % (CONSOLE[ANTHROPIC], CONSOLE[PERPLEXITY]))
    lines.append('_After a top-up, state the new balance and counting restarts from it._')
    return '\n'.join(lines)


def footer_line(spend_path=None, credits_path=None, now=None):
    """One line for the end of a research report, or '' when there is nothing to say."""
    parts, low = [], False
    for provider in PROVIDERS:
        s = status(provider, spend_path, credits_path, now)
        if s['estimate'] is None:
            continue
        parts.append('%s ≈ %s' % ('Anthropic' if provider == ANTHROPIC else 'Perplexity', money(s['estimate'])))
        if s['estimate'] <= 0 or (s['average_run'] and s['estimate'] < s['average_run']):
            low = True
    if not parts:
        return '\U0001F4B3 _Credits left: not tracked yet — /shouldisell credits_'
    line = '\U0001F4B3 Credits left (est.): %s' % ' · '.join(parts)
    return line + ('  ⚠️ _low: below one more run_' if low else '')
