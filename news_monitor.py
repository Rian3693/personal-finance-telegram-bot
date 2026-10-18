"""
News Monitor Agent - 24/7 monitoring for watchlist stocks
Sends alerts via Telegram and Windows notifications for significant news
"""
import os
import time
import json
import hashlib
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import requests
from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

load_dotenv()

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
CHECK_INTERVAL_MINUTES = int(os.getenv("NEWS_CHECK_INTERVAL", "15"))  # Check every 15 min
SEEN_NEWS_FILE = "seen_news.json"


class NewsMonitor:
    """24/7 News monitoring agent for watchlist stocks"""
    
    def __init__(self):
        self.console = Console()
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.seen_news = self._load_seen_news()
        self.running = False
        self.monitor_thread = None
        
        # Keywords that indicate potentially significant news
        self.significant_keywords = {
            "positive": [
                "partnership", "deal", "agreement", "contract", "acquisition",
                "merger", "buyout", "expansion", "growth", "revenue beat",
                "earnings beat", "upgrade", "raised price target", "new product",
                "fda approval", "patent", "breakthrough", "record", "surges",
                "soars", "jumps", "rallies", "government contract", "ai deal",
                "strategic alliance", "joint venture", "billion dollar",
                "market share", "outperform", "strong buy", "bullish"
            ],
            "negative": [
                "lawsuit", "investigation", "sec probe", "fraud", "scandal",
                "recall", "layoffs", "downsizing", "bankruptcy", "default",
                "downgrade", "lowered price target", "missed earnings", "revenue miss",
                "guidance cut", "warning", "plunges", "crashes", "tumbles",
                "drops", "falls", "sells off", "loses", "regulatory issue",
                "data breach", "hack", "ceo resigns", "cfo leaves", "delisting",
                "subpoena", "antitrust", "fine", "penalty", "weak guidance"
            ]
        }
        
        # Reddit subreddits to monitor for stock discussions
        self.reddit_subreddits = [
            "wallstreetbets",
            "stocks", 
            "investing",
            "stockmarket",
            "options",
            "SecurityAnalysis",
            "ValueInvesting"
        ]
    
    def _load_seen_news(self) -> Dict[str, List[str]]:
        """Load previously seen news to avoid duplicate alerts"""
        if os.path.exists(SEEN_NEWS_FILE):
            try:
                with open(SEEN_NEWS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"news_hashes": [], "last_check": None}
    
    def _save_seen_news(self):
        """Save seen news hashes"""
        self.seen_news["last_check"] = datetime.now().isoformat()
        with open(SEEN_NEWS_FILE, 'w') as f:
            json.dump(self.seen_news, f, indent=2)
    
    def _hash_news(self, title: str, source: str) -> str:
        """Create hash of news to detect duplicates"""
        content = f"{title.lower().strip()}|{source.lower().strip()}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _is_new_news(self, news_hash: str) -> bool:
        """Check if this news has been seen before"""
        return news_hash not in self.seen_news["news_hashes"]
    
    def _mark_as_seen(self, news_hash: str):
        """Mark news as seen"""
        self.seen_news["news_hashes"].append(news_hash)
        # Keep only last 1000 hashes to prevent file from growing too large
        if len(self.seen_news["news_hashes"]) > 1000:
            self.seen_news["news_hashes"] = self.seen_news["news_hashes"][-1000:]
        self._save_seen_news()
    
    def fetch_news(self, symbol: str) -> List[Dict]:
        """Fetch latest news for a stock symbol"""
        news_items = []
        
        # Try multiple news sources
        
        # 1. Finviz news
        try:
            from collectors.news_collector import NewsCollector
            collector = NewsCollector()
            finviz_news = collector._get_finviz_news(symbol)
            for item in finviz_news[:10]:  # Last 10 items
                news_items.append({
                    "title": item.get("title", ""),
                    "source": item.get("source", "Finviz"),
                    "url": item.get("url", ""),
                    "timestamp": item.get("timestamp", datetime.now().isoformat()),
                    "symbol": symbol
                })
        except Exception as e:
            self.console.print(f"[dim]Finviz error for {symbol}: {e}[/]")
        
        # 2. Yahoo Finance news via yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            yahoo_news = ticker.news or []
            for item in yahoo_news[:10]:
                news_items.append({
                    "title": item.get("title", ""),
                    "source": item.get("publisher", "Yahoo Finance"),
                    "url": item.get("link", ""),
                    "timestamp": datetime.fromtimestamp(item.get("providerPublishTime", 0)).isoformat() if item.get("providerPublishTime") else datetime.now().isoformat(),
                    "symbol": symbol
                })
        except Exception as e:
            self.console.print(f"[dim]Yahoo error for {symbol}: {e}[/]")
        
        # 3. Reddit posts mentioning this stock
        try:
            reddit_posts = self._fetch_reddit_mentions(symbol)
            news_items.extend(reddit_posts)
        except Exception as e:
            self.console.print(f"[dim]Reddit error for {symbol}: {e}[/]")
        
        # 4. Stocktwits mentions
        try:
            stocktwits_posts = self._fetch_stocktwits(symbol)
            news_items.extend(stocktwits_posts)
        except Exception as e:
            self.console.print(f"[dim]Stocktwits error for {symbol}: {e}[/]")
        
        return news_items
    
    def _fetch_reddit_mentions(self, symbol: str) -> List[Dict]:
        """Fetch Reddit posts mentioning a stock symbol"""
        posts = []
        headers = {
            'User-Agent': 'StockNewsMonitor/1.0 (Educational purposes)'
        }
        
        # Search across multiple subreddits
        for subreddit in self.reddit_subreddits:
            try:
                # Reddit JSON API (no auth required for public data)
                url = f"https://www.reddit.com/r/{subreddit}/search.json?q={symbol}&sort=new&restrict_sr=1&limit=10&t=week"
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    children = data.get("data", {}).get("children", [])
                    
                    for post in children:
                        post_data = post.get("data", {})
                        title = post_data.get("title", "")
                        selftext = post_data.get("selftext", "")
                        combined_text = f"{title} {selftext}".upper()
                        
                        # More flexible symbol matching - check title and body
                        symbol_found = (
                            f"${symbol}" in combined_text or 
                            f" {symbol} " in f" {combined_text} " or
                            combined_text.startswith(f"{symbol} ") or
                            combined_text.endswith(f" {symbol}") or
                            f"({symbol})" in combined_text or
                            symbol in combined_text.split()
                        )
                        
                        if symbol_found:
                            created = post_data.get("created_utc", 0)
                            upvotes = post_data.get("ups", 0)
                            comments = post_data.get("num_comments", 0)
                            
                            # Include if has decent engagement
                            if upvotes > 10 or comments > 5:
                                posts.append({
                                    "title": f"[Reddit r/{subreddit}] {title}",
                                    "source": f"Reddit r/{subreddit}",
                                    "url": f"https://reddit.com{post_data.get('permalink', '')}",
                                    "timestamp": datetime.fromtimestamp(created).isoformat() if created else datetime.now().isoformat(),
                                    "symbol": symbol,
                                    "upvotes": upvotes,
                                    "comments": comments,
                                    "is_social": True
                                })
                
                # Small delay to avoid rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                self.console.print(f"[dim]Reddit r/{subreddit} error: {e}[/]")
        
        return posts
    
    def _fetch_stocktwits(self, symbol: str) -> List[Dict]:
        """Fetch Stocktwits messages for a symbol"""
        posts = []
        
        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            # Check for Cloudflare block
            if response.status_code == 403:
                # Stocktwits has Cloudflare protection - skip silently
                return posts
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                
                for msg in messages[:10]:  # Last 10 messages
                    body = msg.get("body", "")
                    sentiment = msg.get("entities", {}).get("sentiment", {})
                    sentiment_label = sentiment.get("basic", "Neutral") if sentiment else "Neutral"
                    
                    # Include posts with any engagement, sentiment, or meaningful content
                    likes = msg.get("likes", {}).get("total", 0)
                    
                    # Lower threshold - include if has sentiment tag, any likes, or significant text
                    if likes >= 1 or sentiment_label in ["Bullish", "Bearish"] or len(body) > 50:
                        created = msg.get("created_at", "")
                        posts.append({
                            "title": f"[Stocktwits] {body[:150]}{'...' if len(body) > 150 else ''}",
                            "source": f"Stocktwits ({sentiment_label})",
                            "url": f"https://stocktwits.com/symbol/{symbol}",
                            "timestamp": created,
                            "symbol": symbol,
                            "sentiment": sentiment_label,
                            "likes": likes,
                            "is_social": True
                        })
                        
        except Exception as e:
            self.console.print(f"[dim]Stocktwits error for {symbol}: {e}[/]")
        
        return posts
    
    def analyze_news_significance(self, news_item: Dict) -> Dict:
        """Use AI to analyze if news is significant and its potential impact"""
        title = news_item.get("title", "")
        symbol = news_item.get("symbol", "")
        is_social = news_item.get("is_social", False)
        
        # Quick keyword check first
        title_lower = title.lower()
        has_positive = any(kw in title_lower for kw in self.significant_keywords["positive"])
        has_negative = any(kw in title_lower for kw in self.significant_keywords["negative"])
        
        # For social media, also check for viral indicators
        social_keywords = ["moon", "rocket", "yolo", "diamond hands", "to the moon", 
                          "short squeeze", "gamma squeeze", "breaking", "urgent",
                          "insider", "leak", "confirmed", "massive", "huge"]
        has_social_buzz = any(kw in title_lower for kw in social_keywords)
        
        # For social posts, check engagement (Reddit upvotes, Stocktwits likes)
        high_engagement = False
        if is_social:
            upvotes = news_item.get("upvotes", 0)
            likes = news_item.get("likes", 0)
            comments = news_item.get("comments", 0)
            if upvotes > 100 or likes > 20 or comments > 50:
                high_engagement = True
        
        # If no significant keywords and no social buzz, skip AI analysis
        if not has_positive and not has_negative and not has_social_buzz and not high_engagement:
            return {
                "is_significant": False,
                "impact": "neutral",
                "score": 0,
                "summary": "",
                "action": ""
            }
        
        # Use AI for deeper analysis
        try:
            source_type = "social media post" if is_social else "news headline"
            social_context = ""
            if is_social:
                social_context = f"""
This is from social media. Consider:
- Reddit upvotes: {news_item.get('upvotes', 'N/A')}
- Comments: {news_item.get('comments', 'N/A')}
- Stocktwits likes: {news_item.get('likes', 'N/A')}
- Sentiment tag: {news_item.get('sentiment', 'N/A')}

Social media can sometimes signal retail sentiment ahead of price moves, but verify with official sources."""
            
            prompt = f"""Analyze this {source_type} for stock {symbol} and determine its potential market impact.

Content: "{title}"
{social_context}

Respond in JSON format:
{{
    "is_significant": true/false (is this {'post getting traction and' if is_social else 'news'} likely to affect the stock?),
    "impact": "very_positive" | "positive" | "neutral" | "negative" | "very_negative",
    "price_impact_estimate": "X% to Y%" (estimated price impact range),
    "urgency": "immediate" | "short_term" | "medium_term" (when will impact be felt),
    "category": "deal/partnership" | "earnings" | "product" | "legal" | "management" | "regulatory" | "market" | "social_sentiment" | "other",
    "summary": "Brief 1-2 sentence summary of why this matters",
    "recommended_action": "What the investor should consider doing"
}}

{'For social media, be more skeptical - only mark significant if there is credible info or very high engagement.' if is_social else 'Only mark as significant if this could move the stock by more than 2-3%.'}"""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for faster/cheaper analysis
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Analyze content for potential stock price impact. Be conservative - only flag truly significant items. For social media, be extra skeptical of unverified claims."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=500
            )
            
            analysis = json.loads(response.choices[0].message.content)
            return {
                "is_significant": analysis.get("is_significant", False),
                "impact": analysis.get("impact", "neutral"),
                "price_impact": analysis.get("price_impact_estimate", "Unknown"),
                "urgency": analysis.get("urgency", "short_term"),
                "category": analysis.get("category", "other"),
                "summary": analysis.get("summary", ""),
                "action": analysis.get("recommended_action", "")
            }
            
        except Exception as e:
            self.console.print(f"[red]AI analysis error: {e}[/]")
            # Fallback to keyword-based analysis
            return {
                "is_significant": has_positive or has_negative,
                "impact": "positive" if has_positive else "negative",
                "price_impact": "Unknown",
                "urgency": "short_term",
                "category": "other",
                "summary": title,
                "action": "Review news details"
            }
    
    def send_telegram_notification(self, message: str) -> bool:
        """Send notification via Telegram"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            self.console.print("[yellow]Telegram not configured. Skipping.[/]")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            self.console.print(f"[red]Telegram error: {e}[/]")
            return False
    
    def send_windows_notification(self, title: str, message: str, symbol: str = "") -> bool:
        """Send Windows toast notification"""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                title=f"📈 Stock Alert: {symbol}" if symbol else title,
                msg=message[:250],  # Windows has character limit
                duration=10,
                threaded=True
            )
            return True
        except ImportError:
            # Try alternative method using PowerShell
            try:
                import subprocess
                ps_script = f'''
                [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
                [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
                $template = @"
                <toast>
                    <visual>
                        <binding template="ToastText02">
                            <text id="1">📈 {title}</text>
                            <text id="2">{message[:200]}</text>
                        </binding>
                    </visual>
                </toast>
"@
                $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
                $xml.LoadXml($template)
                $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
                [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Stock Agent").Show($toast)
                '''
                subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
                return True
            except:
                self.console.print("[yellow]Windows notification failed. Install win10toast: pip install win10toast[/]")
                return False
        except Exception as e:
            self.console.print(f"[red]Windows notification error: {e}[/]")
            return False
    
    def format_alert_message(self, news_item: Dict, analysis: Dict) -> str:
        """Format alert message for notifications"""
        symbol = news_item.get("symbol", "Unknown")
        title = news_item.get("title", "")
        source = news_item.get("source", "")
        url = news_item.get("url", "")
        is_social = news_item.get("is_social", False)
        
        impact = analysis.get("impact", "neutral")
        impact_emoji = {
            "very_positive": "🚀🟢",
            "positive": "📈🟢",
            "neutral": "➡️🟡",
            "negative": "📉🔴",
            "very_negative": "💥🔴"
        }.get(impact, "❓")
        
        urgency = analysis.get("urgency", "short_term")
        urgency_emoji = {
            "immediate": "⚡",
            "short_term": "⏰",
            "medium_term": "📅"
        }.get(urgency, "")
        
        # Add social media specific info
        social_info = ""
        if is_social:
            if "Reddit" in source:
                upvotes = news_item.get("upvotes", 0)
                comments = news_item.get("comments", 0)
                social_info = f"\n<b>👍 Upvotes:</b> {upvotes} | <b>💬 Comments:</b> {comments}"
            elif "Stocktwits" in source:
                sentiment = news_item.get("sentiment", "neutral")
                likes = news_item.get("likes", 0)
                social_info = f"\n<b>🎭 Sentiment:</b> {sentiment} | <b>❤️ Likes:</b> {likes}"
        
        source_emoji = "🗣️" if is_social else "📰"
        alert_type = "SOCIAL BUZZ" if is_social else "NEWS ALERT"
        
        message = f"""
{impact_emoji} <b>STOCK {alert_type}: ${symbol}</b> {impact_emoji}

<b>{source_emoji} {'Post' if is_social else 'News'}:</b> {title}{social_info}

<b>📊 Impact:</b> {impact.upper().replace("_", " ")}
<b>💰 Est. Price Effect:</b> {analysis.get('price_impact', 'N/A')}
<b>{urgency_emoji} Urgency:</b> {urgency.replace("_", " ").title()}
<b>📁 Category:</b> {analysis.get('category', 'N/A').title()}

<b>💡 Summary:</b>
{analysis.get('summary', 'N/A')}

<b>🎯 Recommended Action:</b>
{analysis.get('action', 'Review and assess')}

<i>Source: {source}</i>
<a href="{url}">{'View Post' if is_social else 'Read Full Article'}</a>

⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return message.strip()
    
    def format_windows_message(self, news_item: Dict, analysis: Dict) -> tuple:
        """Format message for Windows notification (shorter)"""
        symbol = news_item.get("symbol", "")
        impact = analysis.get("impact", "neutral")
        title = f"{symbol}: {impact.upper().replace('_', ' ')}"
        
        message = f"{news_item.get('title', '')[:100]}... | {analysis.get('summary', '')[:100]}"
        return title, message
    
    def _get_monitored_symbols(self) -> set:
        """Get all symbols from watchlists and portfolio"""
        all_stocks = set()
        
        # Get from watchlists
        try:
            from watchlist import WatchlistManager
            wl_manager = WatchlistManager()
            for key, watchlist in wl_manager.get_all_watchlists().items():
                stocks = watchlist.get("stocks", {}).keys()
                all_stocks.update(stocks)
        except Exception as e:
            self.console.print(f"[dim]Error loading watchlist: {e}[/]")
        
        # Get from portfolio
        try:
            portfolio_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "my_portfolio.json")
            if os.path.exists(portfolio_file):
                with open(portfolio_file, 'r') as f:
                    portfolio_data = json.load(f)
                    for holding in portfolio_data.get("holdings", []):
                        all_stocks.add(holding.get("symbol", ""))
        except Exception as e:
            self.console.print(f"[dim]Error loading portfolio: {e}[/]")
        
        # Remove empty strings
        all_stocks.discard("")
        return all_stocks
    
    def check_watchlist_news(self) -> List[Dict]:
        """Check news for all stocks in watchlists and portfolio"""
        alerts = []
        
        # Get all monitored symbols (watchlists + portfolio)
        all_stocks = self._get_monitored_symbols()
        
        if not all_stocks:
            self.console.print("[yellow]No stocks in watchlist or portfolio to monitor.[/]")
            return alerts
        
        self.console.print(f"\n[cyan]Checking news for {len(all_stocks)} stocks: {', '.join(sorted(all_stocks))}[/]")
        
        for symbol in all_stocks:
            news_items = self.fetch_news(symbol)
            
            for news in news_items:
                news_hash = self._hash_news(news["title"], news["source"])
                
                # Skip if already seen
                if not self._is_new_news(news_hash):
                    continue
                
                # Analyze significance
                analysis = self.analyze_news_significance(news)
                
                # Mark as seen regardless of significance
                self._mark_as_seen(news_hash)
                
                if analysis["is_significant"]:
                    alerts.append({
                        "news": news,
                        "analysis": analysis
                    })
        
        return alerts
    
    def process_alerts(self, alerts: List[Dict]):
        """Process and send all alerts"""
        for alert in alerts:
            news = alert["news"]
            analysis = alert["analysis"]
            
            # Print to console
            impact = analysis.get("impact", "neutral")
            color = "green" if "positive" in impact else ("red" if "negative" in impact else "yellow")
            
            self.console.print(Panel(
                f"[bold]{news['title']}[/]\n\n"
                f"Symbol: {news['symbol']}\n"
                f"Impact: [{color}]{impact.upper()}[/{color}]\n"
                f"Summary: {analysis.get('summary', '')}\n"
                f"Action: {analysis.get('action', '')}",
                title=f"🚨 SIGNIFICANT NEWS ALERT",
                border_style=color
            ))
            
            # Send Telegram notification
            telegram_msg = self.format_alert_message(news, analysis)
            if self.send_telegram_notification(telegram_msg):
                self.console.print("[green]✓ Telegram notification sent[/]")
            
            # Send Windows notification
            win_title, win_msg = self.format_windows_message(news, analysis)
            if self.send_windows_notification(win_title, win_msg, news['symbol']):
                self.console.print("[green]✓ Windows notification sent[/]")
            
            # Small delay between alerts
            time.sleep(1)
    
    def run_once(self) -> int:
        """Run a single check cycle, return number of alerts"""
        self.console.print(f"\n[bold cyan]{'='*60}[/]")
        self.console.print(f"[bold]📰 News Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/]")
        self.console.print(f"[bold cyan]{'='*60}[/]")
        
        alerts = self.check_watchlist_news()
        
        if alerts:
            self.console.print(f"\n[bold yellow]⚠️ Found {len(alerts)} significant news items![/]")
            self.process_alerts(alerts)
        else:
            self.console.print("[dim]No significant news found.[/]")
        
        return len(alerts)
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.running:
            try:
                self.run_once()
            except Exception as e:
                self.console.print(f"[red]Monitor error: {e}[/]")
            
            # Wait for next check
            next_check = datetime.now() + timedelta(minutes=CHECK_INTERVAL_MINUTES)
            self.console.print(f"\n[dim]Next check at {next_check.strftime('%H:%M:%S')} (every {CHECK_INTERVAL_MINUTES} min)[/]")
            
            # Sleep in small increments to allow graceful shutdown
            for _ in range(CHECK_INTERVAL_MINUTES * 60):
                if not self.running:
                    break
                time.sleep(1)
    
    def send_todays_news_recap(self):
        """Send a recap of all today's news to Telegram on startup"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            self.console.print("[yellow]Telegram not configured - skipping news recap[/]")
            return
        
        self.console.print("[cyan]📰 Gathering today's news recap...[/]")
        
        # Get all symbols to monitor
        symbols = self._get_monitored_symbols()
        if not symbols:
            self.console.print("[yellow]No symbols to monitor[/]")
            return
        
        today = datetime.now().date()
        all_news = []
        
        for symbol in symbols:
            self.console.print(f"[dim]Fetching news for {symbol}...[/]")
            news_items = self.fetch_news(symbol)
            
            for news in news_items:
                # Parse timestamp and check if today
                try:
                    ts = news.get("timestamp", "")
                    if ts:
                        news_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                        if news_date == today:
                            all_news.append(news)
                except:
                    pass
        
        if not all_news:
            self.send_telegram_notification(
                "📰 <b>News Monitor Started</b>\n\n"
                f"No significant news found today for your {len(symbols)} tracked stocks.\n"
                f"Will notify you when news breaks!"
            )
            self.console.print("[green]✓ Startup notification sent (no news today)[/]")
            return
        
        # Remove duplicates by title
        seen_titles = set()
        unique_news = []
        for news in all_news:
            title = news.get("title", "")[:50]  # First 50 chars
            if title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)
        
        # Group by symbol
        by_symbol = {}
        for news in unique_news:
            sym = news.get("symbol", "UNKNOWN")
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(news)
        
        # Build recap message
        message = f"📰 <b>Today's News Recap</b>\n"
        message += f"📅 {today.strftime('%B %d, %Y')}\n"
        message += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for symbol, news_list in sorted(by_symbol.items()):
            message += f"<b>${symbol}</b> ({len(news_list)} items)\n"
            for news in news_list[:3]:  # Max 3 per symbol
                title = news.get("title", "")[:80]
                source = news.get("source", "")
                message += f"• {title}\n"
                if source:
                    message += f"  <i>via {source}</i>\n"
            if len(news_list) > 3:
                message += f"  <i>...and {len(news_list) - 3} more</i>\n"
            message += "\n"
        
        message += f"━━━━━━━━━━━━━━━━━━━━\n"
        message += f"📊 Total: {len(unique_news)} news items for {len(by_symbol)} stocks\n"
        message += "🔔 Monitoring for new alerts..."
        
        # Telegram has 4096 char limit
        if len(message) > 4000:
            message = message[:3900] + "\n\n<i>...message truncated</i>"
        
        if self.send_telegram_notification(message):
            self.console.print(f"[green]✓ News recap sent! ({len(unique_news)} items for {len(by_symbol)} stocks)[/]")
        else:
            self.console.print("[red]✗ Failed to send recap[/]")
    
    def start(self):
        """Start 24/7 monitoring in background"""
        if self.running:
            self.console.print("[yellow]Monitor already running![/]")
            return
        
        self.running = True
        
        # Send today's news recap on startup
        self.send_todays_news_recap()
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.console.print(Panel(
            f"[bold green]✓ News Monitor Started![/]\n\n"
            f"• Checking every {CHECK_INTERVAL_MINUTES} minutes\n"
            f"• Monitoring all watchlist stocks\n"
            f"• Telegram: {'✓ Configured' if TELEGRAM_BOT_TOKEN else '✗ Not configured'}\n"
            f"• Windows notifications: Enabled\n\n"
            "[dim]Press Ctrl+C to stop[/]",
            title="📰 24/7 News Monitor"
        ))
    
    def stop(self):
        """Stop monitoring"""
        self.running = False
        self.console.print("\n[yellow]Stopping news monitor...[/]")
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        self.console.print("[green]✓ News monitor stopped[/]")
    
    def run_forever(self):
        """Run monitor continuously (blocking)"""
        self.start()
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()


def setup_telegram():
    """Interactive setup for Telegram bot"""
    console = Console()
    
    console.print(Panel(
        "[bold]Telegram Bot Setup[/]\n\n"
        "To receive alerts via Telegram, you need:\n"
        "1. Create a bot via @BotFather on Telegram\n"
        "2. Get your bot token\n"
        "3. Get your chat ID (send a message to your bot, then check the API)\n\n"
        "[cyan]Steps:[/]\n"
        "1. Open Telegram and search for @BotFather\n"
        "2. Send /newbot and follow instructions\n"
        "3. Copy the bot token\n"
        "4. Start a chat with your new bot\n"
        "5. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates\n"
        "6. Find your chat_id in the response",
        title="📱 Telegram Setup"
    ))
    
    from rich.prompt import Prompt
    
    token = Prompt.ask("\n[bold]Enter your Telegram Bot Token[/]")
    chat_id = Prompt.ask("[bold]Enter your Telegram Chat ID[/]")
    
    if token and chat_id:
        # Update .env file
        env_path = ".env"
        env_content = ""
        
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                env_content = f.read()
        
        # Update or add Telegram settings
        if "TELEGRAM_BOT_TOKEN" in env_content:
            lines = env_content.split('\n')
            lines = [l for l in lines if not l.startswith("TELEGRAM_BOT_TOKEN") and not l.startswith("TELEGRAM_CHAT_ID")]
            env_content = '\n'.join(lines)
        
        env_content += f"\nTELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat_id}\n"
        
        with open(env_path, 'w') as f:
            f.write(env_content)
        
        console.print("[green]✓ Telegram credentials saved to .env[/]")
        
        # Test notification
        if Prompt.ask("Send test notification?", choices=["y", "n"], default="y") == "y":
            monitor = NewsMonitor()
            monitor.send_telegram_notification("🎉 <b>Test Alert!</b>\n\nYour Stock Agent news monitor is now connected to Telegram!")
            console.print("[green]✓ Test notification sent! Check your Telegram.[/]")
    
    return token, chat_id


def main():
    """Main entry point"""
    import sys
    
    console = Console()
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "setup":
            setup_telegram()
        elif command == "once":
            monitor = NewsMonitor()
            monitor.run_once()
        elif command == "start":
            monitor = NewsMonitor()
            monitor.run_forever()
        else:
            console.print(f"Unknown command: {command}")
            console.print("Usage: python news_monitor.py [setup|once|start]")
    else:
        # Default: run forever
        console.print(Panel(
            "[bold]News Monitor Commands:[/]\n\n"
            "• [cyan]python news_monitor.py setup[/] - Setup Telegram notifications\n"
            "• [cyan]python news_monitor.py once[/] - Run a single check\n"
            "• [cyan]python news_monitor.py start[/] - Start 24/7 monitoring\n",
            title="📰 News Monitor"
        ))
        
        from rich.prompt import Prompt
        choice = Prompt.ask("What would you like to do?", choices=["setup", "once", "start", "quit"], default="once")
        
        if choice == "setup":
            setup_telegram()
        elif choice == "once":
            monitor = NewsMonitor()
            monitor.run_once()
        elif choice == "start":
            monitor = NewsMonitor()
            monitor.run_forever()


if __name__ == "__main__":
    main()
