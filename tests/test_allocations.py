"""/allocated: parsing what was really moved, and what should be left in the checking account."""
import pytest

import allocations as al

ILS_STEP = {"key": "ILS_EMERGENCY", "ils": 1000.0, "ccy": "ILS"}
USD_STEP = {"key": "USD_STOCKS", "ils": 3700.0, "ccy": "USD"}


def test_shekel_amount():
    assert al.parse_amount("1,200", ILS_STEP)["ils"] == 1200.0


def test_dollars_with_their_rate_in_one_answer():
    got = al.parse_actual("$1,000 3.70", USD_STEP)
    assert got["foreign"] == 1000.0 and got["ils"] == 3700.0 and got["rate_source"] == "yours"


def test_shekels_converted_at_the_market_rate_when_no_rate_is_typed():
    got = al.parse_actual("3700", USD_STEP, market_rate=3.70)
    assert got["foreign"] == 1000.0 and got["rate_source"] == "market"


@pytest.mark.parametrize("text", ["394 34", "394 0.5"])
def test_impossible_exchange_rates_are_refused(text):
    with pytest.raises(ValueError):
        al.parse_amount(text, USD_STEP)


def test_euro_share_is_a_shekel_step():
    steps = al.suggestion_steps({"split": {"ILS_EMERGENCY": 100, "ILS_FUTURE": 0, "EUR": 50, "USD_STOCKS": 0}})
    eur = next(s for s in steps if s["key"] == "EUR")
    assert eur["ccy"] == "ILS" and eur["ils"] == 50.0


def test_checking_left_after_the_moves_and_the_bank_fee():
    payment = {"amount": 9000.0, "checking_before": 500.0, "refill": 2000.0}
    steps = [ILS_STEP, USD_STEP]
    actual = {"ILS_EMERGENCY": {"ils": 1000.0}, "USD_STOCKS": {"ils": 3700.0}}
    calc = al.checking_left(payment, steps, actual)
    assert calc["start"] == 9500.0
    assert calc["fee"] == 5.0                                # something went to the ILS bank
    assert calc["expected"] == 9500.0 - 4700.0 - 5.0
    assert calc["target"] == 2500.0


def test_an_overdrawn_balance_can_be_reported():
    assert al.parse_balance("-120") == -120.0
