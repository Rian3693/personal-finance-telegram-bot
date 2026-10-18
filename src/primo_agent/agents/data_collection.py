"""
Data Collection Agent - Collects market data, company info, and financial metrics
"""
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class DataCollectionAgent:
    """
    Agent responsible for collecting all market data for analysis.
    Collects: market data, company info, news, financial metrics
    """
    
    def __init__(self):
        self.name = "Data Collection Agent"
    
    async def collect(self, symbol: str, analysis_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Collect all relevant data for a stock symbol.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')
            analysis_date: Date for analysis in YYYY-MM-DD format
            
        Returns:
            Dict with market_data, company_info, news_data, basic_financials
        """
        symbol = symbol.upper()
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Get historical data
            if analysis_date:
                target_date = datetime.strptime(analysis_date, "%Y-%m-%d")
                start_date = target_date - timedelta(days=90)
                hist = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=analysis_date)
            else:
                hist = ticker.history(period='3mo')
            
            # Current price
            current_price = hist['Close'].iloc[-1] if not hist.empty else info.get('regularMarketPrice', 0)
            
            # Market data
            market_data = {
                'symbol': symbol,
                'current_price': float(current_price),
                'open': float(hist['Open'].iloc[-1]) if not hist.empty else 0,
                'high': float(hist['High'].iloc[-1]) if not hist.empty else 0,
                'low': float(hist['Low'].iloc[-1]) if not hist.empty else 0,
                'volume': int(hist['Volume'].iloc[-1]) if not hist.empty else 0,
                'previous_close': float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price,
                'history': hist
            }
            
            # Company info
            company_info = {
                'name': info.get('longName', info.get('shortName', symbol)),
                'industry': info.get('industry', 'Unknown'),
                'sector': info.get('sector', 'Unknown'),
                'exchange': info.get('exchange', 'Unknown'),
                'country': info.get('country', 'Unknown'),
                'description': info.get('longBusinessSummary', '')[:500] if info.get('longBusinessSummary') else '',
                'website': info.get('website', ''),
                'employees': info.get('fullTimeEmployees', 0)
            }
            
            # Company profile (financial metrics)
            company_profile = {
                'market_cap': info.get('marketCap', 0),
                'enterprise_value': info.get('enterpriseValue', 0),
                'trailing_pe': info.get('trailingPE', 0),
                'forward_pe': info.get('forwardPE', 0),
                'peg_ratio': info.get('pegRatio', 0),
                'price_to_book': info.get('priceToBook', 0),
                'price_to_sales': info.get('priceToSalesTrailing12Months', 0),
                'dividend_yield': info.get('dividendYield', 0),
                'beta': info.get('beta', 0),
                '52_week_high': info.get('fiftyTwoWeekHigh', 0),
                '52_week_low': info.get('fiftyTwoWeekLow', 0)
            }
            
            # Basic financials
            basic_financials = {
                'revenue': info.get('totalRevenue', 0),
                'gross_profit': info.get('grossProfits', 0),
                'ebitda': info.get('ebitda', 0),
                'net_income': info.get('netIncomeToCommon', 0),
                'operating_margin': info.get('operatingMargins', 0),
                'profit_margin': info.get('profitMargins', 0),
                'return_on_equity': info.get('returnOnEquity', 0),
                'return_on_assets': info.get('returnOnAssets', 0),
                'debt_to_equity': info.get('debtToEquity', 0),
                'current_ratio': info.get('currentRatio', 0),
                'free_cash_flow': info.get('freeCashflow', 0),
                'revenue_growth': info.get('revenueGrowth', 0),
                'earnings_growth': info.get('earningsGrowth', 0)
            }
            
            # Get recent news
            news_data = self._get_news(symbol)
            
            return {
                'symbol': symbol,
                'analysis_date': analysis_date or datetime.now().strftime("%Y-%m-%d"),
                'market_data': market_data,
                'company_info': company_info,
                'company_profile': company_profile,
                'basic_financials': basic_financials,
                'news_data': news_data,
                'success': True
            }
            
        except Exception as e:
            return {
                'symbol': symbol,
                'analysis_date': analysis_date,
                'success': False,
                'error': str(e)
            }
    
    def _get_news(self, symbol: str) -> Dict[str, Any]:
        """Get recent news for the symbol"""
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            
            articles = []
            for item in news[:10]:
                articles.append({
                    'title': item.get('title', ''),
                    'publisher': item.get('publisher', ''),
                    'link': item.get('link', ''),
                    'published': datetime.fromtimestamp(item.get('providerPublishTime', 0)).isoformat() if item.get('providerPublishTime') else '',
                    'type': item.get('type', 'STORY')
                })
            
            return {
                'articles': articles,
                'count': len(articles)
            }
        except:
            return {'articles': [], 'count': 0}
