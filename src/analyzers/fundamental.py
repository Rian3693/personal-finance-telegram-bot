"""
Fundamental Analysis Module - Evaluates company financials and valuation
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
import numpy as np
from config import get_timeframe_config, DEFAULT_TIMEFRAME


class FundamentalAnalyzer:
    """Analyzes fundamental data to assess company value and health"""
    
    def __init__(self):
        # Sector-specific P/E benchmarks
        self.sector_pe_benchmarks = {
            "Technology": 30,
            "Healthcare": 25,
            "Financial Services": 15,
            "Consumer Cyclical": 20,
            "Consumer Defensive": 22,
            "Industrials": 20,
            "Energy": 12,
            "Utilities": 18,
            "Real Estate": 35,
            "Basic Materials": 15,
            "Communication Services": 20,
        }
    
    def analyze(self, stock_data: Dict[str, Any], timeframe: str = DEFAULT_TIMEFRAME) -> Dict[str, Any]:
        """
        Perform comprehensive fundamental analysis
        
        Args:
            stock_data: Dictionary containing stock fundamental data
            timeframe: Analysis timeframe ('swing', 'short', 'medium', 'long')
        """
        tf_config = get_timeframe_config(timeframe)
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "timeframe": timeframe,
            "timeframe_name": tf_config['name'],
            "valuation": {},
            "profitability": {},
            "growth": {},
            "financial_health": {},
            "dividend": {},
            "analyst_consensus": {},
            "overall_score": 0,
            "overall_signal": None,
            "key_insights": [],
            "concerns": [],
            "error": None
        }
        
        try:
            fundamentals = stock_data.get("fundamentals", {})
            company_info = stock_data.get("company_info", {})
            analyst_ratings = stock_data.get("analyst_ratings", {})
            price_data = stock_data.get("price_data", {})
            
            if not fundamentals:
                result["error"] = "No fundamental data available"
                return result
            
            sector = company_info.get("sector", "")
            current_price = price_data.get("current_price", 0) if price_data else 0
            
            # Valuation Analysis
            result["valuation"] = self._analyze_valuation(fundamentals, sector, current_price, analyst_ratings)
            
            # Profitability Analysis
            result["profitability"] = self._analyze_profitability(fundamentals)
            
            # Growth Analysis
            result["growth"] = self._analyze_growth(fundamentals)
            
            # Financial Health Analysis
            result["financial_health"] = self._analyze_financial_health(fundamentals)
            
            # Dividend Analysis
            result["dividend"] = self._analyze_dividend(fundamentals)
            
            # Analyst Consensus
            result["analyst_consensus"] = self._analyze_analyst_consensus(analyst_ratings, current_price)
            
            # Generate insights and concerns
            result["key_insights"], result["concerns"] = self._generate_insights(result, fundamentals)
            
            # Calculate overall score
            result["overall_score"], result["overall_signal"] = self._calculate_overall_score(result)
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _analyze_valuation(self, fundamentals: Dict, sector: str, current_price: float, analyst_ratings: Dict) -> Dict[str, Any]:
        """Analyze stock valuation metrics"""
        pe_ratio = fundamentals.get("pe_ratio")
        forward_pe = fundamentals.get("forward_pe")
        peg_ratio = fundamentals.get("peg_ratio")
        pb_ratio = fundamentals.get("price_to_book")
        ps_ratio = fundamentals.get("price_to_sales")
        ev_ebitda = fundamentals.get("ev_to_ebitda")
        
        # Get sector benchmark
        benchmark_pe = self.sector_pe_benchmarks.get(sector, 20)
        
        valuation_result = {
            "pe_ratio": {
                "value": pe_ratio,
                "sector_benchmark": benchmark_pe,
                "assessment": self._assess_pe(pe_ratio, benchmark_pe)
            },
            "forward_pe": {
                "value": forward_pe,
                "assessment": self._assess_forward_pe(pe_ratio, forward_pe)
            },
            "peg_ratio": {
                "value": peg_ratio,
                "assessment": self._assess_peg(peg_ratio)
            },
            "price_to_book": {
                "value": pb_ratio,
                "assessment": self._assess_pb(pb_ratio)
            },
            "price_to_sales": {
                "value": ps_ratio,
                "assessment": self._assess_ps(ps_ratio)
            },
            "ev_to_ebitda": {
                "value": ev_ebitda,
                "assessment": self._assess_ev_ebitda(ev_ebitda)
            },
            "market_cap": fundamentals.get("market_cap"),
            "enterprise_value": fundamentals.get("enterprise_value"),
        }
        
        # Price target analysis
        if analyst_ratings and current_price:
            target_mean = analyst_ratings.get("target_mean")
            if target_mean and current_price:
                upside = ((target_mean / current_price) - 1) * 100
                valuation_result["price_target_analysis"] = {
                    "current_price": current_price,
                    "target_mean": target_mean,
                    "target_high": analyst_ratings.get("target_high"),
                    "target_low": analyst_ratings.get("target_low"),
                    "upside_potential": round(upside, 2),
                    "assessment": "undervalued" if upside > 15 else ("fairly valued" if upside > -10 else "overvalued")
                }
        
        # Overall valuation score
        valuation_result["overall_assessment"] = self._overall_valuation_assessment(valuation_result)
        
        return valuation_result
    
    def _analyze_profitability(self, fundamentals: Dict) -> Dict[str, Any]:
        """Analyze profitability metrics"""
        return {
            "profit_margin": {
                "value": fundamentals.get("profit_margin"),
                "assessment": self._assess_margin(fundamentals.get("profit_margin"), "profit")
            },
            "operating_margin": {
                "value": fundamentals.get("operating_margin"),
                "assessment": self._assess_margin(fundamentals.get("operating_margin"), "operating")
            },
            "gross_margin": {
                "value": fundamentals.get("gross_margin"),
                "assessment": self._assess_margin(fundamentals.get("gross_margin"), "gross")
            },
            "return_on_equity": {
                "value": fundamentals.get("return_on_equity"),
                "assessment": self._assess_roe(fundamentals.get("return_on_equity"))
            },
            "return_on_assets": {
                "value": fundamentals.get("return_on_assets"),
                "assessment": self._assess_roa(fundamentals.get("return_on_assets"))
            },
            "eps": fundamentals.get("eps"),
            "forward_eps": fundamentals.get("forward_eps"),
            "revenue_per_share": fundamentals.get("revenue_per_share"),
        }
    
    def _analyze_growth(self, fundamentals: Dict) -> Dict[str, Any]:
        """Analyze growth metrics"""
        revenue_growth = fundamentals.get("revenue_growth")
        earnings_growth = fundamentals.get("earnings_growth")
        quarterly_growth = fundamentals.get("earnings_quarterly_growth")
        
        return {
            "revenue_growth": {
                "value": revenue_growth,
                "assessment": self._assess_growth(revenue_growth, "revenue")
            },
            "earnings_growth": {
                "value": earnings_growth,
                "assessment": self._assess_growth(earnings_growth, "earnings")
            },
            "earnings_quarterly_growth": {
                "value": quarterly_growth,
                "assessment": self._assess_growth(quarterly_growth, "quarterly")
            },
            "growth_consistency": self._assess_growth_consistency(revenue_growth, earnings_growth),
        }
    
    def _analyze_financial_health(self, fundamentals: Dict) -> Dict[str, Any]:
        """Analyze financial health and stability"""
        debt_to_equity = fundamentals.get("debt_to_equity")
        current_ratio = fundamentals.get("current_ratio")
        quick_ratio = fundamentals.get("quick_ratio")
        
        return {
            "debt_to_equity": {
                "value": debt_to_equity,
                "assessment": self._assess_debt_equity(debt_to_equity)
            },
            "current_ratio": {
                "value": current_ratio,
                "assessment": self._assess_current_ratio(current_ratio)
            },
            "quick_ratio": {
                "value": quick_ratio,
                "assessment": self._assess_quick_ratio(quick_ratio)
            },
            "total_cash": fundamentals.get("total_cash"),
            "total_debt": fundamentals.get("total_debt"),
            "free_cash_flow": fundamentals.get("free_cash_flow"),
            "cash_position": self._assess_cash_position(fundamentals),
        }
    
    def _analyze_dividend(self, fundamentals: Dict) -> Dict[str, Any]:
        """Analyze dividend metrics"""
        dividend_yield = fundamentals.get("dividend_yield")
        payout_ratio = fundamentals.get("payout_ratio")
        
        if not dividend_yield:
            return {
                "status": "No dividend",
                "assessment": "Company does not pay dividends"
            }
        
        return {
            "yield": {
                "value": dividend_yield,
                "assessment": self._assess_dividend_yield(dividend_yield)
            },
            "payout_ratio": {
                "value": payout_ratio,
                "assessment": self._assess_payout_ratio(payout_ratio)
            },
            "dividend_rate": fundamentals.get("dividend_rate"),
            "sustainability": self._assess_dividend_sustainability(dividend_yield, payout_ratio)
        }
    
    def _analyze_analyst_consensus(self, analyst_ratings: Dict, current_price: float) -> Dict[str, Any]:
        """Analyze analyst recommendations"""
        if not analyst_ratings:
            return {"status": "No analyst data available"}
        
        recommendation = analyst_ratings.get("recommendation", "")
        rec_mean = analyst_ratings.get("recommendation_mean")  # 1=Strong Buy, 5=Strong Sell
        num_analysts = analyst_ratings.get("num_analysts", 0)
        
        consensus = {
            "recommendation": recommendation,
            "recommendation_score": rec_mean,
            "num_analysts": num_analysts,
            "price_targets": {
                "high": analyst_ratings.get("target_high"),
                "mean": analyst_ratings.get("target_mean"),
                "low": analyst_ratings.get("target_low"),
            }
        }
        
        # Interpret recommendation
        if rec_mean:
            if rec_mean <= 1.5:
                consensus["interpretation"] = "Strong Buy consensus"
            elif rec_mean <= 2.5:
                consensus["interpretation"] = "Buy/Moderate Buy consensus"
            elif rec_mean <= 3.5:
                consensus["interpretation"] = "Hold consensus"
            elif rec_mean <= 4.5:
                consensus["interpretation"] = "Sell/Underperform consensus"
            else:
                consensus["interpretation"] = "Strong Sell consensus"
        
        return consensus
    
    def _generate_insights(self, analysis: Dict, fundamentals: Dict) -> tuple:
        """Generate key insights and concerns"""
        insights = []
        concerns = []
        
        # Valuation insights
        valuation = analysis.get("valuation", {})
        if valuation.get("price_target_analysis", {}).get("upside_potential", 0) > 20:
            insights.append(f"Significant upside potential ({valuation['price_target_analysis']['upside_potential']}%) based on analyst targets")
        elif valuation.get("price_target_analysis", {}).get("upside_potential", 0) < -10:
            concerns.append(f"Trading above analyst price targets (downside risk: {abs(valuation['price_target_analysis']['upside_potential'])}%)")
        
        peg = valuation.get("peg_ratio", {}).get("value")
        if peg and peg < 1:
            insights.append(f"Attractive PEG ratio ({peg}) suggests growth at reasonable price")
        elif peg and peg > 2:
            concerns.append(f"High PEG ratio ({peg}) - may be overpriced relative to growth")
        
        # Profitability insights
        profitability = analysis.get("profitability", {})
        roe = profitability.get("return_on_equity", {}).get("value")
        if roe and roe > 0.20:
            insights.append(f"Strong return on equity ({roe*100:.1f}%) indicates efficient capital use")
        elif roe and roe < 0.05:
            concerns.append(f"Low return on equity ({roe*100:.1f}%)")
        
        # Growth insights
        growth = analysis.get("growth", {})
        rev_growth = growth.get("revenue_growth", {}).get("value")
        if rev_growth and rev_growth > 0.20:
            insights.append(f"Strong revenue growth ({rev_growth*100:.1f}%)")
        elif rev_growth and rev_growth < 0:
            concerns.append(f"Declining revenue ({rev_growth*100:.1f}%)")
        
        # Financial health
        health = analysis.get("financial_health", {})
        debt_equity = health.get("debt_to_equity", {}).get("value")
        if debt_equity and debt_equity > 100:
            concerns.append(f"High debt-to-equity ratio ({debt_equity}) - elevated financial risk")
        elif debt_equity and debt_equity < 30:
            insights.append(f"Conservative debt levels ({debt_equity}%)")
        
        current_ratio = health.get("current_ratio", {}).get("value")
        if current_ratio and current_ratio < 1:
            concerns.append("Current ratio below 1 - potential liquidity concerns")
        
        # Free cash flow
        fcf = health.get("free_cash_flow")
        if fcf and fcf > 0:
            insights.append("Positive free cash flow generation")
        elif fcf and fcf < 0:
            concerns.append("Negative free cash flow")
        
        return insights, concerns
    
    def _calculate_overall_score(self, analysis: Dict) -> tuple:
        """Calculate overall fundamental score (-100 to 100)"""
        score = 0
        
        # Valuation score
        valuation = analysis.get("valuation", {})
        val_assessment = valuation.get("overall_assessment", "")
        if "undervalued" in val_assessment.lower():
            score += 25
        elif "overvalued" in val_assessment.lower():
            score -= 25
        
        upside = valuation.get("price_target_analysis", {}).get("upside_potential", 0)
        score += min(20, max(-20, upside * 0.5))
        
        # Profitability score
        profitability = analysis.get("profitability", {})
        roe = profitability.get("return_on_equity", {}).get("value")
        if roe:
            if roe > 0.15:
                score += 15
            elif roe > 0.10:
                score += 10
            elif roe < 0:
                score -= 15
        
        # Growth score
        growth = analysis.get("growth", {})
        rev_growth = growth.get("revenue_growth", {}).get("value")
        if rev_growth:
            if rev_growth > 0.20:
                score += 15
            elif rev_growth > 0.10:
                score += 10
            elif rev_growth < 0:
                score -= 15
        
        # Financial health score
        health = analysis.get("financial_health", {})
        debt_equity = health.get("debt_to_equity", {}).get("value")
        if debt_equity:
            if debt_equity < 50:
                score += 10
            elif debt_equity > 100:
                score -= 10
        
        # Analyst consensus score
        consensus = analysis.get("analyst_consensus", {})
        rec_score = consensus.get("recommendation_score")
        if rec_score:
            score += (3 - rec_score) * 10  # 1=+20, 2=+10, 3=0, 4=-10, 5=-20
        
        # Insights/concerns balance
        insights_count = len(analysis.get("key_insights", []))
        concerns_count = len(analysis.get("concerns", []))
        score += (insights_count - concerns_count) * 5
        
        # Clamp score
        score = max(-100, min(100, score))
        
        # Determine signal
        if score >= 30:
            signal = "STRONG BUY"
        elif score >= 10:
            signal = "BUY"
        elif score <= -30:
            signal = "STRONG SELL"
        elif score <= -10:
            signal = "SELL"
        else:
            signal = "HOLD"
        
        return round(score, 1), signal
    
    # Assessment helper methods
    def _assess_pe(self, pe: float, benchmark: float) -> str:
        if pe is None:
            return "N/A"
        if pe < 0:
            return "Negative (company losing money)"
        if pe < benchmark * 0.7:
            return "Undervalued relative to sector"
        if pe > benchmark * 1.5:
            return "Overvalued relative to sector"
        return "Fairly valued"
    
    def _assess_forward_pe(self, pe: float, forward_pe: float) -> str:
        if pe is None or forward_pe is None:
            return "N/A"
        if forward_pe < pe * 0.8:
            return "Expected earnings growth (bullish)"
        if forward_pe > pe * 1.2:
            return "Expected earnings decline (bearish)"
        return "Stable earnings expected"
    
    def _assess_peg(self, peg: float) -> str:
        if peg is None:
            return "N/A"
        if peg < 0:
            return "Negative growth"
        if peg < 1:
            return "Undervalued relative to growth"
        if peg < 2:
            return "Fairly valued"
        return "Overvalued relative to growth"
    
    def _assess_pb(self, pb: float) -> str:
        if pb is None:
            return "N/A"
        if pb < 1:
            return "Trading below book value"
        if pb < 3:
            return "Reasonable"
        return "Premium valuation"
    
    def _assess_ps(self, ps: float) -> str:
        if ps is None:
            return "N/A"
        if ps < 2:
            return "Attractive"
        if ps < 5:
            return "Reasonable"
        return "Expensive"
    
    def _assess_ev_ebitda(self, ev_ebitda: float) -> str:
        if ev_ebitda is None:
            return "N/A"
        if ev_ebitda < 10:
            return "Attractive"
        if ev_ebitda < 15:
            return "Reasonable"
        return "Expensive"
    
    def _assess_margin(self, margin: float, margin_type: str) -> str:
        if margin is None:
            return "N/A"
        if margin_type == "gross":
            return "Strong" if margin > 0.4 else ("Healthy" if margin > 0.25 else "Low")
        elif margin_type == "operating":
            return "Strong" if margin > 0.2 else ("Healthy" if margin > 0.1 else "Low")
        else:  # profit
            return "Strong" if margin > 0.15 else ("Healthy" if margin > 0.05 else "Low")
    
    def _assess_roe(self, roe: float) -> str:
        if roe is None:
            return "N/A"
        if roe > 0.20:
            return "Excellent"
        if roe > 0.15:
            return "Good"
        if roe > 0.10:
            return "Average"
        if roe > 0:
            return "Below average"
        return "Negative (losing money)"
    
    def _assess_roa(self, roa: float) -> str:
        if roa is None:
            return "N/A"
        if roa > 0.10:
            return "Excellent"
        if roa > 0.05:
            return "Good"
        if roa > 0:
            return "Average"
        return "Poor"
    
    def _assess_growth(self, growth: float, growth_type: str) -> str:
        if growth is None:
            return "N/A"
        if growth > 0.25:
            return "High growth"
        if growth > 0.10:
            return "Moderate growth"
        if growth > 0:
            return "Slow growth"
        return "Declining"
    
    def _assess_growth_consistency(self, rev_growth: float, earn_growth: float) -> str:
        if rev_growth is None or earn_growth is None:
            return "Insufficient data"
        if rev_growth > 0 and earn_growth > 0:
            if earn_growth > rev_growth:
                return "Improving efficiency (earnings growing faster than revenue)"
            return "Consistent growth"
        if rev_growth > 0 and earn_growth < 0:
            return "Margin compression (revenue up, earnings down)"
        return "Mixed signals"
    
    def _assess_debt_equity(self, de: float) -> str:
        if de is None:
            return "N/A"
        if de < 30:
            return "Conservative"
        if de < 60:
            return "Moderate"
        if de < 100:
            return "Elevated"
        return "High risk"
    
    def _assess_current_ratio(self, cr: float) -> str:
        if cr is None:
            return "N/A"
        if cr > 2:
            return "Strong liquidity"
        if cr > 1.5:
            return "Healthy"
        if cr > 1:
            return "Adequate"
        return "Liquidity concern"
    
    def _assess_quick_ratio(self, qr: float) -> str:
        if qr is None:
            return "N/A"
        if qr > 1:
            return "Strong"
        if qr > 0.5:
            return "Adequate"
        return "Weak"
    
    def _assess_cash_position(self, fundamentals: Dict) -> str:
        cash = fundamentals.get("total_cash", 0) or 0
        debt = fundamentals.get("total_debt", 0) or 0
        
        if cash == 0 and debt == 0:
            return "Insufficient data"
        
        if cash > debt:
            return "Net cash position (positive)"
        if cash > debt * 0.5:
            return "Reasonable cash reserves"
        return "Debt exceeds cash significantly"
    
    def _assess_dividend_yield(self, dy: float) -> str:
        if dy is None:
            return "N/A"
        if dy > 0.05:
            return "High yield"
        if dy > 0.02:
            return "Moderate yield"
        if dy > 0:
            return "Low yield"
        return "No dividend"
    
    def _assess_payout_ratio(self, pr: float) -> str:
        if pr is None:
            return "N/A"
        if pr < 0.3:
            return "Conservative (room for growth)"
        if pr < 0.6:
            return "Healthy"
        if pr < 0.8:
            return "Elevated"
        return "Unsustainable"
    
    def _assess_dividend_sustainability(self, dy: float, pr: float) -> str:
        if dy is None or pr is None:
            return "Insufficient data"
        if pr and pr < 0.6:
            return "Sustainable"
        if pr and pr < 0.8:
            return "Monitor closely"
        return "At risk"
    
    def _overall_valuation_assessment(self, valuation: Dict) -> str:
        scores = []
        
        pe_assess = valuation.get("pe_ratio", {}).get("assessment", "")
        if "undervalued" in pe_assess.lower():
            scores.append(1)
        elif "overvalued" in pe_assess.lower():
            scores.append(-1)
        else:
            scores.append(0)
        
        peg_assess = valuation.get("peg_ratio", {}).get("assessment", "")
        if "undervalued" in peg_assess.lower():
            scores.append(1)
        elif "overvalued" in peg_assess.lower():
            scores.append(-1)
        else:
            scores.append(0)
        
        target_assess = valuation.get("price_target_analysis", {}).get("assessment", "")
        if "undervalued" in target_assess.lower():
            scores.append(1)
        elif "overvalued" in target_assess.lower():
            scores.append(-1)
        else:
            scores.append(0)
        
        avg_score = sum(scores) / len(scores) if scores else 0
        
        if avg_score > 0.3:
            return "Undervalued - potential buying opportunity"
        if avg_score < -0.3:
            return "Overvalued - exercise caution"
        return "Fairly valued"


if __name__ == "__main__":
    from collectors.stock_data import StockDataCollector
    collector = StockDataCollector()
    data = collector.get_stock_data("AAPL")
    
    analyzer = FundamentalAnalyzer()
    analysis = analyzer.analyze(data)
    print(f"Fundamental Score: {analysis['overall_score']}")
    print(f"Signal: {analysis['overall_signal']}")
