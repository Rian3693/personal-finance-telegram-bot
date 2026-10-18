"""
FinRobot-Inspired Financial Deep Dive Agent
Based on AI4Finance-Foundation/FinRobot's Chain-of-Thought financial analysis methodology.
Performs structured analysis of income statement, balance sheet, cash flow,
SEC filings risk assessment, and valuation metrics.
"""
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any
from research_agents.base_agent import BaseAgent


class FinRobotAgent(BaseAgent):
    """
    FinRobot-style financial deep dive specialist.
    Uses Chain-of-Thought (CoT) prompting for structured financial statement analysis,
    risk assessment, and valuation — inspired by FinRobot's equity research methodology.
    """

    def __init__(self):
        super().__init__(
            name="FinRobot Financial Analyst",
            role="Expert financial analyst performing deep-dive analysis of financial statements, "
                 "valuation metrics, risk factors, and business fundamentals using Chain-of-Thought reasoning"
        )

    def _get_financial_statements(self, symbol: str) -> Dict[str, Any]:
        """Pull income statement, balance sheet, and cash flow from yfinance"""
        try:
            ticker = yf.Ticker(symbol)
            income_stmt = ticker.financials
            balance_sheet = ticker.balance_sheet
            cash_flow = ticker.cashflow
            info = ticker.info or {}

            # Key metrics extraction
            metrics = {}
            if income_stmt is not None and not income_stmt.empty:
                latest = income_stmt.iloc[:, 0]
                prev = income_stmt.iloc[:, 1] if income_stmt.shape[1] > 1 else None
                metrics["revenue"] = latest.get("Total Revenue", 0)
                metrics["gross_profit"] = latest.get("Gross Profit", 0)
                metrics["operating_income"] = latest.get("Operating Income", latest.get("EBIT", 0))
                metrics["net_income"] = latest.get("Net Income", 0)
                metrics["ebitda"] = latest.get("EBITDA", 0)
                if prev is not None:
                    prev_rev = prev.get("Total Revenue", 0)
                    if prev_rev and prev_rev != 0:
                        metrics["revenue_growth"] = (metrics["revenue"] - prev_rev) / abs(prev_rev)
                    prev_ni = prev.get("Net Income", 0)
                    if prev_ni and prev_ni != 0:
                        metrics["earnings_growth"] = (metrics["net_income"] - prev_ni) / abs(prev_ni)

                # Margins
                if metrics["revenue"] and metrics["revenue"] != 0:
                    metrics["gross_margin"] = metrics["gross_profit"] / metrics["revenue"]
                    metrics["operating_margin"] = metrics["operating_income"] / metrics["revenue"]
                    metrics["net_margin"] = metrics["net_income"] / metrics["revenue"]

            if balance_sheet is not None and not balance_sheet.empty:
                bs = balance_sheet.iloc[:, 0]
                metrics["total_assets"] = bs.get("Total Assets", 0)
                metrics["total_liabilities"] = bs.get("Total Liabilities Net Minority Interest",
                                                      bs.get("Total Liab", 0))
                metrics["total_equity"] = bs.get("Stockholders Equity",
                                                 bs.get("Total Stockholder Equity", 0))
                metrics["current_assets"] = bs.get("Current Assets", 0)
                metrics["current_liabilities"] = bs.get("Current Liabilities", 0)
                metrics["total_debt"] = bs.get("Total Debt", bs.get("Long Term Debt", 0))
                metrics["cash"] = bs.get("Cash And Cash Equivalents",
                                         bs.get("Cash", 0))

                if metrics["current_liabilities"] and metrics["current_liabilities"] != 0:
                    metrics["current_ratio"] = metrics["current_assets"] / metrics["current_liabilities"]
                if metrics["total_equity"] and metrics["total_equity"] != 0:
                    metrics["debt_to_equity"] = metrics["total_debt"] / metrics["total_equity"]
                    metrics["roe"] = metrics.get("net_income", 0) / metrics["total_equity"]

            if cash_flow is not None and not cash_flow.empty:
                cf = cash_flow.iloc[:, 0]
                metrics["operating_cf"] = cf.get("Operating Cash Flow",
                                                 cf.get("Total Cash From Operating Activities", 0))
                metrics["investing_cf"] = cf.get("Investing Cash Flow",
                                                 cf.get("Total Cashflows From Investing Activities", 0))
                metrics["financing_cf"] = cf.get("Financing Cash Flow",
                                                 cf.get("Total Cash From Financing Activities", 0))
                metrics["capex"] = cf.get("Capital Expenditure", 0)
                metrics["free_cash_flow"] = cf.get("Free Cash Flow", 0)
                if not metrics["free_cash_flow"]:
                    ocf = metrics.get("operating_cf", 0) or 0
                    capex = metrics.get("capex", 0) or 0
                    metrics["free_cash_flow"] = ocf + capex  # capex is typically negative

            # Additional from info
            metrics["pe_ratio"] = info.get("trailingPE")
            metrics["forward_pe"] = info.get("forwardPE")
            metrics["pb_ratio"] = info.get("priceToBook")
            metrics["ps_ratio"] = info.get("priceToSalesTrailing12Months")
            metrics["ev_to_ebitda"] = info.get("enterpriseToEbitda")
            metrics["ev_to_revenue"] = info.get("enterpriseToRevenue")
            metrics["peg_ratio"] = info.get("pegRatio")
            metrics["dividend_yield"] = info.get("dividendYield")
            metrics["market_cap"] = info.get("marketCap", 0)
            metrics["beta"] = info.get("beta")
            metrics["shares_outstanding"] = info.get("sharesOutstanding", 0)
            metrics["enterprise_value"] = info.get("enterpriseValue", 0)
            metrics["roic"] = info.get("returnOnCapital")

            # FCF yield
            if metrics.get("free_cash_flow") and metrics.get("market_cap") and metrics["market_cap"] != 0:
                metrics["fcf_yield"] = metrics["free_cash_flow"] / metrics["market_cap"]

            return {
                "income_stmt": income_stmt.to_string() if income_stmt is not None and not income_stmt.empty else "N/A",
                "balance_sheet": balance_sheet.to_string() if balance_sheet is not None and not balance_sheet.empty else "N/A",
                "cash_flow": cash_flow.to_string() if cash_flow is not None and not cash_flow.empty else "N/A",
                "metrics": metrics,
                "has_data": bool(metrics.get("revenue"))
            }
        except Exception as e:
            return {"has_data": False, "error": str(e), "metrics": {}, "income_stmt": "N/A", "balance_sheet": "N/A", "cash_flow": "N/A"}

    def _format_metrics_summary(self, m: Dict) -> str:
        """Format key metrics into readable text"""
        def fmt_num(val, is_pct=False, is_money=False, is_ratio=False):
            if val is None:
                return "N/A"
            if is_pct:
                return f"{val * 100:.1f}%"
            if is_money:
                if abs(val) >= 1e12:
                    return f"${val/1e12:.2f}T"
                if abs(val) >= 1e9:
                    return f"${val/1e9:.2f}B"
                if abs(val) >= 1e6:
                    return f"${val/1e6:.1f}M"
                return f"${val:,.0f}"
            if is_ratio:
                return f"{val:.2f}"
            return f"{val:,.0f}"

        lines = [
            "=== INCOME STATEMENT METRICS ===",
            f"Revenue: {fmt_num(m.get('revenue'), is_money=True)}",
            f"Revenue Growth: {fmt_num(m.get('revenue_growth'), is_pct=True)}",
            f"Gross Profit: {fmt_num(m.get('gross_profit'), is_money=True)}",
            f"Gross Margin: {fmt_num(m.get('gross_margin'), is_pct=True)}",
            f"Operating Income: {fmt_num(m.get('operating_income'), is_money=True)}",
            f"Operating Margin: {fmt_num(m.get('operating_margin'), is_pct=True)}",
            f"Net Income: {fmt_num(m.get('net_income'), is_money=True)}",
            f"Net Margin: {fmt_num(m.get('net_margin'), is_pct=True)}",
            f"EBITDA: {fmt_num(m.get('ebitda'), is_money=True)}",
            f"Earnings Growth: {fmt_num(m.get('earnings_growth'), is_pct=True)}",
            "",
            "=== BALANCE SHEET METRICS ===",
            f"Total Assets: {fmt_num(m.get('total_assets'), is_money=True)}",
            f"Total Liabilities: {fmt_num(m.get('total_liabilities'), is_money=True)}",
            f"Stockholders Equity: {fmt_num(m.get('total_equity'), is_money=True)}",
            f"Cash & Equivalents: {fmt_num(m.get('cash'), is_money=True)}",
            f"Total Debt: {fmt_num(m.get('total_debt'), is_money=True)}",
            f"Current Ratio: {fmt_num(m.get('current_ratio'), is_ratio=True)}",
            f"Debt-to-Equity: {fmt_num(m.get('debt_to_equity'), is_ratio=True)}",
            f"ROE: {fmt_num(m.get('roe'), is_pct=True)}",
            "",
            "=== CASH FLOW METRICS ===",
            f"Operating Cash Flow: {fmt_num(m.get('operating_cf'), is_money=True)}",
            f"Free Cash Flow: {fmt_num(m.get('free_cash_flow'), is_money=True)}",
            f"Capital Expenditure: {fmt_num(m.get('capex'), is_money=True)}",
            f"Investing Cash Flow: {fmt_num(m.get('investing_cf'), is_money=True)}",
            f"Financing Cash Flow: {fmt_num(m.get('financing_cf'), is_money=True)}",
            "",
            "=== VALUATION METRICS ===",
            f"Market Cap: {fmt_num(m.get('market_cap'), is_money=True)}",
            f"Enterprise Value: {fmt_num(m.get('enterprise_value'), is_money=True)}",
            f"P/E Ratio: {fmt_num(m.get('pe_ratio'), is_ratio=True)}",
            f"Forward P/E: {fmt_num(m.get('forward_pe'), is_ratio=True)}",
            f"P/B Ratio: {fmt_num(m.get('pb_ratio'), is_ratio=True)}",
            f"P/S Ratio: {fmt_num(m.get('ps_ratio'), is_ratio=True)}",
            f"EV/EBITDA: {fmt_num(m.get('ev_to_ebitda'), is_ratio=True)}",
            f"EV/Revenue: {fmt_num(m.get('ev_to_revenue'), is_ratio=True)}",
            f"PEG Ratio: {fmt_num(m.get('peg_ratio'), is_ratio=True)}",
            f"FCF Yield: {fmt_num(m.get('fcf_yield'), is_pct=True)}",
            f"Dividend Yield: {fmt_num(m.get('dividend_yield'), is_pct=True)}",
            f"Beta: {fmt_num(m.get('beta'), is_ratio=True)}",
        ]
        return "\n".join(lines)

    def _get_sec_risk_analysis(self, symbol: str, name: str) -> str:
        """Use Perplexity to get 10-K risk factors and business overview"""
        try:
            prompt = (
                f"For {name} (ticker: {symbol}), provide a comprehensive analysis based on their latest "
                f"SEC 10-K filing and recent financial reports. Include:\n\n"
                f"1. BUSINESS OVERVIEW: Brief description of the company, key business segments, "
                f"revenue drivers, and competitive moat\n\n"
                f"2. TOP 3 RISK FACTORS from their most recent 10-K filing, with specific details:\n"
                f"   - What the risk is\n"
                f"   - How severe it could be\n"
                f"   - Any mitigating factors\n\n"
                f"3. MANAGEMENT GUIDANCE: Latest forward guidance, revenue/earnings expectations, "
                f"and any notable management commentary\n\n"
                f"4. RECENT MATERIAL EVENTS: Any significant recent developments (acquisitions, "
                f"restructuring, new products, regulatory changes)\n\n"
                f"Be specific with facts, numbers, and dates. Today is {datetime.now().strftime('%Y-%m-%d')}."
            )
            return self._call_perplexity(prompt)
        except Exception as e:
            return f"SEC/Risk analysis unavailable: {e}"

    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Perform full FinRobot-style financial deep dive"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")

        # Step 1: Pull financial statements
        fin_data = self._get_financial_statements(symbol)
        metrics = fin_data["metrics"]

        # Step 2: Get SEC risk analysis via Perplexity
        sec_analysis = self._get_sec_risk_analysis(symbol, name)

        # Step 3: Synthesize using FinRobot's Chain-of-Thought methodology
        metrics_text = self._format_metrics_summary(metrics)

        cot_system_prompt = (
            "You are an expert equity research analyst using Chain-of-Thought (CoT) reasoning "
            "for financial analysis, inspired by FinRobot's methodology. You perform structured, "
            "step-by-step analysis of financial statements to assess a company's financial health, "
            "valuation, and investment potential. Be precise with numbers and percentages."
        )

        cot_user_prompt = (
            f"COMPANY: {name} ({symbol}) | Price: ${price:.2f} | Sector: {sector} | Industry: {industry}\n\n"
            f"FINANCIAL DATA:\n{metrics_text}\n\n"
            f"RAW INCOME STATEMENT (last 4 years):\n{fin_data['income_stmt'][:3000]}\n\n"
            f"RAW BALANCE SHEET:\n{fin_data['balance_sheet'][:3000]}\n\n"
            f"RAW CASH FLOW:\n{fin_data['cash_flow'][:3000]}\n\n"
            f"SEC FILING & RISK ANALYSIS:\n{sec_analysis[:3000]}\n\n"
            f"Perform a FinRobot-style Chain-of-Thought analysis. Work through EACH step:\n\n"
            f"📊 STEP 1 — INCOME STATEMENT ANALYSIS:\n"
            f"- Revenue trend (YoY growth, acceleration/deceleration)\n"
            f"- Profit margins trajectory (gross, operating, net)\n"
            f"- Earnings quality (one-time items vs recurring)\n"
            f"- Key takeaway for this company\n\n"
            f"📋 STEP 2 — BALANCE SHEET HEALTH:\n"
            f"- Liquidity (current ratio, cash position)\n"
            f"- Solvency (debt-to-equity, interest coverage)\n"
            f"- Asset efficiency and capital structure\n"
            f"- Key takeaway\n\n"
            f"💵 STEP 3 — CASH FLOW QUALITY:\n"
            f"- Operating cash flow vs net income (earnings quality check)\n"
            f"- Free cash flow generation and trend\n"
            f"- Capital allocation (capex, buybacks, dividends, debt repayment)\n"
            f"- Key takeaway\n\n"
            f"🏷️ STEP 4 — VALUATION ASSESSMENT:\n"
            f"- Current multiples vs historical average\n"
            f"- Comparison to sector/industry norms\n"
            f"- Is it cheap, fair, or expensive? By how much?\n"
            f"- Key takeaway\n\n"
            f"⚠️ STEP 5 — RISK ASSESSMENT:\n"
            f"- Top 3 financial risks from the data\n"
            f"- Cyclicality and economic sensitivity\n"
            f"- Downside protections in place\n\n"
            f"🏦 FINAL VERDICT:\n"
            f"Financial Health: [STRONG / HEALTHY / ADEQUATE / WEAK / CRITICAL]\n"
            f"Valuation: [DEEPLY UNDERVALUED / UNDERVALUED / FAIR / OVERVALUED / EXTREMELY OVERVALUED]\n"
            f"Overall: One concise paragraph summarizing the financial story, "
            f"key strengths, key risks, and whether the numbers support buying at the current price.\n"
        )

        try:
            analysis = self._call_openai(cot_system_prompt, cot_user_prompt, max_tokens=3000)
        except Exception as e:
            analysis = f"CoT analysis failed: {e}"

        # Build the rating
        rating = self._determine_rating(metrics, analysis)

        summary = (
            f"🏦 FinRobot Financial Deep Dive — {symbol}\n\n"
            f"{analysis}\n\n"
            f"📐 Key Metrics Snapshot:\n"
            f"• Revenue: {self._fmt(metrics.get('revenue'))} ({self._fmt_pct(metrics.get('revenue_growth'))} YoY)\n"
            f"• Net Income: {self._fmt(metrics.get('net_income'))}\n"
            f"• FCF: {self._fmt(metrics.get('free_cash_flow'))}\n"
            f"• Gross Margin: {self._fmt_pct(metrics.get('gross_margin'))}\n"
            f"• Net Margin: {self._fmt_pct(metrics.get('net_margin'))}\n"
            f"• Debt/Equity: {self._fmt_ratio(metrics.get('debt_to_equity'))}\n"
            f"• Current Ratio: {self._fmt_ratio(metrics.get('current_ratio'))}\n"
            f"• P/E: {self._fmt_ratio(metrics.get('pe_ratio'))} | Fwd P/E: {self._fmt_ratio(metrics.get('forward_pe'))}\n"
            f"• EV/EBITDA: {self._fmt_ratio(metrics.get('ev_to_ebitda'))}\n"
            f"• FCF Yield: {self._fmt_pct(metrics.get('fcf_yield'))}\n"
            f"• ROE: {self._fmt_pct(metrics.get('roe'))}\n"
        )

        return {
            "agent": self.name,
            "symbol": symbol,
            "rating": rating,
            "summary": summary,
            "metrics": metrics,
        }

    def _determine_rating(self, metrics: Dict, analysis: str) -> str:
        """Determine overall financial health rating from metrics"""
        score = 0
        checks = 0

        # Revenue growth
        rg = metrics.get("revenue_growth")
        if rg is not None:
            checks += 1
            if rg > 0.15:
                score += 2
            elif rg > 0.05:
                score += 1
            elif rg < -0.05:
                score -= 1

        # Positive net income
        ni = metrics.get("net_income")
        if ni is not None:
            checks += 1
            if ni > 0:
                score += 1
            else:
                score -= 1

        # Gross margin
        gm = metrics.get("gross_margin")
        if gm is not None:
            checks += 1
            if gm > 0.50:
                score += 2
            elif gm > 0.30:
                score += 1
            elif gm < 0.20:
                score -= 1

        # Current ratio
        cr = metrics.get("current_ratio")
        if cr is not None:
            checks += 1
            if cr > 2.0:
                score += 1
            elif cr < 1.0:
                score -= 1

        # Debt/equity
        de = metrics.get("debt_to_equity")
        if de is not None:
            checks += 1
            if de < 0.5:
                score += 1
            elif de > 2.0:
                score -= 1

        # Positive FCF
        fcf = metrics.get("free_cash_flow")
        if fcf is not None:
            checks += 1
            if fcf > 0:
                score += 1
            else:
                score -= 1

        # ROE
        roe = metrics.get("roe")
        if roe is not None:
            checks += 1
            if roe > 0.15:
                score += 1
            elif roe < 0:
                score -= 1

        if checks == 0:
            return "⚪ INSUFFICIENT DATA"

        pct = score / (checks * 2)  # normalize to -0.5 to 1.0 range
        if pct >= 0.6:
            return "🟢 STRONG FINANCIALS"
        elif pct >= 0.3:
            return "🟢 HEALTHY FINANCIALS"
        elif pct >= 0.0:
            return "🟡 ADEQUATE FINANCIALS"
        elif pct >= -0.3:
            return "🟠 WEAK FINANCIALS"
        else:
            return "🔴 CONCERNING FINANCIALS"

    @staticmethod
    def _fmt(val):
        if val is None:
            return "N/A"
        if abs(val) >= 1e12:
            return f"${val/1e12:.2f}T"
        if abs(val) >= 1e9:
            return f"${val/1e9:.2f}B"
        if abs(val) >= 1e6:
            return f"${val/1e6:.1f}M"
        return f"${val:,.0f}"

    @staticmethod
    def _fmt_pct(val):
        if val is None:
            return "N/A"
        return f"{val * 100:.1f}%"

    @staticmethod
    def _fmt_ratio(val):
        if val is None:
            return "N/A"
        return f"{val:.2f}"
