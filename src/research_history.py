"""
Research History Manager
Stores past research results and enables comparison between runs.
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_history.json")


def _load_history() -> Dict:
    """Load research history from file"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_history(history: Dict):
    """Save research history to file"""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def save_research(symbol: str, result: Dict):
    """Save a research result to history"""
    history = _load_history()
    
    symbol = symbol.upper()
    if symbol not in history:
        history[symbol] = []
    
    # Extract key data to store (not the full raw agent reports — too large)
    entry = {
        "date": result.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "price": result.get("price", 0),
        "name": result.get("name", symbol),
        "has_dual_verdict": result.get("has_dual_verdict", False),
        "final_report": result.get("final_report", ""),
        "action_plan": result.get("action_plan", ""),
        # Extract verdict and key signals
        "verdict": _extract_verdict(result.get("final_report", "")),
        "action": _extract_action(result.get("action_plan", "")),
        "confidence": _extract_confidence(result.get("action_plan", "")),
        # Agent ratings snapshot
        "agent_ratings": _extract_agent_ratings(result.get("agent_reports", {})),
    }
    
    history[symbol].append(entry)
    
    # Keep max 20 researches per stock to prevent bloat
    if len(history[symbol]) > 20:
        history[symbol] = history[symbol][-20:]
    
    _save_history(history)


def get_previous_research(symbol: str) -> Optional[Dict]:
    """Get the most recent previous research for a stock"""
    history = _load_history()
    symbol = symbol.upper()
    entries = history.get(symbol, [])
    if entries:
        return entries[-1]
    return None


def get_research_history(symbol: str) -> List[Dict]:
    """Get all research history for a stock"""
    history = _load_history()
    return history.get(symbol.upper(), [])


def get_all_researched_stocks() -> Dict[str, int]:
    """Get all stocks that have been researched with their count"""
    history = _load_history()
    return {symbol: len(entries) for symbol, entries in history.items()}


def format_history_list() -> str:
    """Format all research history into a readable list"""
    history = _load_history()
    if not history:
        return "📭 No research history yet. Use /research to analyze a stock!"
    
    lines = ["📚 <b>RESEARCH HISTORY</b>\n"]
    
    # Sort by most recent research date
    sorted_stocks = sorted(
        history.items(),
        key=lambda x: x[1][-1]["date"] if x[1] else "",
        reverse=True
    )
    
    for symbol, entries in sorted_stocks:
        latest = entries[-1]
        count = len(entries)
        date = latest.get("date", "?")
        price = latest.get("price", 0)
        verdict = latest.get("verdict", "?")
        action = latest.get("action", "?")
        
        price_str = f"${price:,.2f}" if price else "?"
        count_str = f"({count}x)" if count > 1 else ""
        
        lines.append(
            f"{'─' * 28}\n"
            f"<b>{symbol}</b> {count_str} | Last: {date}\n"
            f"  💵 Price: {price_str} | 📊 {verdict}\n"
            f"  🎬 {action}"
        )
    
    lines.append(f"\n{'─' * 28}")
    lines.append(f"📊 Total: {len(history)} stocks | {sum(len(v) for v in history.values())} researches")
    lines.append("\n💡 Use <code>/researchlog SYMBOL</code> to see full history for a stock")
    
    return "\n".join(lines)


def format_stock_history(symbol: str) -> str:
    """Format detailed history for a specific stock"""
    entries = get_research_history(symbol)
    if not entries:
        return f"📭 No research history for {symbol.upper()}. Use /research {symbol.upper()} to analyze it!"
    
    symbol = symbol.upper()
    lines = [f"📚 <b>RESEARCH HISTORY: {symbol}</b>\n"]
    
    for i, entry in enumerate(reversed(entries), 1):
        date = entry.get("date", "?")
        price = entry.get("price", 0)
        verdict = entry.get("verdict", "?")
        action = entry.get("action", "?")
        confidence = entry.get("confidence", "?")
        dual = "🧠+🟣" if entry.get("has_dual_verdict") else "🧠"
        
        price_str = f"${price:,.2f}" if price else "?"
        
        # Calculate time ago
        time_ago = _time_ago(date)
        
        lines.append(
            f"{'━' * 28}\n"
            f"<b>#{i}</b> — {date} ({time_ago})\n"
            f"  💵 Price: {price_str}\n"
            f"  📊 Verdict: {verdict}\n"
            f"  🎬 Action: {action}\n"
            f"  📊 Confidence: {confidence}\n"
            f"  🤖 Models: {dual}"
        )
        
        # Show agent ratings if available
        ratings = entry.get("agent_ratings", {})
        if ratings:
            rating_lines = []
            for agent, rating in ratings.items():
                if rating:
                    rating_lines.append(f"    • {agent}: {rating}")
            if rating_lines:
                lines.append("  📋 Agent ratings:")
                lines.extend(rating_lines)
        
        # Show price change from previous
        if i < len(entries):
            prev = entries[-(i+1)] if i < len(entries) else None
            if prev and prev.get("price") and price:
                prev_price = prev["price"]
                if prev_price:
                    change = ((price - prev_price) / prev_price) * 100
                    arrow = "📈" if change > 0 else "📉"
                    lines.append(f"  {arrow} Price change from prev research: {change:+.1f}%")
    
    lines.append(f"\n{'━' * 28}")
    lines.append(f"📊 Total researches: {len(entries)}")
    
    return "\n".join(lines)


def generate_comparison(symbol: str, new_result: Dict) -> str:
    """Generate a comparison between the new research and the most recent previous one"""
    prev = get_previous_research(symbol)
    if not prev:
        return ""
    
    symbol = symbol.upper()
    new_price = new_result.get("price", 0)
    prev_price = prev.get("price", 0)
    prev_date = prev.get("date", "?")
    prev_verdict = prev.get("verdict", "?")
    prev_action = prev.get("action", "?")
    new_verdict = _extract_verdict(new_result.get("final_report", ""))
    new_action = _extract_action(new_result.get("action_plan", ""))
    
    # Time elapsed
    time_str = _time_ago(prev_date)
    
    # Price change
    price_change = ""
    if prev_price and new_price:
        change_pct = ((new_price - prev_price) / prev_price) * 100
        arrow = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡️"
        price_change = f"{arrow} ${prev_price:,.2f} → ${new_price:,.2f} ({change_pct:+.1f}%)"
    
    # Verdict change
    verdict_changed = prev_verdict != new_verdict and prev_verdict != "?" and new_verdict != "?"
    if verdict_changed:
        verdict_line = f"⚡ {prev_verdict} → {new_verdict} (CHANGED!)"
    else:
        verdict_line = f"✅ {prev_verdict} (unchanged)"
    
    # Action change
    action_changed = prev_action != new_action and prev_action != "?" and new_action != "?"
    if action_changed:
        action_line = f"⚡ {prev_action} → {new_action} (CHANGED!)"
    else:
        action_line = f"✅ {prev_action} (unchanged)"
    
    # Count
    all_entries = get_research_history(symbol)
    research_count = len(all_entries) + 1  # +1 for the current one (not saved yet)
    
    comparison = (
        f"{'━' * 30}\n"
        f"🔄 <b>PREVIOUS RESEARCH COMPARISON</b>\n"
        f"{'━' * 30}\n\n"
        f"📅 Last researched: {prev_date} ({time_str})\n"
        f"🔢 This is research #{research_count} for {symbol}\n\n"
        f"💵 Price: {price_change}\n"
        f"📊 Verdict: {verdict_line}\n"
        f"🎬 Action: {action_line}\n"
    )
    
    # Add agent rating changes
    prev_ratings = prev.get("agent_ratings", {})
    new_ratings = _extract_agent_ratings(new_result.get("agent_reports", {}))
    rating_changes = []
    for agent in set(list(prev_ratings.keys()) + list(new_ratings.keys())):
        old_r = prev_ratings.get(agent, "?")
        new_r = new_ratings.get(agent, "?")
        if old_r != new_r and old_r != "?" and new_r != "?":
            rating_changes.append(f"  ⚡ {agent}: {old_r} → {new_r}")
    
    if rating_changes:
        comparison += "\n📋 <b>Agent Rating Changes:</b>\n" + "\n".join(rating_changes) + "\n"
    else:
        comparison += "\n📋 Agent ratings: No significant changes\n"
    
    return comparison


# === Helper functions ===

def _extract_verdict(report: str) -> str:
    """Extract the verdict (STRONG BUY/BUY/HOLD/SELL/STRONG SELL) from report text"""
    verdicts = ["STRONG BUY", "STRONG SELL", "BUY", "SELL", "HOLD"]
    # Check GPT verdict first (it appears first in the report)
    upper = report.upper()
    for line in upper.split('\n'):
        if 'VERDICT' in line:
            for v in verdicts:
                if v in line:
                    return v
            break
    # Fallback: find first verdict mention
    for v in verdicts:
        if v in upper:
            return v
    return "?"


def _extract_action(plan: str) -> str:
    """Extract the action (BUY NOW/SCALE IN/WAIT/HOLD/TRIM/SELL) from action plan"""
    actions = ["BUY NOW", "SCALE IN", "WAIT FOR DIP", "HOLD", "TRIM", "SELL"]
    upper = plan.upper()
    for line in upper.split('\n'):
        if 'ACTION' in line and 'PLAN' not in line:
            for a in actions:
                if a in line:
                    return a
            break
    for a in actions:
        if a in upper[:200]:
            return a
    return "?"


def _extract_confidence(plan: str) -> str:
    """Extract confidence percentage from action plan"""
    import re
    match = re.search(r'CONFIDENCE[:\s]*(\d+)%', plan.upper())
    if match:
        return f"{match.group(1)}%"
    return "?"


def _extract_agent_ratings(agent_reports: Dict) -> Dict[str, str]:
    """Extract key ratings from each agent's report"""
    ratings = {}
    for agent_name, report in agent_reports.items():
        rating = report.get("rating", "")
        if rating:
            ratings[agent_name] = rating
    return ratings


def _time_ago(date_str: str) -> str:
    """Convert a date string to 'X days/weeks/months ago' format"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return "unknown"
    
    now = datetime.now()
    diff = now - dt
    days = diff.days
    
    if days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            minutes = diff.seconds // 60
            return f"{minutes}m ago"
        return f"{hours}h ago"
    elif days == 1:
        return "yesterday"
    elif days < 7:
        return f"{days} days ago"
    elif days < 30:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    elif days < 365:
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    else:
        years = days // 365
        return f"{years} year{'s' if years > 1 else ''} ago"
