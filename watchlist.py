"""
Watchlist Manager - Persistent stock watchlist with JSON storage
Supports multiple named watchlists (e.g., Long Term, Short Term, Swing Trades)
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

WATCHLIST_FILE = "watchlists.json"

# Default watchlist categories
DEFAULT_WATCHLISTS = {
    "default": "General Watchlist",
    "long_term": "Long Term (1-5 Years)",
    "medium_term": "Medium Term (3-12 Months)",
    "short_term": "Short Term (1-3 Months)",
    "swing": "Swing Trades (Days-Weeks)"
}


class WatchlistManager:
    """Manages multiple persistent stock watchlists"""
    
    def __init__(self, filepath: str = WATCHLIST_FILE):
        self.filepath = filepath
        self.console = Console()
        self.data = self._load_data()
        self.current_watchlist = self.data.get("active_watchlist", "default")
    
    def _load_data(self) -> Dict[str, Any]:
        """Load all watchlists from JSON file"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    data = json.load(f)
                    # Ensure structure is correct
                    if "watchlists" not in data:
                        data["watchlists"] = {}
                    return data
            except:
                pass
        
        # Create default structure
        return {
            "watchlists": {
                "default": {
                    "name": "General Watchlist",
                    "stocks": {},
                    "created_at": datetime.now().isoformat()
                }
            },
            "active_watchlist": "default",
            "created_at": datetime.now().isoformat()
        }
    
    def _save_data(self):
        """Save all watchlists to JSON file"""
        self.data["updated_at"] = datetime.now().isoformat()
        self.data["active_watchlist"] = self.current_watchlist
        with open(self.filepath, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
    
    def _get_current_watchlist(self) -> Dict:
        """Get the currently active watchlist"""
        if self.current_watchlist not in self.data["watchlists"]:
            self.data["watchlists"][self.current_watchlist] = {
                "name": self.current_watchlist,
                "stocks": {},
                "created_at": datetime.now().isoformat()
            }
        return self.data["watchlists"][self.current_watchlist]
    
    # ==================== Watchlist Management ====================
    
    def create_watchlist(self, key: str, name: str = None) -> bool:
        """Create a new watchlist"""
        key = key.lower().replace(" ", "_")
        
        if key in self.data["watchlists"]:
            self.console.print(f"[yellow]Watchlist '{key}' already exists[/]")
            return False
        
        self.data["watchlists"][key] = {
            "name": name or key.replace("_", " ").title(),
            "stocks": {},
            "created_at": datetime.now().isoformat()
        }
        self._save_data()
        self.console.print(f"[green]✓ Created watchlist: {name or key}[/]")
        return True
    
    def delete_watchlist(self, key: str) -> bool:
        """Delete a watchlist"""
        key = key.lower().replace(" ", "_")
        
        if key not in self.data["watchlists"]:
            self.console.print(f"[red]Watchlist '{key}' not found[/]")
            return False
        
        if key == "default":
            self.console.print("[red]Cannot delete the default watchlist[/]")
            return False
        
        name = self.data["watchlists"][key].get("name", key)
        del self.data["watchlists"][key]
        
        # Switch to default if we deleted the active watchlist
        if self.current_watchlist == key:
            self.current_watchlist = "default"
        
        self._save_data()
        self.console.print(f"[red]✓ Deleted watchlist: {name}[/]")
        return True
    
    def switch_watchlist(self, key: str) -> bool:
        """Switch to a different watchlist"""
        key = key.lower().replace(" ", "_")
        
        if key not in self.data["watchlists"]:
            self.console.print(f"[red]Watchlist '{key}' not found[/]")
            return False
        
        self.current_watchlist = key
        self._save_data()
        name = self.data["watchlists"][key].get("name", key)
        self.console.print(f"[green]✓ Switched to: {name}[/]")
        return True
    
    def get_all_watchlists(self) -> Dict[str, Dict]:
        """Get all watchlists"""
        return self.data["watchlists"]
    
    def get_current_watchlist_name(self) -> str:
        """Get the name of the current watchlist"""
        wl = self._get_current_watchlist()
        return wl.get("name", self.current_watchlist)
    
    def get_current_watchlist_key(self) -> str:
        """Get the key of the current watchlist"""
        return self.current_watchlist
    
    def rename_watchlist(self, key: str, new_name: str) -> bool:
        """Rename a watchlist"""
        key = key.lower().replace(" ", "_")
        
        if key not in self.data["watchlists"]:
            self.console.print(f"[red]Watchlist '{key}' not found[/]")
            return False
        
        old_name = self.data["watchlists"][key].get("name", key)
        self.data["watchlists"][key]["name"] = new_name
        self._save_data()
        self.console.print(f"[green]✓ Renamed '{old_name}' to '{new_name}'[/]")
        return True
    
    def show_all_watchlists(self):
        """Display all watchlists"""
        table = Table(title="📋 All Watchlists", box=box.ROUNDED)
        table.add_column("#", style="dim", width=4)
        table.add_column("Key", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("Stocks", justify="center")
        table.add_column("Active", justify="center")
        
        for i, (key, wl) in enumerate(self.data["watchlists"].items(), 1):
            is_active = "⭐" if key == self.current_watchlist else ""
            stock_count = len(wl.get("stocks", {}))
            table.add_row(
                str(i),
                key,
                wl.get("name", key),
                str(stock_count),
                is_active
            )
        
        self.console.print(table)
    
    # ==================== Stock Management ====================
    
    def add_stock(self, symbol: str, notes: str = "") -> bool:
        """Add a stock to the current watchlist"""
        symbol = symbol.upper().strip()
        watchlist = self._get_current_watchlist()
        
        if symbol in watchlist["stocks"]:
            self.console.print(f"[yellow]{symbol} is already in '{watchlist['name']}'[/]")
            return False
        
        watchlist["stocks"][symbol] = {
            "added_at": datetime.now().isoformat(),
            "notes": notes,
            "last_analysis": None,
            "alerts": []
        }
        self._save_data()
        self.console.print(f"[green]✓ Added {symbol} to '{watchlist['name']}'[/]")
        return True
    
    def add_multiple(self, symbols: List[str]) -> int:
        """Add multiple stocks at once"""
        added = 0
        watchlist = self._get_current_watchlist()
        for symbol in symbols:
            if self.add_stock(symbol.strip()):
                added += 1
        self.console.print(f"\n[bold green]Added {added} stocks to '{watchlist['name']}'[/]")
        return added
    
    def remove_stock(self, symbol: str) -> bool:
        """Remove a stock from the current watchlist"""
        symbol = symbol.upper().strip()
        watchlist = self._get_current_watchlist()
        
        if symbol not in watchlist["stocks"]:
            self.console.print(f"[yellow]{symbol} is not in '{watchlist['name']}'[/]")
            return False
        
        del watchlist["stocks"][symbol]
        self._save_data()
        self.console.print(f"[red]✓ Removed {symbol} from '{watchlist['name']}'[/]")
        return True
    
    def remove_multiple(self, symbols: List[str]) -> int:
        """Remove multiple stocks at once"""
        removed = 0
        for symbol in symbols:
            if self.remove_stock(symbol.strip()):
                removed += 1
        self.console.print(f"\n[bold red]Removed {removed} stocks[/]")
        return removed
    
    def clear_all(self) -> bool:
        """Clear all stocks from the current watchlist"""
        watchlist = self._get_current_watchlist()
        count = len(watchlist["stocks"])
        watchlist["stocks"] = {}
        self._save_data()
        self.console.print(f"[red]Cleared {count} stocks from '{watchlist['name']}'[/]")
        return True
    
    def get_stocks(self) -> List[str]:
        """Get list of all stock symbols in current watchlist"""
        watchlist = self._get_current_watchlist()
        return list(watchlist["stocks"].keys())
    
    def get_stock_info(self, symbol: str) -> Optional[Dict]:
        """Get info about a specific stock in current watchlist"""
        symbol = symbol.upper().strip()
        watchlist = self._get_current_watchlist()
        return watchlist["stocks"].get(symbol)
    
    def update_notes(self, symbol: str, notes: str):
        """Update notes for a stock"""
        symbol = symbol.upper().strip()
        watchlist = self._get_current_watchlist()
        if symbol in watchlist["stocks"]:
            watchlist["stocks"][symbol]["notes"] = notes
            self._save_data()
            self.console.print(f"[green]✓ Updated notes for {symbol}[/]")
    
    def update_last_analysis(self, symbol: str, analysis_summary: Dict):
        """Update the last analysis data for a stock"""
        symbol = symbol.upper().strip()
        watchlist = self._get_current_watchlist()
        if symbol in watchlist["stocks"]:
            watchlist["stocks"][symbol]["last_analysis"] = {
                "timestamp": datetime.now().isoformat(),
                "score": analysis_summary.get("overall_score"),
                "recommendation": analysis_summary.get("recommendation"),
                "price": analysis_summary.get("price")
            }
            self._save_data()
    
    def move_stock(self, symbol: str, target_watchlist: str) -> bool:
        """Move a stock from current watchlist to another"""
        symbol = symbol.upper().strip()
        target_key = target_watchlist.lower().replace(" ", "_")
        
        if target_key not in self.data["watchlists"]:
            self.console.print(f"[red]Target watchlist '{target_watchlist}' not found[/]")
            return False
        
        current = self._get_current_watchlist()
        if symbol not in current["stocks"]:
            self.console.print(f"[red]{symbol} not in current watchlist[/]")
            return False
        
        # Copy stock data to target
        stock_data = current["stocks"][symbol]
        self.data["watchlists"][target_key]["stocks"][symbol] = stock_data
        
        # Remove from current
        del current["stocks"][symbol]
        self._save_data()
        
        target_name = self.data["watchlists"][target_key].get("name", target_key)
        self.console.print(f"[green]✓ Moved {symbol} to '{target_name}'[/]")
        return True
    
    def copy_stock(self, symbol: str, target_watchlist: str) -> bool:
        """Copy a stock from current watchlist to another"""
        symbol = symbol.upper().strip()
        target_key = target_watchlist.lower().replace(" ", "_")
        
        if target_key not in self.data["watchlists"]:
            self.console.print(f"[red]Target watchlist '{target_watchlist}' not found[/]")
            return False
        
        current = self._get_current_watchlist()
        if symbol not in current["stocks"]:
            self.console.print(f"[red]{symbol} not in current watchlist[/]")
            return False
        
        # Copy stock data to target
        stock_data = current["stocks"][symbol].copy()
        self.data["watchlists"][target_key]["stocks"][symbol] = stock_data
        self._save_data()
        
        target_name = self.data["watchlists"][target_key].get("name", target_key)
        self.console.print(f"[green]✓ Copied {symbol} to '{target_name}'[/]")
        return True
    
    def show_watchlist(self):
        """Display the current watchlist in a nice table"""
        watchlist = self._get_current_watchlist()
        stocks = watchlist["stocks"]
        
        if not stocks:
            self.console.print(Panel(
                f"[yellow]'{watchlist['name']}' is empty![/]\n\n"
                "Add stocks with option 1 or:\n"
                "[cyan]watchlist.add_stock('AAPL')[/]",
                title=f"📋 {watchlist['name']}"
            ))
            return
        
        table = Table(title=f"📋 {watchlist['name']} ({len(stocks)} stocks)", box=box.ROUNDED)
        table.add_column("#", style="dim", width=4)
        table.add_column("Symbol", style="cyan bold")
        table.add_column("Added", style="dim")
        table.add_column("Last Analysis", justify="center")
        table.add_column("Score", justify="center")
        table.add_column("Signal", justify="center")
        table.add_column("Notes", max_width=30)
        
        for i, (symbol, data) in enumerate(stocks.items(), 1):
            added = data.get("added_at", "")[:10]
            
            last_analysis = data.get("last_analysis", {})
            if last_analysis:
                analysis_date = last_analysis.get("timestamp", "")[:10]
                score = last_analysis.get("score", "N/A")
                rec = last_analysis.get("recommendation", "N/A")
                
                # Color the recommendation
                if rec and "BUY" in str(rec):
                    rec = f"[green]{rec}[/]"
                elif rec and "SELL" in str(rec):
                    rec = f"[red]{rec}[/]"
                else:
                    rec = f"[yellow]{rec}[/]"
                
                score_display = f"[{'green' if score and score > 0 else 'red'}]{score}[/]" if score else "N/A"
            else:
                analysis_date = "[dim]Never[/]"
                score_display = "[dim]—[/]"
                rec = "[dim]—[/]"
            
            notes = data.get("notes", "")[:30]
            
            table.add_row(
                str(i),
                symbol,
                added,
                analysis_date,
                score_display,
                rec,
                notes
            )
        
        self.console.print(table)
        self.console.print(f"\n[dim]Active watchlist: {watchlist['name']} | Last updated: {self.data.get('updated_at', 'N/A')}[/]")


def main():
    """Command-line interface for watchlist management"""
    import sys
    
    watchlist = WatchlistManager()
    
    if len(sys.argv) < 2:
        watchlist.show_all_watchlists()
        watchlist.show_watchlist()
        return
    
    command = sys.argv[1].lower()
    
    if command == "show" or command == "list":
        watchlist.show_watchlist()
    
    elif command == "all":
        watchlist.show_all_watchlists()
    
    elif command == "switch":
        if len(sys.argv) < 3:
            print("Usage: python watchlist.py switch WATCHLIST_KEY")
            watchlist.show_all_watchlists()
            return
        watchlist.switch_watchlist(sys.argv[2])
    
    elif command == "create":
        if len(sys.argv) < 3:
            print("Usage: python watchlist.py create KEY [NAME]")
            return
        key = sys.argv[2]
        name = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        watchlist.create_watchlist(key, name)
    
    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: python watchlist.py delete WATCHLIST_KEY")
            return
        watchlist.delete_watchlist(sys.argv[2])
    
    elif command == "add":
        if len(sys.argv) < 3:
            print("Usage: python watchlist.py add SYMBOL [SYMBOL2 SYMBOL3 ...]")
            return
        symbols = sys.argv[2:]
        watchlist.add_multiple(symbols)
    
    elif command == "remove":
        if len(sys.argv) < 3:
            print("Usage: python watchlist.py remove SYMBOL [SYMBOL2 SYMBOL3 ...]")
            return
        symbols = sys.argv[2:]
        watchlist.remove_multiple(symbols)
    
    elif command == "clear":
        confirm = input("Are you sure you want to clear all stocks from current watchlist? (yes/no): ")
        if confirm.lower() == "yes":
            watchlist.clear_all()
    
    else:
        print(f"Unknown command: {command}")
        print("Available commands: show, all, switch, create, delete, add, remove, clear")


if __name__ == "__main__":
    main()
