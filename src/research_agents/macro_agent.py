"""
Macro & Sector Agent
Analyzes macroeconomic conditions, sector rotation, interest rate impact, and economic cycle context
"""
import yfinance as yf
from typing import Dict, Any
from research_agents.base_agent import BaseAgent


class MacroSectorAgent(BaseAgent):
    """Specialist in macro-economic analysis and sector trends"""

    def __init__(self):
        super().__init__(
            name="Macro & Sector Agent",
            role="Expert at analyzing macroeconomic conditions, interest rate impact, sector rotation, and how the economic cycle affects specific stocks"
        )

    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Analyze macro and sector context"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        beta = info.get("beta", 1)
        market_cap = info.get("marketCap", 0)

        # Get sector ETF performance for context
        sector_etfs = {
            "Technology": "XLK", "Communication Services": "XLC",
            "Healthcare": "XLV", "Financial Services": "XLF", "Financials": "XLF",
            "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
            "Energy": "XLE", "Industrials": "XLI", "Basic Materials": "XLB",
            "Real Estate": "XLRE", "Utilities": "XLU",
        }
        sector_etf = sector_etfs.get(sector, "SPY")
        
        sector_perf = ""
        try:
            etf = yf.Ticker(sector_etf)
            etf_hist = etf.history(period="3mo")
            if not etf_hist.empty and len(etf_hist) >= 2:
                etf_return = ((etf_hist['Close'].iloc[-1] / etf_hist['Close'].iloc[0]) - 1) * 100
                sector_perf = f"Sector ETF ({sector_etf}) 3-month return: {etf_return:.1f}%"
            
            # SPY for market context
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="3mo")
            if not spy_hist.empty and len(spy_hist) >= 2:
                spy_return = ((spy_hist['Close'].iloc[-1] / spy_hist['Close'].iloc[0]) - 1) * 100
                sector_perf += f"\nS&P 500 (SPY) 3-month return: {spy_return:.1f}%"
        except Exception:
            sector_perf = "Could not fetch sector performance"

        # Perplexity for macro analysis
        perplexity_result = ""
        try:
            perplexity_result = self._call_perplexity(
                f"Analyze the MACROECONOMIC environment for investing in {symbol} ({name}), "
                f"sector: {sector}, industry: {industry}:\n"
                f"1. Current interest rate environment - is the Fed raising, cutting, or holding? How does this affect {sector} stocks?\n"
                f"2. Where are we in the ECONOMIC CYCLE? (expansion, peak, recession, recovery) How does this affect {symbol}?\n"
                f"3. Is there sector ROTATION happening? Is money flowing INTO or OUT OF {sector}?\n"
                f"4. What are the biggest MACRO RISKS right now? (inflation, geopolitics, recession, tariffs, etc.)\n"
                f"5. What MACRO TAILWINDS could benefit {symbol}?\n"
                f"6. Are there any GOVERNMENT POLICIES, regulation changes, or subsidy programs that affect {industry}?\n"
                f"Use current real data and specific numbers. Include dates."
            )
        except Exception as e:
            perplexity_result = f"Unavailable: {e}"

        # AI synthesis
        cap_str = f"${market_cap/1e9:.1f}B" if market_cap > 1e9 else f"${market_cap/1e6:.0f}M"
        summary = ""
        try:
            summary = self._call_openai(
                system_prompt=(
                    "You are a macro-economic strategist who advises on how the big picture affects individual stocks. "
                    "Rate the MACRO ENVIRONMENT for this stock as:\n"
                    "🟢 FAVORABLE (macro tailwinds, sector in favor)\n"
                    "🟡 NEUTRAL (mixed macro signals)\n"
                    "🔴 UNFAVORABLE (macro headwinds, sector out of favor)\n\n"
                    "Also assess SECTOR MOMENTUM: STRONG / MODERATE / WEAK\n"
                    "Keep under 400 words. Use bullet points."
                ),
                user_prompt=(
                    f"Stock: {symbol} ({name}) at ${price:.2f} | {cap_str}\n"
                    f"Sector: {sector} | Industry: {industry} | Beta: {beta}\n\n"
                    f"MARKET PERFORMANCE:\n{sector_perf}\n\n"
                    f"MACRO RESEARCH:\n{perplexity_result}\n\n"
                    f"Analyze: economic cycle impact, interest rate sensitivity, sector rotation positioning, "
                    f"policy tailwinds/headwinds, and macro risk assessment."
                ),
                max_tokens=1500
            )
        except Exception as e:
            summary = f"AI synthesis unavailable: {e}"

        return {
            "agent": self.name,
            "symbol": symbol,
            "sector": sector,
            "industry": industry,
            "sector_etf": sector_etf,
            "beta": beta,
            "sector_performance": sector_perf,
            "perplexity_research": perplexity_result,
            "summary": summary
        }
