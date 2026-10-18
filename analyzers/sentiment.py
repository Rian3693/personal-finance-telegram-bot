"""
Sentiment Analysis Module - Analyzes news and social media sentiment
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from textblob import TextBlob
import re


class SentimentAnalyzer:
    """Analyzes sentiment from news and social media data"""
    
    def __init__(self):
        # Financial sentiment keywords with weights
        self.bullish_keywords = {
            'buy': 2, 'long': 2, 'bullish': 3, 'upgrade': 3, 'outperform': 2,
            'beat': 2, 'exceeds': 2, 'strong': 1, 'growth': 1, 'breakout': 2,
            'undervalued': 3, 'opportunity': 1, 'momentum': 1, 'rally': 2,
            'surge': 2, 'soar': 2, 'jump': 1, 'gain': 1, 'positive': 1,
            'optimistic': 2, 'confident': 1, 'upside': 2, 'catalyst': 2,
            'innovative': 1, 'expansion': 1, 'record': 2, 'breakthrough': 2,
        }
        
        self.bearish_keywords = {
            'sell': 2, 'short': 2, 'bearish': 3, 'downgrade': 3, 'underperform': 2,
            'miss': 2, 'disappointing': 2, 'weak': 1, 'decline': 1, 'breakdown': 2,
            'overvalued': 3, 'risk': 1, 'concern': 1, 'crash': 3, 'plunge': 2,
            'drop': 1, 'fall': 1, 'loss': 1, 'negative': 1, 'warning': 2,
            'pessimistic': 2, 'downside': 2, 'lawsuit': 2, 'investigation': 2,
            'recall': 2, 'layoff': 2, 'debt': 1, 'bankruptcy': 3,
        }
    
    def analyze(self, news_data: Dict, social_data: Dict) -> Dict[str, Any]:
        """
        Comprehensive sentiment analysis from all sources
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "news_sentiment": {},
            "social_sentiment": {},
            "combined_sentiment": {},
            "key_topics": [],
            "sentiment_trend": None,
            "overall_score": 0,
            "overall_signal": None,
            "error": None
        }
        
        try:
            # Analyze news sentiment
            if news_data and news_data.get("articles"):
                result["news_sentiment"] = self._analyze_news_sentiment(news_data["articles"])
            
            # Analyze social media sentiment (already processed by collector)
            if social_data:
                result["social_sentiment"] = self._process_social_sentiment(social_data)
            
            # Combine sentiments
            result["combined_sentiment"] = self._combine_sentiments(
                result["news_sentiment"],
                result["social_sentiment"]
            )
            
            # Extract key topics
            all_texts = []
            if news_data and news_data.get("articles"):
                all_texts.extend([a.get("title", "") for a in news_data["articles"]])
            result["key_topics"] = self._extract_key_topics(all_texts)
            
            # Calculate overall score and signal
            result["overall_score"], result["overall_signal"] = self._calculate_overall_score(result)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _analyze_news_sentiment(self, articles: List[Dict]) -> Dict[str, Any]:
        """Analyze sentiment from news articles"""
        if not articles:
            return {"status": "No articles to analyze"}
        
        sentiments = []
        bullish_articles = []
        bearish_articles = []
        neutral_articles = []
        
        for article in articles:
            title = article.get("title", "")
            summary = article.get("summary", "")
            text = f"{title} {summary}"
            
            sentiment = self._analyze_text(text)
            sentiments.append(sentiment)
            
            article_info = {
                "title": title[:100],
                "source": article.get("source", "Unknown"),
                "sentiment_score": sentiment["score"],
                "sentiment_label": sentiment["label"]
            }
            
            if sentiment["label"] == "bullish":
                bullish_articles.append(article_info)
            elif sentiment["label"] == "bearish":
                bearish_articles.append(article_info)
            else:
                neutral_articles.append(article_info)
        
        # Calculate aggregate
        scores = [s["score"] for s in sentiments]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            "average_score": round(avg_score, 3),
            "label": self._score_to_label(avg_score),
            "total_articles": len(articles),
            "bullish_count": len(bullish_articles),
            "bearish_count": len(bearish_articles),
            "neutral_count": len(neutral_articles),
            "bullish_articles": bullish_articles[:5],
            "bearish_articles": bearish_articles[:5],
            "sentiment_distribution": {
                "bullish": len(bullish_articles) / len(articles) * 100 if articles else 0,
                "bearish": len(bearish_articles) / len(articles) * 100 if articles else 0,
                "neutral": len(neutral_articles) / len(articles) * 100 if articles else 0,
            }
        }
    
    def _analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of a single text"""
        if not text:
            return {"score": 0, "label": "neutral", "confidence": 0}
        
        # Clean text
        text_clean = text.lower()
        text_clean = re.sub(r'http\S+', '', text_clean)
        text_clean = re.sub(r'[^\w\s]', ' ', text_clean)
        
        # TextBlob sentiment
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity  # -1 to 1
        subjectivity = blob.sentiment.subjectivity  # 0 to 1
        
        # Keyword-based sentiment
        bullish_score = 0
        bearish_score = 0
        
        words = text_clean.split()
        for word in words:
            if word in self.bullish_keywords:
                bullish_score += self.bullish_keywords[word]
            if word in self.bearish_keywords:
                bearish_score += self.bearish_keywords[word]
        
        # Normalize keyword scores
        total_keywords = bullish_score + bearish_score
        keyword_score = 0
        if total_keywords > 0:
            keyword_score = (bullish_score - bearish_score) / total_keywords
        
        # Combine scores (weighted average)
        combined_score = (polarity * 0.4 + keyword_score * 0.6)
        combined_score = max(-1, min(1, combined_score))
        
        # Confidence based on subjectivity and keyword matches
        confidence = min(1, (1 - subjectivity * 0.5) * (1 + total_keywords * 0.1))
        
        return {
            "score": round(combined_score, 3),
            "label": self._score_to_label(combined_score),
            "confidence": round(confidence, 2),
            "polarity": round(polarity, 3),
            "keyword_score": round(keyword_score, 3),
            "bullish_keywords_found": bullish_score,
            "bearish_keywords_found": bearish_score
        }
    
    def _process_social_sentiment(self, social_data: Dict) -> Dict[str, Any]:
        """Process pre-analyzed social media sentiment"""
        result = {
            "reddit": None,
            "stocktwits": None,
            "overall": None
        }
        
        scores = []
        weights = []
        
        # Reddit data
        reddit = social_data.get("reddit", {})
        if reddit and reddit.get("sentiment_score") is not None:
            result["reddit"] = {
                "score": reddit["sentiment_score"],
                "label": reddit.get("sentiment_label", "neutral"),
                "mentions": reddit.get("total_mentions", 0),
                "bullish_count": reddit.get("bullish_count", 0),
                "bearish_count": reddit.get("bearish_count", 0),
                "trending_score": reddit.get("trending_score", 0)
            }
            scores.append(reddit["sentiment_score"])
            weights.append(1.5)  # Reddit gets higher weight due to discussion depth
        
        # StockTwits data
        stocktwits = social_data.get("stocktwits", {})
        if stocktwits and stocktwits.get("sentiment_score") is not None:
            result["stocktwits"] = {
                "score": stocktwits["sentiment_score"],
                "label": stocktwits.get("sentiment_label", "neutral"),
                "messages": stocktwits.get("total_messages", 0),
                "bullish_count": stocktwits.get("bullish_count", 0),
                "bearish_count": stocktwits.get("bearish_count", 0),
                "watchers": stocktwits.get("watchers", 0)
            }
            scores.append(stocktwits["sentiment_score"])
            weights.append(1.0)
        
        # Overall social sentiment
        if scores:
            weighted_sum = sum(s * w for s, w in zip(scores, weights))
            total_weight = sum(weights)
            overall_score = weighted_sum / total_weight
            
            result["overall"] = {
                "score": round(overall_score, 3),
                "label": self._score_to_label(overall_score),
                "data_points": sum([
                    result["reddit"]["mentions"] if result["reddit"] else 0,
                    result["stocktwits"]["messages"] if result["stocktwits"] else 0
                ])
            }
        
        return result
    
    def _combine_sentiments(self, news_sentiment: Dict, social_sentiment: Dict) -> Dict[str, Any]:
        """Combine news and social sentiment into unified score"""
        scores = []
        weights = []
        
        # News sentiment (moderate weight)
        if news_sentiment and news_sentiment.get("average_score") is not None:
            scores.append(news_sentiment["average_score"])
            # Weight by number of articles
            article_count = news_sentiment.get("total_articles", 1)
            weights.append(min(2.0, 1.0 + article_count * 0.05))
        
        # Social sentiment (high weight for recent market sentiment)
        if social_sentiment and social_sentiment.get("overall", {}).get("score") is not None:
            scores.append(social_sentiment["overall"]["score"])
            # Weight by data points
            data_points = social_sentiment["overall"].get("data_points", 1)
            weights.append(min(2.5, 1.5 + data_points * 0.02))
        
        if not scores:
            return {
                "score": 0,
                "label": "neutral",
                "confidence": "low",
                "composition": {}
            }
        
        # Weighted average
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)
        combined_score = weighted_sum / total_weight
        
        # Calculate confidence
        data_volume = (
            (news_sentiment.get("total_articles", 0) if news_sentiment else 0) +
            (social_sentiment.get("overall", {}).get("data_points", 0) if social_sentiment else 0)
        )
        
        if data_volume > 100:
            confidence = "high"
        elif data_volume > 30:
            confidence = "medium"
        else:
            confidence = "low"
        
        return {
            "score": round(combined_score, 3),
            "label": self._score_to_label(combined_score),
            "confidence": confidence,
            "data_volume": data_volume,
            "composition": {
                "news_weight": round(weights[0] / total_weight * 100, 1) if len(weights) > 0 else 0,
                "social_weight": round(weights[1] / total_weight * 100, 1) if len(weights) > 1 else 0,
            }
        }
    
    def _extract_key_topics(self, texts: List[str]) -> List[Dict[str, Any]]:
        """Extract key topics from text collection"""
        if not texts:
            return []
        
        # Combine all text
        all_text = " ".join(texts).lower()
        
        # Common financial topics to look for
        topics = {
            "earnings": ["earnings", "eps", "revenue", "profit", "quarterly", "annual report"],
            "growth": ["growth", "expansion", "increase", "surge", "rise"],
            "decline": ["decline", "drop", "fall", "decrease", "plunge"],
            "acquisition": ["acquisition", "merger", "buyout", "deal", "takeover"],
            "product": ["product", "launch", "release", "innovation", "new"],
            "legal": ["lawsuit", "legal", "court", "investigation", "sec"],
            "management": ["ceo", "executive", "management", "board", "leadership"],
            "market": ["market", "sector", "industry", "competition", "share"],
            "dividend": ["dividend", "yield", "payout", "distribution"],
            "analyst": ["analyst", "upgrade", "downgrade", "rating", "target"],
        }
        
        found_topics = []
        for topic, keywords in topics.items():
            count = sum(1 for kw in keywords if kw in all_text)
            if count > 0:
                found_topics.append({
                    "topic": topic,
                    "relevance": count,
                    "keywords_found": [kw for kw in keywords if kw in all_text]
                })
        
        # Sort by relevance
        found_topics.sort(key=lambda x: x["relevance"], reverse=True)
        
        return found_topics[:5]
    
    def _score_to_label(self, score: float) -> str:
        """Convert sentiment score to label"""
        if score > 0.2:
            return "bullish"
        elif score < -0.2:
            return "bearish"
        else:
            return "neutral"
    
    def _calculate_overall_score(self, analysis: Dict) -> tuple:
        """Calculate overall sentiment score (-100 to 100)"""
        combined = analysis.get("combined_sentiment", {})
        score = combined.get("score", 0)
        
        # Scale to -100 to 100
        scaled_score = score * 100
        
        # Determine signal
        if scaled_score >= 30:
            signal = "VERY BULLISH"
        elif scaled_score >= 10:
            signal = "BULLISH"
        elif scaled_score <= -30:
            signal = "VERY BEARISH"
        elif scaled_score <= -10:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"
        
        return round(scaled_score, 1), signal


if __name__ == "__main__":
    analyzer = SentimentAnalyzer()
    
    # Test with sample data
    test_articles = [
        {"title": "Apple beats earnings expectations with strong iPhone sales", "summary": "Apple reported strong growth"},
        {"title": "Concerns grow over Apple's China exposure", "summary": "Analysts worry about risks"}
    ]
    
    result = analyzer._analyze_news_sentiment(test_articles)
    print(f"News Sentiment: {result['label']} (score: {result['average_score']})")
