"""Which broker holds which shares: Interactive Brokers or the bank's app.

A holding stays one record per symbol (average price, total cost) and carries a
'brokers' map of shares per broker. Holdings from before Interactive have no
map: all their shares are at the bank. Each broker also has its own USD cash:
the bank's is the long-standing 'free_cash', Interactive's is 'ibkr_cash'.
"""

IBKR = 'IBKR'
BANK = 'BANK'
BROKERS = (IBKR, BANK)
LABEL = {IBKR: 'Interactive Brokers', BANK: 'אפליקציית הבנק'}
SHORT = {IBKR: '🌐 Interactive', BANK: '🏦 בנק'}
CASH_KEY = {IBKR: 'ibkr_cash', BANK: 'free_cash'}
_EPS = 1e-6


class NeedBroker(Exception):
    """The symbol is held at both brokers, so a sale has to say which."""


def split(holding):
    """Shares per broker. Whatever the map does not account for is at the bank."""
    shares = float((holding or {}).get('shares') or 0)
    raw = (holding or {}).get('brokers') or {}
    out = {b: max(0.0, float(raw.get(b, 0) or 0)) for b in BROKERS}
    out[IBKR] = min(out[IBKR], shares)
    out[BANK] = max(0.0, shares - out[IBKR])
    return out


def where(holding):
    """Brokers that hold some of this symbol."""
    return [b for b, n in split(holding).items() if n > _EPS]


def after_buy(holding, broker, shares):
    """The map once `shares` more are bought at `broker` (holding may be None)."""
    out = split(holding) if holding else {b: 0.0 for b in BROKERS}
    out[broker] = out[broker] + float(shares)
    return _tidy(out)


def after_sell(holding, shares, broker=None):
    """(map once `shares` are sold, broker they were sold at).

    Without a broker: the one that holds the symbol, or NeedBroker if both do.
    Raises ValueError when that broker does not hold enough.
    """
    have = split(holding)
    if broker is None:
        held = where(holding)
        if len(held) > 1:
            raise NeedBroker(have)
        broker = held[0] if held else BANK
    if float(shares) > have[broker] + _EPS:
        raise ValueError('ב-%s יש רק %g מניות' % (SHORT[broker], round(have[broker], 6)))
    have[broker] = max(0.0, have[broker] - float(shares))
    return _tidy(have), broker


def _tidy(out):
    return {b: round(n, 6) for b, n in out.items() if n > _EPS}


def value_split(holdings, price_of):
    """USD market value per broker; price_of(holding) gives the price to use."""
    totals = {b: 0.0 for b in BROKERS}
    for holding in holdings or []:
        price = float(price_of(holding) or 0)
        for b, n in split(holding).items():
            totals[b] += n * price
    return totals


def cash(portfolio_data):
    """USD cash per broker."""
    return {b: float(portfolio_data.get(CASH_KEY[b], 0) or 0) for b in BROKERS}
