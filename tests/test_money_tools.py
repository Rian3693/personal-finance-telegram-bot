"""Smaller money tools: the euro fund, financial independence, pension, tax year, Visa cycle, categories."""
from datetime import date

import pytest

import categories as cat
import eur_fund as ef
import expenses as ex
import fi
import pension
import taxyear


class TestEurFund:
    def test_deposits_and_withdrawals_are_logged(self):
        data = {}
        ef.deposit(data, 500, date(2027, 1, 11), "monthly")
        ef.deposit(data, -200, date(2027, 2, 1), "converted")
        assert ef.balance(data) == 300.0
        assert [e["balance_after"] for e in data["eur_fund"]["log"]] == [500.0, 300.0]

    def test_setting_the_bank_balance_logs_the_difference(self):
        data = {"eur_fund": {"balance": 300.0, "log": []}}
        ef.set_balance(data, 312.4, date(2027, 3, 1))
        assert ef.balance(data) == 312.4 and data["eur_fund"]["log"][-1]["amount"] == 12.4


class TestFinancialIndependence:
    def test_fi_number_is_annual_spend_over_four_percent(self):
        assert fi.fi_number(120000) == 3_000_000

    def test_months_to_a_target_without_growth(self):
        assert fi.months_to(220000, 100000, 10000, 0.0) == 12
        assert fi.months_to(100, 200, 0, 0.05) == 0

    def test_income_loss_drawn_from_the_emergency_fund(self):
        w = fi.whatif(10000, 6000, 1000, 20000, 100, 3)
        assert w["from_fund"] == 18000 and w["fund_left"] == 2000 and w["runs_out_month"] is None
        assert fi.whatif(10000, 6000, 1000, 10000, 100, 3)["runs_out_month"] == 2


def test_pension_projection_without_growth():
    assert round(pension.project(85000, 1800, 40, 0.0)) == 949000


def test_pension_reminder_once_a_quarter():
    assert pension.due_reminder({}, date(2027, 1, 15))[0]
    assert not pension.due_reminder({"reminded": "2027-Q1"}, date(2027, 1, 20))[0]
    assert not pension.due_reminder({}, date(2027, 2, 15))[0]


def test_tax_year_counts_this_years_sales_and_paper_losses():
    portfolio = {"sold_history": [{"sell_date": "2026-03-01", "profit_loss": 500.0, "tax_withheld": 100.0},
                                  {"sell_date": "2026-10-14", "profit_loss": -1781.0},
                                  {"sell_date": "2025-12-01", "profit_loss": 900.0}],
                 "holdings": [{"symbol": "AAA", "shares": 10, "purchase_price": 50.0},
                              {"symbol": "BBB", "shares": 5, "purchase_price": 10.0}]}
    s = taxyear.summary(portfolio, {"AAA": 40.0, "BBB": 20.0}, 2026)
    assert s["sales"] == 2 and s["net"] == -1281 and s["withheld"] == 100
    assert s["paper"] == [("AAA", -100.0)]


@pytest.mark.parametrize("today, charge", [(date(2026, 11, 5), date(2026, 11, 10)),
                                           (date(2026, 11, 10), date(2026, 11, 10)),
                                           (date(2026, 11, 11), date(2026, 12, 10))])
def test_next_visa_charge_date(today, charge):
    assert ex.next_charge_date(today) == charge


def test_reserved_visa_purchases_are_not_charged_twice():
    entries = [{"card": "visa", "amount": 100.0, "reserved": True},
               {"card": "visa", "amount": 50.0},
               {"card": "debit", "amount": 70.0}]
    assert [ex.is_reserved(e) for e in entries] == [True, False, False]


class TestCategories:
    def test_paths_split_into_category_and_sub_category(self):
        assert cat.split_path("תחבורה › מונית") == ("תחבורה", "מונית")
        assert cat.split_path("תחבורה") == ("תחבורה", None)

    def test_a_store_is_remembered_after_one_classification(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cat, "FILE", str(tmp_path / "categories.json"))
        data = cat.load()
        cat.learn(data, "Carrefour", "סופר ומכולת")
        assert cat.remembered(data, {"store": "  carrefour "}) == "סופר ומכולת"
        assert cat.remembered(data, {"store": "Unknown shop"}) is None
