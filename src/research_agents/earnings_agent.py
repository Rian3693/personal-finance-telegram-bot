"""
Earnings & Report Agent
Deep-dives into financial reports, earnings quality, revenue trends, and guidance
"""
import yfinance as yf
from typing import Dict, Any
from research_agents.base_agent import BaseAgent


class EarningsReportAgent(BaseAgent):
    """Specialist in reading and evaluating earnings reports and financials"""
    
    def __init__(self):
        super().__init__(
            name="Earnings Report Agent",
            role="Expert at analyzing earnings reports, financial statements, revenue trends, margins, and management guidance"
        )
    
    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Analyze earnings and financial reports"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        
        # Extract financial data from yfinance
        financials = {}
        try:
            ticker = yf.Ticker(symbol)
            
            # Income statement
            inc = ticker.quarterly_income_stmt
            if inc is not None and not inc.empty:
                latest_q = inc.iloc[:, 0]
                prev_q = inc.iloc[:, 1] if inc.shape[1] > 1 else None
                year_ago_q = inc.iloc[:, 3] if inc.shape[1] > 3 else None
                
                rev = latest_q.get("Total Revenue", 0)
                net_income = latest_q.get("Net Income", 0)
                gross_profit = latest_q.get("Gross Profit", 0)
                
                financials["latest_revenue"] = float(rev) if rev else 0
                financials["latest_net_income"] = float(net_income) if net_income else 0
                financials["gross_margin"] = (float(gross_profit) / float(rev) * 100) if rev and gross_profit else 0
                
                if year_ago_q is not None:
                    yago_rev = year_ago_q.get("Total Revenue", 0)
                    if yago_rev and float(yago_rev) > 0:
                        financials["revenue_growth_yoy"] = ((float(rev) - float(yago_rev)) / float(yago_rev)) * 100
            
            # Key ratios from info
            financials["pe_ratio"] = info.get("trailingPE", "N/A")
            financials["forward_pe"] = info.get("forwardPE", "N/A")
            financials["peg_ratio"] = info.get("pegRatio", "N/A")
            financials["profit_margin"] = info.get("profitMargins", 0)
            financials["revenue_growth"] = info.get("revenueGrowth", 0)
            financials["earnings_growth"] = info.get("earningsGrowth", 0)
            financials["debt_to_equity"] = info.get("debtToEquity", "N/A")
            financials["free_cash_flow"] = info.get("freeCashflow", 0)
            financials["eps_trailing"] = info.get("trailingEps", "N/A")
            financials["eps_forward"] = info.get("forwardEps", "N/A")
            
            # Earnings history
            try:
                eh = ticker.earnings_history
                if eh is not None and not eh.empty:
                    recent = eh.tail(4)
                    beats = sum(1 for _, r in recent.iterrows() if r.get("epsActual", 0) > r.get("epsEstimate", 0))
                    financials["earnings_beats_last_4q"] = f"{beats}/4"
            except Exception:
                pass
                
        except Exception as e:
            financials["error"] = str(e)
        
        # Format financials for AI
        fin_text = "\n".join([f"  {k}: {v}" for k, v in financials.items()])
        
        # Use Perplexity for latest earnings report details
        perplexity_result = ""
        try:
            perplexity_result = self._call_perplexity(
                f"For {symbol} ({name}):\n"
                f"1. What were the results of the MOST RECENT earnings report? (revenue, EPS, beat/miss estimates?)\n"
                f"2. What guidance did management provide for next quarter/year?\n"
                f"3. What did the CEO/CFO say on the earnings call about growth outlook?\n"
                f"4. Are margins improving or declining? Why?\n"
                f"5. Any concerns raised by analysts after the report?\n"
                f"Be specific with actual numbers, dates, and quotes."
            )
        except Exception as e:
            perplexity_result = f"Unavailable: {e}"
        
        # AI synthesis
        summary = ""
        try:
            summary = self._call_openai(
                system_prompt=(
                    "You are a financial analyst who specializes in reading earnings reports. "
                    "Evaluate the earnings quality and financial health. "
                    "Rate as: EXCELLENT / GOOD / MIXED / WEAK / POOR. "
                    "Keep under 400 words. Use bullet points."
                ),
                user_prompt=(
                    f"Stock: {symbol} ({name}) at ${price:.2f}\n\n"
                    f"Financial metrics:\n{fin_text}\n\n"
                    f"Latest earnings research:\n{perplexity_result}\n\n"
                    f"Analyze: earnings quality, revenue trajectory, margin trends, "
                    f"management credibility, balance sheet health, and forward outlook."
                ),
                max_tokens=1500
            )
        except Exception as e:
            summary = f"AI synthesis unavailable: {e}"
        
        return {
            "agent": self.name,
            "symbol": symbol,
            "financials": financials,
            "perplexity_research": perplexity_result,
            "summary": summary
        }
