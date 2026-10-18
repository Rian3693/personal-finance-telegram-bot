"""
Insider & Institutional Activity Agent
Tracks insider buying/selling, institutional ownership changes, and short interest
"""
import yfinance as yf
import requests
from typing import Dict, Any
from config import FINNHUB_API_KEY
from research_agents.base_agent import BaseAgent


class InsiderInstitutionalAgent(BaseAgent):
    """Specialist in insider transactions, institutional ownership, and short interest"""

    def __init__(self):
        super().__init__(
            name="Insider & Institutional Agent",
            role="Expert at tracking insider buys/sells, institutional ownership changes, short interest, and smart money flows"
        )

    def _get_finnhub_insiders(self, symbol: str) -> str:
        """Fetch insider transactions from Finnhub"""
        if not FINNHUB_API_KEY:
            return ""
        try:
            resp = requests.get(
                "https://finnhub.io/api/v1/stock/insider-transactions",
                params={"symbol": symbol, "token": FINNHUB_API_KEY},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])[:15]
            if not data:
                return "No recent insider transactions found"
            lines = []
            for t in data:
                name = t.get("name", "Unknown")
                shares = t.get("share", 0)
                tx_type = t.get("transactionType", "")
                date = t.get("transactionDate", "")
                price = t.get("transactionPrice", 0)
                action = "BUY" if "Purchase" in tx_type or "Buy" in tx_type else "SELL" if "Sale" in tx_type else tx_type
                lines.append(f"  {date} | {name} | {action} | {shares:,.0f} shares @ ${price:.2f}" if price else
                             f"  {date} | {name} | {action} | {shares:,.0f} shares")
            return "\n".join(lines)
        except Exception as e:
            return f"Finnhub error: {e}"

    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Analyze insider and institutional activity"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)

        # yfinance data
        inst_pct = info.get("heldPercentInstitutions", 0)
        insider_pct = info.get("heldPercentInsiders", 0)
        short_pct = info.get("shortPercentOfFloat", 0)
        short_ratio = info.get("shortRatio", 0)
        float_shares = info.get("floatShares", 0)
        shares_short = info.get("sharesShort", 0)

        # Finnhub insider transactions
        insider_txns = self._get_finnhub_insiders(symbol)

        # Major holders from yfinance
        holders_text = ""
        try:
            ticker = yf.Ticker(symbol)
            inst_holders = ticker.institutional_holders
            if inst_holders is not None and not inst_holders.empty:
                top5 = inst_holders.head(5)
                holders_text = "\n".join([
                    f"  {row.get('Holder', 'Unknown')}: {row.get('Shares', 0):,.0f} shares ({row.get('pctHeld', 0)*100:.1f}%)"
                    for _, row in top5.iterrows()
                ])
        except Exception:
            holders_text = "Could not fetch institutional holders"

        # Perplexity for latest insider/institutional news
        perplexity_result = ""
        try:
            perplexity_result = self._call_perplexity(
                f"For the stock {symbol} ({name}), currently at ${price:.2f}:\n"
                f"1. Have any INSIDERS (CEO, CFO, directors, officers) bought or sold shares in the last 3 months? Details.\n"
                f"2. Have any major HEDGE FUNDS or INSTITUTIONAL investors recently increased or decreased their position? (13F filings)\n"
                f"3. What is the current SHORT INTEREST? Is it increasing or decreasing? Any short squeeze potential?\n"
                f"4. Are there any insider lockup expirations or secondary offerings coming up?\n"
                f"5. Is smart money buying or selling? What does the institutional flow look like?\n"
                f"Use specific names, dates, and share amounts. Only real data."
            )
        except Exception as e:
            perplexity_result = f"Unavailable: {e}"

        # AI synthesis
        data_block = (
            f"Institutional Ownership: {inst_pct*100:.1f}%\n"
            f"Insider Ownership: {insider_pct*100:.1f}%\n"
            f"Short % of Float: {short_pct*100:.1f}%\n"
            f"Short Ratio (days to cover): {short_ratio:.1f}\n"
            f"Shares Short: {shares_short:,.0f}\n"
            f"Float: {float_shares:,.0f}\n\n"
            f"TOP INSTITUTIONAL HOLDERS:\n{holders_text}\n\n"
            f"RECENT INSIDER TRANSACTIONS (Finnhub):\n{insider_txns}"
        )

        summary = ""
        try:
            summary = self._call_openai(
                system_prompt=(
                    "You are an expert at reading insider and institutional activity to predict stock moves. "
                    "Analyze smart money flows and rate the signal as:\n"
                    "🟢 STRONG BULLISH (insiders accumulating, institutions increasing)\n"
                    "🟡 NEUTRAL (mixed signals)\n"
                    "🔴 BEARISH (insiders dumping, institutions fleeing)\n\n"
                    "Also comment on short squeeze potential if short interest is high.\n"
                    "Keep under 400 words. Use bullet points."
                ),
                user_prompt=(
                    f"Stock: {symbol} ({name}) at ${price:.2f}\n\n"
                    f"OWNERSHIP DATA:\n{data_block}\n\n"
                    f"WEB RESEARCH:\n{perplexity_result}\n\n"
                    f"Analyze: insider sentiment, institutional conviction, short squeeze risk, "
                    f"and what smart money is telling us."
                ),
                max_tokens=1500
            )
        except Exception as e:
            summary = f"AI synthesis unavailable: {e}"

        return {
            "agent": self.name,
            "symbol": symbol,
            "institutional_pct": inst_pct,
            "insider_pct": insider_pct,
            "short_pct": short_pct,
            "short_ratio": short_ratio,
            "insider_transactions": insider_txns,
            "perplexity_research": perplexity_result,
            "summary": summary
        }
