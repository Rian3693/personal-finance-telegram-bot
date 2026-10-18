"""
Hype Meter Agent
Detects social media buzz, meme status, and whether stock is real value or overhyped
"""
import yfinance as yf
from typing import Dict, Any
from research_agents.base_agent import BaseAgent


class HypeMeterAgent(BaseAgent):
    """Specialist in detecting hype, meme status, and real vs speculative value"""
    
    def __init__(self):
        super().__init__(
            name="Hype Meter Agent",
            role="Expert at gauging social media buzz, retail trader sentiment, meme stock detection, and valuation reality checks"
        )
    
    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Analyze hype level and real vs speculative value"""
        info = stock_data.get("info", {})
        name = info.get("longName", info.get("shortName", symbol))
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        market_cap = info.get("marketCap", 0)
        volume = info.get("averageVolume", 0)
        short_pct = info.get("shortPercentOfFloat", 0)
        beta = info.get("beta", 1)
        pe = info.get("trailingPE", 0)
        forward_pe = info.get("forwardPE", 0)
        ps_ratio = info.get("priceToSalesTrailing12Months", 0)
        pb_ratio = info.get("priceToBook", 0)
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        
        # Hype signals from data
        hype_signals = []
        if pe and pe > 100:
            hype_signals.append(f"Very high P/E: {pe:.1f}")
        if ps_ratio and ps_ratio > 20:
            hype_signals.append(f"Very high P/S: {ps_ratio:.1f}")
        if short_pct and short_pct > 0.15:
            hype_signals.append(f"High short interest: {short_pct*100:.1f}%")
        if beta and beta > 2:
            hype_signals.append(f"High beta: {beta:.2f}")
        if volume and volume > 50_000_000:
            hype_signals.append(f"Very high volume: {volume:,.0f}")
        
        # Use Perplexity to search social buzz
        perplexity_result = ""
        try:
            perplexity_result = self._call_perplexity(
                f"For the stock {symbol} ({name}):\n"
                f"1. How much is {symbol} being discussed on Reddit (r/wallstreetbets, r/stocks), Twitter/X, and StockTwits RIGHT NOW?\n"
                f"2. Is {symbol} considered a 'meme stock' or retail trader favorite? Why or why not?\n"
                f"3. What is the overall retail vs institutional ownership split?\n"
                f"4. Is the current price justified by fundamentals, or is it driven by hype/speculation?\n"
                f"5. Compare to sector peers - is {symbol} overvalued, fairly valued, or undervalued?\n"
                f"6. Any recent viral posts, influencer mentions, or social media catalysts?\n"
                f"Be objective and data-driven."
            )
        except Exception as e:
            perplexity_result = f"Unavailable: {e}"
        
        # AI synthesis
        summary = ""
        try:
            cap_str = f"${market_cap/1e9:.1f}B" if market_cap > 1e9 else f"${market_cap/1e6:.0f}M"
            
            summary = self._call_openai(
                system_prompt=(
                    "You are a stock hype detector and valuation reality-checker. "
                    "Classify the stock into one of these categories:\n"
                    "🎰 MEME/HYPE - Driven by social media, no fundamentals justify price\n"
                    "⚠️ SPECULATIVE - Some fundamentals but priced on future hopes\n"
                    "📊 GROWTH - High valuation justified by real growth trajectory\n"  
                    "💎 REAL VALUE - Fundamentally sound, fairly/under-valued\n"
                    "🏦 BLUE CHIP - Established, stable, institutional favorite\n\n"
                    "Also rate HYPE LEVEL: 🔥🔥🔥🔥🔥 (1-5 flames) and OVERVALUATION RISK: LOW/MEDIUM/HIGH/EXTREME.\n"
                    "Keep under 400 words."
                ),
                user_prompt=(
                    f"Stock: {symbol} ({name}) - {sector} / {industry}\n"
                    f"Price: ${price:.2f} | Market Cap: {cap_str}\n"
                    f"P/E: {pe} | Forward P/E: {forward_pe} | P/S: {ps_ratio} | P/B: {pb_ratio}\n"
                    f"Beta: {beta} | Short%: {short_pct*100 if short_pct else 0:.1f}%\n"
                    f"Avg Volume: {volume:,.0f}\n"
                    f"Hype signals: {', '.join(hype_signals) if hype_signals else 'None detected'}\n\n"
                    f"Social buzz research:\n{perplexity_result}\n\n"
                    f"Classify this stock and assess its real value vs hype."
                ),
                max_tokens=1500
            )
        except Exception as e:
            summary = f"AI synthesis unavailable: {e}"
        
        return {
            "agent": self.name,
            "symbol": symbol,
            "market_cap": market_cap,
            "valuation": {"pe": pe, "forward_pe": forward_pe, "ps": ps_ratio, "pb": pb_ratio},
            "short_interest": short_pct,
            "beta": beta,
            "hype_signals": hype_signals,
            "perplexity_research": perplexity_result,
            "summary": summary
        }
