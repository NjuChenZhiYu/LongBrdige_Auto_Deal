"""LLM API client for stock analysis using Kimi/Moonshot."""
import os
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """Kimi LLM analyzer for stock alert analysis."""
    
    def __init__(self):
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.moonshot.cn/v1")
        self.model = os.getenv("LLM_MODEL", "kimi-k2.5")
        self.enabled = bool(self.api_key)
        
    async def analyze_stock_alert(
        self,
        symbol: str,
        last_price: float,
        change_rate: float,
        prev_close: float,
        market_type: str = "US",
        additional_context: Optional[str] = None
    ) -> Optional[str]:
        """
        Analyze stock price movement using LLM.
        
        Returns: Analysis text or None if disabled/error.
        """
        if not self.enabled:
            logger.debug("LLM analysis disabled: no API key configured")
            return None
            
        try:
            prompt = self._build_analysis_prompt(
                symbol=symbol,
                last_price=last_price,
                change_rate=change_rate,
                prev_close=prev_close,
                market_type=market_type,
                additional_context=additional_context
            )
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "你是一位专业的股票分析师，擅长分析股价异动原因。请基于提供的数据给出简洁、专业的分析，控制在200字以内。"
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.7,
                        "max_tokens": 500
                    }
                )
                
                response.raise_for_status()
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    analysis = data["choices"][0]["message"]["content"]
                    logger.info(f"LLM analysis generated for {symbol}")
                    return analysis
                else:
                    logger.warning(f"Unexpected LLM response format: {data}")
                    return None
                    
        except Exception as e:
            logger.error(f"LLM analysis failed for {symbol}: {e}")
            return None
    
    def _build_analysis_prompt(
        self,
        symbol: str,
        last_price: float,
        change_rate: float,
        prev_close: float,
        market_type: str,
        additional_context: Optional[str] = None
    ) -> str:
        """Build analysis prompt for LLM."""
        direction = "上涨" if change_rate > 0 else "下跌"
        
        prompt = f"""请分析以下股票的价格异动：

**股票信息**
- 标的代码：{symbol}
- 市场：{"美股" if market_type == "US" else "港股" if market_type == "HK" else market_type}
- 当前价格：{last_price}
- 涨跌幅：{change_rate:.2f}%
- 方向：{direction}
- 昨收价：{prev_close}

**分析要求**
1. 基于技术面的角度简要分析
2. 给出可能的异动原因（如大盘影响、板块轮动、个股消息等）
3. 提示投资者关注的风险或机会
4. 用中文回答，专业但易懂，控制在150字以内
"""
        
        if additional_context:
            prompt += f"\n**额外信息**：{additional_context}"
        
        return prompt


# Global instance
llm_analyzer = LLMAnalyzer()
