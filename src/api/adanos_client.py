import logging
import asyncio
import requests
from typing import List
from config.settings import Settings

logger = logging.getLogger(__name__)

class AdanosClient:
    def __init__(self):
        self.api_key = Settings.ADANOS_API_KEY
        self.base_url = "https://api.adanos.org/reddit/stocks/v1/stock"

    def _fetch_sentiment_sync(self, ticker: str) -> dict:
        """Synchronous method to fetch sentiment data."""
        if not self.api_key:
            return {}
            
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json"
        }
        url = f"{self.base_url}/{ticker}"
        
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Adanos API returned status {response.status_code} for {ticker}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching Adanos data for {ticker}: {e}")
            return {}

    async def get_sentiment_labels(self, symbol: str) -> List[str]:
        """
        Fetch sentiment data for a given symbol and return a list of strategy labels.
        Args:
            symbol: e.g., 'AAPL.US' or 'TSLA'
        Returns:
            List of labels like ['全网极度狂热', '散户强烈看多']
        """
        if not self.api_key:
            return []

        # Strip suffix if present (e.g., AAPL.US -> AAPL)
        ticker = symbol.split('.')[0] if '.' in symbol else symbol
        
        # Run sync request in a separate thread to not block the event loop
        data = await asyncio.to_thread(self._fetch_sentiment_sync, ticker)
        
        if not data or not data.get("found", False):
            return []
            
        labels = []
        
        # 1. 热度解析 (Buzz Score)
        buzz_val = data.get("buzz_score")
        buzz_score = float(buzz_val) if buzz_val is not None else 0.0
        
        if buzz_val is not None:
            if buzz_score >= 80:
                labels.append("全网极度狂热")
            elif buzz_score < 30:
                labels.append("情绪冰点")
            
        # 2. 多空解析 (Bullish/Bearish Percentage)
        bullish_val = data.get("bullish_pct")
        bullish = float(bullish_val) if bullish_val is not None else 0.0
        
        bearish_val = data.get("bearish_pct")
        bearish = float(bearish_val) if bearish_val is not None else 0.0
        
        if bullish_val is not None or bearish_val is not None:
            if bullish > 60:
                labels.append("散户强烈看多")
            if bearish > 50:
                labels.append("极度恐慌")
                
            divergence = abs(bullish - bearish)
            if divergence < 10:
                labels.append("多空极端分歧：方向选择中")
            elif bullish > 2 * bearish:
                labels.append("单边乐观：注意回调风险")
            elif bearish > 2 * bullish:
                labels.append("单边悲观：注意反弹机会")
            
        # 3. 边际解析 (Daily Trend)
        daily_trend = data.get("daily_trend") or []
        if len(daily_trend) >= 2:
            # Sort by date descending just in case
            sorted_trend = sorted(daily_trend, key=lambda x: x.get("date", ""), reverse=True)
            
            lb_val = sorted_trend[0].get("buzz_score")
            latest_buzz = float(lb_val) if lb_val is not None else 0.0
            
            pb_val = sorted_trend[1].get("buzz_score")
            prev_buzz = float(pb_val) if pb_val is not None else 0.0
            
            if prev_buzz > 0 and (latest_buzz - prev_buzz) / prev_buzz > 0.5:
                labels.append("热度脉冲爆发")
                
        return labels

# Global instance
adanos_client = AdanosClient()
