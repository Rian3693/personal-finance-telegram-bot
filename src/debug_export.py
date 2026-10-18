"""
Debug Export Module - Exports all collected data and calculations to a detailed TXT file
"""
from datetime import datetime
from typing import Dict, Any
import json
import os
import glob


class DebugExporter:
    """Exports all analysis data for transparency and debugging"""
    
    def __init__(self):
        self.output_dir = "debug_reports"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _delete_old_reports(self, symbol: str):
        """Delete previous debug reports for the same stock"""
        pattern = os.path.join(self.output_dir, f"{symbol}_debug_*.txt")
        old_files = glob.glob(pattern)
        
        for old_file in old_files:
            try:
                os.remove(old_file)
            except Exception as e:
                pass  # Silently ignore deletion errors
    
    def export_full_analysis(self, symbol: str, data: Dict[str, Any]) -> str:
        """Export all collected data and calculations to a TXT file"""
        
        # Delete old reports for this stock first
        self._delete_old_reports(symbol)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.output_dir}/{symbol}_debug_{timestamp}.txt"
        
        lines = []
        lines.append("=" * 100)
        lines.append(f"FULL DATA EXPORT FOR {symbol}")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 100)
        lines.append("")
        
        # 1. RAW STOCK DATA
        lines.append(self._section_header("1. RAW STOCK DATA (from yfinance)"))
        stock_data = data.get("stock_data", {})
        
        # Company Info
        lines.append("\n--- Company Information ---")
        company_info = stock_data.get("company_info", {})
        for key, value in company_info.items():
            if key == "description":
                lines.append(f"  {key}: {str(value)[:200]}..." if value else f"  {key}: N/A")
            else:
                lines.append(f"  {key}: {value}")
        
        # Price Data
        lines.append("\n--- Price Data ---")
        price_data = stock_data.get("price_data", {})
        for key, value in price_data.items():
            lines.append(f"  {key}: {value}")
        
        # Historical Data Summary
        lines.append("\n--- Historical Data (last 10 days) ---")
        hist = stock_data.get("historical_data", {})
        if hist:
            lines.append(f"  Total data points: {len(hist.get('dates', []))}")
            lines.append(f"  Date range: {hist.get('dates', ['N/A'])[0]} to {hist.get('dates', ['N/A'])[-1] if hist.get('dates') else 'N/A'}")
            if hist.get('dates'):
                lines.append("  Recent prices:")
                for i in range(-10, 0):
                    try:
                        lines.append(f"    {hist['dates'][i]}: Open=${hist['open'][i]:.2f}, High=${hist['high'][i]:.2f}, Low=${hist['low'][i]:.2f}, Close=${hist['close'][i]:.2f}, Vol={hist['volume'][i]:,}")
                    except (IndexError, KeyError):
                        pass
        
        # Analyst Ratings from yfinance
        lines.append("\n--- Yahoo Finance Analyst Data ---")
        analyst = stock_data.get("analyst_ratings", {})
        for key, value in analyst.items():
            lines.append(f"  {key}: {value}")
        
        # 2. INSTITUTIONAL ANALYST RATINGS
        lines.append(self._section_header("2. INSTITUTIONAL ANALYST RATINGS"))
        analyst_ratings = data.get("analyst_ratings", {})
        
        lines.append("\n--- All Collected Ratings ---")
        all_ratings = analyst_ratings.get("institutional_ratings", [])
        lines.append(f"  Total ratings collected: {len(all_ratings)}")
        for i, r in enumerate(all_ratings[:30], 1):  # Show first 30
            pt = f", PT: ${r.get('price_target')}" if r.get('price_target') else ""
            lines.append(f"  {i}. {r.get('source', 'Unknown')}: {r.get('rating', 'N/A')} (Score: {r.get('rating_score', 'N/A')}/5, Weight: {r.get('weight', 0):.2f}{pt})")
        
        lines.append("\n--- Priority Bank Ratings ---")
        priority = analyst_ratings.get("priority_bank_ratings", {})
        for bank, rating in priority.items():
            lines.append(f"  {bank}: {rating.get('rating', 'N/A')} (Score: {rating.get('rating_score', 'N/A')}/5)")
        
        lines.append("\n--- Price Targets Summary ---")
        pt = analyst_ratings.get("price_targets", {})
        lines.append(f"  Average: ${pt.get('average', 'N/A')}")
        lines.append(f"  High: ${pt.get('high', 'N/A')}")
        lines.append(f"  Low: ${pt.get('low', 'N/A')}")
        lines.append(f"  Count: {pt.get('count', 0)}")
        
        lines.append("\n--- Consensus Calculation ---")
        consensus = analyst_ratings.get("consensus", {})
        for key, value in consensus.items():
            lines.append(f"  {key}: {value}")
        
        # 3. TECHNICAL ANALYSIS
        lines.append(self._section_header("3. TECHNICAL ANALYSIS CALCULATIONS"))
        technical = data.get("technical", {})
        
        lines.append("\n--- Technical Indicators ---")
        indicators = technical.get("indicators", {})
        for ind_name, ind_data in indicators.items():
            lines.append(f"\n  {ind_name.upper()}:")
            if isinstance(ind_data, dict):
                for key, value in ind_data.items():
                    lines.append(f"    {key}: {value}")
            else:
                lines.append(f"    value: {ind_data}")
        
        lines.append("\n--- Moving Averages ---")
        ma = technical.get("moving_averages", {})
        for key, value in ma.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Trend Analysis ---")
        trend = technical.get("trend_analysis", {})
        for key, value in trend.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Support & Resistance ---")
        sr = technical.get("support_resistance", {})
        for key, value in sr.items():
            if isinstance(value, list):
                lines.append(f"  {key}: {[f'${v:.2f}' if isinstance(v, (int, float)) else v for v in value]}")
            else:
                lines.append(f"  {key}: ${value:.2f}" if isinstance(value, (int, float)) else f"  {key}: {value}")
        
        lines.append("\n--- Technical Signals ---")
        signals = technical.get("signals", {})
        lines.append(f"  Buy Signals: {signals.get('buy_signals', [])}")
        lines.append(f"  Sell Signals: {signals.get('sell_signals', [])}")
        lines.append(f"  Neutral Signals: {signals.get('neutral_signals', [])}")
        
        lines.append("\n--- Technical Score Calculation ---")
        lines.append(f"  Overall Signal: {technical.get('overall_signal', 'N/A')}")
        lines.append(f"  Technical Score: {technical.get('score', 'N/A')}/100")
        
        # 4. FUNDAMENTAL ANALYSIS
        lines.append(self._section_header("4. FUNDAMENTAL ANALYSIS"))
        fundamental = data.get("fundamental", {})
        
        lines.append("\n--- Valuation Metrics ---")
        valuation = fundamental.get("valuation", {})
        for key, value in valuation.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for k, v in value.items():
                    lines.append(f"    {k}: {v}")
            else:
                lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Financial Health ---")
        health = fundamental.get("financial_health", {})
        for key, value in health.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for k, v in value.items():
                    lines.append(f"    {k}: {v}")
            else:
                lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Profitability Metrics ---")
        profit = fundamental.get("profitability", {})
        for key, value in profit.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for k, v in value.items():
                    lines.append(f"    {k}: {v}")
            else:
                lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Growth Metrics ---")
        growth = fundamental.get("growth", {})
        for key, value in growth.items():
            if isinstance(value, dict):
                lines.append(f"  {key}:")
                for k, v in value.items():
                    lines.append(f"    {k}: {v}")
            else:
                lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Key Insights ---")
        for insight in fundamental.get("key_insights", []):
            lines.append(f"  + {insight}")
        
        lines.append("\n--- Concerns ---")
        for concern in fundamental.get("concerns", []):
            lines.append(f"  - {concern}")
        
        lines.append("\n--- Fundamental Score Calculation ---")
        lines.append(f"  Overall Signal: {fundamental.get('overall_signal', 'N/A')}")
        lines.append(f"  Fundamental Score: {fundamental.get('overall_score', 'N/A')}/100")
        
        # 5. SENTIMENT ANALYSIS
        lines.append(self._section_header("5. SENTIMENT ANALYSIS"))
        sentiment = data.get("sentiment", {})
        
        lines.append("\n--- News Sentiment ---")
        news_sent = sentiment.get("news_sentiment", {})
        lines.append(f"  Average Score: {news_sent.get('average_score', 'N/A')}")
        lines.append(f"  Label: {news_sent.get('label', 'N/A')}")
        lines.append(f"  Total Articles: {news_sent.get('total_articles', 0)}")
        lines.append(f"  Bullish: {news_sent.get('bullish_count', 0)}, Bearish: {news_sent.get('bearish_count', 0)}, Neutral: {news_sent.get('neutral_count', 0)}")
        
        lines.append("\n  Top Bullish Headlines:")
        for art in news_sent.get("bullish_articles", [])[:5]:
            lines.append(f"    + [{art.get('source', 'Unknown')}] {art.get('title', 'N/A')[:80]}...")
        
        lines.append("\n  Top Bearish Headlines:")
        for art in news_sent.get("bearish_articles", [])[:5]:
            lines.append(f"    - [{art.get('source', 'Unknown')}] {art.get('title', 'N/A')[:80]}...")
        
        lines.append("\n--- Social Sentiment ---")
        social_sent = sentiment.get("social_sentiment", {})
        reddit = social_sent.get("reddit", {})
        if reddit:
            lines.append(f"  Reddit Score: {reddit.get('score', 'N/A')}")
            lines.append(f"  Reddit Label: {reddit.get('label', 'N/A')}")
            lines.append(f"  Reddit Mentions: {reddit.get('mentions', 0)}")
        
        lines.append("\n--- Combined Sentiment ---")
        combined = sentiment.get("combined_sentiment", {})
        lines.append(f"  Combined Score: {combined.get('score', 'N/A')}")
        lines.append(f"  Combined Label: {combined.get('label', 'N/A')}")
        lines.append(f"  Confidence: {combined.get('confidence', 'N/A')}")
        
        lines.append("\n--- Sentiment Score Calculation ---")
        lines.append(f"  Overall Score: {sentiment.get('overall_score', 'N/A')}")
        lines.append(f"  Overall Signal: {sentiment.get('overall_signal', 'N/A')}")
        
        # 5B. DETAILED NEWS ANALYSIS (with AI interpretation)
        lines.append(self._section_header("5B. DETAILED NEWS ANALYSIS (AI Price Impact)"))
        news_data = data.get("news_data", {})
        ai_news = data.get("ai_news_analysis", {})
        all_articles = news_data.get("articles", [])
        analyzed_articles = ai_news.get("analyzed_articles", [])
        
        lines.append(f"\n  Total News Articles Collected: {len(all_articles)}")
        lines.append(f"  News Collection Timestamp: {news_data.get('timestamp', 'N/A')}")
        lines.append(f"  AI Analyzed Articles: {len(analyzed_articles)}")
        
        # Use AI analysis if available, otherwise fall back to basic
        if analyzed_articles:
            # AI-powered analysis available
            good_news = [a for a in analyzed_articles if a.get('ai_sentiment') == 'GOOD']
            bad_news = [a for a in analyzed_articles if a.get('ai_sentiment') == 'BAD']
            neutral_news = [a for a in analyzed_articles if a.get('ai_sentiment') == 'NEUTRAL']
        else:
            # Fall back to basic keyword analysis
            good_news = [a for a in all_articles if a.get('impact') == 'Positive']
            bad_news = [a for a in all_articles if a.get('impact') == 'Negative']
            neutral_news = [a for a in all_articles if a.get('impact') == 'Neutral']
        
        lines.append(f"\n  📈 GOOD NEWS (Price likely to RISE): {len(good_news)}")
        lines.append(f"  📉 BAD NEWS (Price likely to FALL): {len(bad_news)}")
        lines.append(f"  ➖ NEUTRAL NEWS: {len(neutral_news)}")
        
        # Good News Section with AI explanations
        lines.append("\n" + "-" * 80)
        lines.append("📈 GOOD NEWS - BULLISH SIGNALS (Price likely to RISE)")
        lines.append("-" * 80)
        if good_news:
            for i, article in enumerate(good_news[:15], 1):
                title = article.get('title', 'N/A')
                source = article.get('source', 'Unknown')
                date = article.get('published_date', 'N/A')
                url = article.get('url', '')
                ai_impact = article.get('ai_price_impact', 'RISE')
                ai_magnitude = article.get('ai_magnitude', 'MEDIUM')
                ai_explanation = article.get('ai_explanation', 'Positive sentiment detected')
                
                lines.append(f"\n  {i}. [{source}] {date}")
                lines.append(f"     📰 {title}")
                lines.append(f"     🔗 {url[:100]}..." if len(url) > 100 else f"     🔗 {url}")
                lines.append(f"     💹 PRICE IMPACT: {ai_impact} (Magnitude: {ai_magnitude})")
                lines.append(f"     ✅ AI Analysis: {ai_explanation}")
        else:
            lines.append("  No positive news articles found.")
        
        # Bad News Section with AI explanations
        lines.append("\n" + "-" * 80)
        lines.append("📉 BAD NEWS - BEARISH SIGNALS (Price likely to FALL)")
        lines.append("-" * 80)
        if bad_news:
            for i, article in enumerate(bad_news[:15], 1):
                title = article.get('title', 'N/A')
                source = article.get('source', 'Unknown')
                date = article.get('published_date', 'N/A')
                url = article.get('url', '')
                ai_impact = article.get('ai_price_impact', 'FALL')
                ai_magnitude = article.get('ai_magnitude', 'MEDIUM')
                ai_explanation = article.get('ai_explanation', 'Negative sentiment detected')
                
                lines.append(f"\n  {i}. [{source}] {date}")
                lines.append(f"     📰 {title}")
                lines.append(f"     🔗 {url[:100]}..." if len(url) > 100 else f"     🔗 {url}")
                lines.append(f"     💹 PRICE IMPACT: {ai_impact} (Magnitude: {ai_magnitude})")
                lines.append(f"     ⚠️ AI Analysis: {ai_explanation}")
        else:
            lines.append("  No negative news articles found.")
        
        # Neutral News Section
        lines.append("\n" + "-" * 80)
        lines.append("➖ NEUTRAL NEWS - Informational Only")
        lines.append("-" * 80)
        if neutral_news:
            for i, article in enumerate(neutral_news[:10], 1):
                title = article.get('title', 'N/A')
                source = article.get('source', 'Unknown')
                date = article.get('published_date', 'N/A')
                ai_explanation = article.get('ai_explanation', 'No significant price impact expected')
                
                lines.append(f"\n  {i}. [{source}] {date}")
                lines.append(f"     📰 {title}")
                lines.append(f"     💹 PRICE IMPACT: MINIMAL/UNCERTAIN")
                lines.append(f"     ℹ️ AI Analysis: {ai_explanation}")
        else:
            lines.append("  No neutral news articles found.")
        
        # Overall News Summary
        lines.append("\n" + "-" * 80)
        lines.append("📊 NEWS ANALYSIS SUMMARY")
        lines.append("-" * 80)
        
        total_analyzed = len(good_news) + len(bad_news) + len(neutral_news)
        good_pct = (len(good_news) / total_analyzed * 100) if total_analyzed else 0
        bad_pct = (len(bad_news) / total_analyzed * 100) if total_analyzed else 0
        neutral_pct = (len(neutral_news) / total_analyzed * 100) if total_analyzed else 0
        
        lines.append(f"\n  Good News Ratio: {len(good_news)}/{total_analyzed} ({good_pct:.1f}%)")
        lines.append(f"  Bad News Ratio: {len(bad_news)}/{total_analyzed} ({bad_pct:.1f}%)")
        lines.append(f"  Neutral News Ratio: {len(neutral_news)}/{total_analyzed} ({neutral_pct:.1f}%)")
        
        # Use AI conclusion if available
        if ai_news and ai_news.get("overall_news_sentiment"):
            news_verdict = ai_news.get("overall_news_sentiment", "NEUTRAL")
            price_direction = ai_news.get("price_direction_prediction", "SIDEWAYS")
            confidence = ai_news.get("confidence", "LOW")
            explanation = ai_news.get("summary", "No detailed analysis available")
        else:
            # Fallback calculation
            if good_pct > bad_pct + 10:
                news_verdict = "BULLISH"
                price_direction = "RISE"
                confidence = "HIGH" if good_pct > 60 else "MODERATE"
                explanation = "The news sentiment is predominantly positive, suggesting upward price pressure."
            elif bad_pct > good_pct + 10:
                news_verdict = "BEARISH"
                price_direction = "FALL"
                confidence = "HIGH" if bad_pct > 60 else "MODERATE"
                explanation = "The news sentiment is predominantly negative, suggesting downward price pressure."
            else:
                news_verdict = "MIXED/NEUTRAL"
                price_direction = "SIDEWAYS"
                confidence = "LOW"
                explanation = "News sentiment is mixed, price direction from news alone is uncertain."
        
        lines.append(f"\n  ═══════════════════════════════════════════════════════")
        lines.append(f"  🤖 AI NEWS VERDICT: {news_verdict}")
        lines.append(f"  📊 Expected Price Direction from News: {price_direction}")
        lines.append(f"  🎯 Confidence: {confidence}")
        lines.append(f"  💡 Analysis: {explanation}")
        lines.append(f"  ═══════════════════════════════════════════════════════")
        
        # 6. AI ANALYSIS OUTPUT
        lines.append(self._section_header("6. AI ANALYSIS OUTPUT"))
        ai = data.get("ai_analysis", {})
        
        lines.append("\n--- Executive Summary ---")
        lines.append(f"  {ai.get('executive_summary', 'N/A')}")
        
        lines.append("\n--- Investment Thesis ---")
        lines.append(f"  {ai.get('investment_thesis', 'N/A')}")
        
        lines.append("\n--- Entry Price Recommendation ---")
        entry = ai.get("entry_price_recommendation", {})
        for key, value in entry.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Stop Loss Levels ---")
        sl = ai.get("stop_loss", {})
        for key, value in sl.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Valuation Assessment ---")
        val = ai.get("valuation_assessment", {})
        for key, value in val.items():
            lines.append(f"  {key}: {value}")
        
        lines.append("\n--- Price Targets (AI Generated) ---")
        pt = ai.get("price_targets", {})
        for timeframe, target_data in pt.items():
            lines.append(f"\n  {timeframe}:")
            if isinstance(target_data, dict):
                for key, value in target_data.items():
                    lines.append(f"    {key}: {value}")
        
        lines.append("\n--- Bull Case (Strengths) ---")
        for i, item in enumerate(ai.get("bull_case", []), 1):
            if isinstance(item, dict):
                lines.append(f"  {i}. {item.get('title', 'N/A')}")
                lines.append(f"     {item.get('detail', 'N/A')}")
            else:
                lines.append(f"  {i}. {item}")
        
        lines.append("\n--- Bear Case (Concerns) ---")
        for i, item in enumerate(ai.get("bear_case", []), 1):
            if isinstance(item, dict):
                lines.append(f"  {i}. {item.get('title', 'N/A')}")
                lines.append(f"     {item.get('detail', 'N/A')}")
            else:
                lines.append(f"  {i}. {item}")
        
        lines.append("\n--- Risk Factors ---")
        rf = ai.get("risk_factors", {})
        lines.append(f"  Overall Risk Level: {rf.get('overall_level', 'N/A')}")
        lines.append("  Company-Specific Risks:")
        for risk in rf.get("company_specific", []):
            lines.append(f"    - {risk}")
        lines.append("  Market/Sector Risks:")
        for risk in rf.get("market_sector", []):
            lines.append(f"    - {risk}")
        
        lines.append("\n--- Key Factors ---")
        for i, factor in enumerate(ai.get("key_factors", []), 1):
            lines.append(f"  {i}. {factor}")
        
        lines.append("\n--- Final Recommendation ---")
        lines.append(f"  Recommendation: {ai.get('recommendation', 'N/A')}")
        lines.append(f"  Confidence Level: {ai.get('confidence_level', 'N/A')}")
        
        # 7. OVERALL ASSESSMENT CALCULATION
        lines.append(self._section_header("7. OVERALL ASSESSMENT CALCULATION"))
        overall = data.get("overall_assessment", {})
        
        lines.append("\n--- Score Breakdown ---")
        lines.append(f"  Technical Score: {technical.get('score', 0)}")
        lines.append(f"  Fundamental Score: {fundamental.get('overall_score', 0)}")
        lines.append(f"  Sentiment Score: {sentiment.get('overall_score', 0)}")
        
        lines.append("\n--- Weighted Calculation ---")
        lines.append("  Formula: (Technical * 0.3) + (Fundamental * 0.4) + (Sentiment * 0.3)")
        tech_weighted = technical.get('score', 0) * 0.3
        fund_weighted = fundamental.get('overall_score', 0) * 0.4
        sent_weighted = sentiment.get('overall_score', 0) * 0.3
        lines.append(f"  Technical Contribution: {technical.get('score', 0)} * 0.3 = {tech_weighted:.2f}")
        lines.append(f"  Fundamental Contribution: {fundamental.get('overall_score', 0)} * 0.4 = {fund_weighted:.2f}")
        lines.append(f"  Sentiment Contribution: {sentiment.get('overall_score', 0)} * 0.3 = {sent_weighted:.2f}")
        lines.append(f"  Total: {tech_weighted + fund_weighted + sent_weighted:.2f}")
        
        lines.append("\n--- Final Assessment ---")
        for key, value in overall.items():
            lines.append(f"  {key}: {value}")
        
        # Write to file
        lines.append("\n" + "=" * 100)
        lines.append("END OF DEBUG EXPORT")
        lines.append("=" * 100)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        
        return filename
    
    def _section_header(self, title: str) -> str:
        """Create a section header"""
        return f"\n\n{'#' * 100}\n# {title}\n{'#' * 100}"
    
    def print_summary(self, symbol: str, data: Dict[str, Any]):
        """Print a condensed summary to console"""
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        from rich import box
        
        console = Console()
        
        console.print(f"\n[bold cyan]{'='*60}[/]")
        console.print(f"[bold cyan]DATA COLLECTION SUMMARY FOR {symbol}[/]")
        console.print(f"[bold cyan]{'='*60}[/]\n")
        
        # Data Sources Table
        table = Table(title="📊 Data Sources & Collection Status", box=box.ROUNDED)
        table.add_column("Data Source", style="cyan", width=25)
        table.add_column("Status", justify="center", width=10)
        table.add_column("Items/Points", justify="center", width=15)
        table.add_column("Key Value", width=30)
        
        # Stock Data
        stock_data = data.get("stock_data", {})
        price = stock_data.get("price_data", {}).get("current_price")
        hist_count = len(stock_data.get("historical_data", {}).get("dates", []))
        table.add_row(
            "Yahoo Finance (Price)",
            "[green]✓[/]" if price else "[red]✗[/]",
            f"{hist_count} days",
            f"${price:.2f}" if price else "N/A"
        )
        
        # Analyst Ratings
        analyst_ratings = data.get("analyst_ratings", {})
        rating_count = len(analyst_ratings.get("institutional_ratings", []))
        consensus = analyst_ratings.get("consensus", {}).get("consensus_rating", "N/A")
        table.add_row(
            "Institutional Ratings",
            "[green]✓[/]" if rating_count > 0 else "[yellow]~[/]",
            f"{rating_count} ratings",
            consensus
        )
        
        # Technical
        technical = data.get("technical", {})
        tech_signal = technical.get("overall_signal", "N/A")
        tech_score = technical.get("score", "N/A")
        table.add_row(
            "Technical Analysis",
            "[green]✓[/]" if tech_signal != "N/A" else "[red]✗[/]",
            "14 indicators",
            f"{tech_signal} ({tech_score})"
        )
        
        # Fundamental
        fundamental = data.get("fundamental", {})
        fund_signal = fundamental.get("overall_signal", "N/A")
        fund_score = fundamental.get("overall_score", "N/A")
        table.add_row(
            "Fundamental Analysis",
            "[green]✓[/]" if fund_signal != "N/A" else "[red]✗[/]",
            "12 metrics",
            f"{fund_signal} ({fund_score})"
        )
        
        # Sentiment
        sentiment = data.get("sentiment", {})
        sent_signal = sentiment.get("overall_signal", "N/A")
        news_count = sentiment.get("news_sentiment", {}).get("total_articles", 0)
        table.add_row(
            "News Sentiment",
            "[green]✓[/]" if news_count > 0 else "[yellow]~[/]",
            f"{news_count} articles",
            sent_signal
        )
        
        # AI Analysis
        ai = data.get("ai_analysis", {})
        ai_rec = ai.get("recommendation", "N/A")
        has_ai = bool(ai.get("executive_summary") and "fallback" not in ai.get("executive_summary", "").lower())
        table.add_row(
            "AI Analysis (GPT-4o)",
            "[green]✓[/]" if has_ai else "[yellow]Fallback[/]",
            "Full analysis",
            ai_rec
        )
        
        console.print(table)
        
        # Key Metrics
        console.print("\n[bold]📈 Key Metrics Collected:[/]")
        
        metrics_table = Table(box=box.SIMPLE)
        metrics_table.add_column("Metric", style="dim")
        metrics_table.add_column("Value", style="bold")
        metrics_table.add_column("Metric", style="dim")
        metrics_table.add_column("Value", style="bold")
        
        price_data = stock_data.get("price_data", {})
        valuation = fundamental.get("valuation", {})
        
        metrics_table.add_row(
            "Current Price", f"${price_data.get('current_price', 0):.2f}",
            "52W High", f"${price_data.get('52_week_high', 0):.2f}"
        )
        metrics_table.add_row(
            "52W Low", f"${price_data.get('52_week_low', 0):.2f}",
            "P/E Ratio", f"{valuation.get('pe_ratio', {}).get('value', 'N/A')}"
        )
        metrics_table.add_row(
            "Support", f"${technical.get('support_resistance', {}).get('nearest_support', 0):.2f}",
            "Resistance", f"${technical.get('support_resistance', {}).get('nearest_resistance', 0):.2f}"
        )
        metrics_table.add_row(
            "RSI", f"{technical.get('indicators', {}).get('rsi', {}).get('value', 'N/A')}",
            "MACD Signal", f"{technical.get('indicators', {}).get('macd', {}).get('signal', 'N/A')}"
        )
        
        console.print(metrics_table)
        
        # Score Breakdown
        console.print("\n[bold]🧮 Score Calculation:[/]")
        console.print(f"  Technical:   {technical.get('score', 0):>6} × 0.30 = {technical.get('score', 0) * 0.3:>6.1f}")
        console.print(f"  Fundamental: {fundamental.get('overall_score', 0):>6} × 0.40 = {fundamental.get('overall_score', 0) * 0.4:>6.1f}")
        console.print(f"  Sentiment:   {sentiment.get('overall_score', 0):>6} × 0.30 = {sentiment.get('overall_score', 0) * 0.3:>6.1f}")
        console.print(f"  [bold]────────────────────────────────[/]")
        total = technical.get('score', 0) * 0.3 + fundamental.get('overall_score', 0) * 0.4 + sentiment.get('overall_score', 0) * 0.3
        console.print(f"  [bold]Total Score:           {total:>6.1f}[/]")
        
        # Bank Ratings Summary
        console.print("\n[bold]🏦 Bank Ratings Found:[/]")
        priority = analyst_ratings.get("priority_bank_ratings", {})
        for bank in ["Morgan Stanley", "Citigroup", "Goldman Sachs", "JPMorgan", "Deutsche Bank", "Zacks", "Bank of America"]:
            if bank in priority:
                r = priority[bank]
                console.print(f"  [green]✓[/] {bank}: {r.get('rating')} ({r.get('rating_score')}/5)")
            else:
                console.print(f"  [dim]✗ {bank}: No recent data[/]")


if __name__ == "__main__":
    # Test with sample data
    exporter = DebugExporter()
    print("Debug exporter ready")
