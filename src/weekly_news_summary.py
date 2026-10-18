"""
Weekly News Summary - Analyzes news from the past week and stock price reactions
"""
import yfinance as yf
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json
import os
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from collectors.news_collector import NewsCollector
from config import OPENAI_API_KEY

console = Console()

try:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    HAS_OPENAI = True
except:
    HAS_OPENAI = False


class WeeklyNewsSummary:
    """Analyzes weekly news and their impact on stock prices"""
    
    def __init__(self):
        self.news_collector = NewsCollector()
        self.output_dir = "weekly_reports"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Reddit subreddits to monitor
        self.reddit_subreddits = [
            "wallstreetbets", "stocks", "investing", 
            "stockmarket", "options", "ValueInvesting"
        ]
    
    def fetch_reddit_posts(self, symbol: str, days: int = 7) -> List[Dict]:
        """Fetch Reddit posts mentioning a stock symbol from the past week"""
        posts = []
        headers = {
            'User-Agent': 'StockNewsMonitor/1.0 (Educational purposes)'
        }
        cutoff_date = datetime.now() - timedelta(days=days)
        
        for subreddit in self.reddit_subreddits:
            try:
                # Reddit JSON API - search for symbol mentions
                url = f"https://www.reddit.com/r/{subreddit}/search.json?q={symbol}&sort=top&restrict_sr=1&limit=10&t=week"
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    children = data.get("data", {}).get("children", [])
                    
                    for post in children:
                        post_data = post.get("data", {})
                        title = post_data.get("title", "")
                        selftext = post_data.get("selftext", "")
                        combined_text = f"{title} {selftext}".upper()
                        
                        # Flexible symbol matching - check title and body
                        symbol_found = (
                            f"${symbol}" in combined_text or 
                            f" {symbol} " in f" {combined_text} " or
                            combined_text.startswith(f"{symbol} ") or
                            f"({symbol})" in combined_text or
                            symbol in combined_text.split()
                        )
                        
                        if symbol_found:
                            created = post_data.get("created_utc", 0)
                            post_date = datetime.fromtimestamp(created) if created else datetime.now()
                            upvotes = post_data.get("ups", 0)
                            comments = post_data.get("num_comments", 0)
                            
                            # Include posts with decent engagement
                            if post_date >= cutoff_date and (upvotes > 10 or comments > 5):
                                posts.append({
                                    'title': f"🗣️ [Reddit r/{subreddit}] {title}",
                                    'date': post_date.strftime('%Y-%m-%d'),
                                    'parsed_date': post_date,
                                    'source': f"Reddit r/{subreddit}",
                                    'url': f"https://reddit.com{post_data.get('permalink', '')}",
                                    'upvotes': upvotes,
                                    'comments': comments,
                                    'is_social': True
                                })
                
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                console.print(f"[dim]Reddit r/{subreddit} error: {e}[/dim]")
        
        return posts
    
    def fetch_stocktwits(self, symbol: str) -> List[Dict]:
        """Fetch Stocktwits messages for a symbol"""
        posts = []
        cutoff_date = datetime.now() - timedelta(days=7)
        
        try:
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            
            # Handle Cloudflare protection
            if response.status_code == 403:
                return posts  # Skip silently
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                
                for msg in messages[:15]:  # Top 15 messages
                    body = msg.get("body", "")
                    sentiment = msg.get("entities", {}).get("sentiment", {})
                    sentiment_label = sentiment.get("basic", "Neutral") if sentiment else "Neutral"
                    likes = msg.get("likes", {}).get("total", 0)
                    
                    # Parse date
                    created = msg.get("created_at", "")
                    try:
                        post_date = datetime.strptime(created[:19], '%Y-%m-%dT%H:%M:%S')
                    except:
                        post_date = datetime.now()
                    
                    if post_date >= cutoff_date and (likes > 3 or sentiment_label in ["Bullish", "Bearish"]):
                        sentiment_emoji = "🟢" if sentiment_label == "Bullish" else ("🔴" if sentiment_label == "Bearish" else "⚪")
                        posts.append({
                            'title': f"💬 [Stocktwits {sentiment_emoji}] {body[:120]}{'...' if len(body) > 120 else ''}",
                            'date': post_date.strftime('%Y-%m-%d'),
                            'parsed_date': post_date,
                            'source': f"Stocktwits ({sentiment_label})",
                            'url': f"https://stocktwits.com/symbol/{symbol}",
                            'sentiment': sentiment_label,
                            'likes': likes,
                            'is_social': True
                        })
                        
        except Exception as e:
            console.print(f"[dim]Stocktwits error for {symbol}: {e}[/dim]")
        
        return posts
    
    def get_watchlist_stocks(self) -> List[str]:
        """Get stocks from the active watchlist"""
        try:
            # Try new multi-watchlist format first
            if os.path.exists("watchlists.json"):
                with open("watchlists.json", "r") as f:
                    data = json.load(f)
                    active = data.get("active_watchlist", "default")
                    return data.get("watchlists", {}).get(active, {}).get("stocks", [])
            # Fall back to old format
            elif os.path.exists("watchlist.json"):
                with open("watchlist.json", "r") as f:
                    data = json.load(f)
                    return data.get("stocks", [])
        except Exception as e:
            console.print(f"[red]Error loading watchlist: {e}[/red]")
        return []
    
    def get_stock_price_data(self, symbol: str, days: int = 14) -> Optional[Dict]:
        """Get stock price data for the past N days"""
        try:
            stock = yf.Ticker(symbol)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            hist = stock.history(start=start_date, end=end_date)
            
            if hist.empty:
                return None
            
            # Calculate daily change for each day (close-to-close from previous day)
            daily_changes = {}
            closes = hist['Close'].tolist()
            dates = hist.index.tolist()
            
            for i, (date, row) in enumerate(hist.iterrows()):
                date_str = date.strftime('%Y-%m-%d')
                close_price = row['Close']
                
                # Calculate close-to-close change (previous day close to current day close)
                if i > 0:
                    prev_close = closes[i - 1]
                    if prev_close > 0:
                        daily_pct = ((close_price - prev_close) / prev_close) * 100
                    else:
                        daily_pct = 0
                else:
                    daily_pct = 0  # First day, no previous close
                
                daily_changes[date_str] = {
                    'open': row['Open'],
                    'close': close_price,
                    'prev_close': closes[i - 1] if i > 0 else None,
                    'high': row['High'],
                    'low': row['Low'],
                    'change_pct': round(daily_pct, 2)
                }
            
            # Calculate weekly change (first day of week to last day)
            week_start_close = hist['Close'].iloc[0] if len(hist) > 0 else 0
            week_end_close = hist['Close'].iloc[-1] if len(hist) > 0 else 0
            if week_start_close > 0:
                weekly_change_pct = ((week_end_close - week_start_close) / week_start_close) * 100
            else:
                weekly_change_pct = 0
            
            return {
                'dates': hist.index.tolist(),
                'close': hist['Close'].tolist(),
                'open': hist['Open'].tolist(),
                'high': hist['High'].tolist(),
                'low': hist['Low'].tolist(),
                'volume': hist['Volume'].tolist(),
                'daily_changes': daily_changes,
                'weekly_change': {
                    'start_price': round(week_start_close, 2),
                    'end_price': round(week_end_close, 2),
                    'change_pct': round(weekly_change_pct, 2),
                    'start_date': hist.index[0].strftime('%Y-%m-%d') if len(hist) > 0 else None,
                    'end_date': hist.index[-1].strftime('%Y-%m-%d') if len(hist) > 0 else None
                }
            }
        except Exception as e:
            console.print(f"[yellow]Warning: Could not get price data for {symbol}: {e}[/yellow]")
            return None
    
    def analyze_price_impact(self, news_date: datetime, price_data: Dict, symbol: str) -> Dict:
        """Analyze how stock price moved in 1-3 days after news"""
        if not price_data:
            return {"impact": "Unknown", "details": "No price data available"}
        
        dates = price_data['dates']
        closes = price_data['close']
        
        # Convert news_date to date object for comparison
        if hasattr(news_date, 'date'):
            n_date = news_date.date()
        elif isinstance(news_date, str):
            try:
                n_date = datetime.strptime(news_date, '%Y-%m-%d').date()
            except:
                return {"impact": "Unknown", "details": "Could not parse news date"}
        else:
            n_date = news_date
        
        # Find the closest trading day ON or BEFORE the news date (news day price)
        news_day_idx = None
        for i in range(len(dates) - 1, -1, -1):  # Search backwards
            d = dates[i]
            if hasattr(d, 'date'):
                d_date = d.date()
            elif hasattr(d, 'to_pydatetime'):
                d_date = d.to_pydatetime().date()
            else:
                d_date = d
            
            if d_date <= n_date:
                news_day_idx = i
                break
        
        # If no trading day on or before news, find the next trading day
        if news_day_idx is None:
            for i, d in enumerate(dates):
                if hasattr(d, 'date'):
                    d_date = d.date()
                elif hasattr(d, 'to_pydatetime'):
                    d_date = d.to_pydatetime().date()
                else:
                    d_date = d
                
                if d_date >= n_date:
                    news_day_idx = i
                    break
        
        if news_day_idx is None:
            return {
                "impact": "⏳ Too Recent",
                "news_day_price": closes[-1] if closes else None,
                "changes": {},
                "overall_change": None,
                "details": "News too recent"
            }
        
        # Get price on news day
        news_day_price = closes[news_day_idx]
        
        # Calculate changes for available days after the news
        changes = {}
        available_days_after = len(closes) - news_day_idx - 1
        
        for days in [1, 2, 3]:
            future_idx = news_day_idx + days
            if future_idx < len(closes):
                future_price = closes[future_idx]
                change_pct = ((future_price - news_day_price) / news_day_price) * 100
                changes[f"day_{days}"] = {
                    "price": round(future_price, 2),
                    "change_pct": round(change_pct, 2)
                }
        
        # Calculate change from news day to latest available price
        latest_price = closes[-1]
        total_change = ((latest_price - news_day_price) / news_day_price) * 100
        
        # Determine overall impact using best available data
        if changes:
            max_days = max([int(k.split('_')[1]) for k in changes.keys()])
            final_change = changes.get(f"day_{max_days}", {}).get("change_pct", 0)
        elif available_days_after >= 0:
            final_change = total_change
        else:
            final_change = 0
        
        # Determine impact label with emojis
        if final_change > 5:
            impact = "🚀 Strong +"
        elif final_change > 2:
            impact = "📈 Positive"
        elif final_change > -2:
            impact = "➡️ Neutral"
        elif final_change > -5:
            impact = "📉 Negative"
        else:
            impact = "💥 Strong -"
        
        # Add note about data availability
        if available_days_after == 0:
            impact = f"⏳ Same Day"
            final_change = 0  # Can't measure impact on same day
        elif available_days_after < 3 and available_days_after > 0:
            impact = f"{impact} ({available_days_after}d)"
        
        return {
            "impact": impact,
            "news_day_price": round(news_day_price, 2),
            "changes": changes,
            "overall_change": round(final_change, 2) if final_change != 0 else 0.0,
            "total_change": round(total_change, 2),
            "days_of_data": available_days_after
        }
    
    def get_ai_summary(self, symbol: str, news_items: List[Dict], price_impacts: List[Dict]) -> str:
        """Get AI-generated summary of news and price impacts"""
        if not HAS_OPENAI:
            return "AI summary not available (OpenAI not configured)"
        
        # Build context for AI
        news_context = []
        social_context = []
        
        for news, impact in zip(news_items, price_impacts):
            is_social = news.get('is_social', False) or 'Reddit' in news.get('source', '') or 'Stocktwits' in news.get('source', '')
            
            item = {
                "headline": news.get('title', 'No title'),
                "date": news.get('date', 'Unknown'),
                "source": news.get('source', 'Unknown'),
                "impact": impact.get('impact', 'Unknown'),
                "price_change": impact.get('overall_change', 'N/A')
            }
            
            if is_social:
                item["upvotes"] = news.get('upvotes', 0)
                item["sentiment"] = news.get('sentiment', 'Unknown')
                social_context.append(item)
            else:
                news_context.append(item)
        
        prompt = f"""Analyze the following news and social media activity from the past week for {symbol}.

NEWS ARTICLES:
{json.dumps(news_context, indent=2) if news_context else 'No news articles found.'}

SOCIAL MEDIA BUZZ (Reddit, Stocktwits):
{json.dumps(social_context, indent=2) if social_context else 'No significant social media activity found.'}

Provide a concise summary (4-6 sentences) covering:
1. The main themes/events that affected the stock this week
2. How the market reacted to each major piece of news
3. Social media sentiment - is retail bullish or bearish?
4. Overall sentiment and trend direction

Be specific about which news caused positive or negative price movements. Note any disconnect between social sentiment and actual price action."""

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a financial analyst summarizing weekly stock news and price impacts. Be concise and insightful."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"AI summary error: {e}"
    
    def generate_stock_summary(self, symbol: str) -> Dict:
        """Generate weekly news summary for a single stock"""
        console.print(f"\n[cyan]Analyzing {symbol}...[/cyan]")
        
        # Get news from news collector
        news_result = self.news_collector.get_stock_news(symbol)
        news_items = news_result.get('articles', [])
        
        # Also get news directly from yfinance (often has better timestamps)
        try:
            stock = yf.Ticker(symbol)
            yf_news = stock.news
            if yf_news:
                for item in yf_news:
                    pub_time = item.get('providerPublishTime', 0)
                    if pub_time:
                        news_date = datetime.fromtimestamp(pub_time)
                        news_items.append({
                            'title': item.get('title', ''),
                            'date': news_date.strftime('%Y-%m-%d'),
                            'source': item.get('publisher', 'Yahoo Finance'),
                            'url': item.get('link', ''),
                            'parsed_date': news_date
                        })
        except Exception as e:
            pass
        
        # Get social media posts (Reddit, Stocktwits)
        console.print(f"[dim]  Fetching Reddit mentions...[/dim]")
        reddit_posts = self.fetch_reddit_posts(symbol)
        news_items.extend(reddit_posts)
        
        console.print(f"[dim]  Fetching Stocktwits...[/dim]")
        stocktwits_posts = self.fetch_stocktwits(symbol)
        news_items.extend(stocktwits_posts)
        
        # Filter to past week only - be more lenient with date parsing
        one_week_ago = datetime.now() - timedelta(days=7)
        recent_news = []
        
        for news in news_items:
            # If already has parsed_date, use it
            if 'parsed_date' in news:
                if news['parsed_date'] >= one_week_ago:
                    recent_news.append(news)
                continue
            
            news_date = news.get('date')
            parsed = False
            
            if news_date:
                if isinstance(news_date, str):
                    # Try various date formats
                    date_formats = [
                        '%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                        '%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y',
                        '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d',
                        '%B %d', '%b %d',  # Without year - assume current year
                    ]
                    
                    for fmt in date_formats:
                        try:
                            parsed_date = datetime.strptime(news_date.strip(), fmt)
                            # If no year in format, assume current year
                            if '%Y' not in fmt:
                                parsed_date = parsed_date.replace(year=datetime.now().year)
                            news['parsed_date'] = parsed_date
                            parsed = True
                            break
                        except:
                            continue
                    
                    # If still not parsed but has "ago" or similar, assume recent
                    if not parsed and any(x in news_date.lower() for x in ['ago', 'today', 'yesterday', 'hour', 'min']):
                        news['parsed_date'] = datetime.now()
                        parsed = True
                
                elif isinstance(news_date, datetime):
                    news['parsed_date'] = news_date
                    parsed = True
            
            # If we couldn't parse date, include it anyway (assume recent)
            if not parsed:
                news['parsed_date'] = datetime.now() - timedelta(days=3)  # Assume 3 days ago
            
            if news.get('parsed_date') and news['parsed_date'] >= one_week_ago:
                recent_news.append(news)
        
        # Remove duplicates based on title
        seen_titles = set()
        unique_news = []
        for news in recent_news:
            title = news.get('title', '').lower()[:50]  # First 50 chars
            if title and title not in seen_titles:
                seen_titles.add(title)
                unique_news.append(news)
        
        # Sort by date (most recent first) and limit to top 10
        unique_news.sort(key=lambda x: x.get('parsed_date', datetime.min), reverse=True)
        recent_news = unique_news[:10]
        
        if not recent_news:
            return {
                "symbol": symbol,
                "news_count": 0,
                "news_items": [],
                "summary": "No news found for the past week."
            }
        
        # Get price data
        price_data = self.get_stock_price_data(symbol, days=14)
        
        # Analyze price impact for each news item
        price_impacts = []
        for news in recent_news:
            impact = self.analyze_price_impact(
                news.get('parsed_date', datetime.now()),
                price_data,
                symbol
            )
            price_impacts.append(impact)
        
        # Get AI summary
        ai_summary = self.get_ai_summary(symbol, recent_news, price_impacts)
        
        # Combine news with impacts
        news_with_impacts = []
        for news, impact in zip(recent_news, price_impacts):
            # Get the best available date
            news_date = news.get('parsed_date')
            if news_date:
                if isinstance(news_date, datetime):
                    date_str = news_date.strftime('%Y-%m-%d')
                else:
                    date_str = str(news_date)
            else:
                date_str = news.get('date', news.get('published_date', 'Unknown'))
            
            news_with_impacts.append({
                "title": news.get('title', 'No title'),
                "date": date_str,
                "source": news.get('source', 'Unknown'),
                "url": news.get('url', ''),
                "impact": impact.get('impact', 'Unknown'),
                "price_change": impact.get('overall_change'),
                "news_day_price": impact.get('news_day_price'),
                "changes": impact.get('changes', {}),
                "days_of_data": impact.get('days_of_data', 0),
                "is_social": news.get('is_social', False),
                "upvotes": news.get('upvotes', 0),
                "sentiment": news.get('sentiment', ''),
                "daily_change": price_data.get('daily_changes', {}).get(date_str, {}).get('change_pct') if price_data else None
            })
        
        return {
            "symbol": symbol,
            "news_count": len(recent_news),
            "news_items": news_with_impacts,
            "ai_summary": ai_summary,
            "current_price": price_data['close'][-1] if price_data else None,
            "daily_changes": price_data.get('daily_changes', {}) if price_data else {},
            "weekly_change": price_data.get('weekly_change', {}) if price_data else {}
        }
    
    def display_stock_summary(self, summary: Dict):
        """Display summary for a single stock"""
        symbol = summary['symbol']
        
        # Header panel
        header_text = f"📰 Weekly News Summary: [bold cyan]{symbol}[/bold cyan]"
        if summary.get('current_price'):
            header_text += f" | Current Price: [green]${summary['current_price']:.2f}[/green]"
        
        console.print(Panel(header_text, style="blue"))
        
        if summary['news_count'] == 0:
            console.print("[yellow]No news found for the past week.[/yellow]")
            return
        
        # News table
        news_count = summary['news_count']
        social_count = sum(1 for n in summary['news_items'] if n.get('is_social', False) or 'Reddit' in n.get('source', '') or 'Stocktwits' in n.get('source', ''))
        regular_count = news_count - social_count
        
        table = Table(title=f"📰 News ({regular_count}) + 🗣️ Social ({social_count})", show_lines=True)
        table.add_column("Date", style="cyan", width=12)
        table.add_column("Headline", style="white", width=50)
        table.add_column("Source", style="magenta", width=14)
        table.add_column("Price @News", style="yellow", width=10)
        table.add_column("Impact", style="bold", width=16)
        table.add_column("Price Δ", style="bold", width=10)
        
        for news in summary['news_items']:
            price_change = news.get('price_change')
            news_price = news.get('news_day_price')
            
            # Format price at news time
            if news_price is not None:
                price_str = f"${news_price:.2f}"
            else:
                price_str = "[dim]N/A[/dim]"
            
            # Format price change
            if price_change is not None:
                if price_change > 0:
                    change_str = f"[green]+{price_change:.1f}%[/green]"
                elif price_change < 0:
                    change_str = f"[red]{price_change:.1f}%[/red]"
                else:
                    change_str = "[white]0.0%[/white]"
            else:
                change_str = "[dim]N/A[/dim]"
            
            table.add_row(
                str(news.get('date', 'Unknown'))[:12],
                news.get('title', 'No title')[:45],
                news.get('source', 'Unknown')[:12],
                price_str,
                news.get('impact', 'Unknown'),
                change_str
            )
        
        console.print(table)
        
        # AI Summary
        if summary.get('ai_summary'):
            console.print(Panel(
                summary['ai_summary'],
                title="🤖 AI Analysis",
                style="green"
            ))
    
    def generate_full_report(self, export_txt: bool = True, individual_files: bool = True) -> str:
        """Generate weekly news summary for all watchlist stocks"""
        stocks = self.get_watchlist_stocks()
        
        if not stocks:
            console.print("[red]No stocks in watchlist. Add some stocks first![/red]")
            return ""
        
        console.print(Panel(
            f"[bold]📊 Weekly News Summary Report[/bold]\n"
            f"Analyzing {len(stocks)} stocks from your watchlist\n"
            f"Period: Past 7 days",
            style="blue"
        ))
        
        all_summaries = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Analyzing stocks...", total=len(stocks))
            
            for symbol in stocks:
                progress.update(task, description=f"Analyzing {symbol}...")
                summary = self.generate_stock_summary(symbol)
                all_summaries.append(summary)
                self.display_stock_summary(summary)
                progress.advance(task)
        
        # Export to files
        if export_txt:
            # Create individual files for each stock
            if individual_files:
                date_str = datetime.now().strftime("%Y-%m-%d")
                week_folder = f"{self.output_dir}/{date_str}_individual_reports"
                
                console.print(f"\n[cyan]📁 Creating individual reports...[/cyan]")
                individual_paths = self.export_individual_reports(all_summaries)
                console.print(f"[green]✅ Created {len(individual_paths)} individual stock reports in:[/green]")
                console.print(f"   [bold]{week_folder}/[/bold]")
                
                # List the files created
                for path in individual_paths:
                    filename = os.path.basename(path)
                    console.print(f"   📄 {filename}")
            
            # Also create combined report
            combined_path = self.export_to_txt(all_summaries)
            console.print(f"\n[green]✅ Combined report exported to: {combined_path}[/green]")
            
            return combined_path
        
        return ""
    
    def export_to_txt(self, summaries: List[Dict]) -> str:
        """Export all summaries to a combined TXT file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.output_dir}/weekly_news_summary_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("WEEKLY NEWS SUMMARY REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Period: Past 7 days\n")
            f.write("=" * 80 + "\n\n")
            
            for summary in summaries:
                symbol = summary['symbol']
                f.write("-" * 80 + "\n")
                f.write(f"STOCK: {symbol}\n")
                if summary.get('current_price'):
                    f.write(f"Current Price: ${summary['current_price']:.2f}\n")
                f.write(f"News Articles Found: {summary['news_count']}\n")
                f.write("-" * 80 + "\n\n")
                
                if summary['news_count'] == 0:
                    f.write("No news found for the past week.\n\n")
                    continue
                
                f.write("NEWS ITEMS & PRICE IMPACT:\n")
                f.write("-" * 40 + "\n")
                
                for i, news in enumerate(summary['news_items'], 1):
                    f.write(f"\n{i}. {news.get('title', 'No title')}\n")
                    f.write(f"   Date: {news.get('date', 'Unknown')}\n")
                    f.write(f"   Source: {news.get('source', 'Unknown')}\n")
                    
                    # Price at news time
                    news_price = news.get('news_day_price')
                    if news_price is not None:
                        f.write(f"   Price at News: ${news_price:.2f}\n")
                    
                    f.write(f"   Impact: {news.get('impact', 'Unknown')}\n")
                    
                    price_change = news.get('price_change')
                    if price_change is not None:
                        direction = "📈" if price_change > 0 else "📉" if price_change < 0 else "➡️"
                        f.write(f"   Price Change: {direction} {price_change:+.2f}%\n")
                    
                    changes = news.get('changes', {})
                    if changes:
                        f.write("   Day-by-day price movement:\n")
                        for day, data in sorted(changes.items()):
                            day_num = day.split('_')[1]
                            direction = "↑" if data['change_pct'] > 0 else "↓" if data['change_pct'] < 0 else "→"
                            f.write(f"      Day {day_num}: ${data['price']:.2f} ({direction} {data['change_pct']:+.2f}%)\n")
                    
                    if news.get('url'):
                        f.write(f"   URL: {news['url']}\n")
                
                f.write("\n")
                
                # AI Summary
                if summary.get('ai_summary'):
                    f.write("AI ANALYSIS:\n")
                    f.write("-" * 40 + "\n")
                    f.write(summary['ai_summary'] + "\n")
                
                f.write("\n" + "=" * 80 + "\n\n")
        
        return filename
    
    def export_individual_reports(self, summaries: List[Dict]) -> List[str]:
        """Export each stock to its own TXT file with clear naming"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        created_files = []
        
        # Create a subfolder for this week's reports
        week_folder = f"{self.output_dir}/{date_str}_individual_reports"
        os.makedirs(week_folder, exist_ok=True)
        
        for summary in summaries:
            symbol = summary['symbol']
            current_price = summary.get('current_price', 0)
            news_count = summary.get('news_count', 0)
            
            # Create clear filename: SYMBOL_PRICE_DATE.txt
            if current_price:
                filename = f"{week_folder}/{symbol}_${current_price:.2f}_{date_str}.txt"
            else:
                filename = f"{week_folder}/{symbol}_{date_str}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                # Header
                f.write("=" * 80 + "\n")
                f.write(f"WEEKLY NEWS REPORT: {symbol}\n")
                f.write("=" * 80 + "\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Report Period: Past 7 days\n")
                f.write("-" * 80 + "\n\n")
                
                # Stock Info Section
                f.write("+" + "-" * 78 + "+\n")
                f.write("|  STOCK SUMMARY" + " " * 63 + "|\n")
                f.write("+" + "-" * 78 + "+\n")
                f.write(f"|  Symbol:        {symbol:<60} |\n")
                if current_price:
                    f.write(f"|  Current Price: ${current_price:<59.2f} |\n")
                
                # Add weekly price change to summary
                weekly_change = summary.get('weekly_change', {})
                if weekly_change:
                    wk_pct = weekly_change.get('change_pct', 0)
                    if wk_pct > 0:
                        wk_str = f"+{wk_pct:.2f}% (UP)"
                    elif wk_pct < 0:
                        wk_str = f"{wk_pct:.2f}% (DOWN)"
                    else:
                        wk_str = "0.00% (FLAT)"
                    f.write(f"|  Weekly Change: {wk_str:<60} |\n")
                
                f.write(f"|  News Found:    {news_count:<60} |\n")
                
                # Count news types
                regular_news = [n for n in summary.get('news_items', []) 
                               if not n.get('is_social', False) and 'Reddit' not in n.get('source', '') 
                               and 'Stocktwits' not in n.get('source', '')]
                social_news = [n for n in summary.get('news_items', []) 
                              if n.get('is_social', False) or 'Reddit' in n.get('source', '') 
                              or 'Stocktwits' in n.get('source', '')]
                
                f.write(f"|  - News Articles: {len(regular_news):<57} |\n")
                f.write(f"|  - Social Media:  {len(social_news):<57} |\n")
                f.write("+" + "-" * 78 + "+\n\n")
                
                if news_count == 0:
                    f.write("No news found for the past week.\n\n")
                else:
                    # News Articles Section
                    if regular_news:
                        f.write("=" * 80 + "\n")
                        f.write(f"NEWS ARTICLES ({len(regular_news)} items)\n")
                        f.write("=" * 80 + "\n\n")
                        
                        for i, news in enumerate(regular_news, 1):
                            f.write("-" * 80 + "\n")
                            f.write(f"{i}. {news.get('title', 'No title')}\n")
                            f.write("-" * 80 + "\n")
                            f.write(f"   Date:        {news.get('date', 'Unknown')}\n")
                            f.write(f"   Source:      {news.get('source', 'Unknown')}\n")
                            
                            news_price = news.get('news_day_price')
                            if news_price is not None:
                                f.write(f"   Price @News: ${news_price:.2f}\n")
                            
                            # Daily change (close-to-close from previous day)
                            daily_change = news.get('daily_change')
                            if daily_change is not None:
                                if daily_change > 0:
                                    dc_str = f"+{daily_change:.2f}% (UP)"
                                elif daily_change < 0:
                                    dc_str = f"{daily_change:.2f}% (DOWN)"
                                else:
                                    dc_str = "0.00% (FLAT)"
                                f.write(f"   Day Change:  {dc_str} (close to close)\n")
                            
                            impact = news.get('impact', 'Unknown')
                            f.write(f"   Impact:      {impact}\n")
                            
                            price_change = news.get('price_change')
                            if price_change is not None:
                                if price_change > 0:
                                    change_str = f"+{price_change:.2f}% (UP)"
                                elif price_change < 0:
                                    change_str = f"{price_change:.2f}% (DOWN)"
                                else:
                                    change_str = f"0.00% (FLAT)"
                                f.write(f"   Price Move:  {change_str}\n")
                            
                            # Day-by-day breakdown
                            changes = news.get('changes', {})
                            if changes:
                                f.write("\n   Price Movement After News:\n")
                                for day, data in sorted(changes.items()):
                                    day_num = day.split('_')[1]
                                    if data['change_pct'] > 0:
                                        direction = "UP"
                                    elif data['change_pct'] < 0:
                                        direction = "DOWN"
                                    else:
                                        direction = "FLAT"
                                    f.write(f"      Day {day_num}: ${data['price']:.2f} ({data['change_pct']:+.2f}% {direction})\n")
                            
                            if news.get('url'):
                                f.write(f"   Link:        {news['url']}\n")
                            
                            f.write("\n")
                    
                    # Social Media Section
                    if social_news:
                        f.write("=" * 80 + "\n")
                        f.write(f"SOCIAL MEDIA BUZZ ({len(social_news)} posts)\n")
                        f.write("=" * 80 + "\n\n")
                        
                        for i, news in enumerate(social_news, 1):
                            f.write("-" * 80 + "\n")
                            title = news.get('title', 'No title')
                            f.write(f"{i}. {title}\n")
                            f.write("-" * 80 + "\n")
                            f.write(f"   Date:        {news.get('date', 'Unknown')}\n")
                            f.write(f"   Source:      {news.get('source', 'Unknown')}\n")
                            
                            upvotes = news.get('upvotes', 0)
                            if upvotes:
                                f.write(f"   Upvotes:     {upvotes}\n")
                            
                            sentiment = news.get('sentiment', '')
                            if sentiment:
                                f.write(f"   Sentiment:   {sentiment}\n")
                            
                            # Daily change (close-to-close from previous day)
                            daily_change = news.get('daily_change')
                            if daily_change is not None:
                                if daily_change > 0:
                                    dc_str = f"+{daily_change:.2f}% (UP)"
                                elif daily_change < 0:
                                    dc_str = f"{daily_change:.2f}% (DOWN)"
                                else:
                                    dc_str = "0.00% (FLAT)"
                                f.write(f"   Day Change:  {dc_str} (close to close)\n")
                            
                            price_change = news.get('price_change')
                            if price_change is not None:
                                if price_change > 0:
                                    change_str = f"+{price_change:.2f}% (UP)"
                                elif price_change < 0:
                                    change_str = f"{price_change:.2f}% (DOWN)"
                                else:
                                    change_str = f"0.00% (FLAT)"
                                f.write(f"   Price Move:  {change_str}\n")
                            
                            f.write("\n")
                
                # AI Analysis Section
                if summary.get('ai_summary'):
                    f.write("=" * 80 + "\n")
                    f.write("AI ANALYSIS SUMMARY\n")
                    f.write("=" * 80 + "\n\n")
                    
                    # Word wrap the AI summary
                    ai_text = summary['ai_summary']
                    words = ai_text.split()
                    current_line = ""
                    for word in words:
                        if len(current_line) + len(word) + 1 <= 78:
                            current_line += (" " if current_line else "") + word
                        else:
                            f.write(current_line + "\n")
                            current_line = word
                    if current_line:
                        f.write(current_line + "\n")
                    f.write("\n")
                
                # Weekly Price Performance Section
                weekly_change = summary.get('weekly_change', {})
                daily_changes = summary.get('daily_changes', {})
                
                if weekly_change or daily_changes:
                    f.write("=" * 80 + "\n")
                    f.write("WEEKLY PRICE PERFORMANCE\n")
                    f.write("=" * 80 + "\n\n")
                    
                    if weekly_change:
                        start_price = weekly_change.get('start_price', 0)
                        end_price = weekly_change.get('end_price', 0)
                        change_pct = weekly_change.get('change_pct', 0)
                        start_date = weekly_change.get('start_date', 'N/A')
                        end_date = weekly_change.get('end_date', 'N/A')
                        
                        f.write(f"   Period:       {start_date} to {end_date}\n")
                        f.write(f"   Start Price:  ${start_price:.2f}\n")
                        f.write(f"   End Price:    ${end_price:.2f}\n")
                        
                        if change_pct > 0:
                            f.write(f"   WEEKLY CHANGE: +{change_pct:.2f}% (UP)\n")
                        elif change_pct < 0:
                            f.write(f"   WEEKLY CHANGE: {change_pct:.2f}% (DOWN)\n")
                        else:
                            f.write(f"   WEEKLY CHANGE: 0.00% (FLAT)\n")
                        
                        f.write("\n")
                    
                    # Daily breakdown
                    if daily_changes:
                        f.write("   Daily Price Changes (Close to Close):\n")
                        f.write("   " + "-" * 50 + "\n")
                        
                        for date_str in sorted(daily_changes.keys()):
                            day_data = daily_changes[date_str]
                            prev_close = day_data.get('prev_close')
                            close_p = day_data.get('close', 0)
                            change = day_data.get('change_pct', 0)
                            
                            if change > 0:
                                direction = "UP"
                                sign = "+"
                            elif change < 0:
                                direction = "DOWN"
                                sign = ""
                            else:
                                direction = "FLAT"
                                sign = ""
                            
                            if prev_close is not None:
                                f.write(f"   {date_str}: ${prev_close:.2f} -> ${close_p:.2f} ({sign}{change:.2f}% {direction})\n")
                            else:
                                f.write(f"   {date_str}: -- -> ${close_p:.2f} (first day)\n")
                        
                        f.write("\n")
                
                # Footer
                f.write("=" * 80 + "\n")
                f.write(f"END OF REPORT FOR {symbol}\n")
                f.write("=" * 80 + "\n")
            
            created_files.append(filename)
            console.print(f"[dim]  Created: {filename}[/dim]")
        
        return created_files


def main():
    """Main function to run weekly news summary"""
    console.print(Panel(
        "[bold cyan]📰 Weekly News Summary Tool[/bold cyan]\n"
        "Analyzing news from the past week and price impacts",
        style="blue"
    ))
    
    analyzer = WeeklyNewsSummary()
    analyzer.generate_full_report(export_txt=True)


if __name__ == "__main__":
    main()
