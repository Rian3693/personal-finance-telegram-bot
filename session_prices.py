"""Session-aware price resolution for the portfolio views.

Yahoo's ``regularMarketPrice`` / ``previousClose`` shift meaning with the session.
Before the open they still describe *yesterday*: ``regularMarketPrice`` holds the
last regular close and ``previousClose`` the one before it. Measuring "today" from
that pair reports yesterday's move, which is why /portfolio showed a full day's
change while the market had not opened yet.

This module resolves, for the session actually running right now, the live price
and the close "today" should be measured from. It also fills in the pre-market
print from Nasdaq when Yahoo omits it -- Yahoo drops the ``preMarketPrice`` key
entirely on some mornings even while reporting ``marketState: PRE``.
"""

import json
import re
import time
import urllib.request
from datetime import datetime, time as dtime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - py<3.9
    from backports.zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

_PRE_OPEN = dtime(4, 0)
_OPEN = dtime(9, 30)
_CLOSE = dtime(16, 0)
_POST_CLOSE = dtime(20, 0)

_NASDAQ_URL = "https://api.nasdaq.com/api/quote/{sym}/info?assetclass={ac}"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "application/json",
}
_TIMEOUT = 6
_CACHE_TTL = 60
_cache = {}


def us_session(now=None):
    """Which US equity session is running: PRE, REGULAR, POST or CLOSED."""
    now = now or datetime.now(ET)
    if now.weekday() >= 5:
        return "CLOSED"
    t = now.time()
    if _PRE_OPEN <= t < _OPEN:
        return "PRE"
    if _OPEN <= t < _CLOSE:
        return "REGULAR"
    if _CLOSE <= t < _POST_CLOSE:
        return "POST"
    return "CLOSED"


def _num(value):
    if value in (None, ""):
        return None
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def nasdaq_quote(symbol):
    """Latest Nasdaq print. Returns {price, last_close, extended, ts} or None.

    ``extended`` is True when the print is an actual pre/post trade rather than a
    stale "Closed at ..." echo of the previous session.
    """
    hit = _cache.get(symbol)
    if hit and time.time() - hit[0] < _CACHE_TTL:
        return hit[1]

    result = None
    for asset_class in ("stocks", "etf"):
        try:
            req = urllib.request.Request(
                _NASDAQ_URL.format(sym=symbol, ac=asset_class), headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = (json.load(resp).get("data") or {})
            if not data:
                continue
            primary = data.get("primaryData") or {}
            secondary = data.get("secondaryData") or {}
            price = _num(primary.get("lastSalePrice"))
            if price is None:
                continue
            stamp = str(primary.get("lastTradeTimestamp") or "")
            result = {
                "price": price,
                "ts": stamp,
                "last_close": _num(secondary.get("lastSalePrice")),
                "extended": "closed" not in stamp.lower(),
            }
            break
        except Exception:
            continue

    _cache[symbol] = (time.time(), result)
    return result


def _regular_is_today(info, now):
    """Is Yahoo's regularMarketPrice from today's session, or an older close?

    False both before the open (nothing has traded yet) and whenever the feed is
    lagging -- Yahoo has served a full day stale here, reporting an Aug 5 close
    while the Aug 6 session was open.
    """
    stamp = info.get("regularMarketTime")
    if not stamp:
        return us_session(now) != "PRE"
    try:
        return datetime.fromtimestamp(float(stamp), ET).date() == now.date()
    except (TypeError, ValueError, OSError):
        return us_session(now) != "PRE"


def resolve_session_prices(symbol, info, now=None, quote_fn=nasdaq_quote):
    """Resolve the live price and the baseline "today" is measured from.

    Returns a dict with: session, live_price, day_baseline, pre_price, pre_change,
    pre_pct, post_price, post_change, post_pct, source, stale.
    """
    now = now or datetime.now(ET)
    session = us_session(now)
    regular = info.get("regularMarketPrice") or info.get("currentPrice") or 0
    previous = info.get("previousClose") or info.get("regularMarketPreviousClose") or 0

    out = {
        "session": session, "live_price": regular, "day_baseline": previous,
        "pre_price": None, "pre_change": 0.0, "pre_pct": 0.0,
        "post_price": None, "post_change": 0.0, "post_pct": 0.0,
        "source": "yahoo", "stale": False,
    }
    if not regular:
        return out

    reg_is_today = _regular_is_today(info, now)
    out["stale"] = not reg_is_today and session in ("REGULAR", "POST")

    # When regularMarketPrice is not from today it IS the last completed close,
    # so it -- not previousClose, which is a day older still -- is the baseline.
    baseline = previous if reg_is_today else regular
    out["day_baseline"] = baseline or previous

    if session == "PRE":
        live = info.get("preMarketPrice")
        source = "yahoo"
        if not live:
            quote = quote_fn(symbol)
            if quote and quote.get("extended"):
                live = quote["price"]
                source = "nasdaq"
        if live and baseline:
            out.update(live_price=live, pre_price=live, source=source,
                       pre_change=live - baseline,
                       pre_pct=(live - baseline) / baseline * 100)
        else:
            out.update(live_price=baseline, source="close")
        return out

    # Regular / post / closed. A fresh feed is authoritative; a stale one is not,
    # so reach for the live print rather than republishing yesterday's close.
    live = regular
    if not reg_is_today:
        quote = quote_fn(symbol)
        if quote and quote.get("price"):
            live = quote["price"]
            out["source"] = "nasdaq"
        else:
            out["source"] = "close"
    out["live_price"] = live

    if session in ("POST", "CLOSED"):
        post = info.get("postMarketPrice")
        if post and reg_is_today:
            out.update(post_price=post, post_change=post - regular,
                       post_pct=(post - regular) / regular * 100 if regular else 0.0)
    return out
