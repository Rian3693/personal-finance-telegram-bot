"""
News Collector - Scrapes financial news from various sources
"""
import requests
from bs4 import BeautifulSoup
import feedparser
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import time
import re
from config import NEWS_API_KEY, NEWS_SOURCES


class NewsCollector:
    """Collects news articles from financial websites and RSS feeds"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # RSS Feeds for financial news
        self.rss_feeds = {
            "yahoo_finance": "https://finance.yahoo.com/rss/",
            "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
            "cnbc": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            "seeking_alpha": "https://seekingalpha.com/market_currents.xml",
            "investing_news": "https://www.investing.com/rss/news.rss",
            "reuters_business": "https://www.reutersagency.com/feed/?best-topics=business-finance",
        }
        
        # Press Release feeds for company announcements
        self.press_release_feeds = {
            "pr_newswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
            "business_wire": "https://feed.businesswire.com/rss/home/?rss=G1QFDERJXkJeEFpRWA==",
            "globe_newswire": "https://www.globenewswire.com/RssFeed/subjectcode/25-Earnings%20Releases/feedTitle/GlobeNewswire%20-%20Earnings%20Releases",
        }
        
        # News categories for classification
        self.news_categories = {
            'price_movement': [
                'surge', 'soar', 'plunge', 'crash', 'rally', 'tumble', 'spike', 'jump',
                'climb', 'slide', 'drop', 'rise', 'fall', 'gain', 'lose', 'hit', 'reach',
                'all-time high', 'all-time low', '52-week', 'record high', 'record low',
                'breakout', 'breakdown', 'momentum', 'volatile', 'trading', 'shares'
            ],
            'product_feature': [
                'launch', 'launches', 'unveil', 'unveils', 'announce', 'announces', 'release',
                'releases', 'introduce', 'introduces', 'new product', 'new feature', 'new service',
                'update', 'upgrade', 'version', 'platform', 'app', 'software', 'hardware',
                'innovation', 'technology', 'patent', 'rollout', 'beta', 'preview', 'debut'
            ],
            'company_changes': [
                'ceo', 'cfo', 'cto', 'executive', 'appoint', 'hire', 'resign', 'retire',
                'step down', 'leadership', 'management', 'restructure', 'restructuring',
                'layoff', 'layoffs', 'workforce', 'employees', 'headcount', 'reorganize',
                'board', 'director', 'chairman', 'president', 'succession', 'transition'
            ],
            'deals_agreements': [
                'deal', 'agreement', 'partnership', 'partner', 'collaboration', 'joint venture',
                'acquisition', 'acquire', 'merger', 'merge', 'buyout', 'takeover', 'bid',
                'contract', 'license', 'licensing', 'alliance', 'mou', 'memorandum',
                'investment', 'stake', 'equity', 'funding', 'ipo', 'spinoff', 'spin-off'
            ],
            'earnings_financial': [
                'earnings', 'revenue', 'profit', 'loss', 'eps', 'guidance', 'forecast',
                'beat', 'miss', 'quarter', 'quarterly', 'annual', 'fiscal', 'results',
                'report', 'outlook', 'dividend', 'buyback', 'repurchase', 'analyst'
            ],
            'regulatory_legal': [
                'sec', 'fda', 'ftc', 'doj', 'lawsuit', 'sue', 'settlement', 'fine',
                'investigation', 'probe', 'regulatory', 'compliance', 'approval', 'reject',
                'antitrust', 'subpoena', 'trial', 'court', 'ruling', 'verdict'
            ]
        }
        
        # Keywords for impact assessment
        self.positive_keywords = [
            'beat', 'beats', 'exceeds', 'surpass', 'upgrade', 'raised', 'raises',
            'bullish', 'growth', 'strong', 'record', 'gain', 'gains', 'soar',
            'surge', 'rally', 'outperform', 'buy', 'positive', 'breakthrough',
            'innovation', 'partnership', 'acquisition', 'dividend', 'profit',
            'expansion', 'launch', 'success', 'optimistic', 'confident',
            'deal', 'contract', 'award', 'approval', 'wins', 'secures'
        ]
        self.negative_keywords = [
            'miss', 'misses', 'disappoints', 'decline', 'downgrade', 'cut', 'cuts',
            'bearish', 'weak', 'loss', 'losses', 'plunge', 'crash', 'drop', 'drops',
            'fall', 'falls', 'underperform', 'sell', 'negative', 'concern', 'warning',
            'lawsuit', 'investigation', 'recall', 'layoff', 'layoffs', 'debt',
            'bankruptcy', 'struggle', 'risk', 'threat', 'slump', 'tumble',
            'delay', 'cancel', 'terminate', 'reject', 'fine', 'penalty'
        ]
    
    def _assess_news_impact(self, title: str) -> str:
        """Assess news impact as Positive, Negative, or Neutral"""
        if not title:
            return "Neutral"
        
        title_lower = title.lower()
        
        positive_count = sum(1 for word in self.positive_keywords if word in title_lower)
        negative_count = sum(1 for word in self.negative_keywords if word in title_lower)
        
        if positive_count > negative_count:
            return "Positive"
        elif negative_count > positive_count:
            return "Negative"
        else:
            return "Neutral"
    
    def _categorize_news(self, title: str, summary: str = "") -> List[str]:
        """Categorize news into types: price, product, company, deals, earnings, legal"""
        categories = []
        text = (title + " " + summary).lower()
        
        for category, keywords in self.news_categories.items():
            if any(kw in text for kw in keywords):
                categories.append(category)
        
        return categories if categories else ['general']
    
    def get_stock_news(self, symbol: str, company_name: str = None) -> Dict[str, Any]:
        """
        Collect news for a specific stock from multiple sources
        """
        result = {
            "symbol": symbol.upper(),
            "timestamp": datetime.now().isoformat(),
            "articles": [],
            "sentiment_summary": None,
            "error": None
        }
        
        try:
            # Collect from different sources
            articles = []
            
            # Yahoo Finance News
            yahoo_articles = self._get_yahoo_finance_news(symbol)
            articles.extend(yahoo_articles)
            
            # Google News RSS
            google_articles = self._get_google_news(symbol, company_name)
            articles.extend(google_articles)
            
            # Finviz News
            finviz_articles = self._get_finviz_news(symbol)
            articles.extend(finviz_articles)
            
            # MarketWatch
            marketwatch_articles = self._get_marketwatch_news(symbol)
            articles.extend(marketwatch_articles)
            
            # Seeking Alpha (company specific)
            seeking_alpha_articles = self._get_seeking_alpha_news(symbol)
            articles.extend(seeking_alpha_articles)
            
            # Press releases (PR Newswire, Business Wire)
            press_articles = self._get_press_releases(symbol, company_name)
            articles.extend(press_articles)
            
            # SEC filings (8-K for major announcements)
            sec_articles = self._get_sec_filings(symbol)
            articles.extend(sec_articles)
            
            # News API (if key available)
            if NEWS_API_KEY:
                newsapi_articles = self._get_newsapi_articles(symbol, company_name)
                articles.extend(newsapi_articles)
            
            # Deduplicate articles
            seen_titles = set()
            unique_articles = []
            for article in articles:
                title_key = article.get('title', '').lower()[:50]
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    # Add impact assessment to each article
                    article['impact'] = self._assess_news_impact(article.get('title', ''))
                    # Add category classification
                    article['categories'] = self._categorize_news(
                        article.get('title', ''), 
                        article.get('summary', '')
                    )
                    unique_articles.append(article)
            
            # Sort by date (newest first)
            unique_articles.sort(
                key=lambda x: x.get('published_date', ''), 
                reverse=True
            )
            
            result["articles"] = unique_articles[:50]  # Limit to 50 articles
            result["total_articles"] = len(unique_articles)
            
            # Summarize impact distribution
            impacts = [a.get('impact', 'Neutral') for a in unique_articles]
            result["impact_summary"] = {
                "positive": impacts.count("Positive"),
                "negative": impacts.count("Negative"),
                "neutral": impacts.count("Neutral")
            }
            
            # Summarize category distribution
            all_categories = []
            for a in unique_articles:
                all_categories.extend(a.get('categories', []))
            result["category_summary"] = {
                "price_movement": all_categories.count("price_movement"),
                "product_feature": all_categories.count("product_feature"),
                "company_changes": all_categories.count("company_changes"),
                "deals_agreements": all_categories.count("deals_agreements"),
                "earnings_financial": all_categories.count("earnings_financial"),
                "regulatory_legal": all_categories.count("regulatory_legal"),
                "general": all_categories.count("general")
            }
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _get_yahoo_finance_news(self, symbol: str) -> List[Dict]:
        """Scrape news from Yahoo Finance"""
        articles = []
        try:
            url = f"https://finance.yahoo.com/quote/{symbol}/news"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Find news articles
                news_items = soup.find_all('li', class_=re.compile(r'stream-item|js-stream-content'))
                
                for item in news_items[:15]:
                    try:
                        title_elem = item.find('h3') or item.find('a')
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            link = title_elem.get('href', '') if title_elem.name == 'a' else ''
                            if not link.startswith('http'):
                                link = f"https://finance.yahoo.com{link}"
                            
                            articles.append({
                                'title': title,
                                'url': link,
                                'source': 'Yahoo Finance',
                                'published_date': datetime.now().isoformat(),
                                'summary': ''
                            })
                    except:
                        continue
                        
        except Exception as e:
            pass
        
        return articles
    
    def _get_google_news(self, symbol: str, company_name: str = None) -> List[Dict]:
        """Get news from Google News RSS"""
        articles = []
        try:
            search_term = company_name if company_name else symbol
            url = f"https://news.google.com/rss/search?q={search_term}+stock&hl=en-US&gl=US&ceid=US:en"
            
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:15]:
                articles.append({
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'source': entry.get('source', {}).get('title', 'Google News'),
                    'published_date': entry.get('published', datetime.now().isoformat()),
                    'summary': BeautifulSoup(entry.get('summary', ''), 'html.parser').get_text()[:300]
                })
                
        except Exception as e:
            pass
        
        return articles
    
    def _get_finviz_news(self, symbol: str) -> List[Dict]:
        """Scrape news from Finviz"""
        articles = []
        try:
            url = f"https://finviz.com/quote.ashx?t={symbol}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                news_table = soup.find('table', {'id': 'news-table'})
                
                if news_table:
                    rows = news_table.find_all('tr')
                    current_date = datetime.now().strftime('%b-%d-%y')  # Format: Jan-20-26
                    
                    for row in rows[:15]:
                        try:
                            date_cell = row.find('td', {'align': 'right'})
                            title_cell = row.find('a')
                            
                            if title_cell:
                                title = title_cell.get_text(strip=True)
                                link = title_cell.get('href', '')
                                
                                date_text = date_cell.get_text(strip=True) if date_cell else ''
                                
                                # Parse Finviz date format: "Jan-20-26 10:30AM" or "Today 10:30AM" or just "10:30AM"
                                parsed_date = None
                                if date_text:
                                    date_text = date_text.strip()
                                    # Check if it contains a date (like "Jan-20-26")
                                    if '-' in date_text and len(date_text) > 8:
                                        # Has full date like "Jan-20-26 10:30AM"
                                        date_part = date_text.split()[0] if ' ' in date_text else date_text
                                        try:
                                            parsed_date = datetime.strptime(date_part, '%b-%d-%y').strftime('%Y-%m-%d')
                                            current_date = date_part  # Update current date for subsequent rows
                                        except:
                                            parsed_date = datetime.now().strftime('%Y-%m-%d')
                                    elif 'Today' in date_text:
                                        parsed_date = datetime.now().strftime('%Y-%m-%d')
                                    elif 'Yesterday' in date_text:
                                        parsed_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                                    else:
                                        # Just time, use current_date from previous row
                                        try:
                                            parsed_date = datetime.strptime(current_date, '%b-%d-%y').strftime('%Y-%m-%d')
                                        except:
                                            parsed_date = datetime.now().strftime('%Y-%m-%d')
                                else:
                                    parsed_date = datetime.now().strftime('%Y-%m-%d')
                                
                                articles.append({
                                    'title': title,
                                    'url': link,
                                    'source': 'Finviz',
                                    'date': parsed_date,
                                    'published_date': parsed_date,
                                    'summary': ''
                                })
                        except:
                            continue
                            
        except Exception as e:
            pass
        
        return articles
    
    def _get_marketwatch_news(self, symbol: str) -> List[Dict]:
        """Get news from MarketWatch"""
        articles = []
        try:
            url = f"https://www.marketwatch.com/investing/stock/{symbol.lower()}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                news_items = soup.find_all('div', class_=re.compile(r'article__content|element--article'))
                
                for item in news_items[:10]:
                    try:
                        title_elem = item.find('a', class_=re.compile(r'link'))
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            link = title_elem.get('href', '')
                            
                            articles.append({
                                'title': title,
                                'url': link if link.startswith('http') else f"https://www.marketwatch.com{link}",
                                'source': 'MarketWatch',
                                'published_date': datetime.now().isoformat(),
                                'summary': ''
                            })
                    except:
                        continue
                        
        except Exception as e:
            pass
        
        return articles
    
    def _get_seeking_alpha_news(self, symbol: str) -> List[Dict]:
        """Get news and analysis from Seeking Alpha"""
        articles = []
        try:
            # Seeking Alpha RSS for specific symbol
            url = f"https://seekingalpha.com/api/sa/combined/{symbol}.xml"
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:10]:
                articles.append({
                    'title': entry.get('title', ''),
                    'url': entry.get('link', ''),
                    'source': 'Seeking Alpha',
                    'published_date': entry.get('published', datetime.now().isoformat()),
                    'summary': BeautifulSoup(entry.get('summary', ''), 'html.parser').get_text()[:300]
                })
        except:
            # Fallback: scrape the news page
            try:
                url = f"https://seekingalpha.com/symbol/{symbol}/news"
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')
                    headlines = soup.find_all('a', {'data-test-id': 'post-list-item-title'})
                    for h in headlines[:10]:
                        articles.append({
                            'title': h.get_text(strip=True),
                            'url': f"https://seekingalpha.com{h.get('href', '')}",
                            'source': 'Seeking Alpha',
                            'published_date': datetime.now().isoformat(),
                            'summary': ''
                        })
            except:
                pass
        
        return articles
    
    def _get_press_releases(self, symbol: str, company_name: str = None) -> List[Dict]:
        """Get press releases from PR Newswire, Business Wire, Globe Newswire"""
        articles = []
        search_term = company_name if company_name else symbol
        
        # Google News search for press releases
        try:
            url = f"https://news.google.com/rss/search?q={search_term}+press+release&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:8]:
                source = entry.get('source', {}).get('title', 'Press Release')
                # Filter for actual press release sources
                if any(pr in source.lower() for pr in ['newswire', 'wire', 'globe', 'pr ', 'business wire']):
                    articles.append({
                        'title': entry.get('title', ''),
                        'url': entry.get('link', ''),
                        'source': source,
                        'published_date': entry.get('published', datetime.now().isoformat()),
                        'summary': BeautifulSoup(entry.get('summary', ''), 'html.parser').get_text()[:300]
                    })
        except:
            pass
        
        # Direct company announcements search
        try:
            url = f"https://news.google.com/rss/search?q={search_term}+announces+OR+launch+OR+partnership+OR+agreement&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:8]:
                title = entry.get('title', '')
                # Check if it's about our company and is an announcement
                if search_term.lower() in title.lower() or symbol.upper() in title.upper():
                    articles.append({
                        'title': title,
                        'url': entry.get('link', ''),
                        'source': entry.get('source', {}).get('title', 'News'),
                        'published_date': entry.get('published', datetime.now().isoformat()),
                        'summary': BeautifulSoup(entry.get('summary', ''), 'html.parser').get_text()[:300]
                    })
        except:
            pass
        
        return articles
    
    def _get_sec_filings(self, symbol: str) -> List[Dict]:
        """Get SEC filings (8-K for major announcements, 10-K/10-Q for financials)"""
        articles = []
        try:
            # SEC EDGAR RSS feed for company filings
            url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=8-K&dateb=&owner=include&count=10&output=atom"
            feed = feedparser.parse(url)
            
            for entry in feed.entries[:5]:
                title = entry.get('title', '')
                # 8-K filings are material events
                if '8-K' in title:
                    articles.append({
                        'title': f"SEC Filing: {title}",
                        'url': entry.get('link', ''),
                        'source': 'SEC EDGAR',
                        'published_date': entry.get('updated', datetime.now().isoformat()),
                        'summary': 'Material event disclosure - may include acquisitions, leadership changes, or other significant announcements'
                    })
        except:
            pass
        
        # Alternative: SEC RSS for recent filings
        try:
            url = f"https://efts.sec.gov/LATEST/search-index?q={symbol}&dateRange=custom&startdt=2025-01-01&enddt=2026-12-31"
            # This is an API endpoint, may need different handling
        except:
            pass
        
        return articles
    
    def _get_newsapi_articles(self, symbol: str, company_name: str = None) -> List[Dict]:
        """Get articles from NewsAPI"""
        articles = []
        try:
            search_term = company_name if company_name else symbol
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f'"{search_term}" stock',
                'apiKey': NEWS_API_KEY,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 20
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                for article in data.get('articles', []):
                    articles.append({
                        'title': article.get('title', ''),
                        'url': article.get('url', ''),
                        'source': article.get('source', {}).get('name', 'NewsAPI'),
                        'published_date': article.get('publishedAt', ''),
                        'summary': article.get('description', '')[:300] if article.get('description') else ''
                    })
                    
        except Exception as e:
            pass
        
        return articles
    
    def get_market_news(self) -> List[Dict]:
        """Get general market news"""
        articles = []
        
        for feed_name, feed_url in self.rss_feeds.items():
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:5]:
                    articles.append({
                        'title': entry.get('title', ''),
                        'url': entry.get('link', ''),
                        'source': feed_name.replace('_', ' ').title(),
                        'published_date': entry.get('published', datetime.now().isoformat()),
                        'summary': BeautifulSoup(entry.get('summary', ''), 'html.parser').get_text()[:300]
                    })
            except:
                continue
        
        return articles[:30]
    
    def get_news_by_category(self, symbol: str, company_name: str = None, 
                             categories: List[str] = None) -> Dict[str, Any]:
        """
        Get news filtered by specific categories.
        
        Categories:
        - price_movement: Stock price surges, drops, volatility
        - product_feature: New products, features, launches, innovations
        - company_changes: Leadership changes, layoffs, restructuring
        - deals_agreements: M&A, partnerships, contracts, investments
        - earnings_financial: Earnings reports, guidance, dividends
        - regulatory_legal: SEC filings, lawsuits, investigations
        """
        # Get all news first
        all_news = self.get_stock_news(symbol, company_name)
        
        if not categories:
            return all_news
        
        # Filter articles by requested categories
        filtered_articles = []
        for article in all_news.get('articles', []):
            article_cats = article.get('categories', [])
            if any(cat in article_cats for cat in categories):
                filtered_articles.append(article)
        
        all_news['articles'] = filtered_articles
        all_news['total_articles'] = len(filtered_articles)
        all_news['filter_categories'] = categories
        
        return all_news
    
    def get_company_announcements(self, symbol: str, company_name: str = None) -> Dict[str, Any]:
        """
        Get specifically product launches, deals, and company changes.
        Excludes pure earnings/analyst news.
        """
        categories = ['product_feature', 'company_changes', 'deals_agreements']
        return self.get_news_by_category(symbol, company_name, categories)
    
    def get_price_catalysts(self, symbol: str, company_name: str = None) -> Dict[str, Any]:
        """
        Get news that could move the stock price.
        Includes price movements, deals, earnings, and regulatory news.
        """
        categories = ['price_movement', 'deals_agreements', 'earnings_financial', 'regulatory_legal']
        return self.get_news_by_category(symbol, company_name, categories)


if __name__ == "__main__":
    collector = NewsCollector()
    news = collector.get_stock_news("AAPL", "Apple")
    print(f"Collected {news['total_articles']} articles")
    for article in news['articles'][:5]:
        print(f"- {article['title'][:60]}...")
