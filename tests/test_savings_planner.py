"""The savings plan: allocation parsing, the payment breakdown and the monthly projection."""
import pytest

import savings_planner as sp

FX = {"USDILS": 3.70, "EURILS": 4.00}
SPLIT = {"ILS_EMERGENCY": 30.0, "ILS_FUTURE": 20.0, "EUR": 10.0, "USD_STOCKS": 40.0}
CFG = {"target": 2500.0, "monthly_spend": 1500.0}


class TestParseAllocation:
    def test_four_numbers_in_bucket_order(self):
        assert sp.parse_allocation(["30", "20", "20", "30"]) == {
            "ILS_EMERGENCY": 30.0, "ILS_FUTURE": 20.0, "EUR": 20.0, "USD_STOCKS": 30.0}

    def test_named_buckets_fill_the_rest_with_zero(self):
        assert sp.parse_allocation(["emg=30", "usd=70"]) == {
            "ILS_EMERGENCY": 30.0, "ILS_FUTURE": 0.0, "EUR": 0.0, "USD_STOCKS": 70.0}

    @pytest.mark.parametrize("tokens", [["60", "60", "0", "0"], ["0", "0", "0", "0"], ["xyz=10"], ["30", "20"]])
    def test_invalid_splits_are_rejected(self, tokens):
        with pytest.raises(ValueError):
            sp.parse_allocation(tokens)


def test_split_amount_never_loses_a_shekel_to_rounding():
    split, unallocated = sp.split_amount(1000.01, {"ILS_EMERGENCY": 33.3, "ILS_FUTURE": 33.3, "EUR": 33.4})
    assert round(sum(split.values()) + unallocated, 2) == 1000.01


class TestPaymentBreakdown:
    def test_order_refill_then_keren_then_split_with_one_bank_fee(self):
        bd = sp.payment_breakdown(9000, SPLIT, 1000.0, dict(CFG, keren_self=1000))
        assert bd["refill"] == 1500.0                     # checking topped up to its 2,500 target
        assert bd["keren_self"] == 1000.0                 # fixed deposit before the percentages
        assert bd["base"] == 6500.0
        assert bd["fee"] == sp.ILS_TRANSFER_FEE           # one transfer covers both ILS funds
        moved = bd["refill"] + bd["excess"] + bd["keren_self"] + sum(bd["split"].values()) + bd["fee"]
        assert round(moved + bd["unallocated"], 2) == 9000.0

    def test_unused_spending_budget_goes_to_future_expenses_not_the_split(self):
        bd = sp.payment_breakdown(9000, SPLIT, 2500.0, dict(CFG))   # checking already full
        assert bd["refill"] == 0 and bd["excess"] == 1500.0
        # ...and the one bank fee comes off whichever ILS fund receives more (here: future expenses)
        assert bd["split"]["ILS_FUTURE"] == pytest.approx(1500.0 + 0.20 * 7500.0 - sp.ILS_TRANSFER_FEE)
        assert bd["split"]["USD_STOCKS"] == pytest.approx(0.40 * 7500.0)

    def test_a_payment_smaller_than_the_refill_saves_nothing(self):
        bd = sp.payment_breakdown(800, SPLIT, 0.0, dict(CFG))
        assert bd["refill"] == 800 and bd["short"] and sum(bd["split"].values()) == 0


class TestProjection:
    PLAN = {"salary": {"amount": 9000.0}, "months": {"2027-01": dict(SPLIT), "2027-02": dict(SPLIT)},
            "float": {"mode": "fixed", "target": 2500.0, "monthly_spend": 1500.0}}

    def test_balances_grow_month_by_month(self):
        start = {b: 0.0 for b in sp.BUCKETS}
        start[sp.CHECKING] = 1000.0
        steps = sp.project_timeline(self.PLAN, start, FX, ["2027-01", "2027-02"])
        assert [s["month"] for s in steps] == ["2027-01", "2027-02"]
        assert steps[1]["balances"]["ILS_EMERGENCY"] > steps[0]["balances"]["ILS_EMERGENCY"] > 0

    def test_a_month_can_carry_its_own_income(self):
        plan = dict(self.PLAN, month_income={"2027-02": 12000.0})
        steps = sp.project_timeline(plan, {sp.CHECKING: 1000.0}, FX, ["2027-01", "2027-02"])
        assert steps[1]["base"] - steps[0]["base"] == pytest.approx(3000.0, abs=1500.0)
        assert steps[1]["base"] > steps[0]["base"]

    def test_euro_share_is_held_in_shekels_and_counted_in_euros(self):
        start = {sp.CHECKING: 2500.0, sp.EUR_FUND: 400.0, "EUR": 100.0}
        step = sp.project_timeline(self.PLAN, start, FX, ["2027-01"])[0]
        put = step["split_ils"]["EUR"]
        assert step["eur_fund"] == pytest.approx(400.0 + put)
        assert step["balances"]["EUR"] == pytest.approx(100.0 + put / FX["EURILS"])

    def test_skipped_months_are_not_projected(self):
        assert sp.project_timeline(self.PLAN, {}, FX, ["2027-03"]) == []


def test_goal_lines_report_what_is_left():
    lines = sp.goal_lines({"goals": {"ILS_EMERGENCY": 40000}}, {"ILS_EMERGENCY": 30000})
    assert len(lines) == 1 and "₪10,000.00 to go" in lines[0] and "75%" in lines[0]
