"""
Interactive CLI for Stock Agent
"""
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich import box
from stock_agent import StockAgent
from watchlist import WatchlistManager
from config import TIMEFRAME_PROFILES, DEFAULT_TIMEFRAME


def select_timeframe(console: Console) -> str:
    """Display timeframe selection menu and return selected timeframe code"""
    console.print("\n[bold cyan]📊 Select Analysis Timeframe:[/]\n")
    
    table = Table(show_header=True, box=box.ROUNDED, title="Investment Horizons")
    table.add_column("#", style="cyan", width=3, justify="center")
    table.add_column("Timeframe", style="bold")
    table.add_column("Horizon")
    table.add_column("Best For")
    
    timeframe_options = []
    for i, (code, config) in enumerate(TIMEFRAME_PROFILES.items(), 1):
        table.add_row(
            str(i),
            config['name'],
            config['horizon'],
            config['description']
        )
        timeframe_options.append(code)
    
    console.print(table)
    
    choice = Prompt.ask(
        "\n[bold]Select timeframe[/]",
        choices=[str(i) for i in range(1, len(timeframe_options) + 1)],
        default="2"  # Default to short-term
    )
    
    selected = timeframe_options[int(choice) - 1]
    console.print(f"\n[green]✓ Selected: {TIMEFRAME_PROFILES[selected]['name']} ({TIMEFRAME_PROFILES[selected]['horizon']})[/]")
    return selected


def display_menu(console: Console):
    """Display main menu"""
    console.print("\n")
    console.print(Panel.fit(
        "[bold cyan]Stock Analysis Agent[/]\n"
        "[dim]AI-powered stock research and analysis[/]",
        border_style="blue"
    ))
    
    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Option", style="cyan", width=4)
    table.add_column("Description")
    
    table.add_row("1", "Analyze a single stock")
    table.add_row("2", "Analyze multiple stocks")
    table.add_row("3", "Get entry price recommendation")
    table.add_row("4", "View previous results")
    table.add_row("5", "Export results")
    table.add_row("", "")
    table.add_row("w", "[bold]📋 Manage Watchlists[/]")
    table.add_row("a", "[bold]🔄 Analyze All Stocks in Current Watchlist[/]")
    table.add_row("s", "[bold]🔄 Switch Watchlist[/]")
    table.add_row("", "")
    table.add_row("p", "[bold]🤖 PrimoAgent Multi-Agent Analysis[/]")
    table.add_row("", "")
    table.add_row("n", "[bold]📰 News Monitor (24/7 Alerts)[/]")
    table.add_row("r", "[bold]📊 Weekly News Summary Report[/]")
    table.add_row("", "")
    table.add_row("q", "Quit")
    
    console.print(table)


def run_interactive():
    """Run interactive CLI"""
    console = Console()
    agent = StockAgent()
    watchlist = WatchlistManager()
    
    console.print("\n[bold green]🚀 Welcome to Stock Analysis Agent![/]")
    console.print(f"[dim]Active Watchlist: {watchlist.get_current_watchlist_name()}[/]")
    console.print("[dim]Your AI-powered assistant for stock research[/]\n")
    
    while True:
        # Show current watchlist name in menu
        console.print(f"\n[bold cyan]📋 Current Watchlist:[/] {watchlist.get_current_watchlist_name()}")
        display_menu(console)
        
        choice = Prompt.ask(
            "\n[bold]Select an option[/]",
            choices=["1", "2", "3", "4", "5", "w", "a", "s", "p", "n", "r", "q"],
            default="1"
        )
        
        if choice == "q":
            console.print("\n[bold blue]Thanks for using Stock Agent! Goodbye! 👋[/]\n")
            break
        
        elif choice == "p":
            # PrimoAgent multi-agent analysis
            run_primo_agent_menu(console)
        
        elif choice == "n":
            # News monitor
            news_monitor_menu(console)
        
        elif choice == "r":
            # Weekly news summary report
            run_weekly_news_summary(console)
        
        elif choice == "1":
            # Single stock analysis
            symbol = Prompt.ask("\n[bold]Enter stock symbol[/]").upper().strip()
            if symbol:
                # Ask for timeframe
                timeframe = select_timeframe(console)
                
                report = agent.analyze_stock(symbol, timeframe=timeframe)
                
                # Update watchlist if stock is in it
                if symbol in watchlist.get_stocks():
                    overall = report.get("overall_assessment", {})
                    watchlist.update_last_analysis(symbol, {
                        "overall_score": overall.get("overall_score"),
                        "recommendation": overall.get("recommendation"),
                        "price": report.get("price_summary", {}).get("current_price")
                    })
        
        elif choice == "2":
            # Multiple stocks
            symbols_input = Prompt.ask(
                "\n[bold]Enter stock symbols[/] (comma-separated, e.g., AAPL,MSFT,GOOGL)"
            )
            symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
            if symbols:
                # Ask for timeframe
                timeframe = select_timeframe(console)
                
                agent.analyze_multiple(symbols, timeframe=timeframe)
        
        elif choice == "3":
            # Entry recommendation
            symbol = Prompt.ask("\n[bold]Enter stock symbol[/]").upper().strip()
            if symbol:
                entry = agent.get_entry_recommendation(symbol)
                if entry.get("error"):
                    console.print(f"[red]{entry['error']}[/]")
                else:
                    console.print(Panel(
                        f"""
[bold]Entry Strategy for {entry['symbol']}[/]

Current Price: [bold]${entry['current_price']:.2f}[/]
Ideal Entry: [green]${entry['entry_strategy']['ideal_entry']:.2f}[/]
Acceptable Range: ${entry['entry_strategy']['acceptable_range']['low']:.2f} - ${entry['entry_strategy']['acceptable_range']['high']:.2f}
Support: ${entry['entry_strategy']['support_level']:.2f}
Resistance: ${entry['entry_strategy']['resistance_level']:.2f}
Risk/Reward Ratio: {entry['entry_strategy']['risk_reward_ratio']:.2f}

[bold]{entry['entry_strategy']['entry_recommendation']}[/]
""",
                        title="Entry Recommendation"
                    ))
                    
                    if entry.get("action_items"):
                        console.print("\n[bold]Action Items:[/]")
                        for action in entry["action_items"]:
                            console.print(f"  {action}")
        
        elif choice == "4":
            # View previous results
            if not agent.results:
                console.print("[yellow]No analysis results available yet.[/]")
            else:
                console.print("\n[bold]Previously Analyzed Stocks:[/]")
                for symbol, report in agent.results.items():
                    overall = report.get("overall_assessment", {})
                    rec = overall.get("recommendation", "N/A")
                    score = overall.get("overall_score", "N/A")
                    console.print(f"  • {symbol}: {rec} (Score: {score})")
                
                # Option to view details
                view_symbol = Prompt.ask(
                    "\nEnter symbol to view details (or press Enter to skip)",
                    default=""
                )
                if view_symbol and view_symbol.upper() in agent.results:
                    agent.report_generator.print_report(agent.results[view_symbol.upper()])
        
        elif choice == "5":
            # Export results
            if not agent.results:
                console.print("[yellow]No results to export.[/]")
            else:
                filepath = Prompt.ask(
                    "\n[bold]Enter output filename[/]",
                    default="stock_analysis_results"
                )
                format_choice = Prompt.ask(
                    "[bold]Select format[/]",
                    choices=["json", "markdown"],
                    default="json"
                )
                
                ext = ".json" if format_choice == "json" else ".md"
                full_path = f"{filepath}{ext}" if not filepath.endswith(ext) else filepath
                
                agent.export_results(full_path, format_choice)
        
        elif choice == "w":
            # Watchlist management
            manage_watchlist(console, watchlist)
        
        elif choice == "a":
            # Analyze all watchlist stocks
            stocks = watchlist.get_stocks()
            if not stocks:
                console.print("[yellow]Your watchlist is empty! Add stocks first.[/]")
            else:
                # Ask for timeframe
                timeframe = select_timeframe(console)
                
                console.print(f"\n[bold]Analyzing {len(stocks)} stocks from watchlist...[/]")
                results = agent.analyze_multiple(stocks, timeframe=timeframe)
                
                # Update watchlist with new analysis data
                for symbol, report in results.get("individual_reports", {}).items():
                    if not report.get("error"):
                        overall = report.get("overall_assessment", {})
                        watchlist.update_last_analysis(symbol, {
                            "overall_score": overall.get("overall_score"),
                            "recommendation": overall.get("recommendation"),
                            "price": report.get("price_summary", {}).get("current_price")
                        })
                
                console.print("\n[green]✓ Watchlist updated with latest analysis![/]")
        
        elif choice == "s":
            # Switch watchlist
            switch_watchlist_menu(console, watchlist)
        
        # Ask to continue
        if choice != "q":
            input("\n[Press Enter to continue...]")


def switch_watchlist_menu(console: Console, watchlist: WatchlistManager):
    """Quick menu to switch between watchlists"""
    console.print("\n")
    watchlist.show_all_watchlists()
    
    all_watchlists = watchlist.get_all_watchlists()
    keys = list(all_watchlists.keys())
    
    console.print("\n[bold]Available watchlists:[/]")
    for i, key in enumerate(keys, 1):
        wl = all_watchlists[key]
        active = " ⭐" if key == watchlist.get_current_watchlist_key() else ""
        console.print(f"  [cyan]{i}[/] - {wl.get('name', key)} ({len(wl.get('stocks', {}))} stocks){active}")
    
    console.print(f"  [cyan]n[/] - Create new watchlist")
    console.print(f"  [cyan]b[/] - Back")
    
    valid_choices = [str(i) for i in range(1, len(keys) + 1)] + ["n", "b"]
    choice = Prompt.ask("\n[bold]Select watchlist[/]", choices=valid_choices, default="b")
    
    if choice == "b":
        return
    elif choice == "n":
        # Create new watchlist
        name = Prompt.ask("\n[bold]Enter watchlist name[/] (e.g., 'Long Term Tech')")
        if name:
            key = name.lower().replace(" ", "_")
            watchlist.create_watchlist(key, name)
            if Confirm.ask(f"Switch to '{name}' now?"):
                watchlist.switch_watchlist(key)
    else:
        # Switch to selected watchlist
        idx = int(choice) - 1
        watchlist.switch_watchlist(keys[idx])


def manage_watchlist(console: Console, watchlist: WatchlistManager):
    """Watchlist management submenu"""
    while True:
        console.print("\n")
        console.print(f"[bold cyan]Managing: {watchlist.get_current_watchlist_name()}[/]")
        watchlist.show_watchlist()
        
        console.print("\n[bold]Watchlist Options:[/]")
        console.print("  [cyan]1[/] - Add stock(s)")
        console.print("  [cyan]2[/] - Remove stock(s)")
        console.print("  [cyan]3[/] - Edit notes")
        console.print("  [cyan]4[/] - Move stock to another watchlist")
        console.print("  [cyan]5[/] - Copy stock to another watchlist")
        console.print("  [cyan]6[/] - Clear all stocks")
        console.print("  [cyan]---[/]")
        console.print("  [cyan]s[/] - Switch watchlist")
        console.print("  [cyan]n[/] - Create new watchlist")
        console.print("  [cyan]r[/] - Rename current watchlist")
        console.print("  [cyan]d[/] - Delete a watchlist")
        console.print("  [cyan]v[/] - View all watchlists")
        console.print("  [cyan]b[/] - Back to main menu")
        
        choice = Prompt.ask("\n[bold]Select option[/]", choices=["1", "2", "3", "4", "5", "6", "s", "n", "r", "d", "v", "b"], default="b")
        
        if choice == "b":
            break
        
        elif choice == "1":
            # Add stocks
            symbols_input = Prompt.ask(
                "\n[bold]Enter stock symbol(s)[/] (comma-separated, e.g., AAPL,MSFT,GOOGL)"
            )
            symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
            if symbols:
                notes = Prompt.ask("[dim]Add notes (optional)[/]", default="")
                for symbol in symbols:
                    watchlist.add_stock(symbol, notes)
        
        elif choice == "2":
            # Remove stocks
            stocks = watchlist.get_stocks()
            if not stocks:
                console.print("[yellow]Watchlist is empty![/]")
                continue
            
            console.print(f"\n[dim]Current stocks: {', '.join(stocks)}[/]")
            symbols_input = Prompt.ask(
                "\n[bold]Enter symbol(s) to remove[/] (comma-separated)"
            )
            symbols = [s.strip() for s in symbols_input.split(",") if s.strip()]
            if symbols:
                watchlist.remove_multiple(symbols)
        
        elif choice == "3":
            # Edit notes
            symbol = Prompt.ask("\n[bold]Enter stock symbol[/]").upper().strip()
            if symbol in watchlist.get_stocks():
                current = watchlist.get_stock_info(symbol)
                console.print(f"[dim]Current notes: {current.get('notes', 'None')}[/]")
                new_notes = Prompt.ask("[bold]New notes[/]")
                watchlist.update_notes(symbol, new_notes)
            else:
                console.print(f"[red]{symbol} not in watchlist[/]")
        
        elif choice == "4":
            # Move stock to another watchlist
            stocks = watchlist.get_stocks()
            if not stocks:
                console.print("[yellow]Watchlist is empty![/]")
                continue
            
            console.print(f"\n[dim]Current stocks: {', '.join(stocks)}[/]")
            symbol = Prompt.ask("\n[bold]Enter stock symbol to move[/]").upper().strip()
            
            if symbol not in stocks:
                console.print(f"[red]{symbol} not in current watchlist[/]")
                continue
            
            # Show available watchlists
            all_wls = watchlist.get_all_watchlists()
            console.print("\n[bold]Available watchlists:[/]")
            wl_keys = [k for k in all_wls.keys() if k != watchlist.get_current_watchlist_key()]
            for i, key in enumerate(wl_keys, 1):
                console.print(f"  [cyan]{i}[/] - {all_wls[key].get('name', key)}")
            
            if not wl_keys:
                console.print("[yellow]No other watchlists available. Create one first.[/]")
                continue
            
            valid = [str(i) for i in range(1, len(wl_keys) + 1)]
            target_choice = Prompt.ask("\n[bold]Select target watchlist[/]", choices=valid)
            target_key = wl_keys[int(target_choice) - 1]
            watchlist.move_stock(symbol, target_key)
        
        elif choice == "5":
            # Copy stock to another watchlist
            stocks = watchlist.get_stocks()
            if not stocks:
                console.print("[yellow]Watchlist is empty![/]")
                continue
            
            console.print(f"\n[dim]Current stocks: {', '.join(stocks)}[/]")
            symbol = Prompt.ask("\n[bold]Enter stock symbol to copy[/]").upper().strip()
            
            if symbol not in stocks:
                console.print(f"[red]{symbol} not in current watchlist[/]")
                continue
            
            # Show available watchlists
            all_wls = watchlist.get_all_watchlists()
            console.print("\n[bold]Available watchlists:[/]")
            wl_keys = [k for k in all_wls.keys() if k != watchlist.get_current_watchlist_key()]
            for i, key in enumerate(wl_keys, 1):
                console.print(f"  [cyan]{i}[/] - {all_wls[key].get('name', key)}")
            
            if not wl_keys:
                console.print("[yellow]No other watchlists available. Create one first.[/]")
                continue
            
            valid = [str(i) for i in range(1, len(wl_keys) + 1)]
            target_choice = Prompt.ask("\n[bold]Select target watchlist[/]", choices=valid)
            target_key = wl_keys[int(target_choice) - 1]
            watchlist.copy_stock(symbol, target_key)
        
        elif choice == "6":
            # Clear all
            if Confirm.ask(f"[red]Are you sure you want to clear all stocks from '{watchlist.get_current_watchlist_name()}'?[/]"):
                watchlist.clear_all()
        
        elif choice == "s":
            # Switch watchlist
            switch_watchlist_menu(console, watchlist)
        
        elif choice == "n":
            # Create new watchlist
            name = Prompt.ask("\n[bold]Enter watchlist name[/] (e.g., 'Long Term Tech')")
            if name:
                key = name.lower().replace(" ", "_")
                watchlist.create_watchlist(key, name)
                if Confirm.ask(f"Switch to '{name}' now?"):
                    watchlist.switch_watchlist(key)
        
        elif choice == "r":
            # Rename current watchlist
            current_name = watchlist.get_current_watchlist_name()
            console.print(f"\n[dim]Current name: {current_name}[/]")
            new_name = Prompt.ask("[bold]Enter new name[/]")
            if new_name:
                watchlist.rename_watchlist(watchlist.get_current_watchlist_key(), new_name)
        
        elif choice == "d":
            # Delete a watchlist
            all_wls = watchlist.get_all_watchlists()
            deletable = [k for k in all_wls.keys() if k != "default"]
            
            if not deletable:
                console.print("[yellow]No watchlists can be deleted (cannot delete default)[/]")
                continue
            
            console.print("\n[bold]Watchlists that can be deleted:[/]")
            for i, key in enumerate(deletable, 1):
                console.print(f"  [cyan]{i}[/] - {all_wls[key].get('name', key)} ({len(all_wls[key].get('stocks', {}))} stocks)")
            
            valid = [str(i) for i in range(1, len(deletable) + 1)]
            del_choice = Prompt.ask("\n[bold]Select watchlist to delete[/]", choices=valid + ["b"], default="b")
            
            if del_choice != "b":
                key_to_delete = deletable[int(del_choice) - 1]
                name = all_wls[key_to_delete].get('name', key_to_delete)
                if Confirm.ask(f"[red]Delete '{name}' and all its stocks?[/]"):
                    watchlist.delete_watchlist(key_to_delete)
        
        elif choice == "v":
            # View all watchlists
            watchlist.show_all_watchlists()
            input("\n[Press Enter to continue...]")


def run_weekly_news_summary(console: Console):
    """Run the weekly news summary report"""
    from weekly_news_summary import WeeklyNewsSummary
    
    console.print(Panel(
        "[bold]📊 Weekly News Summary[/]\n\n"
        "Analyzes news from the past week for each stock in your watchlist\n"
        "and shows how the stock price was affected in the 1-3 days after each news item.",
        title="Weekly News Summary"
    ))
    
    analyzer = WeeklyNewsSummary()
    stocks = analyzer.get_watchlist_stocks()
    
    if not stocks:
        console.print("[yellow]No stocks in your watchlist. Add some stocks first![/]")
        return
    
    console.print(f"\n[bold]Found {len(stocks)} stocks in watchlist:[/] {', '.join(stocks)}")
    
    if Confirm.ask("\n[bold]Generate weekly news summary report?[/]", default=True):
        analyzer.generate_full_report(export_txt=True)


def run_primo_agent_menu(console: Console):
    """PrimoAgent multi-agent analysis menu"""
    from primo_agent import run_primo_analysis
    from primo_agent.workflow import run_primo_analysis_sync, print_detailed_report
    import os
    
    console.print(Panel(
        "[bold]🤖 PrimoAgent Multi-Agent Analysis[/]\n\n"
        "Advanced AI-powered stock analysis using 4 specialized agents:\n\n"
        "  [cyan]1.[/] Data Collection Agent - Market data, company info, news\n"
        "  [cyan]2.[/] Technical Analysis Agent - SMA, RSI, MACD, BB, ADX, CCI\n"
        "  [cyan]3.[/] News Intelligence Agent - 7 NLP sentiment features\n"
        "  [cyan]4.[/] Portfolio Manager Agent - BUY/SELL/HOLD signals\n\n"
        "[dim]Based on github.com/ivebotunac/PrimoAgent[/]",
        title="PrimoAgent",
        border_style="cyan"
    ))
    
    # Check OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        console.print(f"\n[green]✓ OpenAI API Key configured - LLM analysis enabled[/]")
    else:
        console.print(f"\n[yellow]⚠ No OpenAI API Key - Using rule-based analysis[/]")
        console.print("[dim]Set OPENAI_API_KEY in .env for enhanced AI analysis[/]")
    
    console.print("\n[bold]Options:[/]")
    console.print("  [cyan]1[/] - Analyze single stock")
    console.print("  [cyan]2[/] - Analyze multiple stocks")
    console.print("  [cyan]3[/] - Analyze current watchlist")
    console.print("  [cyan]b[/] - Back to main menu")
    
    choice = Prompt.ask("\n[bold]Select option[/]", choices=["1", "2", "3", "b"], default="1")
    
    if choice == "b":
        return
    
    symbols = []
    
    if choice == "1":
        symbol = Prompt.ask("\n[bold]Enter stock symbol[/]").upper().strip()
        if symbol:
            symbols = [symbol]
    
    elif choice == "2":
        symbols_input = Prompt.ask("\n[bold]Enter stock symbols[/] (comma-separated, e.g., AAPL,MSFT,GOOGL)")
        symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
    
    elif choice == "3":
        from watchlist import WatchlistManager
        wm = WatchlistManager()
        symbols = wm.get_stocks()
        if not symbols:
            console.print("[yellow]No stocks in current watchlist![/]")
            return
        console.print(f"\n[bold]Analyzing watchlist:[/] {', '.join(symbols)}")
    
    if not symbols:
        console.print("[yellow]No symbols provided.[/]")
        return
    
    # Run analysis
    results = run_primo_analysis_sync(
        symbols=symbols,
        openai_api_key=openai_key,
        console=console
    )
    
    # Option to view detailed report
    if len(symbols) == 1 and results.get(symbols[0], {}).get('success'):
        if Confirm.ask("\n[bold]View detailed report?[/]", default=True):
            print_detailed_report(results[symbols[0]], console)
    elif len(symbols) > 1:
        view_symbol = Prompt.ask(
            "\n[bold]Enter symbol to view detailed report (or press Enter to skip)[/]",
            default=""
        )
        if view_symbol and view_symbol.upper() in results:
            if results[view_symbol.upper()].get('success'):
                print_detailed_report(results[view_symbol.upper()], console)


def news_monitor_menu(console: Console):
    """News monitor submenu"""
    from news_monitor import NewsMonitor, setup_telegram
    import os
    
    console.print(Panel(
        "[bold]📰 News Monitor[/]\n\n"
        "24/7 monitoring of news for your watchlist stocks.\n"
        "Get instant alerts via Telegram and Windows notifications\n"
        "when significant news breaks (partnerships, deals, earnings, etc.)",
        title="News Monitor"
    ))
    
    # Check Telegram status
    telegram_configured = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    
    console.print(f"\n[bold]Status:[/]")
    console.print(f"  Telegram: {'[green]✓ Configured[/]' if telegram_configured else '[yellow]✗ Not configured[/]'}")
    console.print(f"  Windows: [green]✓ Available[/]")
    
    console.print("\n[bold]Options:[/]")
    console.print("  [cyan]1[/] - Run single news check now")
    console.print("  [cyan]2[/] - Start 24/7 monitoring")
    console.print("  [cyan]3[/] - Setup Telegram notifications")
    console.print("  [cyan]4[/] - Configure check interval")
    console.print("  [cyan]b[/] - Back to main menu")
    
    choice = Prompt.ask("\n[bold]Select option[/]", choices=["1", "2", "3", "4", "b"], default="b")
    
    if choice == "b":
        return
    
    elif choice == "1":
        # Single check
        console.print("\n[bold]Running single news check...[/]")
        monitor = NewsMonitor()
        alert_count = monitor.run_once()
        console.print(f"\n[green]✓ Check complete. Found {alert_count} significant news items.[/]")
        input("\n[Press Enter to continue...]")
    
    elif choice == "2":
        # Start 24/7 monitoring
        console.print("\n[bold yellow]Starting 24/7 News Monitor...[/]")
        console.print("[dim]This will run in the foreground. Press Ctrl+C to stop.[/]\n")
        
        if not telegram_configured:
            if Confirm.ask("[yellow]Telegram not configured. Setup now?[/]"):
                setup_telegram()
        
        monitor = NewsMonitor()
        try:
            monitor.run_forever()
        except KeyboardInterrupt:
            monitor.stop()
    
    elif choice == "3":
        # Setup Telegram
        setup_telegram()
        input("\n[Press Enter to continue...]")
    
    elif choice == "4":
        # Configure interval
        current = os.getenv("NEWS_CHECK_INTERVAL", "15")
        console.print(f"\n[dim]Current interval: {current} minutes[/]")
        new_interval = Prompt.ask("[bold]Enter new interval (minutes)[/]", default=current)
        
        try:
            interval = int(new_interval)
            if interval < 5:
                console.print("[yellow]Minimum interval is 5 minutes[/]")
                interval = 5
            
            # Update .env
            env_path = ".env"
            env_content = ""
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    env_content = f.read()
            
            if "NEWS_CHECK_INTERVAL" in env_content:
                lines = env_content.split('\n')
                lines = [l if not l.startswith("NEWS_CHECK_INTERVAL") else f"NEWS_CHECK_INTERVAL={interval}" for l in lines]
                env_content = '\n'.join(lines)
            else:
                env_content += f"\nNEWS_CHECK_INTERVAL={interval}\n"
            
            with open(env_path, 'w') as f:
                f.write(env_content)
            
            console.print(f"[green]✓ Check interval set to {interval} minutes[/]")
        except ValueError:
            console.print("[red]Invalid number[/]")
        
        input("\n[Press Enter to continue...]")


if __name__ == "__main__":
    run_interactive()
