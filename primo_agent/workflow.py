"""
PrimoAgent Workflow - Orchestrates the multi-agent analysis pipeline

Data Collection Agent → Technical Analysis Agent → News Intelligence Agent → Portfolio Manager Agent
"""
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box

from .agents import (
    DataCollectionAgent,
    TechnicalAnalysisAgent,
    NewsIntelligenceAgent,
    PortfolioManagerAgent
)


async def run_primo_analysis(
    symbols: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    console: Console = None
) -> Dict[str, Any]:
    """
    Run full PrimoAgent multi-agent analysis workflow.
    
    Pipeline:
    1. Data Collection Agent - Collects market data, company info, news
    2. Technical Analysis Agent - Calculates SMA, RSI, MACD, BB, ADX, CCI
    3. News Intelligence Agent - Analyzes news with 7 NLP features
    4. Portfolio Manager Agent - Generates BUY/SELL/HOLD signals
    
    Args:
        symbols: List of stock symbols to analyze
        start_date: Start date for analysis (YYYY-MM-DD)
        end_date: End date for analysis (YYYY-MM-DD)
        openai_api_key: Optional OpenAI API key for LLM analysis
        console: Rich console for output
        
    Returns:
        Dict with analysis results for each symbol
    """
    if console is None:
        console = Console()
    
    # Initialize agents
    data_agent = DataCollectionAgent()
    tech_agent = TechnicalAnalysisAgent()
    news_agent = NewsIntelligenceAgent(openai_api_key)
    portfolio_agent = PortfolioManagerAgent(openai_api_key)
    
    results = {}
    analysis_date = end_date or datetime.now().strftime("%Y-%m-%d")
    
    console.print(Panel.fit(
        f"[bold cyan]🤖 PrimoAgent Multi-Agent Analysis[/]\n"
        f"[dim]Analyzing {len(symbols)} symbol(s) for {analysis_date}[/]",
        border_style="cyan"
    ))
    
    for symbol in symbols:
        symbol = symbol.upper()
        console.print(f"\n[bold yellow]━━━ Analyzing {symbol} ━━━[/]")
        
        try:
            # Stage 1: Data Collection
            with console.status(f"[cyan]📊 Agent 1: Collecting data for {symbol}...[/]"):
                data_result = await data_agent.collect(symbol, analysis_date)
            
            if not data_result.get('success'):
                console.print(f"[red]✗ Data collection failed: {data_result.get('error')}[/]")
                results[symbol] = {'success': False, 'error': data_result.get('error')}
                continue
            
            console.print(f"[green]✓[/] Data Collection: ${data_result['market_data']['current_price']:.2f}")
            
            # Stage 2: Technical Analysis
            with console.status(f"[cyan]📈 Agent 2: Running technical analysis...[/]"):
                tech_result = await tech_agent.analyze(data_result['market_data'])
            
            if not tech_result.get('success'):
                console.print(f"[red]✗ Technical analysis failed: {tech_result.get('error')}[/]")
                results[symbol] = {'success': False, 'error': tech_result.get('error')}
                continue
            
            # Display technical summary
            indicators = tech_result.get('indicators', {})
            rsi = indicators.get('RSI')
            macd = indicators.get('MACD', {})
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            macd_hist = macd.get('histogram') if macd else None
            macd_str = f"{macd_hist:.4f}" if macd_hist is not None else "N/A"
            console.print(f"[green]✓[/] Technical Analysis: RSI={rsi_str}, MACD={macd_str}")
            
            # Stage 3: News Intelligence
            with console.status(f"[cyan]📰 Agent 3: Analyzing news sentiment...[/]"):
                news_result = await news_agent.analyze(
                    data_result.get('news_data', {}),
                    data_result.get('company_info', {})
                )
            
            nlp = news_result.get('nlp_features', {})
            console.print(f"[green]✓[/] News Intelligence: Sentiment={nlp.get('sentiment', 0):.1f}, Impact={nlp.get('price_impact_potential', 0):.1f}")
            
            # Stage 4: Portfolio Manager
            with console.status(f"[cyan]💼 Agent 4: Generating trading signal...[/]"):
                portfolio_result = await portfolio_agent.analyze(
                    symbol=symbol,
                    technical_data=tech_result,
                    news_data=news_result,
                    company_info=data_result.get('company_info'),
                    basic_financials=data_result.get('basic_financials')
                )
            
            if not portfolio_result.get('success'):
                console.print(f"[red]✗ Portfolio analysis failed: {portfolio_result.get('error')}[/]")
                results[symbol] = {'success': False, 'error': portfolio_result.get('error')}
                continue
            
            # Display result
            signal = portfolio_result['trading_signal']
            confidence = portfolio_result['confidence_level']
            position = portfolio_result['position_size']
            
            signal_color = 'green' if signal == 'BUY' else 'red' if signal == 'SELL' else 'yellow'
            console.print(f"[{signal_color}]✓ Signal: {signal}[/] | Confidence: {confidence:.0%} | Position: {position}%")
            
            # Compile full result
            results[symbol] = {
                'success': True,
                'symbol': symbol,
                'analysis_date': analysis_date,
                'current_price': data_result['market_data']['current_price'],
                'company_info': data_result.get('company_info', {}),
                'data_collection': data_result,
                'technical_analysis': tech_result,
                'news_intelligence': news_result,
                'portfolio_decision': portfolio_result
            }
            
        except Exception as e:
            console.print(f"[red]✗ Error analyzing {symbol}: {str(e)}[/]")
            results[symbol] = {'success': False, 'error': str(e)}
    
    # Print summary
    _print_summary(results, console)
    
    return results


def _print_summary(results: Dict[str, Any], console: Console):
    """Print summary table of all analysis results"""
    console.print("\n")
    
    table = Table(
        title="🤖 PrimoAgent Analysis Summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
    )
    
    table.add_column("Symbol", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Signal", justify="center")
    table.add_column("Confidence", justify="center")
    table.add_column("Position", justify="center")
    table.add_column("Sentiment", justify="center")
    table.add_column("RSI", justify="center")
    
    for symbol, data in results.items():
        if not data.get('success'):
            table.add_row(
                symbol, "Error", "-", "-", "-", "-", "-",
                style="dim red"
            )
            continue
        
        price = f"${data['current_price']:.2f}"
        
        signal = data['portfolio_decision']['trading_signal']
        signal_style = "green" if signal == "BUY" else "red" if signal == "SELL" else "yellow"
        signal_display = f"[{signal_style}]{signal}[/]"
        
        confidence = f"{data['portfolio_decision']['confidence_level']:.0%}"
        position = f"{data['portfolio_decision']['position_size']}%"
        
        sentiment = data['news_intelligence'].get('nlp_features', {}).get('sentiment', 0)
        sentiment_display = f"{sentiment:+.1f}"
        
        rsi = data['technical_analysis'].get('indicators', {}).get('RSI')
        rsi_display = f"{rsi:.1f}" if rsi else "N/A"
        
        table.add_row(
            symbol, price, signal_display, confidence, position, sentiment_display, rsi_display
        )
    
    console.print(table)
    
    # Print recommendations
    buy_signals = [s for s, d in results.items() if d.get('success') and d['portfolio_decision']['trading_signal'] == 'BUY']
    sell_signals = [s for s, d in results.items() if d.get('success') and d['portfolio_decision']['trading_signal'] == 'SELL']
    
    if buy_signals:
        console.print(f"\n[green]🟢 BUY Signals:[/] {', '.join(buy_signals)}")
    if sell_signals:
        console.print(f"[red]🔴 SELL Signals:[/] {', '.join(sell_signals)}")


def run_primo_analysis_sync(
    symbols: List[str],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    console: Console = None
) -> Dict[str, Any]:
    """Synchronous wrapper for run_primo_analysis"""
    return asyncio.run(run_primo_analysis(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        openai_api_key=openai_api_key,
        console=console
    ))


def print_detailed_report(result: Dict[str, Any], console: Console = None):
    """Print detailed report for a single stock analysis"""
    if console is None:
        console = Console()
    
    if not result.get('success'):
        console.print(f"[red]Analysis failed: {result.get('error')}[/]")
        return
    
    symbol = result['symbol']
    price = result['current_price']
    company = result.get('company_info', {})
    tech = result.get('technical_analysis', {})
    news = result.get('news_intelligence', {})
    decision = result.get('portfolio_decision', {})
    
    console.print(Panel.fit(
        f"[bold]{symbol}[/] - {company.get('name', symbol)}\n"
        f"[dim]{company.get('industry', 'Unknown')} | {company.get('sector', 'Unknown')}[/]",
        title="📊 Detailed Analysis Report",
        border_style="cyan"
    ))
    
    # Price & Signal
    signal = decision.get('trading_signal', 'N/A')
    signal_color = 'green' if signal == 'BUY' else 'red' if signal == 'SELL' else 'yellow'
    
    console.print(f"\n[bold]Current Price:[/] ${price:.2f}")
    console.print(f"[bold]Signal:[/] [{signal_color}]{signal}[/]")
    console.print(f"[bold]Confidence:[/] {decision.get('confidence_level', 0):.0%}")
    console.print(f"[bold]Position Size:[/] {decision.get('position_size', 0)}%")
    console.print(f"[bold]Reasoning:[/] {decision.get('reasoning', 'N/A')}")
    
    # Technical Indicators
    indicators = tech.get('indicators', {})
    interpretations = tech.get('interpretations', {})
    
    console.print("\n[bold cyan]Technical Indicators:[/]")
    for key, interp in interpretations.items():
        console.print(f"  • {interp}")
    
    # News Intelligence
    nlp = news.get('nlp_features', {})
    console.print("\n[bold cyan]News Intelligence (NLP Features):[/]")
    for feature, value in nlp.items():
        bar = "█" * int((value + 2) * 2.5)  # Scale -2 to +2 → 0 to 10
        color = 'green' if value > 0 else 'red' if value < 0 else 'white'
        console.print(f"  • {feature}: [{color}]{value:+.1f}[/] {bar}")
    
    console.print(f"\n[dim]{news.get('summary', '')}[/]")
