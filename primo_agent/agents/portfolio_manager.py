"""
Portfolio Manager Agent - Generates trading signals (BUY/SELL/HOLD)
Integrates technical analysis and news intelligence for decision-making
"""
import os
from typing import Dict, Any, Optional
from datetime import datetime

# Try to import OpenAI for LLM analysis
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class PortfolioManagerAgent:
    """
    Agent responsible for generating trading signals.
    Outputs: BUY/SELL/HOLD with confidence level and position size
    """
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.name = "Portfolio Manager Agent"
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
    
    async def analyze(
        self,
        symbol: str,
        technical_data: Dict[str, Any],
        news_data: Dict[str, Any],
        company_info: Dict[str, Any] = None,
        basic_financials: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate trading signal based on all available data.
        
        Args:
            symbol: Stock ticker symbol
            technical_data: Output from Technical Analysis Agent
            news_data: Output from News Intelligence Agent
            company_info: Company information
            basic_financials: Financial metrics
            
        Returns:
            Dict with trading_signal, confidence_level, position_size, reasoning
        """
        try:
            # Extract key metrics
            current_price = technical_data.get('current_price', 0)
            indicators = technical_data.get('indicators', {})
            interpretations = technical_data.get('interpretations', {})
            nlp_features = news_data.get('nlp_features', {})
            
            # Use LLM if available, otherwise use rule-based
            if self.api_key and HAS_OPENAI:
                result = await self._analyze_with_llm(
                    symbol, current_price, indicators, interpretations,
                    nlp_features, company_info, basic_financials
                )
            else:
                result = self._analyze_rule_based(
                    symbol, current_price, indicators, nlp_features
                )
            
            return {
                'success': True,
                'symbol': symbol,
                'current_price': current_price,
                'trading_signal': result['trading_signal'],
                'confidence_level': result['confidence_level'],
                'position_size': result['position_size'],
                'reasoning': result['reasoning'],
                'analysis_date': datetime.now().strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            return {
                'success': False,
                'symbol': symbol,
                'error': str(e)
            }
    
    def _analyze_rule_based(
        self,
        symbol: str,
        current_price: float,
        indicators: Dict[str, Any],
        nlp_features: Dict[str, float]
    ) -> Dict[str, Any]:
        """Rule-based trading signal generation"""
        
        score = 0  # -10 to +10 scale
        reasons = []
        
        # === Technical Analysis Scoring ===
        
        # 1. SMA Analysis
        sma = indicators.get('SMA', {})
        sma_20 = sma.get('SMA_20')
        sma_50 = sma.get('SMA_50')
        
        if sma_20 and current_price > sma_20:
            score += 1
            reasons.append("Price above SMA-20 (+1)")
        elif sma_20:
            score -= 1
            reasons.append("Price below SMA-20 (-1)")
        
        if sma_20 and sma_50 and sma_20 > sma_50:
            score += 1
            reasons.append("Golden cross pattern (+1)")
        elif sma_20 and sma_50:
            score -= 1
            reasons.append("Death cross pattern (-1)")
        
        # 2. RSI Analysis
        rsi = indicators.get('RSI')
        if rsi:
            if rsi < 30:
                score += 2
                reasons.append(f"RSI oversold at {rsi:.1f} (+2)")
            elif rsi > 70:
                score -= 2
                reasons.append(f"RSI overbought at {rsi:.1f} (-2)")
            elif 40 <= rsi <= 60:
                reasons.append(f"RSI neutral at {rsi:.1f}")
        
        # 3. MACD Analysis
        macd = indicators.get('MACD', {})
        histogram = macd.get('histogram')
        if histogram is not None:
            if histogram > 0:
                score += 1
                reasons.append("MACD histogram positive (+1)")
            else:
                score -= 1
                reasons.append("MACD histogram negative (-1)")
        
        # 4. Bollinger Bands
        bb = indicators.get('BBANDS', {})
        if bb.get('lower') and current_price < bb['lower']:
            score += 1.5
            reasons.append("Price below lower BB (+1.5)")
        elif bb.get('upper') and current_price > bb['upper']:
            score -= 1.5
            reasons.append("Price above upper BB (-1.5)")
        
        # 5. ADX Trend Strength
        adx = indicators.get('ADX')
        if adx:
            if adx > 25:
                reasons.append(f"Strong trend (ADX={adx:.1f})")
            else:
                reasons.append(f"Weak trend (ADX={adx:.1f})")
        
        # === News/Sentiment Scoring ===
        
        sentiment = nlp_features.get('sentiment', 0)
        price_impact = nlp_features.get('price_impact_potential', 0)
        trend_direction = nlp_features.get('trend_direction', 0)
        investor_confidence = nlp_features.get('investor_confidence', 0)
        
        # Combined news score (weighted)
        news_score = (
            sentiment * 0.3 +
            price_impact * 0.3 +
            trend_direction * 0.2 +
            investor_confidence * 0.2
        )
        
        score += news_score * 2  # Scale news contribution
        
        if news_score > 0.5:
            reasons.append(f"Positive news sentiment (+{news_score*2:.1f})")
        elif news_score < -0.5:
            reasons.append(f"Negative news sentiment ({news_score*2:.1f})")
        
        # === Generate Signal ===
        
        if score >= 3:
            signal = "BUY"
            confidence = min(0.9, 0.5 + (score / 20))
        elif score <= -3:
            signal = "SELL"
            confidence = min(0.9, 0.5 + (abs(score) / 20))
        else:
            signal = "HOLD"
            confidence = 0.5 + (abs(score) / 30)
        
        # Position sizing based on confidence
        if confidence >= 0.8:
            position_size = 80
        elif confidence >= 0.7:
            position_size = 60
        elif confidence >= 0.6:
            position_size = 40
        else:
            position_size = 20
        
        reasoning = f"Technical score: {score:.1f}/10. " + " | ".join(reasons[:5])
        
        return {
            'trading_signal': signal,
            'confidence_level': round(confidence, 2),
            'position_size': position_size,
            'reasoning': reasoning
        }
    
    async def _analyze_with_llm(
        self,
        symbol: str,
        current_price: float,
        indicators: Dict[str, Any],
        interpretations: Dict[str, str],
        nlp_features: Dict[str, float],
        company_info: Dict[str, Any] = None,
        basic_financials: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Use OpenAI to generate trading signal"""
        try:
            client = OpenAI(api_key=self.api_key)
            
            # Format technical indicators
            tech_summary = []
            for key, interp in interpretations.items():
                tech_summary.append(f"- {interp}")
            tech_text = "\n".join(tech_summary) if tech_summary else "No technical data"
            
            # Format news features
            news_text = "\n".join([
                f"- Sentiment: {nlp_features.get('sentiment', 0):.1f}",
                f"- Price Impact Potential: {nlp_features.get('price_impact_potential', 0):.1f}",
                f"- Trend Direction: {nlp_features.get('trend_direction', 0):.1f}",
                f"- Investor Confidence: {nlp_features.get('investor_confidence', 0):.1f}",
                f"- Risk Profile Change: {nlp_features.get('risk_profile_change', 0):.1f}"
            ])
            
            # Company context
            company_text = ""
            if company_info:
                company_text = f"Company: {company_info.get('name', symbol)} | Industry: {company_info.get('industry', 'Unknown')}"
            
            prompt = f"""You are a quantitative portfolio manager. Analyze this data and provide a trading recommendation.

Symbol: {symbol}
Current Price: ${current_price:.2f}
{company_text}

TECHNICAL ANALYSIS:
{tech_text}

NEWS INTELLIGENCE (scale -2 to +2):
{news_text}

Based on this analysis, provide:
1. trading_signal: BUY, SELL, or HOLD
2. confidence_level: 0.0 to 1.0
3. position_size: 10, 20, 30, 40, 50, 60, 70, 80, 90, or 100 (% of portfolio)
4. reasoning: Brief explanation (1-2 sentences)

Return ONLY valid JSON with these 4 fields."""

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.3
            )
            
            # Parse response
            import json
            result_text = response.choices[0].message.content.strip()
            
            # Clean up response if needed
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            # Validate
            signal = result.get('trading_signal', 'HOLD').upper()
            if signal not in ['BUY', 'SELL', 'HOLD']:
                signal = 'HOLD'
            
            confidence = max(0.0, min(1.0, float(result.get('confidence_level', 0.5))))
            position = int(result.get('position_size', 20))
            if position not in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
                position = 20
            
            return {
                'trading_signal': signal,
                'confidence_level': confidence,
                'position_size': position,
                'reasoning': result.get('reasoning', 'Analysis complete.')
            }
            
        except Exception as e:
            print(f"LLM analysis failed: {e}, falling back to rule-based")
            return self._analyze_rule_based(symbol, current_price, indicators, nlp_features)
