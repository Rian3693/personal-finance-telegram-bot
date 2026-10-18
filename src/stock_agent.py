"""
Stock Analysis Agent - Main orchestrator for comprehensive stock analysis
"""
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel

from collectors import StockDataCollector, NewsCollector, SocialSentimentCollector, AnalystRatingsCollector
from analyzers import TechnicalAnalyzer, FundamentalAnalyzer, SentimentAnalyzer
from ai_advisor import AIAdvisor
from report_generator import ReportGenerator
from debug_export import DebugExporter
from config import SCORING_WEIGHTS, TIMEFRAME_PROFILES, DEFAULT_TIMEFRAME, get_timeframe_config


class StockAgent:
    """
    Main stock analysis agent that orchestrates data collection,
    analysis, and report generation for investment decision support.
    """
    
    def __init__(self):
        self.console = Console()
        
        # Initialize collectors
        self.stock_collector = StockDataCollector()
        self.news_collector = NewsCollector()
        self.social_collector = SocialSentimentCollector()
        self.analyst_collector = AnalystRatingsCollector()
        
        # Initialize analyzers
        self.technical_analyzer = TechnicalAnalyzer()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.sentiment_analyzer = SentimentAnalyzer()
        
        # Initialize AI advisor and report generator
        self.ai_advisor = AIAdvisor()
        self.report_generator = ReportGenerator()
        self.debug_exporter = DebugExporter()
        
        # Store results
        self.results = {}
        self.raw_data = {}  # Store raw data for debug export
    
    def analyze_stock(self, symbol: str, verbose: bool = True, timeframe: str = DEFAULT_TIMEFRAME) -> Dict[str, Any]:
        """
        Perform comprehensive analysis on a single stock
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
            verbose: Whether to print progress updates
            timeframe: Analysis timeframe ('swing', 'short', 'medium', 'long')
        
        Returns:
            Complete analysis report
        """
        symbol = symbol.upper().strip()
        tf_config = get_timeframe_config(timeframe)
        
        if verbose:
            self.console.print(f"\n[bold blue]🔍 Analyzing {symbol}...[/]")
            self.console.print(f"[dim]Timeframe: {tf_config['name']} ({tf_config['description']})[/]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            transient=True,
            console=self.console if verbose else None
        ) as progress:
            
            # Step 1: Collect stock data
            task1 = progress.add_task("[cyan]Collecting stock data...", total=1)
            stock_data = self.stock_collector.get_stock_data(symbol)
            progress.update(task1, completed=1)
            
            if stock_data.get("error"):
                self.console.print(f"[red]Error collecting stock data: {stock_data['error']}[/]")
                return {"error": stock_data["error"], "symbol": symbol}
            
            company_name = stock_data.get("company_info", {}).get("name")
            
            # Step 2: Collect news
            task2 = progress.add_task("[cyan]Collecting news articles...", total=1)
            news_data = self.news_collector.get_stock_news(symbol, company_name)
            progress.update(task2, completed=1)
            
            # Step 3: Collect social sentiment
            task3 = progress.add_task("[cyan]Collecting social sentiment...", total=1)
            social_data = self.social_collector.get_social_sentiment(symbol)
            progress.update(task3, completed=1)
            
            # Step 3b: Collect institutional analyst ratings
            task3b = progress.add_task("[cyan]Collecting analyst ratings (Banks & Research)...", total=1)
            reddit_sentiment = social_data.get("reddit", {}) if social_data else None
            analyst_ratings = self.analyst_collector.get_institutional_sentiment(symbol, reddit_sentiment)
            progress.update(task3b, completed=1)
            
            # Step 3c: AI News Analysis
            task3c = progress.add_task("[cyan]AI analyzing news impact...", total=1)
            current_price = stock_data.get("price_data", {}).get("current_price")
            ai_news_analysis = self.ai_advisor.analyze_news_impact(
                symbol, 
                news_data.get("articles", []),
                current_price
            )
            progress.update(task3c, completed=1)
            
            # Step 4: Technical analysis
            task4 = progress.add_task("[cyan]Performing technical analysis...", total=1)
            technical_analysis = self.technical_analyzer.analyze(
                stock_data.get("price_data", {}),
                timeframe=timeframe
            )
            progress.update(task4, completed=1)
            
            # Step 5: Fundamental analysis
            task5 = progress.add_task("[cyan]Performing fundamental analysis...", total=1)
            fundamental_analysis = self.fundamental_analyzer.analyze(stock_data, timeframe=timeframe)
            progress.update(task5, completed=1)
            
            # Step 6: Sentiment analysis
            task6 = progress.add_task("[cyan]Analyzing sentiment...", total=1)
            sentiment_analysis = self.sentiment_analyzer.analyze(news_data, social_data)
            progress.update(task6, completed=1)
            
            # Step 7: AI-powered analysis
            task7 = progress.add_task("[cyan]Generating AI insights...", total=1)
            ai_analysis = self.ai_advisor.generate_analysis(
                stock_data, technical_analysis, fundamental_analysis,
                sentiment_analysis, symbol, timeframe=timeframe,
                analyst_ratings=analyst_ratings
            )
            progress.update(task7, completed=1)
            
            # Step 8: Generate report
            task8 = progress.add_task("[cyan]Generating report...", total=1)
            report = self.report_generator.generate_report(
                symbol, stock_data, technical_analysis,
                fundamental_analysis, sentiment_analysis, ai_analysis,
                timeframe=timeframe, analyst_ratings=analyst_ratings
            )
            progress.update(task8, completed=1)
        
        # Store result and raw data
        self.results[symbol] = report
        self.raw_data[symbol] = {
            "stock_data": stock_data,
            "news_data": news_data,
            "ai_news_analysis": ai_news_analysis,
            "social_data": social_data,
            "analyst_ratings": analyst_ratings,
            "technical": technical_analysis,
            "fundamental": fundamental_analysis,
            "sentiment": sentiment_analysis,
            "ai_analysis": ai_analysis,
            "overall_assessment": report.get("overall_assessment", {})
        }
        
        # Always export debug data to TXT file
        try:
            debug_filepath = self.debug_exporter.export_full_analysis(symbol, self.raw_data[symbol])
            self.console.print(f"\n[bold cyan]📁 Debug data exported to:[/] {debug_filepath}")
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not export debug data: {e}[/]")
        
        # Print report if verbose
        if verbose:
            self.report_generator.print_report(report)
        
        return report
    
    def analyze_multiple(self, symbols: List[str], verbose: bool = True, timeframe: str = DEFAULT_TIMEFRAME) -> Dict[str, Any]:
        """
        Analyze multiple stocks and generate comparative report
        
        Args:
            symbols: List of stock ticker symbols
            verbose: Whether to print progress updates
            timeframe: Analysis timeframe ('swing', 'short', 'medium', 'long')
        
        Returns:
            Dictionary containing all analysis reports and comparison
        """
        results = {}
        tf_config = get_timeframe_config(timeframe)
        
        if verbose:
            self.console.print(Panel(
                f"[bold]Analyzing {len(symbols)} stocks:[/] {', '.join(symbols)}\n"
                f"[dim]Timeframe: {tf_config['name']} ({tf_config['description']})[/]",
                title="Stock Agent"
            ))
        
        for i, symbol in enumerate(symbols, 1):
            if verbose:
                self.console.print(f"\n[bold]({i}/{len(symbols)}) Processing {symbol}[/]")
            
            try:
                report = self.analyze_stock(symbol, verbose=verbose, timeframe=timeframe)
                results[symbol] = report
            except Exception as e:
                if verbose:
                    self.console.print(f"[red]Error analyzing {symbol}: {str(e)}[/]")
                results[symbol] = {"error": str(e), "symbol": symbol}
        
        # Generate comparison
        comparison = self._compare_stocks(results)
        
        if verbose:
            self._print_comparison(comparison)
        
        return {
            "individual_reports": results,
            "comparison": comparison,
            "generated_at": datetime.now().isoformat()
        }
    
    def _compare_stocks(self, results: Dict[str, Dict]) -> Dict[str, Any]:
        """Compare multiple stock analyses"""
        comparison = {
            "rankings": [],
            "best_entry": None,
            "strongest_fundamentals": None,
            "best_sentiment": None,
            "summary": ""
        }
        
        valid_results = {
            k: v for k, v in results.items() 
            if not v.get("error") and v.get("overall_assessment")
        }
        
        if not valid_results:
            comparison["summary"] = "No valid results to compare"
            return comparison
        
        # Rank by overall score
        rankings = []
        for symbol, report in valid_results.items():
            overall = report.get("overall_assessment", {})
            rankings.append({
                "symbol": symbol,
                "overall_score": overall.get("overall_score", 0),
                "recommendation": overall.get("recommendation", "N/A"),
                "technical_score": overall.get("component_scores", {}).get("technical", 0),
                "fundamental_score": overall.get("component_scores", {}).get("fundamental", 0),
                "sentiment_score": overall.get("component_scores", {}).get("sentiment", 0)
            })
        
        # Sort by overall score
        rankings.sort(key=lambda x: x["overall_score"], reverse=True)
        comparison["rankings"] = rankings
        
        if rankings:
            # Best overall
            comparison["best_overall"] = rankings[0]["symbol"]
            
            # Best entry (highest technical score with buy signal)
            tech_rankings = sorted(rankings, key=lambda x: x["technical_score"], reverse=True)
            comparison["best_entry"] = tech_rankings[0]["symbol"]
            
            # Strongest fundamentals
            fund_rankings = sorted(rankings, key=lambda x: x["fundamental_score"], reverse=True)
            comparison["strongest_fundamentals"] = fund_rankings[0]["symbol"]
            
            # Best sentiment
            sent_rankings = sorted(rankings, key=lambda x: x["sentiment_score"], reverse=True)
            comparison["best_sentiment"] = sent_rankings[0]["symbol"]
            
            # Summary
            top = rankings[0]
            comparison["summary"] = (
                f"Based on comprehensive analysis, {top['symbol']} ranks highest "
                f"with an overall score of {top['overall_score']:.1f}/100 "
                f"({top['recommendation']}). "
                f"Best entry opportunity: {comparison['best_entry']}. "
                f"Strongest fundamentals: {comparison['strongest_fundamentals']}."
            )
        
        return comparison
    
    def _print_comparison(self, comparison: Dict):
        """Print comparison results"""
        from rich.table import Table
        from rich import box
        
        self.console.print("\n")
        self.console.print(Panel("[bold]Stock Comparison Results[/]", box=box.DOUBLE))
        
        # Rankings table
        table = Table(title="Overall Rankings", box=box.ROUNDED)
        table.add_column("Rank", justify="center", style="cyan")
        table.add_column("Symbol", style="bold")
        table.add_column("Score", justify="center")
        table.add_column("Recommendation", justify="center")
        table.add_column("Technical", justify="center")
        table.add_column("Fundamental", justify="center")
        table.add_column("Sentiment", justify="center")
        
        for i, stock in enumerate(comparison.get("rankings", []), 1):
            rec_color = "green" if "BUY" in stock["recommendation"] else (
                "red" if "SELL" in stock["recommendation"] else "yellow"
            )
            
            table.add_row(
                str(i),
                stock["symbol"],
                f"[bold]{stock['overall_score']:.1f}[/]",
                f"[{rec_color}]{stock['recommendation']}[/]",
                f"{stock['technical_score']:.0f}",
                f"{stock['fundamental_score']:.0f}",
                f"{stock['sentiment_score']:.0f}"
            )
        
        self.console.print(table)
        
        # Summary
        if comparison.get("summary"):
            self.console.print(Panel(comparison["summary"], title="[bold]Summary[/]"))
    
    def get_entry_recommendation(self, symbol: str) -> Dict[str, Any]:
        """
        Get specific entry price recommendation for a stock
        """
        if symbol not in self.results:
            # Need to analyze first
            self.analyze_stock(symbol, verbose=False)
        
        report = self.results.get(symbol, {})
        
        if not report or report.get("error"):
            return {"error": "Unable to generate entry recommendation"}
        
        price = report.get("price_summary", {}).get("current_price", 0)
        tech = report.get("technical_summary", {})
        levels = tech.get("key_levels", {})
        
        support = levels.get("support", price * 0.95)
        resistance = levels.get("resistance", price * 1.1)
        
        # Use AI advisor's entry strategy
        entry_strategy = self.ai_advisor.generate_entry_strategy(
            current_price=price,
            support=support,
            resistance=resistance,
            volatility=0.02  # Default volatility
        )
        
        return {
            "symbol": symbol,
            "current_price": price,
            "entry_strategy": entry_strategy,
            "action_items": report.get("action_items", [])
        }
    
    def export_results(self, filepath: str, format: str = "json"):
        """
        Export all analysis results to file
        
        Args:
            filepath: Output file path
            format: 'json' or 'markdown'
        """
        if format == "json":
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, default=str, ensure_ascii=False)
            self.console.print(f"[green]Results exported to {filepath}[/]")
        
        elif format == "markdown":
            md_content = []
            for symbol, report in self.results.items():
                md_content.append(self.report_generator.export_to_markdown(report))
                md_content.append("\n---\n")
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(md_content))
            self.console.print(f"[green]Results exported to {filepath}[/]")
    
    def export_debug(self, symbol: str, show_summary: bool = True) -> str:
        """
        Export full debug data for a stock to TXT file and show summary
        
        Args:
            symbol: Stock ticker symbol
            show_summary: Whether to print summary to console
            
        Returns:
            Path to the debug file
        """
        symbol = symbol.upper()
        
        if symbol not in self.raw_data:
            self.console.print(f"[red]No data available for {symbol}. Run analysis first.[/]")
            return ""
        
        data = self.raw_data[symbol]
        
        # Export to TXT file
        filepath = self.debug_exporter.export_full_analysis(symbol, data)
        self.console.print(f"\n[green]✓ Full debug data exported to: {filepath}[/]")
        
        # Show summary in console
        if show_summary:
            self.debug_exporter.print_summary(symbol, data)
        
        return filepath
    
    def analyze_with_debug(self, symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> Dict[str, Any]:
        """
        Analyze a stock and automatically export debug data
        
        Args:
            symbol: Stock ticker symbol
            timeframe: Analysis timeframe
            
        Returns:
            Analysis report
        """
        # Run analysis
        report = self.analyze_stock(symbol, verbose=True, timeframe=timeframe)
        
        # Export debug data
        if symbol.upper() in self.raw_data:
            self.export_debug(symbol.upper(), show_summary=True)
        
        return report


def main():
    """Main entry point for command-line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Stock Analysis Agent - AI-powered stock analysis tool"
    )
    parser.add_argument(
        "symbols",
        nargs="+",
        help="Stock symbols to analyze (e.g., AAPL MSFT GOOGL)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path for results"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress verbose output"
    )
    
    args = parser.parse_args()
    
    # Create agent and run analysis
    agent = StockAgent()
    
    if len(args.symbols) == 1:
        agent.analyze_stock(args.symbols[0], verbose=not args.quiet)
    else:
        agent.analyze_multiple(args.symbols, verbose=not args.quiet)
    
    # Export if output specified
    if args.output:
        agent.export_results(args.output, args.format)


if __name__ == "__main__":
    main()
