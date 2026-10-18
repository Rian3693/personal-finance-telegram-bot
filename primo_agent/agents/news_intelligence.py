"""
News Intelligence Agent - Processes financial news with NLP features
7 quantified NLP features: relevance, sentiment, price_impact, trend_direction,
earnings_impact, investor_confidence, risk_profile_change
"""
import os
import sys
from typing import Dict, Any, List, Optional
from datetime import datetime

# Try to import OpenAI for LLM analysis
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class NewsIntelligenceAgent:
    """
    Agent responsible for analyzing news sentiment and generating NLP features.
    Produces 7 quantified features on a -2 to +2 scale.
    """
    
    def __init__(self, openai_api_key: Optional[str] = None):
        self.name = "News Intelligence Agent"
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        
        # NLP feature definitions
        self.nlp_features = {
            'news_relevance': 'How relevant is the news to stock price movement (-2 to +2)',
            'sentiment': 'Overall sentiment of the news (-2 very negative to +2 very positive)',
            'price_impact_potential': 'Potential impact on stock price (-2 to +2)',
            'trend_direction': 'Indicated trend direction (-2 strong bearish to +2 strong bullish)',
            'earnings_impact': 'Impact related to earnings/financials (-2 to +2)',
            'investor_confidence': 'Effect on investor confidence (-2 to +2)',
            'risk_profile_change': 'Change in perceived risk (-2 higher risk to +2 lower risk)'
        }
        
        # Keywords for rule-based analysis
        self.positive_keywords = [
            'beat', 'beats', 'exceeds', 'surpass', 'upgrade', 'raised', 'bullish',
            'growth', 'strong', 'record', 'gain', 'soar', 'surge', 'rally',
            'outperform', 'buy', 'positive', 'breakthrough', 'innovation',
            'partnership', 'acquisition', 'dividend', 'profit', 'expansion',
            'launch', 'success', 'optimistic', 'deal', 'contract', 'award', 'approval'
        ]
        
        self.negative_keywords = [
            'miss', 'misses', 'disappoints', 'decline', 'downgrade', 'cut',
            'bearish', 'weak', 'loss', 'plunge', 'crash', 'drop', 'fall',
            'underperform', 'sell', 'negative', 'concern', 'warning',
            'lawsuit', 'investigation', 'recall', 'layoff', 'debt',
            'bankruptcy', 'struggle', 'risk', 'threat', 'slump', 'tumble',
            'delay', 'cancel', 'terminate', 'reject', 'fine', 'penalty'
        ]
    
    async def analyze(self, news_data: Dict[str, Any], company_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Analyze news and generate NLP features.
        
        Args:
            news_data: Dict containing news articles
            company_info: Optional company information for context
            
        Returns:
            Dict with NLP features and analysis
        """
        try:
            articles = news_data.get('articles', [])
            
            if not articles:
                return self._empty_result("No news articles available")
            
            # Filter significant articles
            significant_articles = self._filter_significant_news(articles)
            
            # Use LLM if available, otherwise use rule-based analysis
            if self.api_key and HAS_OPENAI:
                nlp_features = await self._analyze_with_llm(significant_articles, company_info)
            else:
                nlp_features = self._analyze_rule_based(significant_articles)
            
            # Generate summary
            summary = self._generate_summary(nlp_features, significant_articles)
            
            return {
                'success': True,
                'articles_analyzed': len(significant_articles),
                'total_articles': len(articles),
                'nlp_features': nlp_features,
                'summary': summary,
                'significant_headlines': [a.get('title', '') for a in significant_articles[:5]]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'nlp_features': self._default_features()
            }
    
    def _empty_result(self, message: str) -> Dict[str, Any]:
        """Return empty result with default features"""
        return {
            'success': True,
            'articles_analyzed': 0,
            'message': message,
            'nlp_features': self._default_features(),
            'summary': 'No news data available for analysis'
        }
    
    def _default_features(self) -> Dict[str, float]:
        """Return neutral default features"""
        return {
            'news_relevance': 0,
            'sentiment': 0,
            'price_impact_potential': 0,
            'trend_direction': 0,
            'earnings_impact': 0,
            'investor_confidence': 0,
            'risk_profile_change': 0
        }
    
    def _filter_significant_news(self, articles: List[Dict]) -> List[Dict]:
        """Filter out promotional/irrelevant content"""
        significant = []
        
        # Sources to filter out
        promotional_sources = ['pr newswire', 'business wire', 'globe newswire', 'accesswire']
        clickbait_phrases = ['you won\'t believe', 'secret', 'shocking', 'must read', 
                           'click here', 'sponsored', 'advertisement']
        
        for article in articles:
            title = article.get('title', '').lower()
            source = article.get('publisher', '').lower()
            
            # Skip if from promotional source
            if any(ps in source for ps in promotional_sources):
                continue
            
            # Skip if clickbait
            if any(cb in title for cb in clickbait_phrases):
                continue
            
            # Skip very short titles (likely not real articles)
            if len(title) < 20:
                continue
            
            significant.append(article)
        
        return significant[:10]  # Limit to 10 most relevant
    
    def _analyze_rule_based(self, articles: List[Dict]) -> Dict[str, float]:
        """Rule-based sentiment analysis when LLM not available"""
        features = self._default_features()
        
        if not articles:
            return features
        
        positive_count = 0
        negative_count = 0
        total_relevance = 0
        
        for article in articles:
            title = article.get('title', '').lower()
            
            # Count positive and negative keywords
            pos = sum(1 for kw in self.positive_keywords if kw in title)
            neg = sum(1 for kw in self.negative_keywords if kw in title)
            
            positive_count += pos
            negative_count += neg
            
            # Relevance based on keyword presence
            if pos > 0 or neg > 0:
                total_relevance += 1
        
        # Calculate features based on keyword analysis
        total = positive_count + negative_count
        
        if total > 0:
            # Sentiment: ratio of positive to total
            sentiment_ratio = (positive_count - negative_count) / total
            features['sentiment'] = max(-2, min(2, sentiment_ratio * 2))
            
            # Price impact: based on total keyword matches
            impact = min(total / 5, 2)  # Cap at 2
            features['price_impact_potential'] = impact if positive_count > negative_count else -impact
            
            # Trend direction follows sentiment
            features['trend_direction'] = features['sentiment']
            
            # Investor confidence
            features['investor_confidence'] = features['sentiment'] * 0.8
            
            # Risk profile (inverse of negative sentiment)
            features['risk_profile_change'] = -features['sentiment'] * 0.5 if features['sentiment'] < 0 else features['sentiment'] * 0.3
        
        # News relevance based on how many articles had keywords
        if len(articles) > 0:
            features['news_relevance'] = min(2, (total_relevance / len(articles)) * 2)
        
        # Round all features
        features = {k: round(v, 2) for k, v in features.items()}
        
        return features
    
    async def _analyze_with_llm(self, articles: List[Dict], company_info: Dict = None) -> Dict[str, float]:
        """Use OpenAI to analyze news sentiment (when API key available)"""
        try:
            client = OpenAI(api_key=self.api_key)
            
            # Prepare headlines for analysis
            headlines = "\n".join([f"- {a.get('title', '')}" for a in articles[:7]])
            
            company_context = ""
            if company_info:
                company_context = f"Company: {company_info.get('name', 'Unknown')} in {company_info.get('industry', 'Unknown')} industry."
            
            prompt = f"""Analyze these financial news headlines and provide NLP features on a scale of -2 to +2:

{company_context}

Headlines:
{headlines}

Provide JSON with these exact features (values from -2 to +2):
- news_relevance: How relevant to stock price movement
- sentiment: Overall sentiment (-2 very negative to +2 very positive)
- price_impact_potential: Potential impact on stock price
- trend_direction: Indicated trend (-2 strong bearish to +2 strong bullish)
- earnings_impact: Impact related to earnings/financials
- investor_confidence: Effect on investor confidence
- risk_profile_change: Change in perceived risk (-2 higher risk to +2 lower risk)

Return ONLY valid JSON, no other text."""

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
            
            features = json.loads(result_text)
            
            # Validate and clamp values
            validated = {}
            for key in self._default_features().keys():
                value = features.get(key, 0)
                validated[key] = max(-2, min(2, float(value)))
            
            return validated
            
        except Exception as e:
            print(f"LLM analysis failed: {e}, falling back to rule-based")
            return self._analyze_rule_based(articles)
    
    def _generate_summary(self, features: Dict[str, float], articles: List[Dict]) -> str:
        """Generate a human-readable summary of the news analysis"""
        sentiment = features.get('sentiment', 0)
        impact = features.get('price_impact_potential', 0)
        trend = features.get('trend_direction', 0)
        
        # Determine overall tone
        if sentiment > 1:
            tone = "strongly positive"
        elif sentiment > 0.3:
            tone = "moderately positive"
        elif sentiment < -1:
            tone = "strongly negative"
        elif sentiment < -0.3:
            tone = "moderately negative"
        else:
            tone = "neutral"
        
        # Determine expected impact
        if abs(impact) > 1.5:
            impact_str = "high potential impact"
        elif abs(impact) > 0.5:
            impact_str = "moderate potential impact"
        else:
            impact_str = "limited expected impact"
        
        # Determine trend signal
        if trend > 1:
            trend_str = "bullish signals"
        elif trend > 0:
            trend_str = "slightly bullish signals"
        elif trend < -1:
            trend_str = "bearish signals"
        elif trend < 0:
            trend_str = "slightly bearish signals"
        else:
            trend_str = "mixed/neutral signals"
        
        summary = f"News sentiment is {tone} with {impact_str}. "
        summary += f"Technical trend shows {trend_str}. "
        summary += f"Analyzed {len(articles)} significant articles."
        
        return summary
