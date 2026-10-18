"""
Report Generator - Creates comprehensive stock analysis reports
"""
from typing import Dict, List, Any
from datetime import datetime
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from config import get_timeframe_config, DEFAULT_TIMEFRAME


class ReportGenerator:
    """Generates formatted reports for stock analysis"""
    
    def __init__(self):
        self.console = Console()
    
    def generate_report(self, symbol: str, stock_data: Dict, technical: Dict,
                       fundamental: Dict, sentiment: Dict, ai_analysis: Dict,
                       timeframe: str = DEFAULT_TIMEFRAME,
                       analyst_ratings: Dict = None) -> Dict[str, Any]:
        """
        Generate a comprehensive analysis report
        
        Args:
            symbol: Stock ticker symbol
            stock_data: Raw stock data from collectors
            technical: Technical analysis results
            fundamental: Fundamental analysis results
            sentiment: Sentiment analysis results
            ai_analysis: AI advisor recommendations
            timeframe: Analysis timeframe ('swing', 'short', 'medium', 'long')
            analyst_ratings: Institutional analyst ratings
        """
        tf_config = get_timeframe_config(timeframe)
        
        report = {
            "symbol": symbol,
            "generated_at": datetime.now().isoformat(),
            "timeframe": {
                "code": timeframe,
                "name": tf_config['name'],
                "description": tf_config['description'],
                "horizon": tf_config['horizon']
            },
            "company_info": self._extract_company_info(stock_data),
            "price_summary": self._extract_price_summary(stock_data),
            "technical_summary": self._extract_technical_summary(technical),
            "fundamental_summary": self._extract_fundamental_summary(fundamental),
            "sentiment_summary": self._extract_sentiment_summary(sentiment),
            "ai_recommendation": ai_analysis,
            "institutional_ratings": analyst_ratings,
            "overall_assessment": self._calculate_overall_assessment(
                technical, fundamental, sentiment, ai_analysis, tf_config
            ),
            "action_items": self._generate_action_items(
                stock_data, technical, fundamental, sentiment, ai_analysis
            )
        }
        
        return report
    
    def _extract_company_info(self, stock_data: Dict) -> Dict[str, Any]:
        """Extract company information"""
        info = stock_data.get("company_info", {})
        return {
            "name": info.get("name", "Unknown"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "description": info.get("description", "")[:500] if info.get("description") else "",
            "employees": info.get("employees"),
            "website": info.get("website")
        }
    
    def _extract_price_summary(self, stock_data: Dict) -> Dict[str, Any]:
        """Extract price summary"""
        price = stock_data.get("price_data", {})
        return {
            "current_price": price.get("current_price"),
            "previous_close": price.get("previous_close"),
            "day_range": {
                "low": price.get("day_low"),
                "high": price.get("day_high")
            },
            "52_week_range": {
                "low": price.get("52_week_low"),
                "high": price.get("52_week_high")
            },
            "moving_averages": {
                "50_day": price.get("50_day_avg"),
                "200_day": price.get("200_day_avg")
            },
            "volume": price.get("volume"),
            "avg_volume": price.get("avg_volume")
        }
    
    def _extract_technical_summary(self, technical: Dict) -> Dict[str, Any]:
        """Extract technical analysis summary"""
        if not technical or technical.get("error"):
            return {"status": "unavailable", "error": technical.get("error") if technical else "No data"}
        
        return {
            "signal": technical.get("overall_signal"),
            "score": technical.get("score"),
            "trend": technical.get("trend_analysis", {}).get("overall_trend"),
            "key_levels": {
                "support": technical.get("support_resistance", {}).get("nearest_support"),
                "resistance": technical.get("support_resistance", {}).get("nearest_resistance")
            },
            "indicators": {
                "rsi": technical.get("indicators", {}).get("rsi", {}).get("value"),
                "rsi_signal": technical.get("indicators", {}).get("rsi", {}).get("signal"),
                "macd_signal": technical.get("indicators", {}).get("macd", {}).get("signal")
            },
            "buy_signals": technical.get("signals", {}).get("buy_signals", []),
            "sell_signals": technical.get("signals", {}).get("sell_signals", []),
            "patterns": [p.get("name") for p in technical.get("patterns", {}).get("detected", [])]
        }
    
    def _extract_fundamental_summary(self, fundamental: Dict) -> Dict[str, Any]:
        """Extract fundamental analysis summary"""
        if not fundamental or fundamental.get("error"):
            return {"status": "unavailable", "error": fundamental.get("error") if fundamental else "No data"}
        
        valuation = fundamental.get("valuation", {})
        
        return {
            "signal": fundamental.get("overall_signal"),
            "score": fundamental.get("overall_score"),
            "valuation_assessment": valuation.get("overall_assessment"),
            "key_metrics": {
                "pe_ratio": valuation.get("pe_ratio", {}).get("value"),
                "peg_ratio": valuation.get("peg_ratio", {}).get("value"),
                "price_to_book": valuation.get("price_to_book", {}).get("value")
            },
            "price_targets": valuation.get("price_target_analysis", {}),
            "key_insights": fundamental.get("key_insights", []),
            "concerns": fundamental.get("concerns", [])
        }
    
    def _extract_sentiment_summary(self, sentiment: Dict) -> Dict[str, Any]:
        """Extract sentiment analysis summary"""
        if not sentiment or sentiment.get("error"):
            return {"status": "unavailable", "error": sentiment.get("error") if sentiment else "No data"}
        
        combined = sentiment.get("combined_sentiment", {})
        
        return {
            "signal": sentiment.get("overall_signal"),
            "score": sentiment.get("overall_score"),
            "overall_sentiment": combined.get("label"),
            "confidence": combined.get("confidence"),
            "news_sentiment": sentiment.get("news_sentiment", {}).get("label"),
            "social_sentiment": sentiment.get("social_sentiment", {}).get("overall", {}).get("label"),
            "key_topics": [t.get("topic") for t in sentiment.get("key_topics", [])]
        }
    
    def _calculate_overall_assessment(self, technical: Dict, fundamental: Dict,
                                     sentiment: Dict, ai_analysis: Dict,
                                     tf_config: Dict = None) -> Dict[str, Any]:
        """Calculate overall assessment from all analyses using timeframe-specific weights"""
        
        scores = {}
        signals = {}
        
        # Collect scores
        if technical and technical.get("score") is not None:
            scores["technical"] = technical["score"]
            signals["technical"] = technical.get("overall_signal")
        
        if fundamental and fundamental.get("overall_score") is not None:
            scores["fundamental"] = fundamental["overall_score"]
            signals["fundamental"] = fundamental.get("overall_signal")
        
        if sentiment and sentiment.get("overall_score") is not None:
            scores["sentiment"] = sentiment["overall_score"]
            signals["sentiment"] = sentiment.get("overall_signal")
        
        # Use timeframe-specific weights if available, otherwise defaults
        if tf_config and 'weights' in tf_config:
            weights = tf_config['weights']
        else:
            weights = {"technical": 0.35, "fundamental": 0.35, "sentiment": 0.30}
        
        weighted_sum = 0
        total_weight = 0
        for key, score in scores.items():
            weight = weights.get(key, 0.33)
            weighted_sum += score * weight
            total_weight += weight
        
        overall_score = weighted_sum / total_weight if total_weight > 0 else 0
        
        # Determine overall recommendation
        if overall_score >= 40:
            recommendation = "STRONG BUY"
            action = "Consider aggressive accumulation"
        elif overall_score >= 20:
            recommendation = "BUY"
            action = "Consider building a position"
        elif overall_score >= -20:
            recommendation = "HOLD"
            action = "Maintain current position, monitor for changes"
        elif overall_score >= -40:
            recommendation = "SELL"
            action = "Consider reducing position"
        else:
            recommendation = "STRONG SELL"
            action = "Consider exiting position"
        
        # AI recommendation override/confirmation
        ai_rec = ai_analysis.get("recommendation") if ai_analysis else None
        
        return {
            "overall_score": round(overall_score, 1),
            "recommendation": recommendation,
            "suggested_action": action,
            "component_scores": scores,
            "component_signals": signals,
            "ai_recommendation": ai_rec,
            "confidence": self._calculate_confidence(scores, ai_rec, recommendation)
        }
    
    def _calculate_confidence(self, scores: Dict, ai_rec: str, calculated_rec: str) -> str:
        """Calculate confidence level based on agreement between analyses"""
        
        # Check if all analyses agree on direction
        bullish_count = sum(1 for s in scores.values() if s > 10)
        bearish_count = sum(1 for s in scores.values() if s < -10)
        
        total = len(scores)
        
        if total == 0:
            return "LOW"
        
        # Strong agreement
        if bullish_count == total or bearish_count == total:
            # AI agrees
            if ai_rec:
                ai_bullish = ai_rec in ["STRONG BUY", "BUY"]
                calc_bullish = calculated_rec in ["STRONG BUY", "BUY"]
                if ai_bullish == calc_bullish:
                    return "HIGH"
            return "MEDIUM-HIGH"
        
        # Partial agreement
        if bullish_count >= total * 0.66 or bearish_count >= total * 0.66:
            return "MEDIUM"
        
        # Mixed signals
        return "LOW"
    
    def _generate_action_items(self, stock_data: Dict, technical: Dict,
                              fundamental: Dict, sentiment: Dict, ai_analysis: Dict) -> List[str]:
        """Generate actionable recommendations"""
        actions = []
        
        price_data = stock_data.get("price_data", {})
        current_price = price_data.get("current_price", 0)
        
        # Entry price actions
        if technical:
            support = technical.get("support_resistance", {}).get("nearest_support")
            resistance = technical.get("support_resistance", {}).get("nearest_resistance")
            
            if support and resistance and current_price:
                if current_price < support * 1.05:
                    actions.append(f"📈 ENTRY OPPORTUNITY: Price near support (${support:.2f})")
                elif current_price > resistance * 0.95:
                    actions.append(f"⚠️ CAUTION: Price near resistance (${resistance:.2f})")
                else:
                    ideal_entry = support + (resistance - support) * 0.2
                    actions.append(f"💡 IDEAL ENTRY: Consider buying near ${ideal_entry:.2f}")
        
        # RSI-based actions
        if technical:
            rsi = technical.get("indicators", {}).get("rsi", {}).get("value")
            if rsi:
                if rsi < 30:
                    actions.append("📊 RSI indicates oversold conditions - potential buying opportunity")
                elif rsi > 70:
                    actions.append("📊 RSI indicates overbought conditions - consider taking profits")
        
        # Fundamental actions
        if fundamental:
            upside = fundamental.get("valuation", {}).get("price_target_analysis", {}).get("upside_potential")
            if upside:
                if upside > 20:
                    actions.append(f"🎯 Analysts see {upside:.1f}% upside potential")
                elif upside < -10:
                    actions.append(f"⚠️ Trading {abs(upside):.1f}% above analyst targets")
        
        # Sentiment actions
        if sentiment:
            sent_label = sentiment.get("combined_sentiment", {}).get("label")
            confidence = sentiment.get("combined_sentiment", {}).get("confidence")
            if sent_label == "bullish" and confidence in ["high", "medium"]:
                actions.append("📰 Positive sentiment across news and social media")
            elif sent_label == "bearish" and confidence in ["high", "medium"]:
                actions.append("📰 Negative sentiment detected - monitor for developments")
        
        # AI-specific actions
        if ai_analysis and ai_analysis.get("entry_price_recommendation"):
            entry_rec = ai_analysis["entry_price_recommendation"]
            if entry_rec.get("ideal_entry"):
                actions.append(f"🤖 AI suggests ideal entry at ${entry_rec['ideal_entry']}")
        
        # Add stop-loss recommendation
        if technical:
            support = technical.get("support_resistance", {}).get("nearest_support")
            if support and current_price:
                stop_loss = support * 0.97  # 3% below support
                actions.append(f"🛡️ Suggested stop-loss: ${stop_loss:.2f} (3% below support)")
        
        return actions
    
    def print_report(self, report: Dict):
        """Print formatted report to console"""
        
        self.console.print()
        
        # Header
        company = report.get("company_info", {})
        header = f"[bold blue]{report['symbol']}[/] - {company.get('name', 'Unknown')}"
        self.console.print(Panel(header, title="Stock Analysis Report", box=box.DOUBLE))
        
        # Price Summary
        price = report.get("price_summary", {})
        if price.get("current_price"):
            price_text = f"Current: [bold green]${price['current_price']:.2f}[/]"
            if price.get("52_week_range", {}).get("low") and price.get("52_week_range", {}).get("high"):
                price_text += f"  |  52W Range: ${price['52_week_range']['low']:.2f} - ${price['52_week_range']['high']:.2f}"
            self.console.print(Panel(price_text, title="Price"))
        
        # Analysis Summary Table
        table = Table(title="Analysis Summary", box=box.ROUNDED)
        table.add_column("Category", style="cyan")
        table.add_column("Score", justify="center")
        table.add_column("Signal", justify="center")
        
        # Technical
        tech = report.get("technical_summary", {})
        if tech.get("signal"):
            score_color = "green" if tech.get("score", 0) > 0 else "red"
            table.add_row(
                "Technical",
                f"[{score_color}]{tech.get('score', 'N/A')}[/]",
                self._colorize_signal(tech.get("signal"))
            )
        
        # Fundamental
        fund = report.get("fundamental_summary", {})
        if fund.get("signal"):
            score_color = "green" if fund.get("score", 0) > 0 else "red"
            table.add_row(
                "Fundamental",
                f"[{score_color}]{fund.get('score', 'N/A')}[/]",
                self._colorize_signal(fund.get("signal"))
            )
        
        # Sentiment
        sent = report.get("sentiment_summary", {})
        if sent.get("signal"):
            score_color = "green" if sent.get("score", 0) > 0 else "red"
            table.add_row(
                "Sentiment",
                f"[{score_color}]{sent.get('score', 'N/A')}[/]",
                self._colorize_signal(sent.get("signal"))
            )
        
        self.console.print(table)
        
        # Valuation Assessment
        self._print_valuation_assessment(report)
        
        # Entry Price & Stop-Loss
        self._print_entry_stoploss(report)
        
        # Institutional Analyst Ratings
        self._print_institutional_ratings(report)
        
        # Overall Assessment
        overall = report.get("overall_assessment", {})
        if overall:
            rec_color = "green" if "BUY" in overall.get("recommendation", "") else (
                "red" if "SELL" in overall.get("recommendation", "") else "yellow"
            )
            
            assessment_text = f"""
[bold]Overall Score:[/] [{rec_color}]{overall.get('overall_score', 'N/A')}[/]/100
[bold]Recommendation:[/] [{rec_color}]{overall.get('recommendation', 'N/A')}[/]
[bold]Confidence:[/] {overall.get('confidence', 'N/A')}
[bold]Action:[/] {overall.get('suggested_action', 'N/A')}
"""
            self.console.print(Panel(assessment_text, title="[bold]Overall Assessment[/]"))
        
        # Key Levels
        tech = report.get("technical_summary", {})
        if tech.get("key_levels"):
            levels = tech["key_levels"]
            levels_text = f"""
Support: [green]${levels.get('support', 'N/A')}[/]
Resistance: [red]${levels.get('resistance', 'N/A')}[/]
"""
            self.console.print(Panel(levels_text, title="Key Price Levels"))
        
        # Price Targets by Timeframe
        self._print_price_targets(report)
        
        # Bull/Bear Case Analysis
        self._print_bull_bear_case(report)
        
        # Risk Factors
        self._print_risk_factors(report)
        
        # Action Items
        actions = report.get("action_items", [])
        if actions:
            actions_text = "\n".join(actions)
            self.console.print(Panel(actions_text, title="[bold yellow]Action Items[/]"))
        
        # AI Analysis
        ai = report.get("ai_recommendation", {})
        if ai and ai.get("executive_summary"):
            self.console.print(Panel(ai["executive_summary"], title="[bold magenta]AI Analysis[/]"))
        
        self.console.print()
    
    def _print_valuation_assessment(self, report: Dict):
        """Print valuation assessment (undervalued/overvalued/fairly valued)"""
        ai = report.get("ai_recommendation", {})
        valuation = ai.get("valuation_assessment", {})
        
        if not valuation or not valuation.get("status"):
            return
        
        status = valuation.get("status", "unknown")
        label = valuation.get("label", "Unknown")
        
        # Color based on valuation
        if "undervalued" in status.lower():
            color = "green"
            icon = "📈"
        elif "overvalued" in status.lower():
            color = "red"
            icon = "📉"
        else:
            color = "yellow"
            icon = "➡️"
        
        details = valuation.get("details", [])
        reasoning = valuation.get("reasoning", "")
        
        valuation_text = f"{icon} [bold {color}]{label}[/bold {color}]"
        
        if reasoning:
            valuation_text += f"\n\n{reasoning}"
        
        if details:
            valuation_text += "\n\n[dim]Key Metrics:[/dim]"
            for detail in details[:5]:
                valuation_text += f"\n• {detail}"
        
        self.console.print(Panel(valuation_text, title="[bold]💰 Valuation Assessment[/]"))
    
    def _print_entry_stoploss(self, report: Dict):
        """Print entry price and stop-loss recommendations"""
        ai = report.get("ai_recommendation", {})
        entry = ai.get("entry_price_recommendation", {})
        stop_loss = ai.get("stop_loss", {})
        
        current_price = report.get("price_summary", {}).get("current_price")
        
        if not entry and not stop_loss:
            return
        
        # Helper function to safely convert to float
        def to_float(val):
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        
        # Create a table for entry and stop-loss
        table = Table(title="🎯 Entry Price & Stop-Loss", box=box.ROUNDED)
        table.add_column("Type", style="cyan", width=15)
        table.add_column("Price", justify="right", width=12)
        table.add_column("Notes", width=40)
        
        # Entry prices
        ideal = to_float(entry.get("ideal_entry"))
        if ideal:
            pct_from_current = ((ideal - current_price) / current_price * 100) if current_price else 0
            table.add_row(
                "🟢 Ideal Entry",
                f"[bold green]${ideal:.2f}[/]",
                f"{pct_from_current:+.1f}% from current" if current_price else ""
            )
        
        range_low = to_float(entry.get("acceptable_range_low"))
        range_high = to_float(entry.get("acceptable_range_high"))
        if range_low and range_high:
            table.add_row(
                "📊 Buy Range",
                f"${range_low:.2f} - ${range_high:.2f}",
                entry.get("reasoning", "")[:40] if entry.get("reasoning") else ""
            )
        
        # Stop-loss prices
        rec_sl = to_float(stop_loss.get("recommended"))
        if rec_sl:
            risk_pct = ((current_price - rec_sl) / current_price * 100) if current_price else 0
            table.add_row(
                "🛑 Stop-Loss",
                f"[bold red]${rec_sl:.2f}[/]",
                f"-{risk_pct:.1f}% risk from current" if current_price else ""
            )
        
        tight_sl = to_float(stop_loss.get("tight"))
        if tight_sl:
            table.add_row(
                "   Tight SL",
                f"[red]${tight_sl:.2f}[/]",
                "[dim]For aggressive traders[/dim]"
            )
        
        wide_sl = to_float(stop_loss.get("wide"))
        if wide_sl:
            table.add_row(
                "   Wide SL",
                f"[red]${wide_sl:.2f}[/]",
                "[dim]For swing traders[/dim]"
            )
        
        # Show reasoning if available
        if stop_loss.get("reasoning"):
            table.add_row("", "", f"[dim]{stop_loss['reasoning'][:50]}[/dim]")
        
        self.console.print(table)
        
        # Current price context
        if current_price:
            self.console.print(f"[dim]Current Price: ${current_price:.2f}[/dim]\n")
    
    def _print_institutional_ratings(self, report: Dict):
        """Print institutional analyst ratings from major banks"""
        inst_ratings = report.get("institutional_ratings", {})
        
        if not inst_ratings:
            return
        
        # Get priority bank ratings
        priority_banks = inst_ratings.get("priority_bank_ratings", {})
        price_targets = inst_ratings.get("price_targets", {})
        average_rating = inst_ratings.get("average_rating", {})
        consensus = inst_ratings.get("consensus", {})
        
        # ===== PRIORITY BANKS TABLE (Zacks, JPMorgan, etc.) =====
        requested_banks = ["Zacks", "JPMorgan", "Deutsche Bank", "Bank of America", "Morgan Stanley", "Goldman Sachs", "Citigroup"]
        
        table = Table(title="🏦 Bank & Research Firm Ratings", box=box.ROUNDED)
        table.add_column("Bank/Firm", style="cyan", width=18)
        table.add_column("Rating", justify="center", width=14)
        table.add_column("Score", justify="center", width=8)
        table.add_column("Price Target", justify="right", width=14)
        
        for bank in requested_banks:
            if bank in priority_banks:
                r = priority_banks[bank]
                rating = r.get("rating", "N/A")
                score = r.get("rating_score", 0)
                pt = r.get("price_target")
                
                # Color rating
                if score >= 4:
                    rating_str = f"[bold green]{rating}[/]"
                    score_str = f"[green]{score}/5[/]"
                elif score <= 2:
                    rating_str = f"[bold red]{rating}[/]"
                    score_str = f"[red]{score}/5[/]"
                else:
                    rating_str = f"[yellow]{rating}[/]"
                    score_str = f"[yellow]{score}/5[/]"
                
                pt_str = f"${pt:.2f}" if pt else "-"
                table.add_row(bank, rating_str, score_str, pt_str)
            else:
                table.add_row(bank, "[dim]No data[/]", "[dim]-[/]", "[dim]-[/]")
        
        self.console.print(table)
        
        # ===== PRICE TARGETS SUMMARY =====
        if price_targets and price_targets.get("average"):
            current_price = report.get("price_summary", {}).get("current_price")
            avg_target = price_targets.get("average")
            high_target = price_targets.get("high")
            low_target = price_targets.get("low")
            target_count = price_targets.get("count", 0)
            
            # Calculate upside/downside
            upside = ((avg_target - current_price) / current_price * 100) if current_price and avg_target else 0
            upside_color = "green" if upside > 0 else "red"
            
            targets_text = f"""
[bold]Average Target:[/] [bold {upside_color}]${avg_target:.2f}[/] ({upside:+.1f}% from current)
[bold]High Target:[/]    [green]${high_target:.2f}[/]
[bold]Low Target:[/]     [red]${low_target:.2f}[/]
[dim]Based on {target_count} analyst price targets[/]
"""
            self.console.print(Panel(targets_text, title="[bold]📊 Analyst Price Targets[/]"))
        
        # ===== AVERAGE RATING =====
        if average_rating and average_rating.get("score"):
            avg_score = average_rating.get("score")
            avg_label = average_rating.get("label", "N/A")
            rating_count = average_rating.get("count", 0)
            
            # Color based on rating
            if avg_score >= 3.5:
                color = "green"
            elif avg_score <= 2.5:
                color = "red"
            else:
                color = "yellow"
            
            rating_text = f"[bold {color}]{avg_label}[/] (Score: {avg_score:.2f}/5.0 from {rating_count} analysts)"
            self.console.print(f"\n[bold]📈 Total Average Rating:[/] {rating_text}\n")
        
        # ===== CONSENSUS BREAKDOWN =====
        if consensus:
            consensus_rating = consensus.get("consensus_rating", "N/A")
            weighted_score = consensus.get("weighted_score", 0)
            
            # Color based on consensus
            if "Buy" in consensus_rating:
                color = "green"
            elif "Sell" in consensus_rating:
                color = "red"
            else:
                color = "yellow"
            
            consensus_text = f"""
[bold {color}]{consensus_rating}[/] (Weighted Score: {weighted_score:.2f}/5.0)

Ratings Breakdown:
  🟢 Buy: {consensus.get('buy_count', 0)}  |  🟡 Hold: {consensus.get('hold_count', 0)}  |  🔴 Sell: {consensus.get('sell_count', 0)}
  Total Analyst Ratings: {consensus.get('total_ratings', 0)}
"""
            self.console.print(Panel(consensus_text, title="[bold]Weighted Consensus (Banks weighted higher)[/]"))
        
        # AI summary of institutional views
        ai = report.get("ai_recommendation", {})
        inst_summary = ai.get("institutional_summary")
        if inst_summary:
            self.console.print(Panel(inst_summary, title="[dim]What Banks Are Saying[/dim]"))
    
    def _print_price_targets(self, report: Dict):
        """Print price targets for all timeframes"""
        ai = report.get("ai_recommendation", {})
        price_targets = ai.get("price_targets", {})
        current_timeframe = report.get("timeframe", {}).get("code", "short")
        
        if not price_targets:
            return
        
        # Check if we have any valid targets
        has_targets = any(
            price_targets.get(tf, {}).get("target") is not None 
            for tf in ["short_term", "medium_term", "long_term"]
        )
        
        if not has_targets:
            return
        
        # Create price targets table
        table = Table(title="🎯 Price Targets by Investment Horizon", box=box.ROUNDED)
        table.add_column("Timeframe", style="cyan", width=15)
        table.add_column("Target", justify="center", width=12)
        table.add_column("Bear Case", justify="center", width=12)
        table.add_column("Bull Case", justify="center", width=12)
        table.add_column("Confidence", justify="center", width=10)
        table.add_column("Notes", width=35)
        
        # Map internal keys to display info
        timeframe_map = {
            "short_term": {"code": "short", "icon": "📅", "label": "1-3 Months"},
            "medium_term": {"code": "medium", "icon": "📆", "label": "3-12 Months"},
            "long_term": {"code": "long", "icon": "📈", "label": "1-5 Years"}
        }
        
        current_price = report.get("price_summary", {}).get("current_price")
        
        for tf_key, tf_info in timeframe_map.items():
            target_data = price_targets.get(tf_key, {})
            
            if not target_data.get("target"):
                continue
            
            # Highlight the selected timeframe
            is_selected = current_timeframe in [tf_info["code"], tf_key.replace("_term", "")]
            style = "bold yellow" if is_selected else ""
            marker = " ⭐" if is_selected else ""
            
            # Format prices - safely convert to float
            def safe_float(val):
                if val is None:
                    return None
                try:
                    return float(str(val).replace('$', '').replace(',', ''))
                except (ValueError, TypeError):
                    return None
            
            target = safe_float(target_data.get("target"))
            low = safe_float(target_data.get("low"))
            high = safe_float(target_data.get("high"))
            confidence = target_data.get("confidence", "N/A")
            reasoning = target_data.get("reasoning", "")[:35] + "..." if len(target_data.get("reasoning", "")) > 35 else target_data.get("reasoning", "")
            
            # Calculate upside/downside from current price
            if current_price and target:
                pct_change = ((target - current_price) / current_price) * 100
                target_str = f"${target:.2f} ({pct_change:+.1f}%)"
            else:
                target_str = f"${target:.2f}" if target else "N/A"
            
            low_str = f"${low:.2f}" if low else "N/A"
            high_str = f"${high:.2f}" if high else "N/A"
            
            # Color confidence
            conf_color = "green" if confidence == "HIGH" else ("yellow" if confidence == "MEDIUM" else "red")
            conf_str = f"[{conf_color}]{confidence}[/{conf_color}]"
            
            timeframe_label = f"{tf_info['icon']} {tf_info['label']}{marker}"
            
            if is_selected:
                table.add_row(
                    f"[{style}]{timeframe_label}[/{style}]",
                    f"[{style}]{target_str}[/{style}]",
                    f"[red]{low_str}[/red]",
                    f"[green]{high_str}[/green]",
                    conf_str,
                    reasoning
                )
            else:
                table.add_row(
                    timeframe_label,
                    target_str,
                    f"[dim]{low_str}[/dim]",
                    f"[dim]{high_str}[/dim]",
                    conf_str,
                    f"[dim]{reasoning}[/dim]"
                )
        
        self.console.print(table)
        
        # Print current price context
        if current_price:
            self.console.print(f"\n[dim]Current Price: ${current_price:.2f}[/dim]")
    
    def _print_bull_bear_case(self, report: Dict):
        """Print bull case (strengths) and bear case (concerns) analysis"""
        ai = report.get("ai_recommendation", {})
        bull_case = ai.get("bull_case", [])
        bear_case = ai.get("bear_case", [])
        
        if not bull_case and not bear_case:
            return
        
        # Investment Thesis if available
        investment_thesis = ai.get("investment_thesis")
        if investment_thesis:
            self.console.print(Panel(
                f"[bold]{investment_thesis}[/bold]",
                title="[bold magenta]📋 Investment Thesis[/]"
            ))
        
        # Create side-by-side display for bull and bear cases
        from rich.columns import Columns
        
        bull_items = []
        bear_items = []
        
        # Bull Case - Strengths
        if bull_case:
            bull_text = "[bold green]🐂 BULL CASE - Key Strengths[/]\n\n"
            for i, item in enumerate(bull_case[:3], 1):
                if isinstance(item, dict):
                    title = item.get("title", f"Strength {i}")
                    detail = item.get("detail", "")
                    bull_text += f"[bold green]{i}. {title}[/]\n"
                    bull_text += f"   {detail}\n\n"
                else:
                    bull_text += f"[bold green]{i}.[/] {item}\n\n"
            bull_items.append(Panel(bull_text, border_style="green"))
        
        # Bear Case - Concerns
        if bear_case:
            bear_text = "[bold red]🐻 BEAR CASE - Key Concerns[/]\n\n"
            for i, item in enumerate(bear_case[:3], 1):
                if isinstance(item, dict):
                    title = item.get("title", f"Concern {i}")
                    detail = item.get("detail", "")
                    bear_text += f"[bold red]{i}. {title}[/]\n"
                    bear_text += f"   {detail}\n\n"
                else:
                    bear_text += f"[bold red]{i}.[/] {item}\n\n"
            bear_items.append(Panel(bear_text, border_style="red"))
        
        # Display side by side if both exist
        if bull_items and bear_items:
            self.console.print(Columns(bull_items + bear_items, equal=True, expand=True))
        elif bull_items:
            self.console.print(bull_items[0])
        elif bear_items:
            self.console.print(bear_items[0])
    
    def _print_risk_factors(self, report: Dict):
        """Print risk factors section with company-specific and market risks"""
        ai = report.get("ai_recommendation", {})
        risk_factors = ai.get("risk_factors", {})
        
        if not risk_factors:
            return
        
        company_risks = risk_factors.get("company_specific", [])
        market_risks = risk_factors.get("market_sector", [])
        overall_level = risk_factors.get("overall_level", "medium")
        
        if not company_risks and not market_risks:
            return
        
        # Risk level color
        level_colors = {
            "low": "green",
            "medium": "yellow",
            "high": "red"
        }
        level_color = level_colors.get(overall_level.lower(), "yellow")
        level_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(overall_level.lower(), "🟡")
        
        risk_text = f"[bold]Overall Risk Level:[/] [{level_color}]{level_icon} {overall_level.upper()}[/{level_color}]\n\n"
        
        # Company-Specific Risks
        if company_risks:
            risk_text += "[bold cyan]Company-Specific Risks:[/]\n"
            for risk in company_risks[:3]:
                risk_text += f"  ⚠️ {risk}\n"
            risk_text += "\n"
        
        # Market/Sector Risks
        if market_risks:
            risk_text += "[bold cyan]Market & Sector Risks:[/]\n"
            for risk in market_risks[:3]:
                risk_text += f"  🌐 {risk}\n"
        
        self.console.print(Panel(risk_text, title="[bold]⚠️ Risk Factors[/]"))
    
    def _colorize_signal(self, signal: str) -> str:
        """Add color to signal based on type"""
        if not signal:
            return "N/A"
        
        signal_upper = signal.upper()
        if "STRONG BUY" in signal_upper:
            return f"[bold green]{signal}[/]"
        elif "BUY" in signal_upper or "BULLISH" in signal_upper:
            return f"[green]{signal}[/]"
        elif "STRONG SELL" in signal_upper:
            return f"[bold red]{signal}[/]"
        elif "SELL" in signal_upper or "BEARISH" in signal_upper:
            return f"[red]{signal}[/]"
        else:
            return f"[yellow]{signal}[/]"
    
    def export_to_json(self, report: Dict, filepath: str):
        """Export report to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)
    
    def export_to_markdown(self, report: Dict) -> str:
        """Export report to markdown format"""
        md = []
        
        # Header
        company = report.get("company_info", {})
        md.append(f"# {report['symbol']} - {company.get('name', 'Unknown')}")
        md.append(f"*Generated: {report['generated_at']}*")
        md.append("")
        
        # Price Summary
        price = report.get("price_summary", {})
        if price.get("current_price"):
            md.append("## Price Summary")
            md.append(f"- **Current Price:** ${price['current_price']:.2f}")
            if price.get("52_week_range"):
                md.append(f"- **52-Week Range:** ${price['52_week_range'].get('low', 'N/A')} - ${price['52_week_range'].get('high', 'N/A')}")
            md.append("")
        
        # Overall Assessment
        overall = report.get("overall_assessment", {})
        if overall:
            md.append("## Overall Assessment")
            md.append(f"- **Score:** {overall.get('overall_score', 'N/A')}/100")
            md.append(f"- **Recommendation:** {overall.get('recommendation', 'N/A')}")
            md.append(f"- **Confidence:** {overall.get('confidence', 'N/A')}")
            md.append(f"- **Suggested Action:** {overall.get('suggested_action', 'N/A')}")
            md.append("")
        
        # Technical Summary
        tech = report.get("technical_summary", {})
        if tech.get("signal"):
            md.append("## Technical Analysis")
            md.append(f"- **Signal:** {tech.get('signal')}")
            md.append(f"- **Score:** {tech.get('score')}")
            md.append(f"- **Trend:** {tech.get('trend')}")
            levels = tech.get("key_levels", {})
            if levels:
                md.append(f"- **Support:** ${levels.get('support', 'N/A')}")
                md.append(f"- **Resistance:** ${levels.get('resistance', 'N/A')}")
            md.append("")
        
        # Fundamental Summary
        fund = report.get("fundamental_summary", {})
        if fund.get("signal"):
            md.append("## Fundamental Analysis")
            md.append(f"- **Signal:** {fund.get('signal')}")
            md.append(f"- **Score:** {fund.get('score')}")
            md.append(f"- **Valuation:** {fund.get('valuation_assessment')}")
            
            if fund.get("key_insights"):
                md.append("### Key Insights")
                for insight in fund["key_insights"]:
                    md.append(f"- {insight}")
            
            if fund.get("concerns"):
                md.append("### Concerns")
                for concern in fund["concerns"]:
                    md.append(f"- {concern}")
            md.append("")
        
        # Action Items
        actions = report.get("action_items", [])
        if actions:
            md.append("## Action Items")
            for action in actions:
                md.append(f"- {action}")
            md.append("")
        
        # Price Targets
        ai = report.get("ai_recommendation", {})
        price_targets = ai.get("price_targets", {})
        current_price = price.get("current_price") if price else None
        
        if price_targets:
            has_targets = any(
                price_targets.get(tf, {}).get("target") is not None 
                for tf in ["short_term", "medium_term", "long_term"]
            )
            
            if has_targets:
                md.append("## 🎯 Price Targets by Investment Horizon")
                md.append("")
                md.append("| Timeframe | Target | Bear Case | Bull Case | Confidence |")
                md.append("|-----------|--------|-----------|-----------|------------|")
                
                timeframe_map = {
                    "short_term": "1-3 Months",
                    "medium_term": "3-12 Months",
                    "long_term": "1-5 Years"
                }
                
                for tf_key, tf_label in timeframe_map.items():
                    target_data = price_targets.get(tf_key, {})
                    if target_data.get("target"):
                        target = target_data.get("target")
                        if current_price and target:
                            pct_change = ((target - current_price) / current_price) * 100
                            target_str = f"${target:.2f} ({pct_change:+.1f}%)"
                        else:
                            target_str = f"${target:.2f}" if target else "N/A"
                        
                        low_str = f"${target_data.get('low'):.2f}" if target_data.get('low') else "N/A"
                        high_str = f"${target_data.get('high'):.2f}" if target_data.get('high') else "N/A"
                        conf = target_data.get("confidence", "N/A")
                        
                        md.append(f"| {tf_label} | {target_str} | {low_str} | {high_str} | {conf} |")
                
                md.append("")
        
        # Investment Thesis
        if ai.get("investment_thesis"):
            md.append("## 📋 Investment Thesis")
            md.append(ai["investment_thesis"])
            md.append("")
        
        # Bull/Bear Case
        bull_case = ai.get("bull_case", [])
        bear_case = ai.get("bear_case", [])
        
        if bull_case:
            md.append("## 🐂 Bull Case - Key Strengths")
            for i, item in enumerate(bull_case[:3], 1):
                if isinstance(item, dict):
                    title = item.get("title", f"Strength {i}")
                    detail = item.get("detail", "")
                    md.append(f"### {i}. {title}")
                    md.append(detail)
                else:
                    md.append(f"{i}. {item}")
                md.append("")
        
        if bear_case:
            md.append("## 🐻 Bear Case - Key Concerns")
            for i, item in enumerate(bear_case[:3], 1):
                if isinstance(item, dict):
                    title = item.get("title", f"Concern {i}")
                    detail = item.get("detail", "")
                    md.append(f"### {i}. {title}")
                    md.append(detail)
                else:
                    md.append(f"{i}. {item}")
                md.append("")
        
        # Risk Factors
        risk_factors = ai.get("risk_factors", {})
        if risk_factors:
            company_risks = risk_factors.get("company_specific", [])
            market_risks = risk_factors.get("market_sector", [])
            overall_level = risk_factors.get("overall_level", "medium")
            
            if company_risks or market_risks:
                md.append("## ⚠️ Risk Factors")
                md.append(f"**Overall Risk Level:** {overall_level.upper()}")
                md.append("")
                
                if company_risks:
                    md.append("### Company-Specific Risks")
                    for risk in company_risks:
                        md.append(f"- {risk}")
                    md.append("")
                
                if market_risks:
                    md.append("### Market & Sector Risks")
                    for risk in market_risks:
                        md.append(f"- {risk}")
                    md.append("")
        
        # AI Analysis / Executive Summary
        if ai and ai.get("executive_summary"):
            md.append("## AI Analysis")
            md.append(ai["executive_summary"])
            md.append("")
        
        # Disclaimer
        md.append("---")
        md.append("")
        md.append("*This report is for informational purposes only and should not be considered as personalized investment advice. Past performance does not guarantee future results. Please consult with a qualified financial advisor before making investment decisions.*")
        md.append("")
        
        return "\n".join(md)
