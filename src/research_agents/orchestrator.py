"""
Research Orchestrator
Coordinates all specialist agents and produces unified research reports
"""
import yfinance as yf
import asyncio
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Any
from research_agents.base_agent import BaseAgent
from research_agents.news_analyst_agent import NewsAnalystAgent
from research_agents.earnings_agent import EarningsReportAgent
from research_agents.hype_agent import HypeMeterAgent
from research_agents.technical_agent import TechnicalInsightAgent
from research_agents.insider_agent import InsiderInstitutionalAgent
from research_agents.peer_agent import PeerComparisonAgent
from research_agents.macro_agent import MacroSectorAgent
from research_agents.finrobot_agent import FinRobotAgent


class ResearchOrchestrator(BaseAgent):
    """Coordinates specialist agents and synthesizes final research report"""
    
    def __init__(self):
        super().__init__(
            name="Research Orchestrator",
            role="Lead researcher who coordinates specialist agents and produces final investment research"
        )
        self.agents = [
            NewsAnalystAgent(),
            EarningsReportAgent(),
            HypeMeterAgent(),
            TechnicalInsightAgent(),
            InsiderInstitutionalAgent(),
            PeerComparisonAgent(),
            MacroSectorAgent(),
            FinRobotAgent(),
        ]
    
    def _fetch_stock_data(self, symbol: str) -> Dict:
        """Fetch base stock data that all agents need"""
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return {
            "info": info,
            "symbol": symbol,
            "name": info.get("longName", info.get("shortName", symbol)),
            "price": info.get("regularMarketPrice") or info.get("currentPrice", 0),
        }
    
    def _run_agent(self, agent, symbol: str, stock_data: Dict) -> Dict:
        """Run a single agent with error handling"""
        try:
            return agent.run(symbol, stock_data)
        except Exception as e:
            return {
                "agent": agent.name,
                "symbol": symbol,
                "error": str(e),
                "summary": f"Agent failed: {e}"
            }
    
    def research_stock(self, symbol: str, progress_callback=None, user_question: str = "") -> Dict[str, Any]:
        """
        Run full multi-agent research on a single stock.
        progress_callback: optional callable(agent_name, status) for progress updates
        user_question: optional personal context/question from the user
        """
        symbol = symbol.upper().strip()
        
        # Step 1: Fetch base data
        if progress_callback:
            progress_callback("Data Collection", "fetching")
        stock_data = self._fetch_stock_data(symbol)
        
        if not stock_data["price"]:
            return {"symbol": symbol, "error": f"Could not find stock {symbol}"}
        
        # Step 2: Run all agents in parallel
        agent_results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = {}
            for agent in self.agents:
                if progress_callback:
                    progress_callback(agent.name, "started")
                futures[executor.submit(self._run_agent, agent, symbol, stock_data)] = agent.name
            
            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                result = future.result()
                agent_results[agent_name] = result
                if progress_callback:
                    progress_callback(agent_name, "done")
        
        # Step 3: Synthesize final verdict
        if progress_callback:
            progress_callback("Final Synthesis", "started")
        
        final_report = self._synthesize(symbol, stock_data, agent_results, user_question)
        
        if progress_callback:
            progress_callback("Final Synthesis", "done")
        
        return final_report
    
    def research_multiple(self, symbols: List[str], progress_callback=None) -> List[Dict]:
        """Research multiple stocks sequentially"""
        results = []
        for i, symbol in enumerate(symbols):
            if progress_callback:
                progress_callback(f"Stock {i+1}/{len(symbols)}: {symbol}", "starting")
            result = self.research_stock(symbol, progress_callback)
            results.append(result)
        return results

    def compare_stocks(self, results: List[Dict], user_question: str = "") -> str:
        """Generate a head-to-head comparison verdict for multiple stocks"""
        if len(results) < 2:
            return ""

        # Build comparison data from each stock's research
        comparison_data = ""
        for r in results:
            symbol = r.get("symbol", "?")
            name = r.get("name", symbol)
            price = r.get("price", 0)
            final = r.get("final_report", "")
            action = r.get("action_plan", "")
            comparison_data += (
                f"\n{'=' * 40}\n"
                f"STOCK: {symbol} ({name}) — ${price:,.2f}\n"
                f"RESEARCH VERDICT:\n{final[:2000]}\n"
                f"ACTION PLAN:\n{action[:1500]}\n"
            )

        tickers = [r.get('symbol', '?') for r in results]
        user_line = ""
        if user_question:
            user_line = (
                f"\nThe investor asked: \"{user_question}\"\n"
                f"You MUST directly answer their question.\n"
            )

        prompt = (
            "You are a HEAD PORTFOLIO STRATEGIST. The investor just researched multiple stocks "
            "and needs you to COMPARE them head-to-head and give a CLEAR WINNER recommendation.\n"
            f"{user_line}\n"
            "Structure your comparison EXACTLY like this:\n\n"
            f"🏆 HEAD-TO-HEAD: {' vs '.join(tickers)}\n\n"
            "📊 COMPARISON TABLE:\n"
            "For each stock, list: Verdict | Confidence | Price Target Upside | Risk Level | Stock Type\n\n"
            "⚡ KEY DIFFERENCES:\n"
            "• Risk/Reward: Which has better upside vs downside?\n"
            "• Momentum: Which has stronger near-term catalysts?\n"
            "• Fundamentals: Which has stronger financials?\n"
            "• Value: Which is cheaper relative to growth?\n\n"
            "🏆 WINNER: [TICKER] — One clear sentence on why\n\n"
            "🥈 RUNNER-UP: [TICKER] — When this would be the better pick\n\n"
            "💡 MY RECOMMENDATION:\n"
            "Give a specific, actionable answer. Examples:\n"
            "• 'Buy X now, and add Y on a dip to $Z'\n"
            "• 'X is the clear winner for growth, Y is safer for income'\n"
            "• 'If you can only pick one, go with X because...'\n\n"
            "🎯 PORTFOLIO PLAY (if buying multiple):\n"
            "• Suggest allocation split (e.g., 60% X / 30% Y / 10% Z)\n"
            "• Which to buy first and why\n\n"
            "Be DECISIVE. The investor wants a CLEAR answer, not 'it depends.' "
            "Take a bold stance backed by the research data."
        )

        try:
            return self._call_openai(prompt, comparison_data, max_tokens=2000)
        except Exception as e:
            return f"Comparison unavailable: {e}"
    
    def _synthesize(self, symbol: str, stock_data: Dict, agent_results: Dict, user_question: str = "") -> Dict:
        """Combine all agent findings into a final research report with dual AI verdicts"""
        name = stock_data["name"]
        price = stock_data["price"]
        
        # Gather all agent summaries
        agent_summaries = ""
        for agent_name, result in agent_results.items():
            agent_summaries += f"\n\n--- {agent_name} ---\n{result.get('summary', 'No summary')}"
        
        synthesis_prompt = (
            "You are the HEAD RESEARCH ANALYST at a top investment firm. "
            "You have received reports from 8 specialist analysts. Your job is to synthesize "
            "their findings into a FINAL RESEARCH VERDICT.\n\n"
            "Structure your report EXACTLY like this:\n"
            "📊 VERDICT: [STRONG BUY / BUY / HOLD / SELL / STRONG SELL]\n"
            "🎯 CONFIDENCE: [HIGH / MEDIUM / LOW]\n\n"
            "🏢 WHAT THIS COMPANY DOES:\n"
            "• What is their core product/service (1-2 sentences)\n"
            "• What real-world PROBLEM does it solve right now?\n"
            "• How urgent/needed is their product in today's market?\n\n"
            "📉📈 WHY IT'S BEEN MOVING (3-6 months):\n"
            "• Key events that drove the price up or down (with dates)\n"
            "• The main narrative/story around this stock right now\n\n"
            "🔑 KEY FINDINGS (3-5 bullet points)\n\n"
            "📈 BULL CASE (top 3 reasons to buy)\n\n"
            "📉 BEAR CASE (top 3 risks)\n\n"
            "🎯 PRICE TARGETS\n"
            "• Near-term (1-3 months): $X - $X\n"
            "• Medium-term (6-12 months): $X - $X\n\n"
            "⚡ CATALYST TIMELINE (upcoming events that could move the stock)\n\n"
            "🏷️ STOCK TYPE: [Meme/Hype | Speculative Growth | Quality Growth | Value | Blue Chip]\n\n"
            "💡 BOTTOM LINE: One-paragraph final recommendation\n\n"
            "Be bold and decisive. Take a clear stance. Use specific numbers."
        )
        
        data_prompt = (
            f"Stock: {symbol} ({name}) at ${price:.2f}\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"SPECIALIST REPORTS:{agent_summaries}"
        )
        
        # Run GPT-4o and Claude in parallel for dual verdicts
        gpt_verdict = ""
        claude_verdict = ""
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            gpt_future = executor.submit(self._safe_call_openai, synthesis_prompt, data_prompt)
            claude_future = executor.submit(self._safe_call_claude, synthesis_prompt, data_prompt)
            gpt_verdict = gpt_future.result()
            claude_verdict = claude_future.result()
        
        # Build the combined report
        if claude_verdict:
            final_summary = (
                f"🧠 <b>GPT-4o ANALYSIS:</b>\n"
                f"{gpt_verdict}\n\n"
                f"{'─' * 30}\n\n"
                f"🟣 <b>CLAUDE ANALYSIS:</b>\n"
                f"{claude_verdict}\n\n"
                f"{'─' * 30}\n"
                f"{self._compare_verdicts(gpt_verdict, claude_verdict)}"
            )
        else:
            final_summary = gpt_verdict or "No analysis could be generated."
        
        # Generate ACTION PLAN - the practical "what to do" summary
        action_plan = self._generate_action_plan(symbol, name, price, agent_summaries, gpt_verdict, claude_verdict, user_question)
        
        return {
            "symbol": symbol,
            "name": name,
            "price": price,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "agent_reports": agent_results,
            "final_report": final_summary,
            "action_plan": action_plan,
            "has_dual_verdict": bool(claude_verdict)
        }
    
    def _safe_call_openai(self, system_prompt, user_prompt):
        try:
            return self._call_openai(system_prompt, user_prompt, max_tokens=2000)
        except Exception as e:
            return f"GPT-4o unavailable: {e}"
    
    def _safe_call_claude(self, system_prompt, user_prompt):
        try:
            return self._call_claude(system_prompt, user_prompt, max_tokens=2000)
        except Exception as e:
            return ""  # Silent fail - Claude is optional
    
    def _generate_action_plan(self, symbol, name, price, agent_summaries, gpt_verdict, claude_verdict, user_question=""):
        """Generate the practical ACTION PLAN with entry/exit strategy and scenarios"""
        combined_verdicts = f"GPT-4o verdict:\n{gpt_verdict}"
        if claude_verdict:
            combined_verdicts += f"\n\nClaude verdict:\n{claude_verdict}"
        
        # Add personal context if user provided a question
        personal_context = ""
        if user_question:
            personal_context = (
                "\n\nIMPORTANT — The investor has provided PERSONAL CONTEXT about their situation. "
                "You MUST address their specific question/situation directly in the action plan. "
                "Tailor all entry/exit prices, position sizing, and recommendations to THEIR situation.\n"
                f"INVESTOR'S QUESTION/CONTEXT: {user_question}\n"
            )
        
        action_prompt = (
            "You are a PORTFOLIO STRATEGIST. Based on all the research below, create a PRACTICAL ACTION PLAN "
            "for an individual investor. Be specific with numbers. No vague advice."
            f"{personal_context}\n\n"
            "CRITICAL RULES:\n"
            "- NEVER write N/A for ANY field. EVERY field must have a real dollar amount or percentage.\n"
            "- Even if the verdict is SELL or AVOID, you MUST still fill in ALL price levels.\n"
            "- For SELL/TRIM: Entry Strategy becomes 'Re-entry levels' (prices where it becomes interesting again).\n"
            "- For SELL/TRIM: Exit Strategy shows where to sell NOW and where the stock could bounce.\n"
            "- Always use the current stock price to calculate realistic support/resistance levels.\n\n"
            "Structure your plan EXACTLY like this:\n\n"
            "🎬 ACTION: [BUY NOW / SCALE IN / WAIT FOR DIP / HOLD / TRIM / SELL]\n"
            "📊 CONFIDENCE: [X]% (give an actual percentage 0-100)\n\n"
            "💰 ENTRY STRATEGY (if BUY/SCALE IN/WAIT):\n"
            "• Aggressive entry: $X.XX (buy now at current price)\n"
            "• Conservative entry: $X.XX (wait for pullback to this support level)\n"
            "• DCA Plan: Buy X% now, X% at $X.XX, X% at $X.XX\n"
            "• Ideal position size: X% of portfolio\n\n"
            "💰 RE-ENTRY STRATEGY (if SELL/TRIM/HOLD — prices where it becomes a buy):\n"
            "• Watch level #1: $X.XX (X% below current — first level of interest)\n"
            "• Watch level #2: $X.XX (X% below current — strong buy zone)\n"
            "• Capitulation price: $X.XX (back-up-the-truck level if it reaches here)\n"
            "• What must change: [specific catalyst needed before buying]\n\n"
            "🚪 EXIT STRATEGY (if currently holding):\n"
            "• Sell now at: $X.XX (current market price)\n"
            "• Stop-loss / floor: $X.XX (absolute must-sell level)\n"
            "• Bounce target: $X.XX (if stock recovers, sell at this resistance)\n"
            "• Take profit #1: $X.XX (X% gain from current)\n"
            "• Take profit #2: $X.XX (X% gain — stretch target)\n"
            "• Trailing stop: X% once above take profit #1\n\n"
            "📈 SCENARIO ANALYSIS:\n"
            "🟢 BULL CASE (X% probability): Stock reaches $X.XX within X months because [reason]. Return: +X%\n"
            "🟡 BASE CASE (X% probability): Stock trades between $X.XX-$X.XX because [reason]. Return: +/-X%\n"
            "🔴 BEAR CASE (X% probability): Stock drops to $X.XX because [reason]. Return: -X%\n\n"
            "⏰ TIMELINE: [Short-term trade (days-weeks) / Swing trade (1-3 months) / Medium hold (3-12 months) / Long-term (1+ year)]\n\n"
            "⚠️ KEY RISKS TO WATCH: Top 3 specific things that would make you EXIT immediately\n\n"
            "🔄 WHAT WOULD CHANGE MY MIND: Top 2 specific catalysts that would flip this to a BUY (if SELL/HOLD) or SELL (if BUY)\n\n"
            "Use the current price and all research data to calculate realistic numbers. "
            "Use technical support/resistance levels, peer valuations, and fundamental targets for price levels."
        )

        action_data = (
            f"Stock: {symbol} ({name}) at ${price:.2f}\n\n"
            f"ALL AGENT RESEARCH:{agent_summaries}\n\n"
            f"AI VERDICTS:\n{combined_verdicts}"
        )

        try:
            return self._call_openai(action_prompt, action_data, max_tokens=2000)
        except Exception as e:
            return f"Action plan unavailable: {e}"

    def _compare_verdicts(self, gpt: str, claude: str) -> str:
        """Compare the two AI verdicts and highlight agreement/disagreement"""
        verdicts = ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL"]
        gpt_v = next((v for v in verdicts if v in gpt.upper()), None)
        claude_v = next((v for v in verdicts if v in claude.upper()), None)
        
        if not gpt_v or not claude_v:
            return "🔄 <b>CONSENSUS:</b> Could not compare verdicts automatically."
        
        if gpt_v == claude_v:
            return f"✅ <b>CONSENSUS: BOTH AI AGREE → {gpt_v}</b> — High conviction signal!"
        
        gpt_idx = verdicts.index(gpt_v)
        claude_idx = verdicts.index(claude_v)
        diff = abs(gpt_idx - claude_idx)
        
        if diff == 1:
            return (
                f"⚠️ <b>NEAR CONSENSUS:</b> GPT-4o says {gpt_v}, Claude says {claude_v}\n"
                f"Slight difference — both lean the same direction."
            )
        else:
            return (
                f"❌ <b>DISAGREEMENT:</b> GPT-4o says {gpt_v}, Claude says {claude_v}\n"
                f"⚠️ Significant split — do your own due diligence before acting!"
            )
    
    @staticmethod
    def format_telegram_report(result: Dict) -> str:
        """Format a research result for Telegram message"""
        if "error" in result and not result.get("final_report"):
            return f"❌ {result['symbol']}: {result['error']}"
        
        symbol = result["symbol"]
        name = result.get("name", symbol)
        price = result.get("price", 0)
        date = result.get("date", "")
        
        header = (
            f"🔬 <b>DEEP RESEARCH: {symbol}</b>\n"
            f"<i>{name}</i> | ${price:,.2f}\n"
            f"📅 {date}\n"
            f"{'─' * 30}\n\n"
        )
        
        # Final verdict
        final = result.get("final_report", "No report generated")
        
        # Action Plan section
        action_plan = result.get("action_plan", "")
        action_section = ""
        if action_plan:
            action_section = (
                f"\n\n{'━' * 30}\n"
                f"🎯 <b>YOUR ACTION PLAN</b>\n"
                f"{'━' * 30}\n\n"
                f"{action_plan}"
            )
        
        # Agent mini-summaries for transparency
        agents_used = []
        for agent_name, report in result.get("agent_reports", {}).items():
            status = "✅" if "error" not in report else "⚠️"
            agents_used.append(f"{status} {agent_name}")
        
        # Show which AI models powered the analysis
        if result.get("has_dual_verdict"):
            model_line = "🧠 GPT-4o + 🟣 Claude (dual verdict)"
        else:
            model_line = "🧠 GPT-4o (single verdict)"
        
        footer = (
            f"\n\n{'─' * 30}\n"
            f"🤖 <b>Agents consulted:</b>\n"
            + "\n".join(agents_used)
            + f"\n\n💻 <b>Models:</b> {model_line}"
            + f"\n\n<i>⚠️ This is AI-generated research, not financial advice.</i>"
        )
        
        return header + final + action_section + footer
