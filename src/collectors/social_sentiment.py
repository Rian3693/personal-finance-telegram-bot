"""
Social Media Sentiment Collector - Reddit, StockTwits, and other forums
"""
import praw
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from textblob import TextBlob
import re
from config import (
    REDDIT_CLIENT_ID, 
    REDDIT_CLIENT_SECRET, 
    REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS,
    MAX_REDDIT_POSTS
)


class SocialSentimentCollector:
    """Collects sentiment data from social media and forums"""
    
    def __init__(self):
        self.reddit = None
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            try:
                self.reddit = praw.Reddit(
                    client_id=REDDIT_CLIENT_ID,
                    client_secret=REDDIT_CLIENT_SECRET,
                    user_agent=REDDIT_USER_AGENT
                )
            except:
                pass
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_social_sentiment(self, symbol: str) -> Dict[str, Any]:
        """
        Collect sentiment from social media platforms
        """
        result = {
            "symbol": symbol.upper(),
            "timestamp": datetime.now().isoformat(),
            "reddit": None,
            "stocktwits": None,
            "overall_sentiment": None,
            "error": None
        }
        
        try:
            # Reddit sentiment
            if self.reddit:
                result["reddit"] = self._get_reddit_sentiment(symbol)
            
            # StockTwits sentiment
            result["stocktwits"] = self._get_stocktwits_sentiment(symbol)
            
            # Calculate overall sentiment
            result["overall_sentiment"] = self._calculate_overall_sentiment(result)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _get_reddit_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Collect and analyze Reddit posts and comments"""
        reddit_data = {
            "posts": [],
            "total_mentions": 0,
            "sentiment_score": 0,
            "sentiment_label": "neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "trending_score": 0
        }
        
        try:
            all_posts = []
            
            for subreddit_name in REDDIT_SUBREDDITS:
                try:
                    subreddit = self.reddit.subreddit(subreddit_name)
                    
                    # Search for stock mentions
                    search_queries = [f"${symbol}", symbol, f"{symbol} stock"]
                    
                    for query in search_queries:
                        try:
                            posts = subreddit.search(
                                query, 
                                time_filter='week',
                                limit=MAX_REDDIT_POSTS // len(REDDIT_SUBREDDITS)
                            )
                            
                            for post in posts:
                                # Analyze sentiment of title and selftext
                                text = f"{post.title} {post.selftext}"
                                sentiment = self._analyze_text_sentiment(text)
                                
                                post_data = {
                                    "title": post.title,
                                    "subreddit": subreddit_name,
                                    "score": post.score,
                                    "num_comments": post.num_comments,
                                    "created_utc": datetime.fromtimestamp(post.created_utc).isoformat(),
                                    "url": f"https://reddit.com{post.permalink}",
                                    "sentiment_score": sentiment["score"],
                                    "sentiment_label": sentiment["label"]
                                }
                                all_posts.append(post_data)
                                
                        except Exception:
                            continue
                            
                except Exception:
                    continue
            
            # Deduplicate by title
            seen_titles = set()
            unique_posts = []
            for post in all_posts:
                if post["title"] not in seen_titles:
                    seen_titles.add(post["title"])
                    unique_posts.append(post)
            
            # Sort by engagement (score + comments)
            unique_posts.sort(
                key=lambda x: x["score"] + x["num_comments"], 
                reverse=True
            )
            
            reddit_data["posts"] = unique_posts[:30]
            reddit_data["total_mentions"] = len(unique_posts)
            
            # Calculate aggregate sentiment
            if unique_posts:
                # Weight by engagement
                total_weight = 0
                weighted_sentiment = 0
                
                for post in unique_posts:
                    weight = 1 + post["score"] * 0.1 + post["num_comments"] * 0.05
                    weighted_sentiment += post["sentiment_score"] * weight
                    total_weight += weight
                    
                    if post["sentiment_label"] == "bullish":
                        reddit_data["bullish_count"] += 1
                    elif post["sentiment_label"] == "bearish":
                        reddit_data["bearish_count"] += 1
                    else:
                        reddit_data["neutral_count"] += 1
                
                reddit_data["sentiment_score"] = weighted_sentiment / total_weight if total_weight > 0 else 0
                reddit_data["sentiment_label"] = self._score_to_label(reddit_data["sentiment_score"])
                
                # Trending score (mentions * average engagement)
                avg_engagement = sum(p["score"] + p["num_comments"] for p in unique_posts) / len(unique_posts)
                reddit_data["trending_score"] = len(unique_posts) * avg_engagement
                
        except Exception as e:
            reddit_data["error"] = str(e)
        
        return reddit_data
    
    def _get_stocktwits_sentiment(self, symbol: str) -> Dict[str, Any]:
        """Collect sentiment from StockTwits"""
        stocktwits_data = {
            "messages": [],
            "total_messages": 0,
            "sentiment_score": 0,
            "sentiment_label": "neutral",
            "bullish_count": 0,
            "bearish_count": 0,
            "watchers": 0
        }
        
        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Get symbol info
                symbol_info = data.get("symbol", {})
                stocktwits_data["watchers"] = symbol_info.get("watchlist_count", 0)
                
                messages = data.get("messages", [])
                processed_messages = []
                
                for msg in messages:
                    sentiment = msg.get("entities", {}).get("sentiment", {})
                    sentiment_basic = sentiment.get("basic") if sentiment else None
                    
                    # If no StockTwits sentiment, analyze text
                    if not sentiment_basic:
                        text_sentiment = self._analyze_text_sentiment(msg.get("body", ""))
                        sentiment_label = text_sentiment["label"]
                        sentiment_score = text_sentiment["score"]
                    else:
                        sentiment_label = sentiment_basic.lower()
                        sentiment_score = 1 if sentiment_label == "bullish" else (-1 if sentiment_label == "bearish" else 0)
                    
                    processed_messages.append({
                        "body": msg.get("body", "")[:200],
                        "created_at": msg.get("created_at"),
                        "sentiment_label": sentiment_label,
                        "sentiment_score": sentiment_score,
                        "likes": msg.get("likes", {}).get("total", 0)
                    })
                    
                    if sentiment_label == "bullish":
                        stocktwits_data["bullish_count"] += 1
                    elif sentiment_label == "bearish":
                        stocktwits_data["bearish_count"] += 1
                
                stocktwits_data["messages"] = processed_messages[:20]
                stocktwits_data["total_messages"] = len(messages)
                
                # Calculate aggregate sentiment
                if processed_messages:
                    avg_sentiment = sum(m["sentiment_score"] for m in processed_messages) / len(processed_messages)
                    stocktwits_data["sentiment_score"] = avg_sentiment
                    stocktwits_data["sentiment_label"] = self._score_to_label(avg_sentiment)
                    
        except Exception as e:
            stocktwits_data["error"] = str(e)
        
        return stocktwits_data
    
    def _analyze_text_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of text using TextBlob and custom rules"""
        # Clean text
        text = re.sub(r'http\S+', '', text)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = text.lower()
        
        # TextBlob sentiment
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity  # -1 to 1
        
        # Custom stock-specific keywords
        bullish_keywords = [
            'buy', 'long', 'calls', 'moon', 'rocket', 'bullish', 'pump',
            'undervalued', 'squeeze', 'breakout', 'support', 'accumulate',
            'upside', 'growth', 'beat', 'strong', 'positive', 'upgrade',
            'outperform', 'catalyst', '🚀', '📈', 'diamond hands', 'hodl'
        ]
        
        bearish_keywords = [
            'sell', 'short', 'puts', 'dump', 'bearish', 'crash', 'overvalued',
            'resistance', 'downside', 'weak', 'negative', 'downgrade',
            'underperform', 'miss', 'decline', 'fall', 'drop', '📉',
            'paper hands', 'bag holder', 'rug pull'
        ]
        
        # Count keyword matches
        bullish_count = sum(1 for word in bullish_keywords if word in text)
        bearish_count = sum(1 for word in bearish_keywords if word in text)
        
        # Combine TextBlob sentiment with keyword analysis
        keyword_score = (bullish_count - bearish_count) * 0.2
        combined_score = (polarity + keyword_score) / 2
        
        # Clamp to [-1, 1]
        combined_score = max(-1, min(1, combined_score))
        
        return {
            "score": combined_score,
            "label": self._score_to_label(combined_score),
            "polarity": polarity,
            "bullish_keywords": bullish_count,
            "bearish_keywords": bearish_count
        }
    
    def _score_to_label(self, score: float) -> str:
        """Convert sentiment score to label"""
        if score > 0.15:
            return "bullish"
        elif score < -0.15:
            return "bearish"
        else:
            return "neutral"
    
    def _calculate_overall_sentiment(self, data: Dict) -> Dict[str, Any]:
        """Calculate overall sentiment from all sources"""
        scores = []
        weights = []
        
        # Reddit sentiment (higher weight due to discussion depth)
        if data.get("reddit") and data["reddit"].get("sentiment_score") is not None:
            scores.append(data["reddit"]["sentiment_score"])
            # Weight by number of mentions
            mentions = data["reddit"].get("total_mentions", 0)
            weights.append(min(2.0, 1.0 + mentions * 0.05))
        
        # StockTwits sentiment
        if data.get("stocktwits") and data["stocktwits"].get("sentiment_score") is not None:
            scores.append(data["stocktwits"]["sentiment_score"])
            messages = data["stocktwits"].get("total_messages", 0)
            weights.append(min(1.5, 1.0 + messages * 0.02))
        
        if not scores:
            return {
                "score": 0,
                "label": "neutral",
                "confidence": "low"
            }
        
        # Weighted average
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        total_weight = sum(weights)
        overall_score = weighted_sum / total_weight
        
        # Confidence based on data volume
        total_data_points = (
            (data.get("reddit", {}).get("total_mentions", 0) or 0) +
            (data.get("stocktwits", {}).get("total_messages", 0) or 0)
        )
        
        if total_data_points > 50:
            confidence = "high"
        elif total_data_points > 20:
            confidence = "medium"
        else:
            confidence = "low"
        
        return {
            "score": overall_score,
            "label": self._score_to_label(overall_score),
            "confidence": confidence,
            "data_points": total_data_points
        }


if __name__ == "__main__":
    collector = SocialSentimentCollector()
    sentiment = collector.get_social_sentiment("AAPL")
    print(f"Overall Sentiment: {sentiment['overall_sentiment']}")
    if sentiment.get('stocktwits'):
        print(f"StockTwits: {sentiment['stocktwits']['sentiment_label']}")
