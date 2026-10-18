"""
US portfolio daily heatmap - GitHub-contributions style.

One column per calendar week, seven squares per column (Mon..Sun):
    green  -> the US stock portfolio finished the day up
    red    -> it finished the day down
    gray   -> market closed (weekend / US market holiday)
    dim    -> trading day with no snapshot in the log (bot was off)

The daily % is the market move of the positions held that day, measured
from each stock's previous close (from its purchase price for shares
bought that same day), so deposits and new buys never colour a square.
It is rebuilt from the `stocks` snapshot in my_portfolio.json ->
portfolio_log; entries without usable price data fall back to the stored
`true_daily_pl_pct` / `market_profit_pct`.

Only the US portfolio (my_portfolio.json) is used - Israeli holdings
and reserves are not part of this view.
"""

import datetime as dt
import io
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(BASE_DIR, "my_portfolio.json")

# ---------------------------------------------------------------- calendar

# NYSE full-day closures.  Half days (early close) still count as trading days.
NYSE_HOLIDAYS = {
    # 2025
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    # 2027
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    # 2028
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
}


def is_market_closed(day):
    """True for weekends and US market holidays."""
    return day.weekday() >= 5 or day.isoformat() in NYSE_HOLIDAYS


# ---------------------------------------------------------------- data

def _market_move_pct(entry):
    """Daily market move of the positions in one portfolio_log entry.

    Each holding is measured against its previous close, or against its
    purchase price when it was bought that same day, so money moved into or
    out of the portfolio never shows up as a gain or a loss.
    """
    date = str(entry.get("date") or "")[:10]
    profit = 0.0
    base = 0.0
    for stock in entry.get("stocks") or []:
        shares = stock.get("shares")
        price = stock.get("price")
        if not shares or price is None:
            continue
        if str(stock.get("purchase_date") or "")[:10] == date:
            start = stock.get("purchase_price") or stock.get("prev_close")
        else:
            start = stock.get("prev_close") or stock.get("open_price")
        if not start:
            continue
        profit += shares * (price - start)
        base += shares * start
    if base <= 0:
        return None
    return profit / base * 100


def load_daily_returns():
    """Return {date_str: pct} for every logged US-portfolio trading day.

    Days where the snapshot is identical to the previous one (the bot ran on
    a closed market) are dropped - nothing actually moved on those days.
    """
    if not os.path.exists(PORTFOLIO_FILE):
        return {}
    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    returns = {}
    for entry in data.get("portfolio_log", []):
        date = str(entry.get("date") or "")[:10]
        if not date:
            continue
        value = entry.get("value")
        prev = entry.get("prev_value")
        # The first day ever has no baseline, and a frozen value means the
        # market never moved (a holiday the bot did not know about).
        if not prev:
            continue
        try:
            if abs(float(value) - float(prev)) < 1e-9:
                continue
        except (TypeError, ValueError):
            pass

        pct = _market_move_pct(entry)
        if pct is None:
            pct = entry.get("true_daily_pl_pct")
        if pct is None:
            pct = entry.get("market_profit_pct")
        if pct is None:
            continue
        returns[date] = float(pct)
    return returns


def build_days(returns, start, end):
    """List of {date, state, pct} for every day in [start, end]."""
    days = []
    cur = start
    while cur <= end:
        key = cur.isoformat()
        if is_market_closed(cur):
            state = "closed"
            pct = None
        elif key in returns:
            pct = returns[key]
            state = "up" if pct > 0 else ("down" if pct < 0 else "flat")
        else:
            state = "nodata"
            pct = None
        days.append({"date": cur, "state": state, "pct": pct})
        cur += dt.timedelta(days=1)
    return days


def summarize(days):
    """Headline stats for the rendered window."""
    traded = [d for d in days if d["pct"] is not None]
    streak_kind, streak_len = None, 0
    for d in reversed(traded):
        if streak_kind is None:
            streak_kind = d["state"]
            streak_len = 1
        elif d["state"] == streak_kind:
            streak_len += 1
        else:
            break

    return {
        "traded": len(traded),
        "up": sum(1 for d in traded if d["state"] == "up"),
        "down": sum(1 for d in traded if d["state"] == "down"),
        "missing": sum(1 for d in days if d["state"] == "nodata"),
        "best": max(traded, key=lambda d: d["pct"]) if traded else None,
        "worst": min(traded, key=lambda d: d["pct"]) if traded else None,
        "avg": (sum(d["pct"] for d in traded) / len(traded)) if traded else 0.0,
        "last": traded[-1] if traded else None,
        "streak_kind": streak_kind,
        "streak_len": streak_len,
    }


def resolve_range(arg, returns):
    """Turn a user argument into (start_date, end_date).

    Accepted: '' / 'all', '3m', '6w', '90d', '2026', '2026-05'.
    """
    dates = sorted(returns)
    first = dt.date.fromisoformat(dates[0]) if dates else dt.date.today()
    today = dt.date.today()
    last = max(today, dt.date.fromisoformat(dates[-1])) if dates else today

    arg = (arg or "").strip().lower()
    if arg in ("", "all"):
        return first, last

    if len(arg) == 7 and arg[4] == "-":          # 2026-05
        year, month = int(arg[:4]), int(arg[5:])
        start = dt.date(year, month, 1)
        end = (dt.date(year + (month == 12), month % 12 + 1, 1)
               - dt.timedelta(days=1))
        return start, min(end, last)

    if len(arg) == 4 and arg.isdigit():          # 2026
        year = int(arg)
        return dt.date(year, 1, 1), min(dt.date(year, 12, 31), last)

    unit, number = arg[-1], arg[:-1]
    if unit in ("d", "w", "m", "y") and number.isdigit():
        n = int(number)
        span = {"d": n, "w": n * 7, "m": n * 30, "y": n * 365}[unit]
        return max(first, last - dt.timedelta(days=span - 1)), last
    if arg.isdigit():                            # bare number of days
        return max(first, last - dt.timedelta(days=int(arg) - 1)), last

    return first, last


# ---------------------------------------------------------------- colors

BG = (13, 17, 23)
CARD = (22, 27, 34)
TEXT = (230, 237, 243)
MUTED = (125, 137, 152)
CLOSED = (61, 68, 77)          # market closed - plain gray
NODATA = (37, 43, 51)          # trading day, no snapshot
FLAT = (48, 54, 61)

GREENS = [(14, 68, 41), (0, 109, 50), (38, 166, 65), (57, 211, 83)]
REDS = [(77, 20, 22), (139, 26, 30), (198, 44, 44), (248, 81, 73)]


def _shade(scale, pct):
    magnitude = abs(pct)
    if magnitude < 0.5:
        return scale[0]
    if magnitude < 1.0:
        return scale[1]
    if magnitude < 2.0:
        return scale[2]
    return scale[3]


def color_for(day):
    state = day["state"]
    if state == "up":
        return _shade(GREENS, day["pct"])
    if state == "down":
        return _shade(REDS, day["pct"])
    if state == "flat":
        return FLAT
    if state == "closed":
        return CLOSED
    return NODATA


# ---------------------------------------------------------------- rendering

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _font(size, bold=False):
    from PIL import ImageFont
    candidates = (["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]
                  if bold else
                  ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
    candidates.append("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_png(days, title="US Portfolio - Daily Heatmap"):
    """Render the heatmap and return PNG bytes."""
    from PIL import Image, ImageDraw

    stats = summarize(days)
    scale = 2                  # supersample, downscaled at the end
    cell, gap = 15, 4
    step = cell + gap

    grid_start = days[0]["date"] - dt.timedelta(days=days[0]["date"].weekday())
    grid_end = days[-1]["date"] + dt.timedelta(days=6 - days[-1]["date"].weekday())
    weeks = ((grid_end - grid_start).days + 1) // 7

    left = 46
    top_grid = 104
    width = max(left + weeks * step + 18, 440)
    grid_h = 7 * step - gap
    legend_y = top_grid + grid_h + 26
    stats_y = legend_y + 34
    height = stats_y + 76

    by_date = {d["date"]: d for d in days}

    img = Image.new("RGB", (width * scale, height * scale), BG)
    draw = ImageDraw.Draw(img)

    f_title = _font(17 * scale, bold=True)
    f_sub = _font(11 * scale)
    f_small = _font(9 * scale)
    f_value = _font(11 * scale, bold=True)

    draw.rounded_rectangle(
        [6 * scale, 6 * scale, (width - 6) * scale, (height - 6) * scale],
        radius=10 * scale, fill=CARD)

    draw.text((18 * scale, 16 * scale), title, font=f_title, fill=TEXT)
    span = (f"{days[0]['date'].strftime('%d %b %Y')}"
            f"  \u2192  {days[-1]['date'].strftime('%d %b %Y')}")
    draw.text((18 * scale, 40 * scale), span, font=f_sub, fill=MUTED)

    # month labels above the grid
    last_month = None
    for week in range(weeks):
        monday = grid_start + dt.timedelta(days=week * 7)
        month = (monday + dt.timedelta(days=6)).month
        if month != last_month:
            x = left + week * step
            if x + 24 < width - 10:
                draw.text((x * scale, (top_grid - 16) * scale),
                          MONTH_LABELS[month - 1], font=f_small, fill=MUTED)
            last_month = month

    # weekday labels
    for row, label in enumerate(WEEKDAY_LABELS):
        y = top_grid + row * step + 3
        draw.text((14 * scale, y * scale), label, font=f_small, fill=MUTED)

    # the squares
    for week in range(weeks):
        for row in range(7):
            day = grid_start + dt.timedelta(days=week * 7 + row)
            entry = by_date.get(day)
            if entry is None:
                continue
            x = left + week * step
            y = top_grid + row * step
            draw.rounded_rectangle(
                [x * scale, y * scale, (x + cell) * scale, (y + cell) * scale],
                radius=3 * scale, fill=color_for(entry))

    # legend
    def chip(x, color):
        draw.rounded_rectangle(
            [x * scale, legend_y * scale, (x + 11) * scale, (legend_y + 11) * scale],
            radius=2 * scale, fill=color)
        return x + 13

    def caption(x, text, pad=6):
        draw.text((x * scale, (legend_y + 1) * scale), text, font=f_small, fill=MUTED)
        return x + draw.textlength(text, font=f_small) / scale + pad

    x = caption(18, "Down")
    for color in reversed(REDS):
        x = chip(x, color)
    x += 4
    for color in GREENS:
        x = chip(x, color)
    x = caption(x, "Up", pad=16)
    x = chip(x, CLOSED)
    x = caption(x + 3, "Market closed", pad=14)
    x = chip(x, NODATA)
    caption(x + 3, "No data")

    # stats
    def stat(x, y, label, value, color=TEXT):
        draw.text((x * scale, y * scale), label, font=f_small, fill=MUTED)
        draw.text((x * scale, (y + 13) * scale), value, font=f_value, fill=color)

    green_c, red_c = GREENS[3], REDS[3]
    win_rate = (stats["up"] / stats["traded"] * 100) if stats["traded"] else 0

    stat(18, stats_y, "Green days", str(stats["up"]), green_c)
    stat(100, stats_y, "Red days", str(stats["down"]), red_c)
    stat(176, stats_y, "Win rate", f"{win_rate:.0f}%")
    stat(248, stats_y, "Avg day", f"{stats['avg']:+.2f}%",
         green_c if stats["avg"] >= 0 else red_c)
    stat(330, stats_y, "Days missing", str(stats["missing"]))

    y2 = stats_y + 38
    if stats["best"]:
        stat(18, y2, "Best day",
             f"{stats['best']['pct']:+.2f}%  {stats['best']['date'].strftime('%d %b')}",
             green_c)
    if stats["worst"]:
        stat(176, y2, "Worst day",
             f"{stats['worst']['pct']:+.2f}%  {stats['worst']['date'].strftime('%d %b')}",
             red_c)
    if stats["streak_kind"] in ("up", "down") and stats["streak_len"] > 1:
        stat(330, y2, "Current streak",
             f"{stats['streak_len']} {'green' if stats['streak_kind'] == 'up' else 'red'}",
             green_c if stats["streak_kind"] == "up" else red_c)

    img = img.resize((width, height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


EMOJI = {"up": "\U0001F7E9", "down": "\U0001F7E5", "flat": "\u2B1C",
         "closed": "\u2B1B", "nodata": "\u2B1C"}


def render_text(days, max_weeks=26):
    """Emoji fallback grid - rows are weekdays, columns are weeks."""
    grid_start = days[0]["date"] - dt.timedelta(days=days[0]["date"].weekday())
    grid_end = days[-1]["date"] + dt.timedelta(days=6 - days[-1]["date"].weekday())
    weeks = ((grid_end - grid_start).days + 1) // 7
    if weeks > max_weeks:
        grid_start += dt.timedelta(days=(weeks - max_weeks) * 7)
        weeks = max_weeks

    by_date = {d["date"]: d for d in days}
    lines = []
    for row in range(7):
        cells = []
        for week in range(weeks):
            day = grid_start + dt.timedelta(days=week * 7 + row)
            entry = by_date.get(day)
            cells.append(EMOJI[entry["state"]] if entry else "  ")
        lines.append(WEEKDAY_LABELS[row][:2] + " " + "".join(cells))
    return "\n".join(lines)


def build(arg=""):
    """Convenience: returns (days, stats, start, end) for an argument."""
    returns = load_daily_returns()
    start, end = resolve_range(arg, returns)
    days = build_days(returns, start, end)
    return days, summarize(days), start, end


if __name__ == "__main__":
    import sys

    argument = sys.argv[1] if len(sys.argv) > 1 else ""
    days, stats, start, end = build(argument)
    out = os.path.join(BASE_DIR, "portfolio_heatmap.png")
    with open(out, "wb") as f:
        f.write(render_png(days))
    print(render_text(days))
    print()
    print(f"{start} -> {end}  |  green {stats['up']}  red {stats['down']}  "
          f"avg {stats['avg']:+.2f}%")
    print(f"Saved {out}")
