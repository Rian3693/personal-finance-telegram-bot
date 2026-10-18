"""
Analyst Ratings Collector - Fetches ratings from major institutional analysts
Includes: Zacks, JPMorgan, Deutsche Bank, BofA, Morgan Stanley, Goldman Sachs, 
Citigroup, Wells Fargo, UBS, Barclays
"""
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import re
import json
import yfinance as yf


class AnalystRatingsCollector:
    """Collects analyst ratings from major investment banks and research firms"""
    
    # Weighting for different sources (higher = more important)
    SOURCE_WEIGHTS = {
        # Tier 1 - Major Investment Banks (highest weight)
        "Goldman Sachs": 1.0,
        "JPMorgan": 1.0,
        "JP Morgan": 1.0,
        "Morgan Stanley": 1.0,
        
        # Tier 2 - Large Banks
        "Bank of America": 0.95,
        "BofA": 0.95,
        "BofA Securities": 0.95,
        "Citigroup": 0.95,
        "Citi": 0.95,
        "Wells Fargo": 0.90,
        "UBS": 0.90,
        "Deutsche Bank": 0.90,
        "Barclays": 0.90,
        
        # Tier 3 - Research Firms
        "Zacks": 0.80,
        "Morningstar": 0.85,
        "S&P Global": 0.85,
        "Moody's": 0.85,
        "Fitch": 0.80,
        
        # Tier 4 - Other Analysts
        "Jefferies": 0.75,
        "RBC Capital": 0.75,
        "Piper Sandler": 0.70,
        "Wedbush": 0.70,
        "Needham": 0.65,
        "Bernstein": 0.75,
        "KeyBanc": 0.70,
        "Raymond James": 0.70,
        
        # Tier 5 - Social/Retail (lowest weight)
        "Reddit": 0.30,
        "StockTwits": 0.25,
        "Seeking Alpha": 0.40,
    }
    
    RATING_MAP = {
        # Buy ratings
        "strong buy": 5,
        "strong-buy": 5,
        "buy": 4,
        "outperform": 4,
        "overweight": 4,
        "accumulate": 4,
        "positive": 4,
        "sector outperform": 4,
        
        # Hold ratings
        "hold": 3,
        "neutral": 3,
        "market perform": 3,
        "equal weight": 3,
        "equal-weight": 3,
        "sector perform": 3,
        "in-line": 3,
        "peer perform": 3,
        
        # Sell ratings
        "underperform": 2,
        "underweight": 2,
        "reduce": 2,
        "negative": 2,
        "sector underperform": 2,
        "sell": 1,
        "strong sell": 1,
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Priority banks to track (user requested)
        self.priority_banks = [
            "Zacks",
            "JPMorgan",
            "JP Morgan",
            "Deutsche Bank",
            "Bank of America",
            "BofA",
            "BofA Securities",
            "Morgan Stanley",
            "Goldman Sachs",
            "Citigroup",
            "Citi"
        ]
    
    def get_analyst_ratings(self, symbol: str) -> Dict[str, Any]:
        """
        Collect analyst ratings from multiple sources
        """
        result = {
            "symbol": symbol.upper(),
            "timestamp": datetime.now().isoformat(),
            "institutional_ratings": [],
            "priority_bank_ratings": {},  # Specific ratings from requested banks
            "zacks_rating": None,
            "yfinance_summary": None,  # Summary from yfinance
            "consensus": None,
            "weighted_score": None,
            "price_targets": {
                "average": None,
                "high": None,
                "low": None,
                "all_targets": []
            },
            "average_rating": None,
            "recent_changes": [],
            "error": None
        }
        
        try:
            # PRIMARY SOURCE: yfinance analyst recommendations (most reliable)
            yf_ratings = self._get_yfinance_recommendations(symbol)
            if yf_ratings:
                result["institutional_ratings"].extend(yf_ratings.get("ratings", []))
                result["yfinance_summary"] = yf_ratings.get("summary", {})
                result["recent_changes"] = yf_ratings.get("upgrades_downgrades", [])
            
            # Get Zacks rating
            zacks = self._get_zacks_rating(symbol)
            if zacks:
                result["zacks_rating"] = zacks
                result["institutional_ratings"].append(zacks)
            
            # Try to get additional data from web sources
            # Get TipRanks data (aggregates many analyst ratings)
            tipranks = self._get_tipranks_data(symbol)
            if tipranks:
                result["institutional_ratings"].extend(tipranks.get("ratings", []))
            
            # Get Benzinga analyst ratings
            benzinga = self._get_benzinga_ratings(symbol)
            if benzinga:
                result["institutional_ratings"].extend(benzinga)
            
            # Get MarketBeat ratings
            marketbeat = self._get_marketbeat_ratings(symbol)
            if marketbeat:
                result["institutional_ratings"].extend(marketbeat.get("ratings", []))
                if marketbeat.get("changes"):
                    result["recent_changes"].extend(marketbeat.get("changes", []))
            
            # Deduplicate ratings by source
            result["institutional_ratings"] = self._deduplicate_ratings(result["institutional_ratings"])
            
            # Extract priority bank ratings
            result["priority_bank_ratings"] = self._extract_priority_bank_ratings(result["institutional_ratings"])
            
            # Calculate price targets (average, high, low)
            result["price_targets"] = self._calculate_price_targets(result["institutional_ratings"])
            
            # If no price targets from ratings, use yfinance summary
            if not result["price_targets"].get("average") and result.get("yfinance_summary"):
                yf_sum = result["yfinance_summary"]
                result["price_targets"] = {
                    "average": yf_sum.get("target_mean"),
                    "high": yf_sum.get("target_high"),
                    "low": yf_sum.get("target_low"),
                    "count": yf_sum.get("num_analysts", 0),
                    "all_targets": []
                }
            
            # Calculate average rating score
            result["average_rating"] = self._calculate_average_rating(result["institutional_ratings"])
            
            # Calculate weighted consensus
            result["consensus"] = self._calculate_weighted_consensus(result["institutional_ratings"])
            result["weighted_score"] = self._calculate_weighted_score(result["institutional_ratings"])
            
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _get_yfinance_recommendations(self, symbol: str) -> Optional[Dict]:
        """Get analyst recommendations from yfinance - most reliable source"""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            ratings = []
            upgrades_downgrades = []
            
            # Get recent recommendations with firm names
            try:
                recs = ticker.recommendations
                if recs is not None and not recs.empty:
                    # Get the most recent recommendations
                    recent_recs = recs.tail(50)
                    
                    for idx, row in recent_recs.iterrows():
                        firm = row.get('Firm', '') or str(row.name) if hasattr(row, 'name') else ''
                        to_grade = row.get('To Grade', '') or row.get('toGrade', '')
                        from_grade = row.get('From Grade', '') or row.get('fromGrade', '')
                        action = row.get('Action', '') or ''
                        
                        if firm and to_grade:
                            rating_score = self.RATING_MAP.get(to_grade.lower(), 3)
                            weight = self._get_source_weight(firm)
                            
                            ratings.append({
                                "source": firm,
                                "rating": to_grade,
                                "rating_score": rating_score,
                                "previous_rating": from_grade if from_grade else None,
                                "action": action,
                                "date": str(idx) if idx else datetime.now().isoformat(),
                                "weight": weight
                            })
                            
                            # Track upgrades/downgrades
                            if action and action.lower() in ['upgrade', 'downgrade', 'initiated', 'reiterated']:
                                upgrades_downgrades.append({
                                    "source": firm,
                                    "action": action,
                                    "from": from_grade,
                                    "to": to_grade,
                                    "date": str(idx) if idx else datetime.now().isoformat()
                                })
            except Exception as e:
                pass
            
            # Get upgrades/downgrades separately
            try:
                upgrades = ticker.upgrades_downgrades
                if upgrades is not None and not upgrades.empty:
                    recent_changes = upgrades.tail(30)
                    
                    for idx, row in recent_changes.iterrows():
                        firm = row.get('Firm', '')
                        to_grade = row.get('ToGrade', '') or row.get('To Grade', '')
                        from_grade = row.get('FromGrade', '') or row.get('From Grade', '')
                        action = row.get('Action', '')
                        
                        if firm and to_grade:
                            rating_score = self.RATING_MAP.get(to_grade.lower(), 3)
                            weight = self._get_source_weight(firm)
                            
                            # Add if not duplicate
                            existing_firms = [r['source'] for r in ratings]
                            if firm not in existing_firms:
                                ratings.append({
                                    "source": firm,
                                    "rating": to_grade,
                                    "rating_score": rating_score,
                                    "previous_rating": from_grade if from_grade else None,
                                    "action": action,
                                    "date": str(idx) if idx else datetime.now().isoformat(),
                                    "weight": weight
                                })
            except Exception as e:
                pass
            
            # Get summary info
            summary = {
                "recommendation": info.get("recommendationKey"),
                "recommendation_mean": info.get("recommendationMean"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
                "target_high": info.get("targetHighPrice"),
                "target_low": info.get("targetLowPrice"),
                "target_mean": info.get("targetMeanPrice"),
                "target_median": info.get("targetMedianPrice"),
            }
            
            return {
                "ratings": ratings,
                "summary": summary,
                "upgrades_downgrades": upgrades_downgrades
            }
            
        except Exception as e:
            return None
    
    def _deduplicate_ratings(self, ratings: List[Dict]) -> List[Dict]:
        """Remove duplicate ratings, keeping the most recent one per source"""
        seen = {}
        for r in ratings:
            source = r.get("source", "").lower()
            if source:
                # Keep the one with the most info or most recent
                if source not in seen:
                    seen[source] = r
                else:
                    # Keep if this one has a price target and the other doesn't
                    if r.get("price_target") and not seen[source].get("price_target"):
                        seen[source] = r
        return list(seen.values())
    
    def _get_zacks_rating(self, symbol: str) -> Optional[Dict]:
        """Get Zacks rating for a stock"""
        try:
            url = f"https://www.zacks.com/stock/quote/{symbol}"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Find Zacks rank
                rank_elem = soup.find('p', class_='rank_view')
                if rank_elem:
                    rank_text = rank_elem.get_text(strip=True)
                    
                    # Parse rank (1-5, 1 being best)
                    rank_match = re.search(r'(\d)-', rank_text)
                    if rank_match:
                        zacks_rank = int(rank_match.group(1))
                        
                        rank_labels = {
                            1: "Strong Buy",
                            2: "Buy", 
                            3: "Hold",
                            4: "Sell",
                            5: "Strong Sell"
                        }
                        
                        return {
                            "source": "Zacks",
                            "rating": rank_labels.get(zacks_rank, "Unknown"),
                            "rating_score": 6 - zacks_rank,  # Convert to 1-5 (5 being best)
                            "date": datetime.now().isoformat(),
                            "weight": self.SOURCE_WEIGHTS.get("Zacks", 0.5)
                        }
        except:
            pass
        return None
    
    def _get_tipranks_data(self, symbol: str) -> Optional[Dict]:
        """Get analyst ratings from TipRanks (aggregates many analysts)"""
        try:
            # TipRanks has data from many institutional analysts
            url = f"https://www.tipranks.com/stocks/{symbol.lower()}/forecast"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                ratings = []
                price_targets = {}
                
                # Look for analyst ratings in the page
                analyst_cards = soup.find_all('div', class_=re.compile(r'analyst.*card|rating.*card'))
                
                for card in analyst_cards[:20]:
                    try:
                        analyst_name = card.find(class_=re.compile(r'analyst.*name'))
                        firm_name = card.find(class_=re.compile(r'firm|company'))
                        rating = card.find(class_=re.compile(r'rating|recommendation'))
                        target = card.find(class_=re.compile(r'target|price'))
                        
                        if firm_name:
                            firm = firm_name.get_text(strip=True)
                            rating_text = rating.get_text(strip=True).lower() if rating else "hold"
                            
                            ratings.append({
                                "source": firm,
                                "analyst": analyst_name.get_text(strip=True) if analyst_name else None,
                                "rating": rating_text.title(),
                                "rating_score": self.RATING_MAP.get(rating_text, 3),
                                "price_target": self._extract_price(target.get_text() if target else ""),
                                "date": datetime.now().isoformat(),
                                "weight": self._get_source_weight(firm)
                            })
                    except:
                        continue
                
                return {"ratings": ratings, "price_targets": price_targets}
        except:
            pass
        return None
    
    def _get_benzinga_ratings(self, symbol: str) -> List[Dict]:
        """Get analyst ratings from Benzinga"""
        ratings = []
        try:
            url = f"https://www.benzinga.com/stock/{symbol}/ratings"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Find rating tables/cards
                rating_rows = soup.find_all('tr', class_=re.compile(r'rating|analyst'))
                
                for row in rating_rows[:15]:
                    try:
                        cols = row.find_all('td')
                        if len(cols) >= 3:
                            firm = cols[0].get_text(strip=True)
                            rating = cols[1].get_text(strip=True).lower()
                            target = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                            
                            # Check if this is a major bank
                            if any(bank.lower() in firm.lower() for bank in 
                                   ["goldman", "jpmorgan", "morgan stanley", "citi", "bofa", 
                                    "bank of america", "wells fargo", "ubs", "deutsche", "barclays"]):
                                
                                ratings.append({
                                    "source": firm,
                                    "rating": rating.title(),
                                    "rating_score": self.RATING_MAP.get(rating, 3),
                                    "price_target": self._extract_price(target),
                                    "date": datetime.now().isoformat(),
                                    "weight": self._get_source_weight(firm)
                                })
                    except:
                        continue
        except:
            pass
        return ratings
    
    def _get_marketbeat_ratings(self, symbol: str) -> Optional[Dict]:
        """Get analyst ratings from MarketBeat"""
        try:
            url = f"https://www.marketbeat.com/stocks/NYSE/{symbol}/analyst-ratings/"
            response = self.session.get(url, timeout=10)
            
            if response.status_code != 200:
                # Try NASDAQ
                url = f"https://www.marketbeat.com/stocks/NASDAQ/{symbol}/analyst-ratings/"
                response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'lxml')
                
                ratings = []
                changes = []
                
                # Find rating table
                table = soup.find('table', class_=re.compile(r'rating|analyst'))
                if table:
                    rows = table.find_all('tr')[1:20]  # Skip header
                    
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 4:
                            try:
                                firm = cols[0].get_text(strip=True)
                                rating = cols[1].get_text(strip=True).lower()
                                action = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                                target = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                                
                                ratings.append({
                                    "source": firm,
                                    "rating": rating.title(),
                                    "rating_score": self.RATING_MAP.get(rating, 3),
                                    "price_target": self._extract_price(target),
                                    "date": datetime.now().isoformat(),
                                    "weight": self._get_source_weight(firm)
                                })
                                
                                # Track rating changes
                                if "upgrade" in action.lower() or "downgrade" in action.lower():
                                    changes.append({
                                        "source": firm,
                                        "action": action,
                                        "new_rating": rating.title(),
                                        "date": datetime.now().isoformat()
                                    })
                            except:
                                continue
                
                return {"ratings": ratings, "changes": changes}
        except:
            pass
        return None
    
    def _get_source_weight(self, source: str) -> float:
        """Get weight for a source, matching partial names"""
        source_lower = source.lower()
        
        for key, weight in self.SOURCE_WEIGHTS.items():
            if key.lower() in source_lower or source_lower in key.lower():
                return weight
        
        # Default weight for unknown sources
        return 0.50
    
    def _extract_price(self, text: str) -> Optional[float]:
        """Extract price from text"""
        if not text:
            return None
        try:
            # Find number with $ sign
            match = re.search(r'\$?([\d,]+\.?\d*)', text.replace(',', ''))
            if match:
                return float(match.group(1))
        except:
            pass
        return None
    
    def _calculate_weighted_consensus(self, ratings: List[Dict]) -> Dict[str, Any]:
        """Calculate weighted consensus from all ratings"""
        if not ratings:
            return {"status": "No ratings available"}
        
        # Count ratings by category
        buy_count = 0
        hold_count = 0
        sell_count = 0
        
        weighted_sum = 0
        total_weight = 0
        
        for r in ratings:
            score = r.get("rating_score", 3)
            weight = r.get("weight", 0.5)
            
            weighted_sum += score * weight
            total_weight += weight
            
            if score >= 4:
                buy_count += 1
            elif score <= 2:
                sell_count += 1
            else:
                hold_count += 1
        
        weighted_avg = weighted_sum / total_weight if total_weight > 0 else 3
        
        # Determine consensus
        if weighted_avg >= 4.2:
            consensus = "Strong Buy"
        elif weighted_avg >= 3.5:
            consensus = "Buy"
        elif weighted_avg >= 2.5:
            consensus = "Hold"
        elif weighted_avg >= 1.8:
            consensus = "Sell"
        else:
            consensus = "Strong Sell"
        
        return {
            "consensus_rating": consensus,
            "weighted_score": round(weighted_avg, 2),
            "buy_count": buy_count,
            "hold_count": hold_count,
            "sell_count": sell_count,
            "total_ratings": len(ratings)
        }
    
    def _calculate_weighted_score(self, ratings: List[Dict]) -> Optional[float]:
        """Calculate overall weighted score (0-100)"""
        if not ratings:
            return None
        
        weighted_sum = 0
        total_weight = 0
        
        for r in ratings:
            score = r.get("rating_score", 3)
            weight = r.get("weight", 0.5)
            
            # Convert 1-5 to 0-100
            normalized_score = (score - 1) * 25
            
            weighted_sum += normalized_score * weight
            total_weight += weight
        
        return round(weighted_sum / total_weight, 1) if total_weight > 0 else 50
    
    def _extract_priority_bank_ratings(self, ratings: List[Dict]) -> Dict[str, Dict]:
        """Extract ratings specifically from the priority banks (Zacks, JPMorgan, etc.)"""
        priority_ratings = {}
        
        # Bank name variations mapping
        bank_aliases = {
            "Zacks": ["zacks"],
            "JPMorgan": ["jpmorgan", "jp morgan", "jpm"],
            "Deutsche Bank": ["deutsche bank", "deutsche"],
            "Bank of America": ["bank of america", "bofa", "boa", "merrill lynch"],
            "Morgan Stanley": ["morgan stanley"],
            "Goldman Sachs": ["goldman sachs", "goldman"],
            "Citigroup": ["citigroup", "citi", "citibank"]
        }
        
        for r in ratings:
            source = r.get("source", "").lower()
            
            for bank_name, aliases in bank_aliases.items():
                if any(alias in source for alias in aliases):
                    # Only keep the most recent rating for each bank
                    if bank_name not in priority_ratings:
                        priority_ratings[bank_name] = {
                            "bank": bank_name,
                            "rating": r.get("rating", "N/A"),
                            "rating_score": r.get("rating_score", 3),
                            "price_target": r.get("price_target"),
                            "date": r.get("date"),
                            "source_detail": r.get("source", "")
                        }
                    break
        
        return priority_ratings
    
    def _calculate_price_targets(self, ratings: List[Dict]) -> Dict[str, Any]:
        """Calculate average, high, and low price targets from all ratings"""
        targets = []
        
        for r in ratings:
            pt = r.get("price_target")
            if pt and isinstance(pt, (int, float)) and pt > 0:
                targets.append(pt)
        
        if not targets:
            return {
                "average": None,
                "high": None,
                "low": None,
                "count": 0,
                "all_targets": []
            }
        
        return {
            "average": round(sum(targets) / len(targets), 2),
            "high": round(max(targets), 2),
            "low": round(min(targets), 2),
            "count": len(targets),
            "all_targets": targets
        }
    
    def _calculate_average_rating(self, ratings: List[Dict]) -> Dict[str, Any]:
        """Calculate average rating across all analysts"""
        if not ratings:
            return {"score": None, "label": "N/A", "count": 0}
        
        scores = [r.get("rating_score", 3) for r in ratings if r.get("rating_score")]
        
        if not scores:
            return {"score": None, "label": "N/A", "count": 0}
        
        avg_score = sum(scores) / len(scores)
        
        # Convert score to label
        if avg_score >= 4.5:
            label = "Strong Buy"
        elif avg_score >= 3.5:
            label = "Buy"
        elif avg_score >= 2.5:
            label = "Hold"
        elif avg_score >= 1.5:
            label = "Sell"
        else:
            label = "Strong Sell"
        
        return {
            "score": round(avg_score, 2),
            "label": label,
            "count": len(scores)
        }
    
    def get_institutional_sentiment(self, symbol: str, reddit_sentiment: Dict = None) -> Dict[str, Any]:
        """
        Combine institutional ratings with social sentiment (weighted)
        """
        result = self.get_analyst_ratings(symbol)
        
        # Add Reddit sentiment with lower weight
        if reddit_sentiment:
            reddit_score = reddit_sentiment.get("sentiment_score", 0)
            # Convert -1 to 1 scale to 1-5 scale
            reddit_rating_score = (reddit_score + 1) * 2 + 1
            
            result["institutional_ratings"].append({
                "source": "Reddit",
                "rating": reddit_sentiment.get("sentiment_label", "Neutral").title(),
                "rating_score": reddit_rating_score,
                "mentions": reddit_sentiment.get("total_mentions", 0),
                "weight": self.SOURCE_WEIGHTS.get("Reddit", 0.3)
            })
            
            # Recalculate consensus with Reddit included
            result["consensus"] = self._calculate_weighted_consensus(result["institutional_ratings"])
            result["weighted_score"] = self._calculate_weighted_score(result["institutional_ratings"])
        
        return result


if __name__ == "__main__":
    collector = AnalystRatingsCollector()
    ratings = collector.get_analyst_ratings("AAPL")
    print(f"Found {len(ratings['institutional_ratings'])} analyst ratings")
    print(f"Consensus: {ratings['consensus']}")
