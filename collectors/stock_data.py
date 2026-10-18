"""
Stock Data Collector - Fetches stock prices, fundamentals, and market data
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import finnhub
import requests
from config import FINNHUB_API_KEY, HISTORICAL_DATA_DAYS


class StockDataCollector:
    """Collects comprehensive stock data from multiple sources"""
    
    def __init__(self):
        self.finnhub_client = None
        if FINNHUB_API_KEY:
            self.finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    
    def get_stock_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch comprehensive stock data for a given symbol
        """
        result = {
            "symbol": symbol.upper(),
            "timestamp": datetime.now().isoformat(),
            "price_data": None,
            "fundamentals": None,
            "company_info": None,
            "analyst_ratings": None,
            "insider_transactions": None,
            "institutional_holdings": None,
            "error": None
        }
        
        try:
            ticker = yf.Ticker(symbol)
            
            # Get historical price data
            result["price_data"] = self._get_price_data(ticker)
            
            # Get fundamental data
            result["fundamentals"] = self._get_fundamentals(ticker)
            
            # Get company info
            result["company_info"] = self._get_company_info(ticker)
            
            # Get analyst ratings
            result["analyst_ratings"] = self._get_analyst_ratings(ticker)
            
            # Get insider transactions
            result["insider_transactions"] = self._get_insider_transactions(ticker)
            
            # Get institutional holdings
            result["institutional_holdings"] = self._get_institutional_holdings(ticker)
            
            # Get additional data from Finnhub if available
            if self.finnhub_client:
                result["finnhub_data"] = self._get_finnhub_data(symbol)
                
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _get_price_data(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """Get historical price data and current quote"""
        try:
            # Get historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=HISTORICAL_DATA_DAYS)
            hist = ticker.history(start=start_date, end=end_date)
            
            if hist.empty:
                return None
            
            # Current price info
            info = ticker.info
            
            return {
                "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "previous_close": info.get("previousClose"),
                "open": info.get("open") or info.get("regularMarketOpen"),
                "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
                "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
                "volume": info.get("volume") or info.get("regularMarketVolume"),
                "avg_volume": info.get("averageVolume"),
                "avg_volume_10d": info.get("averageVolume10days"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
                "50_day_avg": info.get("fiftyDayAverage"),
                "200_day_avg": info.get("twoHundredDayAverage"),
                "historical": hist.to_dict() if not hist.empty else None,
                "historical_df": hist  # Keep DataFrame for analysis
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_fundamentals(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """Get fundamental financial data"""
        try:
            info = ticker.info
            
            return {
                # Valuation Metrics
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "price_to_book": info.get("priceToBook"),
                "price_to_sales": info.get("priceToSalesTrailing12Months"),
                "ev_to_revenue": info.get("enterpriseToRevenue"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
                
                # Profitability
                "profit_margin": info.get("profitMargins"),
                "operating_margin": info.get("operatingMargins"),
                "gross_margin": info.get("grossMargins"),
                "return_on_equity": info.get("returnOnEquity"),
                "return_on_assets": info.get("returnOnAssets"),
                
                # Growth
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "earnings_quarterly_growth": info.get("earningsQuarterlyGrowth"),
                
                # Financial Health
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "quick_ratio": info.get("quickRatio"),
                "free_cash_flow": info.get("freeCashflow"),
                
                # Dividends
                "dividend_yield": info.get("dividendYield"),
                "dividend_rate": info.get("dividendRate"),
                "payout_ratio": info.get("payoutRatio"),
                
                # Per Share Data
                "eps": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
                "book_value": info.get("bookValue"),
                "revenue_per_share": info.get("revenuePerShare"),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_company_info(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """Get company information"""
        try:
            info = ticker.info
            
            return {
                "name": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "description": info.get("longBusinessSummary"),
                "website": info.get("website"),
                "employees": info.get("fullTimeEmployees"),
                "country": info.get("country"),
                "city": info.get("city"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_analyst_ratings(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """Get analyst recommendations and price targets"""
        try:
            info = ticker.info
            
            # Get recommendations
            recommendations = None
            try:
                recs = ticker.recommendations
                if recs is not None and not recs.empty:
                    recent_recs = recs.tail(20)
                    recommendations = recent_recs.to_dict('records')
            except:
                pass
            
            return {
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "target_mean": info.get("targetMeanPrice"),
                "target_median": info.get("targetMedianPrice"),
                "recommendation": info.get("recommendationKey"),
                "recommendation_mean": info.get("recommendationMean"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
                "recent_recommendations": recommendations
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_insider_transactions(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """Get insider trading activity"""
        try:
            info = ticker.info
            insider_transactions = None
            
            try:
                insiders = ticker.insider_transactions
                if insiders is not None and not insiders.empty:
                    insider_transactions = insiders.head(20).to_dict('records')
            except:
                pass
            
            return {
                "insider_purchases_last_6m": info.get("netSharePurchaseActivity"),
                "insider_percent_held": info.get("heldPercentInsiders"),
                "recent_transactions": insider_transactions
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_institutional_holdings(self, ticker: yf.Ticker) -> Dict[str, Any]:
        """Get institutional ownership data"""
        try:
            info = ticker.info
            major_holders = None
            
            try:
                holders = ticker.institutional_holders
                if holders is not None and not holders.empty:
                    major_holders = holders.head(10).to_dict('records')
            except:
                pass
            
            return {
                "institutional_percent": info.get("heldPercentInstitutions"),
                "shares_short": info.get("sharesShort"),
                "short_ratio": info.get("shortRatio"),
                "short_percent_of_float": info.get("shortPercentOfFloat"),
                "major_holders": major_holders
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _get_finnhub_data(self, symbol: str) -> Dict[str, Any]:
        """Get additional data from Finnhub API"""
        try:
            result = {}
            
            # Company news
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            news = self.finnhub_client.company_news(
                symbol, 
                _from=start_date.strftime('%Y-%m-%d'),
                to=end_date.strftime('%Y-%m-%d')
            )
            result["news"] = news[:20] if news else []
            
            # Basic financials
            try:
                financials = self.finnhub_client.company_basic_financials(symbol, 'all')
                result["basic_financials"] = financials
            except:
                pass
            
            # Recommendation trends
            try:
                trends = self.finnhub_client.recommendation_trends(symbol)
                result["recommendation_trends"] = trends
            except:
                pass
            
            # Earnings surprises
            try:
                earnings = self.finnhub_client.company_earnings(symbol, limit=8)
                result["earnings_history"] = earnings
            except:
                pass
            
            return result
        except Exception as e:
            return {"error": str(e)}
    
    def get_market_overview(self) -> Dict[str, Any]:
        """Get overall market conditions"""
        try:
            # Major indices
            indices = {
                "SPY": "S&P 500",
                "QQQ": "NASDAQ 100",
                "DIA": "Dow Jones",
                "IWM": "Russell 2000",
                "VIX": "Volatility Index"
            }
            
            market_data = {}
            for symbol, name in indices.items():
                ticker = yf.Ticker(symbol)
                info = ticker.info
                hist = ticker.history(period="5d")
                
                if not hist.empty:
                    market_data[symbol] = {
                        "name": name,
                        "price": info.get("regularMarketPrice"),
                        "change_percent": info.get("regularMarketChangePercent"),
                        "5d_performance": ((hist['Close'].iloc[-1] / hist['Close'].iloc[0]) - 1) * 100
                    }
            
            return market_data
        except Exception as e:
            return {"error": str(e)}


if __name__ == "__main__":
    # Test the collector
    collector = StockDataCollector()
    data = collector.get_stock_data("AAPL")
    print(f"Collected data for {data['symbol']}")
    print(f"Current Price: ${data['price_data'].get('current_price', 'N/A')}")
    print(f"P/E Ratio: {data['fundamentals'].get('pe_ratio', 'N/A')}")
