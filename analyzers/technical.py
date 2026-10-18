"""
Technical Analysis Module - Price action, indicators, and pattern recognition
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import ta
from config import TECHNICAL_INDICATORS, MIN_DATA_POINTS, get_timeframe_config, DEFAULT_TIMEFRAME


class TechnicalAnalyzer:
    """Performs technical analysis on stock price data"""
    
    def __init__(self):
        self.indicators_config = TECHNICAL_INDICATORS
    
    def analyze(self, price_data: Dict[str, Any], timeframe: str = DEFAULT_TIMEFRAME) -> Dict[str, Any]:
        """
        Perform comprehensive technical analysis
        
        Args:
            price_data: Dictionary containing historical price data
            timeframe: Analysis timeframe ('swing', 'short', 'medium', 'long')
        """
        tf_config = get_timeframe_config(timeframe)
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "timeframe": timeframe,
            "timeframe_name": tf_config['name'],
            "indicators": {},
            "signals": {},
            "patterns": {},
            "support_resistance": {},
            "trend_analysis": {},
            "overall_signal": None,
            "score": 0,
            "error": None
        }
        
        try:
            # Get DataFrame from price data
            if price_data.get("historical_df") is not None:
                df = price_data["historical_df"].copy()
            elif price_data.get("historical"):
                df = pd.DataFrame(price_data["historical"])
            else:
                result["error"] = "No historical data available"
                return result
            
            if len(df) < MIN_DATA_POINTS:
                result["error"] = f"Insufficient data points ({len(df)} < {MIN_DATA_POINTS})"
                return result
            
            # Calculate all indicators
            df = self._calculate_indicators(df)
            
            # Get current values
            current = df.iloc[-1]
            current_price = current['Close']
            
            # Technical Indicators
            result["indicators"] = self._get_indicator_values(df)
            
            # Generate signals
            result["signals"] = self._generate_signals(df)
            
            # Identify patterns
            result["patterns"] = self._identify_patterns(df)
            
            # Support and Resistance levels
            result["support_resistance"] = self._calculate_support_resistance(df)
            
            # Trend analysis
            result["trend_analysis"] = self._analyze_trend(df)
            
            # Overall technical score and signal
            result["score"], result["overall_signal"] = self._calculate_overall_score(result)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators"""
        
        # RSI
        df['RSI'] = ta.momentum.RSIIndicator(
            df['Close'], 
            window=self.indicators_config['RSI_PERIOD']
        ).rsi()
        
        # MACD
        macd = ta.trend.MACD(
            df['Close'],
            window_slow=self.indicators_config['MACD_SLOW'],
            window_fast=self.indicators_config['MACD_FAST'],
            window_sign=self.indicators_config['MACD_SIGNAL']
        )
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Histogram'] = macd.macd_diff()
        
        # Moving Averages
        df['SMA_20'] = ta.trend.SMAIndicator(df['Close'], window=20).sma_indicator()
        df['SMA_50'] = ta.trend.SMAIndicator(df['Close'], window=50).sma_indicator()
        df['SMA_200'] = ta.trend.SMAIndicator(df['Close'], window=200).sma_indicator()
        df['EMA_12'] = ta.trend.EMAIndicator(df['Close'], window=12).ema_indicator()
        df['EMA_26'] = ta.trend.EMAIndicator(df['Close'], window=26).ema_indicator()
        
        # Bollinger Bands
        bollinger = ta.volatility.BollingerBands(
            df['Close'],
            window=self.indicators_config['BOLLINGER_PERIOD'],
            window_dev=self.indicators_config['BOLLINGER_STD']
        )
        df['BB_Upper'] = bollinger.bollinger_hband()
        df['BB_Middle'] = bollinger.bollinger_mavg()
        df['BB_Lower'] = bollinger.bollinger_lband()
        df['BB_Width'] = bollinger.bollinger_wband()
        df['BB_Percent'] = bollinger.bollinger_pband()
        
        # Stochastic Oscillator
        stoch = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close'])
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal()
        
        # Average True Range (Volatility)
        df['ATR'] = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close']).average_true_range()
        
        # ADX (Trend Strength)
        adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx.adx()
        df['DI_Plus'] = adx.adx_pos()
        df['DI_Minus'] = adx.adx_neg()
        
        # Volume indicators
        df['Volume_SMA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA']
        
        # OBV (On-Balance Volume)
        df['OBV'] = ta.volume.OnBalanceVolumeIndicator(df['Close'], df['Volume']).on_balance_volume()
        
        # CCI (Commodity Channel Index)
        df['CCI'] = ta.trend.CCIIndicator(df['High'], df['Low'], df['Close']).cci()
        
        # Williams %R
        df['Williams_R'] = ta.momentum.WilliamsRIndicator(df['High'], df['Low'], df['Close']).williams_r()
        
        return df
    
    def _get_indicator_values(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Get current indicator values"""
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        return {
            "rsi": {
                "value": round(current['RSI'], 2) if pd.notna(current['RSI']) else None,
                "signal": self._rsi_signal(current['RSI']),
                "trend": "rising" if current['RSI'] > prev['RSI'] else "falling"
            },
            "macd": {
                "value": round(current['MACD'], 4) if pd.notna(current['MACD']) else None,
                "signal_line": round(current['MACD_Signal'], 4) if pd.notna(current['MACD_Signal']) else None,
                "histogram": round(current['MACD_Histogram'], 4) if pd.notna(current['MACD_Histogram']) else None,
                "signal": self._macd_signal(current, prev)
            },
            "moving_averages": {
                "sma_20": round(current['SMA_20'], 2) if pd.notna(current['SMA_20']) else None,
                "sma_50": round(current['SMA_50'], 2) if pd.notna(current['SMA_50']) else None,
                "sma_200": round(current['SMA_200'], 2) if pd.notna(current['SMA_200']) else None,
                "price_vs_sma20": "above" if current['Close'] > current['SMA_20'] else "below",
                "price_vs_sma50": "above" if current['Close'] > current['SMA_50'] else "below",
                "price_vs_sma200": "above" if current['Close'] > current['SMA_200'] else "below",
            },
            "bollinger_bands": {
                "upper": round(current['BB_Upper'], 2) if pd.notna(current['BB_Upper']) else None,
                "middle": round(current['BB_Middle'], 2) if pd.notna(current['BB_Middle']) else None,
                "lower": round(current['BB_Lower'], 2) if pd.notna(current['BB_Lower']) else None,
                "percent_b": round(current['BB_Percent'], 2) if pd.notna(current['BB_Percent']) else None,
                "signal": self._bollinger_signal(current)
            },
            "stochastic": {
                "k": round(current['Stoch_K'], 2) if pd.notna(current['Stoch_K']) else None,
                "d": round(current['Stoch_D'], 2) if pd.notna(current['Stoch_D']) else None,
                "signal": self._stochastic_signal(current)
            },
            "adx": {
                "value": round(current['ADX'], 2) if pd.notna(current['ADX']) else None,
                "di_plus": round(current['DI_Plus'], 2) if pd.notna(current['DI_Plus']) else None,
                "di_minus": round(current['DI_Minus'], 2) if pd.notna(current['DI_Minus']) else None,
                "trend_strength": self._adx_strength(current['ADX'])
            },
            "volatility": {
                "atr": round(current['ATR'], 2) if pd.notna(current['ATR']) else None,
                "atr_percent": round((current['ATR'] / current['Close']) * 100, 2) if pd.notna(current['ATR']) else None
            },
            "volume": {
                "current": int(current['Volume']) if pd.notna(current['Volume']) else None,
                "avg_20d": int(current['Volume_SMA']) if pd.notna(current['Volume_SMA']) else None,
                "ratio": round(current['Volume_Ratio'], 2) if pd.notna(current['Volume_Ratio']) else None,
                "signal": "high" if current['Volume_Ratio'] > 1.5 else ("low" if current['Volume_Ratio'] < 0.5 else "normal")
            },
            "cci": round(current['CCI'], 2) if pd.notna(current['CCI']) else None,
            "williams_r": round(current['Williams_R'], 2) if pd.notna(current['Williams_R']) else None
        }
    
    def _generate_signals(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate trading signals from indicators"""
        current = df.iloc[-1]
        prev = df.iloc[-2]
        
        signals = {
            "buy_signals": [],
            "sell_signals": [],
            "neutral_signals": []
        }
        
        # RSI signals
        if current['RSI'] < 30:
            signals["buy_signals"].append("RSI oversold (<30)")
        elif current['RSI'] > 70:
            signals["sell_signals"].append("RSI overbought (>70)")
        else:
            signals["neutral_signals"].append("RSI neutral")
        
        # MACD crossover signals
        if prev['MACD'] < prev['MACD_Signal'] and current['MACD'] > current['MACD_Signal']:
            signals["buy_signals"].append("MACD bullish crossover")
        elif prev['MACD'] > prev['MACD_Signal'] and current['MACD'] < current['MACD_Signal']:
            signals["sell_signals"].append("MACD bearish crossover")
        
        # Moving average signals
        if current['Close'] > current['SMA_20'] > current['SMA_50'] > current['SMA_200']:
            signals["buy_signals"].append("Price above all major MAs (bullish alignment)")
        elif current['Close'] < current['SMA_20'] < current['SMA_50'] < current['SMA_200']:
            signals["sell_signals"].append("Price below all major MAs (bearish alignment)")
        
        # Golden/Death cross
        if prev['SMA_50'] < prev['SMA_200'] and current['SMA_50'] > current['SMA_200']:
            signals["buy_signals"].append("Golden Cross (50 SMA crossed above 200 SMA)")
        elif prev['SMA_50'] > prev['SMA_200'] and current['SMA_50'] < current['SMA_200']:
            signals["sell_signals"].append("Death Cross (50 SMA crossed below 200 SMA)")
        
        # Bollinger Band signals
        if current['Close'] < current['BB_Lower']:
            signals["buy_signals"].append("Price below lower Bollinger Band")
        elif current['Close'] > current['BB_Upper']:
            signals["sell_signals"].append("Price above upper Bollinger Band")
        
        # Stochastic signals
        if current['Stoch_K'] < 20 and current['Stoch_D'] < 20:
            signals["buy_signals"].append("Stochastic oversold")
        elif current['Stoch_K'] > 80 and current['Stoch_D'] > 80:
            signals["sell_signals"].append("Stochastic overbought")
        
        # Volume confirmation
        if current['Volume_Ratio'] > 2:
            signals["neutral_signals"].append("Unusually high volume (2x+ average)")
        
        return signals
    
    def _identify_patterns(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Identify chart patterns"""
        patterns = {
            "detected": [],
            "potential": []
        }
        
        recent = df.tail(20)
        
        # Double bottom pattern
        if self._check_double_bottom(recent):
            patterns["detected"].append({
                "name": "Double Bottom",
                "type": "bullish",
                "description": "Potential reversal pattern indicating bullish momentum"
            })
        
        # Double top pattern
        if self._check_double_top(recent):
            patterns["detected"].append({
                "name": "Double Top",
                "type": "bearish",
                "description": "Potential reversal pattern indicating bearish momentum"
            })
        
        # Higher highs and higher lows (uptrend)
        if self._check_uptrend(recent):
            patterns["detected"].append({
                "name": "Uptrend",
                "type": "bullish",
                "description": "Series of higher highs and higher lows"
            })
        
        # Lower highs and lower lows (downtrend)
        if self._check_downtrend(recent):
            patterns["detected"].append({
                "name": "Downtrend",
                "type": "bearish",
                "description": "Series of lower highs and lower lows"
            })
        
        # Consolidation
        if self._check_consolidation(recent):
            patterns["detected"].append({
                "name": "Consolidation",
                "type": "neutral",
                "description": "Price moving sideways, potential breakout incoming"
            })
        
        return patterns
    
    def _calculate_support_resistance(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate support and resistance levels"""
        recent = df.tail(60)  # Last ~3 months
        current_price = df.iloc[-1]['Close']
        
        # Find local minima and maxima
        highs = recent['High'].values
        lows = recent['Low'].values
        
        # Simple pivot points
        pivot = (df.iloc[-1]['High'] + df.iloc[-1]['Low'] + df.iloc[-1]['Close']) / 3
        r1 = 2 * pivot - df.iloc[-1]['Low']
        r2 = pivot + (df.iloc[-1]['High'] - df.iloc[-1]['Low'])
        s1 = 2 * pivot - df.iloc[-1]['High']
        s2 = pivot - (df.iloc[-1]['High'] - df.iloc[-1]['Low'])
        
        # Key price levels from historical data
        support_levels = []
        resistance_levels = []
        
        # Recent swing lows as support
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                if lows[i] < current_price:
                    support_levels.append(round(lows[i], 2))
        
        # Recent swing highs as resistance
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                if highs[i] > current_price:
                    resistance_levels.append(round(highs[i], 2))
        
        # Get unique and sorted levels
        support_levels = sorted(list(set(support_levels)), reverse=True)[:3]
        resistance_levels = sorted(list(set(resistance_levels)))[:3]
        
        return {
            "pivot": round(pivot, 2),
            "resistance_1": round(r1, 2),
            "resistance_2": round(r2, 2),
            "support_1": round(s1, 2),
            "support_2": round(s2, 2),
            "key_support_levels": support_levels,
            "key_resistance_levels": resistance_levels,
            "nearest_support": support_levels[0] if support_levels else round(s1, 2),
            "nearest_resistance": resistance_levels[0] if resistance_levels else round(r1, 2)
        }
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze overall trend"""
        current = df.iloc[-1]
        
        # Short-term trend (20 days)
        short_term = df.tail(20)
        short_trend = "up" if short_term['Close'].iloc[-1] > short_term['Close'].iloc[0] else "down"
        short_change = ((short_term['Close'].iloc[-1] / short_term['Close'].iloc[0]) - 1) * 100
        
        # Medium-term trend (50 days)
        medium_term = df.tail(50)
        medium_trend = "up" if medium_term['Close'].iloc[-1] > medium_term['Close'].iloc[0] else "down"
        medium_change = ((medium_term['Close'].iloc[-1] / medium_term['Close'].iloc[0]) - 1) * 100
        
        # Long-term trend (200 days)
        long_term = df.tail(200) if len(df) >= 200 else df
        long_trend = "up" if long_term['Close'].iloc[-1] > long_term['Close'].iloc[0] else "down"
        long_change = ((long_term['Close'].iloc[-1] / long_term['Close'].iloc[0]) - 1) * 100
        
        # Trend strength using ADX
        adx = current['ADX'] if pd.notna(current['ADX']) else 0
        trend_strength = "strong" if adx > 25 else ("moderate" if adx > 20 else "weak")
        
        # Overall trend determination
        trends = [short_trend, medium_trend, long_trend]
        if trends.count("up") >= 2:
            overall = "bullish"
        elif trends.count("down") >= 2:
            overall = "bearish"
        else:
            overall = "mixed"
        
        return {
            "short_term": {
                "direction": short_trend,
                "change_percent": round(short_change, 2),
                "period": "20 days"
            },
            "medium_term": {
                "direction": medium_trend,
                "change_percent": round(medium_change, 2),
                "period": "50 days"
            },
            "long_term": {
                "direction": long_trend,
                "change_percent": round(long_change, 2),
                "period": f"{len(long_term)} days"
            },
            "trend_strength": trend_strength,
            "adx": round(adx, 2),
            "overall_trend": overall
        }
    
    def _calculate_overall_score(self, analysis: Dict) -> tuple:
        """Calculate overall technical score (-100 to 100)"""
        score = 0
        
        signals = analysis.get("signals", {})
        buy_count = len(signals.get("buy_signals", []))
        sell_count = len(signals.get("sell_signals", []))
        
        # Signal scoring
        score += (buy_count - sell_count) * 15
        
        # Trend scoring
        trend = analysis.get("trend_analysis", {})
        if trend.get("overall_trend") == "bullish":
            score += 20
        elif trend.get("overall_trend") == "bearish":
            score -= 20
        
        # RSI scoring
        indicators = analysis.get("indicators", {})
        rsi = indicators.get("rsi", {}).get("value")
        if rsi:
            if rsi < 30:
                score += 15  # Oversold = potential buy
            elif rsi > 70:
                score -= 15  # Overbought = potential sell
        
        # Pattern scoring
        patterns = analysis.get("patterns", {}).get("detected", [])
        for pattern in patterns:
            if pattern.get("type") == "bullish":
                score += 10
            elif pattern.get("type") == "bearish":
                score -= 10
        
        # Clamp score
        score = max(-100, min(100, score))
        
        # Determine signal
        if score >= 30:
            signal = "STRONG BUY"
        elif score >= 10:
            signal = "BUY"
        elif score <= -30:
            signal = "STRONG SELL"
        elif score <= -10:
            signal = "SELL"
        else:
            signal = "NEUTRAL"
        
        return score, signal
    
    # Helper methods for signals
    def _rsi_signal(self, rsi: float) -> str:
        if pd.isna(rsi):
            return "N/A"
        if rsi < 30:
            return "oversold"
        elif rsi > 70:
            return "overbought"
        else:
            return "neutral"
    
    def _macd_signal(self, current, prev) -> str:
        if pd.isna(current['MACD']) or pd.isna(current['MACD_Signal']):
            return "N/A"
        if current['MACD'] > current['MACD_Signal']:
            if prev['MACD'] <= prev['MACD_Signal']:
                return "bullish crossover"
            return "bullish"
        else:
            if prev['MACD'] >= prev['MACD_Signal']:
                return "bearish crossover"
            return "bearish"
    
    def _bollinger_signal(self, current) -> str:
        if pd.isna(current['BB_Percent']):
            return "N/A"
        if current['BB_Percent'] < 0:
            return "below lower band"
        elif current['BB_Percent'] > 1:
            return "above upper band"
        elif current['BB_Percent'] < 0.2:
            return "near lower band"
        elif current['BB_Percent'] > 0.8:
            return "near upper band"
        return "middle range"
    
    def _stochastic_signal(self, current) -> str:
        if pd.isna(current['Stoch_K']):
            return "N/A"
        if current['Stoch_K'] < 20:
            return "oversold"
        elif current['Stoch_K'] > 80:
            return "overbought"
        return "neutral"
    
    def _adx_strength(self, adx: float) -> str:
        if pd.isna(adx):
            return "N/A"
        if adx < 20:
            return "weak/no trend"
        elif adx < 25:
            return "moderate trend"
        elif adx < 50:
            return "strong trend"
        else:
            return "very strong trend"
    
    # Pattern detection helpers
    def _check_double_bottom(self, df: pd.DataFrame) -> bool:
        lows = df['Low'].values
        min_idx = np.argmin(lows)
        if min_idx > 3 and min_idx < len(lows) - 3:
            left_min = np.min(lows[:min_idx-2])
            right_min = np.min(lows[min_idx+2:])
            if abs(left_min - right_min) / lows[min_idx] < 0.03:
                return True
        return False
    
    def _check_double_top(self, df: pd.DataFrame) -> bool:
        highs = df['High'].values
        max_idx = np.argmax(highs)
        if max_idx > 3 and max_idx < len(highs) - 3:
            left_max = np.max(highs[:max_idx-2])
            right_max = np.max(highs[max_idx+2:])
            if abs(left_max - right_max) / highs[max_idx] < 0.03:
                return True
        return False
    
    def _check_uptrend(self, df: pd.DataFrame) -> bool:
        closes = df['Close'].values
        if len(closes) < 5:
            return False
        higher_highs = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
        return higher_highs > len(closes) * 0.6
    
    def _check_downtrend(self, df: pd.DataFrame) -> bool:
        closes = df['Close'].values
        if len(closes) < 5:
            return False
        lower_lows = sum(1 for i in range(1, len(closes)) if closes[i] < closes[i-1])
        return lower_lows > len(closes) * 0.6
    
    def _check_consolidation(self, df: pd.DataFrame) -> bool:
        closes = df['Close'].values
        if len(closes) < 5:
            return False
        price_range = (np.max(closes) - np.min(closes)) / np.mean(closes)
        return price_range < 0.05  # Less than 5% range


if __name__ == "__main__":
    # Test
    from collectors.stock_data import StockDataCollector
    collector = StockDataCollector()
    data = collector.get_stock_data("AAPL")
    
    analyzer = TechnicalAnalyzer()
    analysis = analyzer.analyze(data["price_data"])
    print(f"Technical Score: {analysis['score']}")
    print(f"Signal: {analysis['overall_signal']}")
