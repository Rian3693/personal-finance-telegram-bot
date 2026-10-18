"""
Peer Comparison Agent
Compares stock against sector peers on valuation, growth, and performance metrics
"""
import yfinance as yf
import numpy as np
from typing import Dict, Any, List
from research_agents.base_agent import BaseAgent


class PeerComparisonAgent(BaseAgent):
    """Specialist in comparing a stock against its sector peers"""

    def __init__(self):
        super().__init__(
            name="Peer Comparison Agent",
            role="Expert at comparing stocks against peers using valuation multiples, growth rates, margins, and relative performance"
        )

    def _get_peer_data(self, peer: str) -> Dict:
        """Fetch key metrics for a peer stock"""
        try:
            t = yf.Ticker(peer)
            info = t.info or {}
            return {
                "symbol": peer,
                "name": info.get("shortName", peer),
                "price": info.get("regularMarketPrice") or info.get("currentPrice", 0),
                "market_cap": info.get("marketCap", 0),
                "pe": info.get("trailingPE", None),
                "forward_pe": info.get("forwardPE", None),
                "ps": info.get("priceToSalesTrailing12Months", None),
                "pb": info.get("priceToBook", None),
                "peg": info.get("pegRatio", None),
                "revenue_growth": info.get("revenueGrowth", None),
                "profit_margin": info.get("profitMargins", None),
                "gross_margin": info.get("grossMargins", None),
                "roe": info.get("returnOnEquity", None),
                "debt_to_equity": info.get("debtToEquity", None),
            }
        except Exception:
            return {"symbol": peer, "error": True}

    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Compare stock against peers"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")

        # Use Perplexity to identify top competitors
        peers_text = ""
        try:
            peers_text = self._call_perplexity(
                f"For the stock {symbol} ({name}), sector: {sector}, industry: {industry}:\n"
                f"1. What are the 4-5 most direct COMPETITORS or COMPARABLE stocks to {symbol}? List only ticker symbols.\n"
                f"2. How does {symbol} compare to these peers in valuation (P/E, P/S, EV/Revenue)?\n"
                f"3. How does {symbol} compare in growth rate (revenue growth, earnings growth)?\n"
                f"4. How does {symbol} compare in profitability (margins, ROE)?\n"
                f"5. Is {symbol} a market leader, challenger, or laggard in its space?\n"
                f"6. Which competitor is the biggest threat and why?\n"
                f"Use real data and specific numbers."
            )
        except Exception as e:
            peers_text = f"Unavailable: {e}"

        # Try to extract peer tickers and fetch data
        # Parse common tickers from the Perplexity response
        peer_data = []
        try:
            # Use GPT to extract just tickers from the Perplexity response
            ticker_extract = self._call_openai(
                system_prompt="Extract ONLY the stock ticker symbols mentioned as competitors. Return ONLY comma-separated tickers, nothing else. Max 5 tickers.",
                user_prompt=f"Text:\n{peers_text}\n\nTarget stock to EXCLUDE: {symbol}",
                max_tokens=50
            )
            peer_tickers = [t.strip().upper() for t in ticker_extract.split(",") if t.strip().isalpha() and t.strip().upper() != symbol][:5]

            for pt in peer_tickers:
                pd = self._get_peer_data(pt)
                if not pd.get("error"):
                    peer_data.append(pd)
        except Exception:
            pass

        # Build comparison table text
        target_metrics = {
            "symbol": symbol,
            "name": name,
            "price": price,
            "market_cap": info.get("marketCap", 0),
            "pe": info.get("trailingPE", None),
            "forward_pe": info.get("forwardPE", None),
            "ps": info.get("priceToSalesTrailing12Months", None),
            "pb": info.get("priceToBook", None),
            "peg": info.get("pegRatio", None),
            "revenue_growth": info.get("revenueGrowth", None),
            "profit_margin": info.get("profitMargins", None),
            "gross_margin": info.get("grossMargins", None),
            "roe": info.get("returnOnEquity", None),
            "debt_to_equity": info.get("debtToEquity", None),
        }

        def fmt(val, pct=False):
            if val is None:
                return "N/A"
            if pct:
                return f"{val*100:.1f}%"
            return f"{val:.2f}"

        def cap_fmt(v):
            if not v:
                return "N/A"
            if v >= 1e12:
                return f"${v/1e12:.1f}T"
            if v >= 1e9:
                return f"${v/1e9:.1f}B"
            return f"${v/1e6:.0f}M"

        comparison_lines = [f"📊 {symbol} (TARGET): Cap {cap_fmt(target_metrics['market_cap'])} | P/E {fmt(target_metrics['pe'])} | P/S {fmt(target_metrics['ps'])} | Growth {fmt(target_metrics['revenue_growth'], True)} | Margin {fmt(target_metrics['profit_margin'], True)}"]
        for p in peer_data:
            comparison_lines.append(
                f"  vs {p['symbol']}: Cap {cap_fmt(p['market_cap'])} | P/E {fmt(p['pe'])} | P/S {fmt(p['ps'])} | Growth {fmt(p['revenue_growth'], True)} | Margin {fmt(p['profit_margin'], True)}"
            )
        comparison_text = "\n".join(comparison_lines)

        # AI synthesis
        summary = ""
        try:
            summary = self._call_openai(
                system_prompt=(
                    "You are a comparative equity analyst. Your job is to determine if a stock is "
                    "CHEAP, FAIR, or EXPENSIVE relative to its peers.\n"
                    "Rate as: 🟢 UNDERVALUED vs PEERS / 🟡 FAIRLY VALUED / 🔴 OVERVALUED vs PEERS\n"
                    "Also rank the target stock vs peers: BEST IN CLASS / ABOVE AVERAGE / AVERAGE / BELOW AVERAGE / WORST IN CLASS\n"
                    "Keep under 400 words. Use bullet points."
                ),
                user_prompt=(
                    f"Stock: {symbol} ({name}) at ${price:.2f}\n"
                    f"Sector: {sector} | Industry: {industry}\n\n"
                    f"PEER COMPARISON:\n{comparison_text}\n\n"
                    f"DETAILED PEER RESEARCH:\n{peers_text}\n\n"
                    f"Analyze: relative valuation, growth premium/discount, competitive position, "
                    f"and whether {symbol} deserves its current multiple."
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
            "peers_analyzed": [p["symbol"] for p in peer_data],
            "target_metrics": target_metrics,
            "peer_data": peer_data,
            "perplexity_research": peers_text,
            "summary": summary
        }
