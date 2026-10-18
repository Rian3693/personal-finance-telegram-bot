"""
Technical Analysis Agent - Calculates technical indicators
SMA, RSI, MACD, Bollinger Bands, ADX, CCI
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional


class TechnicalAnalysisAgent:
    """
    Agent responsible for calculating technical indicators.
    Indicators: SMA, EMA, RSI, MACD, Bollinger Bands, ADX, CCI
    """
    
    def __init__(self):
        self.name = "Technical Analysis Agent"
    
    async def analyze(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate technical indicators from market data.
        
        Args:
            market_data: Dict containing historical price data
            
        Returns:
            Dict with technical indicators
        """
        try:
            hist = market_data.get('history')
            if hist is None or hist.empty:
                return {
                    'success': False,
                    'error': 'No historical data available'
                }
            
            # Ensure we have a DataFrame
            df = hist if isinstance(hist, pd.DataFrame) else pd.DataFrame(hist)
            
            if len(df) < 20:
                return {
                    'success': False,
                    'error': f'Insufficient data: need at least 20 days, got {len(df)}'
                }
            
            current_price = float(df['Close'].iloc[-1])
            
            # Calculate all indicators
            indicators = {
                'SMA': self._calculate_sma(df),
                'EMA': self._calculate_ema(df),
                'RSI': self._calculate_rsi(df),
                'MACD': self._calculate_macd(df),
                'BBANDS': self._calculate_bollinger_bands(df),
                'ADX': self._calculate_adx(df),
                'CCI': self._calculate_cci(df)
            }
            
            # Generate interpretations
            interpretations = self._generate_interpretations(indicators, current_price)
            
            return {
                'symbol': market_data.get('symbol', 'Unknown'),
                'current_price': current_price,
                'indicators': indicators,
                'interpretations': interpretations,
                'success': True
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _calculate_sma(self, df: pd.DataFrame, periods: list = [5, 10, 20, 50]) -> Dict:
        """Calculate Simple Moving Averages"""
        sma = {}
        for period in periods:
            if len(df) >= period:
                sma[f'SMA_{period}'] = float(df['Close'].rolling(window=period).mean().iloc[-1])
        return sma
    
    def _calculate_ema(self, df: pd.DataFrame, periods: list = [12, 26]) -> Dict:
        """Calculate Exponential Moving Averages"""
        ema = {}
        for period in periods:
            if len(df) >= period:
                ema[f'EMA_{period}'] = float(df['Close'].ewm(span=period, adjust=False).mean().iloc[-1])
        return ema
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(df) < period + 1:
            return None
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None
    
    def _calculate_macd(self, df: pd.DataFrame) -> Dict:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if len(df) < 26:
            return {'macd': None, 'signal': None, 'histogram': None}
        
        ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
        
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': float(macd_line.iloc[-1]),
            'signal': float(signal_line.iloc[-1]),
            'histogram': float(histogram.iloc[-1])
        }
    
    def _calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Dict:
        """Calculate Bollinger Bands"""
        if len(df) < period:
            return {'upper': None, 'middle': None, 'lower': None}
        
        middle = df['Close'].rolling(window=period).mean()
        std = df['Close'].rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return {
            'upper': float(upper.iloc[-1]),
            'middle': float(middle.iloc[-1]),
            'lower': float(lower.iloc[-1])
        }
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average Directional Index"""
        if len(df) < period * 2:
            return None
        
        high = df['High']
        low = df['Low']
        close = df['Close']
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
        
        # Smoothed TR and DM
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
        
        # ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.ewm(span=period, adjust=False).mean()
        
        return float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else None
    
    def _calculate_cci(self, df: pd.DataFrame, period: int = 20) -> float:
        """Calculate Commodity Channel Index"""
        if len(df) < period:
            return None
        
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        sma_tp = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        
        cci = (tp - sma_tp) / (0.015 * mad)
        
        return float(cci.iloc[-1]) if not pd.isna(cci.iloc[-1]) else None
    
    def _generate_interpretations(self, indicators: Dict, current_price: float) -> Dict:
        """Generate human-readable interpretations of indicators"""
        interpretations = {}
        
        # SMA interpretation
        sma = indicators.get('SMA', {})
        sma_20 = sma.get('SMA_20')
        if sma_20:
            if current_price > sma_20:
                interpretations['sma'] = f"Price ${current_price:.2f} is ABOVE SMA-20 (${sma_20:.2f}) - Bullish"
            else:
                interpretations['sma'] = f"Price ${current_price:.2f} is BELOW SMA-20 (${sma_20:.2f}) - Bearish"
        
        # RSI interpretation
        rsi = indicators.get('RSI')
        if rsi:
            if rsi > 70:
                interpretations['rsi'] = f"RSI {rsi:.1f} - OVERBOUGHT (>70)"
            elif rsi < 30:
                interpretations['rsi'] = f"RSI {rsi:.1f} - OVERSOLD (<30)"
            else:
                interpretations['rsi'] = f"RSI {rsi:.1f} - Neutral range"
        
        # MACD interpretation
        macd = indicators.get('MACD', {})
        if macd.get('histogram'):
            hist = macd['histogram']
            if hist > 0:
                interpretations['macd'] = f"MACD Histogram {hist:.4f} - Bullish momentum"
            else:
                interpretations['macd'] = f"MACD Histogram {hist:.4f} - Bearish momentum"
        
        # Bollinger Bands interpretation
        bb = indicators.get('BBANDS', {})
        if bb.get('upper') and bb.get('lower'):
            if current_price > bb['upper']:
                interpretations['bbands'] = f"Price ABOVE upper band (${bb['upper']:.2f}) - Overbought"
            elif current_price < bb['lower']:
                interpretations['bbands'] = f"Price BELOW lower band (${bb['lower']:.2f}) - Oversold"
            else:
                interpretations['bbands'] = f"Price within bands (${bb['lower']:.2f} - ${bb['upper']:.2f})"
        
        # ADX interpretation
        adx = indicators.get('ADX')
        if adx:
            if adx > 25:
                interpretations['adx'] = f"ADX {adx:.1f} - Strong trend"
            else:
                interpretations['adx'] = f"ADX {adx:.1f} - Weak/No trend"
        
        # CCI interpretation
        cci = indicators.get('CCI')
        if cci:
            if cci > 100:
                interpretations['cci'] = f"CCI {cci:.1f} - Overbought (>100)"
            elif cci < -100:
                interpretations['cci'] = f"CCI {cci:.1f} - Oversold (<-100)"
            else:
                interpretations['cci'] = f"CCI {cci:.1f} - Neutral range"
        
        return interpretations
