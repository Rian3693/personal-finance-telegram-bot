"""
Base Agent class for all research agents
"""
import requests
import json
from typing import Dict, Any, Optional
from config import OPENAI_API_KEY, PERPLEXITY_API_KEY, ANTHROPIC_API_KEY


class BaseAgent:
    """Base class providing shared AI capabilities to all agents"""
    
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
    
    def _call_openai(self, system_prompt: str, user_prompt: str, model: str = "gpt-4o", max_tokens: int = 2000) -> str:
        """Call OpenAI API"""
        if not OPENAI_API_KEY:
            return ""
        import openai
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.3
        )
        return response.choices[0].message.content
    
    def _call_perplexity(self, prompt: str, model: str = "sonar-reasoning") -> str:
        """Call Perplexity API for web-search-enhanced analysis (sonar-reasoning = best quality)"""
        if not PERPLEXITY_API_KEY:
            return ""
        headers = {
            "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 3000,
            "temperature": 0.2,
        }
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    
    def _call_claude(self, system_prompt: str, user_prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 2000) -> str:
        """Call Anthropic Claude API"""
        if not ANTHROPIC_API_KEY:
            return ""
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text
    
    def run(self, symbol: str, stock_data: Dict) -> Dict[str, Any]:
        """Override in subclasses"""
        raise NotImplementedError
