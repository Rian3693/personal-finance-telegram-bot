"""
News & Analyst Agent
Gathers news, analyst ratings, price targets, and near/far-term predictions
"""
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Any
from research_agents.base_agent import BaseAgent


class NewsAnalystAgent(BaseAgent):
    """Specialist in news analysis and analyst consensus"""
    
    def __init__(self):
        super().__init__(
            name="News & Analyst Agent",
            role="Expert at finding and analyzing financial news, analyst ratings, price targets, and market predictions"
        )
    
    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Gather and analyze news + analyst opinions"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        target_mean = info.get("targetMeanPrice", 0)
        target_high = info.get("targetHighPrice", 0)
        target_low = info.get("targetLowPrice", 0)
        rec = info.get("recommendationKey", "N/A")
        num_analysts = info.get("numberOfAnalystOpinions", 0)
        
        # Get recent news from yfinance
        try:
            ticker = yf.Ticker(symbol)
            news_items = ticker.news[:10] if ticker.news else []
            news_text = "\n".join([
                f"- {n.get('title', 'No title')} ({n.get('publisher', 'Unknown')})"
                for n in news_items
            ]) or "No recent news found"
        except Exception:
            news_items = []
            news_text = "Could not fetch news"
        
        # Use Perplexity for real-time web search of analyst opinions
        perplexity_result = ""
        try:
            perplexity_result = self._call_perplexity(
                f"For the stock {symbol} ({name}), currently at ${price:.2f}:\n"
                f"1. What are the latest analyst ratings and price targets from major banks (Goldman Sachs, JPMorgan, Morgan Stanley, Citi, Bank of America, etc.)?\n"
                f"2. What are the most important recent news stories (last 2 weeks)?\n"
                f"3. What do analysts predict for the NEAR term (1-3 months) and FAR term (6-12 months)?\n"
                f"4. Any upcoming catalysts (earnings dates, product launches, regulatory events)?\n"
                f"Be specific with names, dates, and price targets. Use real data only."
            )
        except Exception as e:
            perplexity_result = f"Perplexity unavailable: {e}"

        # Perplexity deep dive: price drivers, company value proposition, problem it solves
        deep_context = ""
        try:
            deep_context = self._call_perplexity(
                f"For the stock {symbol} ({name}), currently at ${price:.2f}:\n"
                f"Answer ALL of these in detail with specific facts and dates:\n\n"
                f"1. PRICE MOVEMENT (3-6 MONTHS): Why has {symbol} been going up or down over the past 3-6 months? "
                f"What were the KEY EVENTS, earnings surprises, partnerships, product launches, lawsuits, or market shifts "
                f"that drove the price? Give specific dates and percentage moves.\n\n"
                f"2. WHAT DOES THIS COMPANY DO: What is {name}'s core product/service? What does it contribute to its industry "
                f"and to the market? What makes it different from competitors?\n\n"
                f"3. PROBLEM IT SOLVES: What real-world problem does {name} solve RIGHT NOW? "
                f"Is this problem currently urgent or growing? Are there trends (AI, energy, healthcare, etc.) "
                f"that make this problem more important today than before?\n\n"
                f"4. MARKET NEED & URGENCY: How strong is the demand for what {name} offers? "
                f"Is the market for their product growing, stable, or shrinking? "
                f"Are there government contracts, regulations, or industry shifts creating urgency for their solutions?\n\n"
                f"Use real, verifiable data. Include revenue/growth numbers where possible."
            )
        except Exception as e:
            deep_context = f"Deep context unavailable: {e}"
        
        # Synthesize with OpenAI
        summary = ""
        try:
            summary = self._call_openai(
                system_prompt=(
                    "You are a financial news analyst. Synthesize ALL the data into a clear, comprehensive research brief. "
                    "Rate overall analyst sentiment as VERY BULLISH / BULLISH / NEUTRAL / BEARISH / VERY BEARISH. "
                    "Keep it under 600 words. Use bullet points.\n\n"
                    "You MUST include ALL of these sections:\n"
                    "1. ANALYST CONSENSUS & TARGETS\n"
                    "2. KEY NEWS THEMES (last 2 weeks)\n"
                    "3. 📉📈 WHY IT'S BEEN MOVING (3-6 month price drivers with dates)\n"
                    "4. 🏢 WHAT THIS COMPANY DOES & WHY IT MATTERS\n"
                    "5. 🎯 THE PROBLEM IT SOLVES (and how urgent/needed it is right now)\n"
                    "6. NEAR-TERM & FAR-TERM OUTLOOK"
                ),
                user_prompt=(
                    f"Stock: {symbol} ({name}) at ${price:.2f}\n"
                    f"Yahoo analyst consensus: {rec} ({num_analysts} analysts)\n"
                    f"Targets: Low ${target_low} | Mean ${target_mean} | High ${target_high}\n\n"
                    f"Recent headlines:\n{news_text}\n\n"
                    f"Analyst & news research:\n{perplexity_result}\n\n"
                    f"Company deep context (price drivers, value prop, problem it solves):\n{deep_context}"
                ),
                max_tokens=2000
            )
        except Exception as e:
            summary = f"AI synthesis unavailable: {e}"
        
        return {
            "agent": self.name,
            "symbol": symbol,
            "analyst_consensus": rec,
            "num_analysts": num_analysts,
            "targets": {"low": target_low, "mean": target_mean, "high": target_high},
            "recent_news_count": len(news_items),
            "perplexity_research": perplexity_result,
            "summary": summary
        }
