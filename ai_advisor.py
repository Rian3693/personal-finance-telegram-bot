"""
AI Advisor Module - Uses OpenAI to generate intelligent analysis and recommendations
"""
import openai
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from config import OPENAI_API_KEY


class AIAdvisor:
    """Uses AI to synthesize data and generate investment recommendations"""
    
    def __init__(self):
        self.client = None
        if OPENAI_API_KEY:
            self.client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        self.model = "gpt-4o"  # Use GPT-4o for best analysis
    
    def generate_analysis(self, stock_data: Dict, technical: Dict, fundamental: Dict, 
                         sentiment: Dict, symbol: str, timeframe: str = "short",
                         analyst_ratings: Dict = None) -> Dict[str, Any]:
        """
        Generate comprehensive AI-powered analysis and recommendation
        
        Args:
            timeframe: Analysis timeframe ('swing', 'short', 'medium', 'long')
            analyst_ratings: Institutional analyst ratings from major banks
        """
        from config import get_timeframe_config
        tf_config = get_timeframe_config(timeframe)
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "executive_summary": "",
            "investment_thesis": "",
            "entry_price_recommendation": {},
            "stop_loss": {},
            "valuation_assessment": {},
            "price_targets": {
                "short_term": {"period": "1-3 months", "target": None, "low": None, "high": None, "confidence": None},
                "medium_term": {"period": "3-12 months", "target": None, "low": None, "high": None, "confidence": None},
                "long_term": {"period": "1-5 years", "target": None, "low": None, "high": None, "confidence": None}
            },
            "institutional_consensus": {},
            "price_outlook": {},
            "bull_case": [],  # Top 3 strengths with data support
            "bear_case": [],  # Top 3 concerns with potential impact
            "risk_factors": {
                "company_specific": [],  # Operational, competitive, management risks
                "market_sector": [],     # Economic, industry, regulatory risks
                "overall_level": "medium" # low/medium/high
            },
            "risk_assessment": {},
            "key_factors": [],
            "recommendation": "",
            "confidence_level": "",
            "error": None
        }
        
        if not self.client:
            result["error"] = "OpenAI API key not configured"
            result["executive_summary"] = self._generate_fallback_analysis(
                stock_data, technical, fundamental, sentiment
            )
            # Still calculate entry/stop-loss from technical data
            result.update(self._calculate_entry_stoploss(stock_data, technical))
            result["valuation_assessment"] = self._calculate_valuation(fundamental)
            return result
        
        try:
            # Prepare context for AI
            context = self._prepare_context(stock_data, technical, fundamental, sentiment, analyst_ratings)
            
            # Generate main analysis with timeframe-specific price targets
            analysis = self._call_ai_analysis(context, symbol, timeframe, tf_config)
            
            if analysis:
                result.update(analysis)
            
            # Add institutional consensus if available
            if analyst_ratings:
                result["institutional_consensus"] = analyst_ratings.get("consensus", {})
            
        except Exception as e:
            result["error"] = str(e)
            result["executive_summary"] = self._generate_fallback_analysis(
                stock_data, technical, fundamental, sentiment
            )
        
        return result
    
    def _calculate_entry_stoploss(self, stock_data: Dict, technical: Dict) -> Dict:
        """Calculate entry price and stop-loss from technical data"""
        result = {"entry_price_recommendation": {}, "stop_loss": {}}
        
        price_data = stock_data.get("price_data", {})
        current_price = price_data.get("current_price")
        
        if not current_price or not technical:
            return result
        
        support = technical.get("support_resistance", {}).get("nearest_support")
        resistance = technical.get("support_resistance", {}).get("nearest_resistance")
        
        if support and resistance:
            # Entry price recommendation
            price_range = resistance - support
            ideal_entry = support + (price_range * 0.15)
            
            result["entry_price_recommendation"] = {
                "ideal_entry": round(ideal_entry, 2),
                "acceptable_range_low": round(support, 2),
                "acceptable_range_high": round(support + (price_range * 0.35), 2),
                "current_vs_ideal": "good" if current_price <= ideal_entry * 1.05 else "wait for pullback"
            }
            
            # Stop-loss calculation
            stop_loss_tight = support * 0.97  # 3% below support
            stop_loss_normal = support * 0.95  # 5% below support
            stop_loss_wide = support * 0.92  # 8% below support
            
            result["stop_loss"] = {
                "tight": round(stop_loss_tight, 2),
                "normal": round(stop_loss_normal, 2),
                "wide": round(stop_loss_wide, 2),
                "recommended": round(stop_loss_normal, 2),
                "support_level": round(support, 2),
                "risk_from_current": round(((current_price - stop_loss_normal) / current_price) * 100, 1)
            }
        
        return result
    
    def _calculate_valuation(self, fundamental: Dict) -> Dict:
        """Calculate valuation assessment from fundamentals"""
        if not fundamental:
            return {"status": "unknown", "reason": "No fundamental data"}
        
        valuation = fundamental.get("valuation", {})
        
        scores = []
        details = []
        
        # PE Ratio assessment
        pe = valuation.get("pe_ratio", {})
        if pe.get("value") and pe.get("sector_benchmark"):
            pe_val = pe["value"]
            benchmark = pe["sector_benchmark"]
            if pe_val < benchmark * 0.7:
                scores.append(2)  # Undervalued
                details.append(f"P/E ({pe_val:.1f}) significantly below sector ({benchmark})")
            elif pe_val < benchmark * 0.9:
                scores.append(1)
                details.append(f"P/E ({pe_val:.1f}) below sector average ({benchmark})")
            elif pe_val > benchmark * 1.3:
                scores.append(-2)  # Overvalued
                details.append(f"P/E ({pe_val:.1f}) significantly above sector ({benchmark})")
            elif pe_val > benchmark * 1.1:
                scores.append(-1)
                details.append(f"P/E ({pe_val:.1f}) above sector average ({benchmark})")
            else:
                scores.append(0)
                details.append(f"P/E ({pe_val:.1f}) in line with sector ({benchmark})")
        
        # PEG Ratio assessment
        peg = valuation.get("peg_ratio", {})
        if peg.get("value"):
            peg_val = peg["value"]
            if peg_val < 1:
                scores.append(2)
                details.append(f"PEG ratio ({peg_val:.2f}) < 1 suggests undervalued vs growth")
            elif peg_val < 1.5:
                scores.append(1)
                details.append(f"PEG ratio ({peg_val:.2f}) reasonable for growth")
            elif peg_val > 2:
                scores.append(-1)
                details.append(f"PEG ratio ({peg_val:.2f}) > 2 suggests overvalued")
            else:
                scores.append(0)
        
        # Price to Book assessment
        pb = valuation.get("price_to_book", {})
        if pb.get("value"):
            pb_val = pb["value"]
            if pb_val < 1:
                scores.append(2)
                details.append(f"P/B ({pb_val:.2f}) < 1 - trading below book value")
            elif pb_val < 3:
                scores.append(1)
            elif pb_val > 10:
                scores.append(-1)
                details.append(f"P/B ({pb_val:.2f}) very high")
            else:
                scores.append(0)
        
        # Price target assessment
        target_analysis = valuation.get("price_target_analysis", {})
        upside = target_analysis.get("upside_potential")
        if upside:
            if upside > 30:
                scores.append(2)
                details.append(f"Analysts see {upside:.1f}% upside - significantly undervalued")
            elif upside > 15:
                scores.append(1)
                details.append(f"Analysts see {upside:.1f}% upside")
            elif upside < -15:
                scores.append(-2)
                details.append(f"Trading {abs(upside):.1f}% above analyst targets - overvalued")
            elif upside < 0:
                scores.append(-1)
                details.append(f"Trading {abs(upside):.1f}% above analyst targets")
            else:
                scores.append(0)
        
        # Calculate overall assessment
        if not scores:
            return {"status": "unknown", "reason": "Insufficient valuation data"}
        
        avg_score = sum(scores) / len(scores)
        
        if avg_score >= 1.5:
            status = "significantly_undervalued"
            label = "Significantly Undervalued"
        elif avg_score >= 0.5:
            status = "undervalued"
            label = "Undervalued"
        elif avg_score <= -1.5:
            status = "significantly_overvalued"
            label = "Significantly Overvalued"
        elif avg_score <= -0.5:
            status = "overvalued"
            label = "Overvalued"
        else:
            status = "fairly_valued"
            label = "Fairly Valued"
        
        return {
            "status": status,
            "label": label,
            "score": round(avg_score, 2),
            "details": details,
            "metrics_analyzed": len(scores)
        }
    
    def _prepare_context(self, stock_data: Dict, technical: Dict, 
                        fundamental: Dict, sentiment: Dict,
                        analyst_ratings: Dict = None) -> str:
        """Prepare analysis context for AI"""
        
        context_parts = []
        
        # Company info
        company_info = stock_data.get("company_info", {})
        if company_info:
            context_parts.append(f"""
COMPANY INFORMATION:
- Name: {company_info.get('name', 'N/A')}
- Sector: {company_info.get('sector', 'N/A')}
- Industry: {company_info.get('industry', 'N/A')}
""")
        
        # Price data
        price_data = stock_data.get("price_data", {})
        if price_data:
            context_parts.append(f"""
PRICE DATA:
- Current Price: ${price_data.get('current_price', 'N/A')}
- 52-Week High: ${price_data.get('52_week_high', 'N/A')}
- 52-Week Low: ${price_data.get('52_week_low', 'N/A')}
- 50-Day Average: ${price_data.get('50_day_avg', 'N/A')}
- 200-Day Average: ${price_data.get('200_day_avg', 'N/A')}
""")
        
        # Technical analysis
        if technical:
            tech_indicators = technical.get("indicators", {})
            tech_signals = technical.get("signals", {})
            context_parts.append(f"""
TECHNICAL ANALYSIS:
- Overall Signal: {technical.get('overall_signal', 'N/A')}
- Technical Score: {technical.get('score', 'N/A')}/100
- RSI: {tech_indicators.get('rsi', {}).get('value', 'N/A')} ({tech_indicators.get('rsi', {}).get('signal', 'N/A')})
- MACD Signal: {tech_indicators.get('macd', {}).get('signal', 'N/A')}
- Trend: {technical.get('trend_analysis', {}).get('overall_trend', 'N/A')}
- Support: ${technical.get('support_resistance', {}).get('nearest_support', 'N/A')}
- Resistance: ${technical.get('support_resistance', {}).get('nearest_resistance', 'N/A')}
- Buy Signals: {', '.join(tech_signals.get('buy_signals', [])) or 'None'}
- Sell Signals: {', '.join(tech_signals.get('sell_signals', [])) or 'None'}
""")
        
        # Fundamental analysis
        if fundamental:
            valuation = fundamental.get("valuation", {})
            context_parts.append(f"""
FUNDAMENTAL ANALYSIS:
- Overall Signal: {fundamental.get('overall_signal', 'N/A')}
- Fundamental Score: {fundamental.get('overall_score', 'N/A')}/100
- P/E Ratio: {valuation.get('pe_ratio', {}).get('value', 'N/A')}
- PEG Ratio: {valuation.get('peg_ratio', {}).get('value', 'N/A')}
- Valuation Assessment: {valuation.get('overall_assessment', 'N/A')}
- Analyst Price Target (Mean): ${valuation.get('price_target_analysis', {}).get('target_mean', 'N/A')}
- Upside Potential: {valuation.get('price_target_analysis', {}).get('upside_potential', 'N/A')}%
- Key Insights: {', '.join(fundamental.get('key_insights', [])) or 'None'}
- Concerns: {', '.join(fundamental.get('concerns', [])) or 'None'}
""")
        
        # Sentiment analysis
        if sentiment:
            combined = sentiment.get("combined_sentiment", {})
            context_parts.append(f"""
SENTIMENT ANALYSIS:
- Overall Sentiment: {combined.get('label', 'N/A')}
- Sentiment Score: {combined.get('score', 'N/A')}
- Confidence: {combined.get('confidence', 'N/A')}
- News Sentiment: {sentiment.get('news_sentiment', {}).get('label', 'N/A')}
- Social Media Sentiment: {sentiment.get('social_sentiment', {}).get('overall', {}).get('label', 'N/A')}
- Key Topics: {', '.join([t.get('topic', '') for t in sentiment.get('key_topics', [])])}
""")
        
        # Analyst ratings from yfinance
        analyst = stock_data.get("analyst_ratings", {})
        if analyst:
            context_parts.append(f"""
ANALYST CONSENSUS (from Yahoo Finance):
- Recommendation: {analyst.get('recommendation', 'N/A')}
- Number of Analysts: {analyst.get('num_analysts', 'N/A')}
- Target High: ${analyst.get('target_high', 'N/A')}
- Target Mean: ${analyst.get('target_mean', 'N/A')}
- Target Low: ${analyst.get('target_low', 'N/A')}
""")
        
        # Institutional analyst ratings (major banks)
        if analyst_ratings:
            consensus = analyst_ratings.get("consensus", {})
            inst_ratings = analyst_ratings.get("institutional_ratings", [])
            
            # Get top bank ratings
            bank_ratings = [r for r in inst_ratings if r.get("weight", 0) >= 0.75][:10]
            
            context_parts.append(f"""
INSTITUTIONAL ANALYST RATINGS (Major Banks & Research Firms):
- Weighted Consensus: {consensus.get('consensus_rating', 'N/A')}
- Weighted Score: {consensus.get('weighted_score', 'N/A')}/5
- Buy Ratings: {consensus.get('buy_count', 0)} | Hold: {consensus.get('hold_count', 0)} | Sell: {consensus.get('sell_count', 0)}
- Total Analyst Ratings: {consensus.get('total_ratings', 0)}

Major Bank Ratings (higher weight = more influential):""")
            
            for r in bank_ratings:
                pt = f" (PT: ${r['price_target']})" if r.get('price_target') else ""
                context_parts.append(f"- {r.get('source', 'Unknown')}: {r.get('rating', 'N/A')}{pt} [weight: {r.get('weight', 0.5):.2f}]")
        
        return "\n".join(context_parts)
    
    def _call_ai_analysis(self, context: str, symbol: str, timeframe: str = "short", tf_config: Dict = None) -> Dict[str, Any]:
        """Call OpenAI API for analysis with timeframe-specific price targets"""
        
        timeframe_focus = {
            "swing": "1-4 weeks (swing trading)",
            "short": "1-3 months (short-term)",
            "medium": "3-12 months (medium-term)",
            "long": "1-5 years (long-term)"
        }.get(timeframe, "1-3 months")
        
        system_prompt = f"""You are an expert stock analyst with deep knowledge of technical analysis, fundamental analysis, and market sentiment. Your task is to provide actionable investment recommendations based on the provided data.

The user has selected a {timeframe_focus} investment horizon. Tailor your analysis and price targets accordingly.

Be specific with numbers and price levels. Always provide price targets for ALL THREE timeframes below, but emphasize the one matching the user's selected horizon.

IMPORTANT: Give higher weight to institutional analyst ratings from major banks (Goldman Sachs, JPMorgan, Morgan Stanley, etc.) compared to social media sentiment from Reddit. The institutional ratings are more reliable for investment decisions.

Respond in JSON format with these fields:
- executive_summary: A 2-3 paragraph summary of the overall investment thesis, emphasizing the {timeframe_focus} outlook. Include what major banks are saying about this stock.
- investment_thesis: A concise 2-3 sentence investment thesis statement
- entry_price_recommendation: Object with "ideal_entry", "acceptable_range_low", "acceptable_range_high", and "reasoning"
- stop_loss: Object with "recommended" (price), "tight" (price), "wide" (price), "reasoning" (why these levels)
- valuation_assessment: Object with "status" (undervalued/fairly_valued/overvalued), "label" (display text), "reasoning" (brief explanation based on P/E, PEG, analyst targets)
- price_targets: Object containing price targets for each horizon:
  - short_term: Object with "period" ("1-3 months"), "target" (price), "low" (bear case), "high" (bull case), "confidence" (HIGH/MEDIUM/LOW), "reasoning" (brief explanation)
  - medium_term: Object with "period" ("3-12 months"), "target" (price), "low" (bear case), "high" (bull case), "confidence" (HIGH/MEDIUM/LOW), "reasoning" (brief explanation)  
  - long_term: Object with "period" ("1-5 years"), "target" (price), "low" (bear case), "high" (bull case), "confidence" (HIGH/MEDIUM/LOW), "reasoning" (brief explanation)
- institutional_summary: Brief summary of what major banks (Goldman, JPMorgan, etc.) are saying about this stock
- bull_case: Array of exactly 3 objects, each with "title" (strength name) and "detail" (explanation with supporting data/metrics)
- bear_case: Array of exactly 3 objects, each with "title" (concern name) and "detail" (explanation with potential impact assessment)
- risk_factors: Object with:
  - company_specific: Array of 2-3 company-specific risks (operational, competitive, management)
  - market_sector: Array of 2-3 market/sector risks (economic, industry, regulatory threats)
  - overall_level: "low", "medium", or "high"
- price_outlook: Object with "1_month", "3_month" targets and "probability" assessments
- risk_assessment: Object with "level" (low/medium/high), "key_risks" (array), and "risk_reward_ratio"
- key_factors: Array of the top 5 factors driving this recommendation
- recommendation: One of "STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL" (based on {timeframe_focus} horizon)
- confidence_level: One of "HIGH", "MEDIUM", "LOW" with explanation"""

        user_prompt = f"""Analyze {symbol} based on the following data and provide your investment recommendation for a {timeframe_focus} investment horizon:

{context}

Focus on:
1. What is the best ENTRY PRICE for maximum gains? Provide specific price levels.
2. What STOP-LOSS levels should be used? (tight, normal, wide options)
3. Is the stock UNDERVALUED, FAIRLY VALUED, or OVERVALUED based on fundamentals?
4. Provide SPECIFIC PRICE TARGETS for ALL THREE timeframes:
   - Short-term (1-3 months): target price, bear case, bull case
   - Medium-term (3-12 months): target price, bear case, bull case  
   - Long-term (1-5 years): target price, bear case, bull case
5. What are major INSTITUTIONAL ANALYSTS (Goldman, JPMorgan, etc.) saying?
6. BULL CASE - What are the top 3 STRENGTHS with supporting data?
7. BEAR CASE - What are the top 3 CONCERNS with potential impact?
8. RISK FACTORS - Separate company-specific risks from market/sector risks
9. What is your overall recommendation for the {timeframe_focus} horizon?

Provide specific, actionable analysis with data-backed reasoning."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            raise Exception(f"AI analysis failed: {str(e)}")
    
    def _generate_fallback_analysis(self, stock_data: Dict, technical: Dict, 
                                   fundamental: Dict, sentiment: Dict) -> str:
        """Generate analysis without AI when API is unavailable"""
        
        parts = []
        
        # Basic info
        company = stock_data.get("company_info", {})
        price = stock_data.get("price_data", {})
        
        parts.append(f"Analysis for {company.get('name', 'Unknown')} ({stock_data.get('symbol', 'N/A')})")
        parts.append(f"Sector: {company.get('sector', 'N/A')} | Industry: {company.get('industry', 'N/A')}")
        parts.append(f"Current Price: ${price.get('current_price', 'N/A')}")
        parts.append("")
        
        # Technical summary
        if technical:
            parts.append(f"TECHNICAL: {technical.get('overall_signal', 'N/A')} (Score: {technical.get('score', 'N/A')}/100)")
            trend = technical.get("trend_analysis", {})
            parts.append(f"  Trend: {trend.get('overall_trend', 'N/A')}")
            sr = technical.get("support_resistance", {})
            parts.append(f"  Support: ${sr.get('nearest_support', 'N/A')} | Resistance: ${sr.get('nearest_resistance', 'N/A')}")
        
        # Fundamental summary
        if fundamental:
            parts.append(f"\nFUNDAMENTAL: {fundamental.get('overall_signal', 'N/A')} (Score: {fundamental.get('overall_score', 'N/A')}/100)")
            val = fundamental.get("valuation", {})
            parts.append(f"  {val.get('overall_assessment', 'N/A')}")
            
            insights = fundamental.get("key_insights", [])
            if insights:
                parts.append(f"  Insights: {'; '.join(insights[:3])}")
            
            concerns = fundamental.get("concerns", [])
            if concerns:
                parts.append(f"  Concerns: {'; '.join(concerns[:3])}")
        
        # Sentiment summary
        if sentiment:
            combined = sentiment.get("combined_sentiment", {})
            parts.append(f"\nSENTIMENT: {combined.get('label', 'N/A')} (Confidence: {combined.get('confidence', 'N/A')})")
        
        # Overall recommendation
        scores = []
        if technical and technical.get("score"):
            scores.append(technical["score"])
        if fundamental and fundamental.get("overall_score"):
            scores.append(fundamental["overall_score"])
        if sentiment and sentiment.get("overall_score"):
            scores.append(sentiment["overall_score"])
        
        if scores:
            avg_score = sum(scores) / len(scores)
            if avg_score >= 30:
                recommendation = "STRONG BUY"
            elif avg_score >= 10:
                recommendation = "BUY"
            elif avg_score <= -30:
                recommendation = "STRONG SELL"
            elif avg_score <= -10:
                recommendation = "SELL"
            else:
                recommendation = "HOLD"
            
            parts.append(f"\nOVERALL RECOMMENDATION: {recommendation}")
            parts.append(f"Combined Score: {avg_score:.1f}/100")
        
        return "\n".join(parts)
    
    def generate_entry_strategy(self, current_price: float, support: float, 
                               resistance: float, volatility: float) -> Dict[str, Any]:
        """Generate entry price strategy based on technical levels"""
        
        # Calculate entry zones
        price_range = resistance - support
        
        # Ideal entry near support with buffer
        ideal_entry = support + (price_range * 0.1)
        
        # Acceptable range
        acceptable_low = support
        acceptable_high = support + (price_range * 0.3)
        
        # Risk/reward calculation
        potential_gain = resistance - ideal_entry
        potential_loss = ideal_entry - support
        risk_reward = potential_gain / potential_loss if potential_loss > 0 else 0
        
        return {
            "current_price": round(current_price, 2),
            "ideal_entry": round(ideal_entry, 2),
            "acceptable_range": {
                "low": round(acceptable_low, 2),
                "high": round(acceptable_high, 2)
            },
            "support_level": round(support, 2),
            "resistance_level": round(resistance, 2),
            "risk_reward_ratio": round(risk_reward, 2),
            "entry_recommendation": self._get_entry_recommendation(
                current_price, ideal_entry, acceptable_high
            )
        }
    
    def _get_entry_recommendation(self, current: float, ideal: float, max_acceptable: float) -> str:
        """Get entry recommendation based on current price vs ideal"""
        
        if current <= ideal:
            return "EXCELLENT ENTRY - Price at or below ideal entry point"
        elif current <= max_acceptable:
            return "GOOD ENTRY - Price within acceptable range"
        elif current <= max_acceptable * 1.1:
            return "FAIR ENTRY - Consider waiting for pullback"
        else:
            return "WAIT - Price extended, wait for better entry"
    
    def analyze_news_impact(self, symbol: str, articles: List[Dict], current_price: float = None) -> Dict[str, Any]:
        """
        Use AI to analyze how each news article will impact the stock price
        
        Returns detailed analysis of good vs bad news and price impact predictions
        """
        result = {
            "analyzed_articles": [],
            "overall_news_sentiment": "NEUTRAL",
            "price_direction_prediction": "SIDEWAYS",
            "confidence": "LOW",
            "summary": ""
        }
        
        if not self.client or not articles:
            return result
        
        # Take top 20 most recent articles for analysis
        top_articles = articles[:20]
        
        # Prepare article summaries for AI
        articles_text = "\n".join([
            f"{i+1}. [{a.get('source', 'Unknown')}] {a.get('title', 'N/A')} (Impact: {a.get('impact', 'Neutral')})"
            for i, a in enumerate(top_articles)
        ])
        
        prompt = f"""Analyze these news articles for {symbol} stock and determine how they will affect the stock price.

ARTICLES:
{articles_text}

Current Price: ${current_price if current_price else 'Unknown'}

For each article, provide:
1. Whether it's GOOD NEWS or BAD NEWS for the stock
2. Expected price impact: RISE, FALL, or MINIMAL
3. Impact magnitude: HIGH, MEDIUM, or LOW
4. Brief explanation (one sentence)

Then provide an OVERALL summary of:
- Overall news sentiment (BULLISH, BEARISH, NEUTRAL)
- Expected price direction from news (RISE, FALL, SIDEWAYS)
- Confidence level (HIGH, MEDIUM, LOW)
- Summary explanation

Return ONLY valid JSON in this exact format:
{{
  "articles": [
    {{"index": 1, "sentiment": "GOOD/BAD/NEUTRAL", "price_impact": "RISE/FALL/MINIMAL", "magnitude": "HIGH/MEDIUM/LOW", "explanation": "brief reason"}},
    ...
  ],
  "overall": {{
    "sentiment": "BULLISH/BEARISH/NEUTRAL",
    "price_direction": "RISE/FALL/SIDEWAYS",
    "confidence": "HIGH/MEDIUM/LOW",
    "summary": "overall explanation"
  }}
}}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for cost efficiency
                messages=[
                    {"role": "system", "content": "You are a financial news analyst expert. Analyze news impact on stock prices. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Clean response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            analysis = json.loads(response_text)
            
            # Map AI analysis back to articles
            analyzed = []
            for i, article in enumerate(top_articles):
                article_analysis = next(
                    (a for a in analysis.get("articles", []) if a.get("index") == i + 1),
                    {"sentiment": "NEUTRAL", "price_impact": "MINIMAL", "magnitude": "LOW", "explanation": "No analysis available"}
                )
                
                analyzed.append({
                    **article,
                    "ai_sentiment": article_analysis.get("sentiment", "NEUTRAL"),
                    "ai_price_impact": article_analysis.get("price_impact", "MINIMAL"),
                    "ai_magnitude": article_analysis.get("magnitude", "LOW"),
                    "ai_explanation": article_analysis.get("explanation", "")
                })
            
            overall = analysis.get("overall", {})
            
            result = {
                "analyzed_articles": analyzed,
                "overall_news_sentiment": overall.get("sentiment", "NEUTRAL"),
                "price_direction_prediction": overall.get("price_direction", "SIDEWAYS"),
                "confidence": overall.get("confidence", "LOW"),
                "summary": overall.get("summary", "")
            }
            
        except Exception as e:
            result["error"] = str(e)
        
        return result


if __name__ == "__main__":
    advisor = AIAdvisor()
    
    # Test entry strategy
    strategy = advisor.generate_entry_strategy(
        current_price=150,
        support=140,
        resistance=165,
        volatility=0.02
    )
    print(f"Entry Strategy: {strategy}")
