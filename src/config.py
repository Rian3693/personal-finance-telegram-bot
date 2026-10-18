"""
Configuration settings for the Stock Agent
"""
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "StockAgent/1.0")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Telegram Bot Configuration
# Read from .env only: after the bot was recreated in BotFather, the new token goes
# in ONE place (.env). A hard-coded copy here used to silently override it.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")   # your own Telegram user id

# Analysis Settings
ANALYSIS_TIMEFRAME_MONTHS = 3  # Default 1-3 months outlook
HISTORICAL_DATA_DAYS = 365  # 1 year of historical data for analysis
MIN_DATA_POINTS = 50  # Minimum data points needed for analysis

# =============================================================================
# TIMEFRAME PROFILES - Different analysis configurations for each strategy
# =============================================================================

TIMEFRAME_PROFILES = {
    "swing": {
        "name": "Swing Trading",
        "horizon": "1-4 weeks",
        "description": "Quick momentum plays and short-term price movements",
        "outlook_days": 28,
        "historical_days": 180,
        "news_days": 7,
        "weights": {
            "technical": 0.50,  # Heavy on technicals
            "fundamental": 0.15,
            "sentiment": 0.35,  # Sentiment matters for short swings
        },
        "indicators": {
            "RSI_PERIOD": 14,
            "MACD_FAST": 12,
            "MACD_SLOW": 26,
            "MACD_SIGNAL": 9,
            "SMA_SHORT": 10,
            "SMA_MEDIUM": 20,
            "SMA_LONG": 50,
            "BOLLINGER_PERIOD": 20,
            "BOLLINGER_STD": 2,
        },
        "trend_periods": {
            "short": 5,
            "medium": 20,
            "long": 50,
        },
        "score_thresholds": {
            "strong_buy": 25,
            "buy": 10,
            "sell": -10,
            "strong_sell": -25,
        }
    },
    "short": {
        "name": "Short-term",
        "horizon": "1-3 months",
        "description": "Near-term catalysts and earnings plays",
        "outlook_days": 90,
        "historical_days": 365,
        "news_days": 14,
        "weights": {
            "technical": 0.40,
            "fundamental": 0.25,
            "sentiment": 0.35,
        },
        "indicators": {
            "RSI_PERIOD": 14,
            "MACD_FAST": 12,
            "MACD_SLOW": 26,
            "MACD_SIGNAL": 9,
            "SMA_SHORT": 20,
            "SMA_MEDIUM": 50,
            "SMA_LONG": 100,
            "BOLLINGER_PERIOD": 20,
            "BOLLINGER_STD": 2,
        },
        "trend_periods": {
            "short": 20,
            "medium": 50,
            "long": 100,
        },
        "score_thresholds": {
            "strong_buy": 30,
            "buy": 10,
            "sell": -10,
            "strong_sell": -30,
        }
    },
    "medium": {
        "name": "Medium-term",
        "horizon": "3-12 months",
        "description": "Growth opportunities and sector trends",
        "outlook_days": 270,
        "historical_days": 730,  # 2 years
        "news_days": 30,
        "weights": {
            "technical": 0.30,
            "fundamental": 0.45,  # Fundamentals matter more
            "sentiment": 0.25,
        },
        "indicators": {
            "RSI_PERIOD": 14,
            "MACD_FAST": 12,
            "MACD_SLOW": 26,
            "MACD_SIGNAL": 9,
            "SMA_SHORT": 50,
            "SMA_MEDIUM": 100,
            "SMA_LONG": 200,
            "BOLLINGER_PERIOD": 20,
            "BOLLINGER_STD": 2,
        },
        "trend_periods": {
            "short": 50,
            "medium": 100,
            "long": 200,
        },
        "score_thresholds": {
            "strong_buy": 35,
            "buy": 15,
            "sell": -15,
            "strong_sell": -35,
        }
    },
    "long": {
        "name": "Long-term",
        "horizon": "1-5 years",
        "description": "Value investing and long-term compounding",
        "outlook_days": 365,
        "historical_days": 1825,  # 5 years
        "news_days": 30,
        "weights": {
            "technical": 0.15,  # Less important for long-term
            "fundamental": 0.60,  # Fundamentals are key
            "sentiment": 0.25,
        },
        "indicators": {
            "RSI_PERIOD": 21,
            "MACD_FAST": 12,
            "MACD_SLOW": 26,
            "MACD_SIGNAL": 9,
            "SMA_SHORT": 50,
            "SMA_MEDIUM": 100,
            "SMA_LONG": 200,
            "BOLLINGER_PERIOD": 20,
            "BOLLINGER_STD": 2,
        },
        "trend_periods": {
            "short": 50,
            "medium": 150,
            "long": 200,
        },
        "score_thresholds": {
            "strong_buy": 40,
            "buy": 20,
            "sell": -20,
            "strong_sell": -40,
        }
    }
}

# Default timeframe
DEFAULT_TIMEFRAME = "short"

# Sentiment Analysis Settings
REDDIT_SUBREDDITS = ["wallstreetbets", "stocks", "investing", "stockmarket", "options"]
MAX_REDDIT_POSTS = 100  # Per subreddit
NEWS_SOURCES = [
    "https://finance.yahoo.com",
    "https://www.marketwatch.com",
    "https://www.cnbc.com",
    "https://seekingalpha.com",
    "https://www.fool.com",
    "https://www.investing.com",
]

# Technical Analysis Settings (default - will be overridden by timeframe)
TECHNICAL_INDICATORS = {
    "RSI_PERIOD": 14,
    "MACD_FAST": 12,
    "MACD_SLOW": 26,
    "MACD_SIGNAL": 9,
    "SMA_SHORT": 20,
    "SMA_LONG": 50,
    "SMA_TREND": 200,
    "BOLLINGER_PERIOD": 20,
    "BOLLINGER_STD": 2,
}

# Scoring Weights (default - will be overridden by timeframe)
SCORING_WEIGHTS = {
    "technical": 0.30,
    "fundamental": 0.25,
    "sentiment": 0.20,
    "news": 0.15,
    "price_target": 0.10,
}

# Risk Levels
RISK_THRESHOLDS = {
    "low": {"volatility_max": 0.20, "beta_max": 1.0},
    "medium": {"volatility_max": 0.40, "beta_max": 1.5},
    "high": {"volatility_max": 1.0, "beta_max": 3.0},
}


def get_timeframe_config(timeframe: str) -> dict:
    """Get configuration for a specific timeframe"""
    return TIMEFRAME_PROFILES.get(timeframe, TIMEFRAME_PROFILES[DEFAULT_TIMEFRAME])
