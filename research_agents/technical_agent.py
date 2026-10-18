"""
Technical Insight Agent
Chart analysis, momentum, support/resistance, and pattern recognition
"""
import yfinance as yf
import numpy as np
from typing import Dict, Any
from research_agents.base_agent import BaseAgent


class TechnicalInsightAgent(BaseAgent):
    """Specialist in technical chart analysis"""
    
    def __init__(self):
        super().__init__(
            name="Technical Insight Agent",
            role="Expert at reading charts, identifying patterns, momentum, support/resistance levels"
        )
    
    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Perform technical analysis"""
        info = stock_data.get("info", {})
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        
        technicals = {}
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="6mo")
            
            if hist.empty or len(hist) < 20:
                return {"agent": self.name, "symbol": symbol, "summary": "Insufficient data for technical analysis"}
            
            close = hist['Close'].values
            volume = hist['Volume'].values
            high = hist['High'].values
            low = hist['Low'].values
            
            # Moving averages
            sma_20 = np.mean(close[-20:])
            sma_50 = np.mean(close[-50:]) if len(close) >= 50 else None
            sma_200 = np.mean(close[-200:]) if len(close) >= 200 else None
            
            # RSI
            deltas = np.diff(close[-15:])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains) if len(gains) > 0 else 0
            avg_loss = np.mean(losses) if len(losses) > 0 else 0.001
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            # MACD
            ema_12 = self._ema(close, 12)
            ema_26 = self._ema(close, 26)
            macd_line = ema_12 - ema_26
            signal_line = self._ema_from_array(np.array([ema_12 - ema_26 for _ in range(9)]), 9) if len(close) > 26 else 0
            
            # Bollinger Bands
            bb_sma = np.mean(close[-20:])
            bb_std = np.std(close[-20:])
            bb_upper = bb_sma + 2 * bb_std
            bb_lower = bb_sma - 2 * bb_std
            
            # Support/Resistance (simple pivot-based)
            recent_low = np.min(low[-20:])
            recent_high = np.max(high[-20:])
            pivot = (recent_high + recent_low + close[-1]) / 3
            support_1 = 2 * pivot - recent_high
            resistance_1 = 2 * pivot - recent_low
            
            # Volume trend
            avg_vol_20 = np.mean(volume[-20:])
            avg_vol_5 = np.mean(volume[-5:])
            vol_trend = "Above average" if avg_vol_5 > avg_vol_20 * 1.2 else "Below average" if avg_vol_5 < avg_vol_20 * 0.8 else "Normal"
            
            # Price momentum
            pct_1w = ((close[-1] / close[-5]) - 1) * 100 if len(close) >= 5 else 0
            pct_1m = ((close[-1] / close[-21]) - 1) * 100 if len(close) >= 21 else 0
            pct_3m = ((close[-1] / close[-63]) - 1) * 100 if len(close) >= 63 else 0
            
            # Trend determination
            trend = "UPTREND" if close[-1] > sma_20 and (sma_50 is None or sma_20 > sma_50) else \
                    "DOWNTREND" if close[-1] < sma_20 and (sma_50 is None or sma_20 < sma_50) else "SIDEWAYS"
            
            technicals = {
                "price": round(price, 2),
                "sma_20": round(sma_20, 2),
                "sma_50": round(sma_50, 2) if sma_50 else "N/A",
                "rsi": round(rsi, 1),
                "macd": round(macd_line, 2),
                "bollinger": {"upper": round(bb_upper, 2), "lower": round(bb_lower, 2)},
                "support": round(support_1, 2),
                "resistance": round(resistance_1, 2),
                "volume_trend": vol_trend,
                "momentum": {"1w": round(pct_1w, 1), "1m": round(pct_1m, 1), "3m": round(pct_3m, 1)},
                "trend": trend
            }
        except Exception as e:
            technicals["error"] = str(e)
        
        # AI synthesis
        tech_text = "\n".join([f"  {k}: {v}" for k, v in technicals.items()])
        summary = ""
        try:
            summary = self._call_openai(
                system_prompt=(
                    "You are a technical chart analyst. Provide a clear technical assessment. "
                    "Rate the technical setup as: STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL. "
                    "Include key levels to watch. Keep under 300 words."
                ),
                user_prompt=(
                    f"Stock: {symbol} at ${price:.2f}\n\n"
                    f"Technical indicators:\n{tech_text}\n\n"
                    f"Provide: trend assessment, momentum analysis, key support/resistance to watch, "
                    f"entry/exit signals, and risk level."
                ),
                max_tokens=1200
            )
        except Exception as e:
            summary = f"AI synthesis unavailable: {e}"
        
        return {
            "agent": self.name,
            "symbol": symbol,
            "technicals": technicals,
            "summary": summary
        }
    
    def _ema(self, data, period):
        """Calculate EMA for the latest value"""
        if len(data) < period:
            return np.mean(data)
        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])
        for val in data[period:]:
            ema = (val - ema) * multiplier + ema
        return ema
    
    def _ema_from_array(self, data, period):
        """Calculate EMA from an array"""
        return self._ema(data, period)
