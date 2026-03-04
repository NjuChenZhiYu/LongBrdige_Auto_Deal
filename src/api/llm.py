"""LLM API client for stock analysis and daily market reports using Kimi/Moonshot."""
import os
import logging
from typing import Optional, Dict, Any, List
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMAnalyzer:
    """Kimi LLM analyzer for stock alert analysis and market reports."""
    
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
        volume: int = 0,
        turnover: float = 0.0,
        market_type: str = "US",
        additional_context: Optional[str] = None
    ) -> Optional[str]:
        """
        Analyze stock price movement using LLM with rich context.
        
        Args:
            volume: Trading volume (shares)
            turnover: Trading turnover (amount)
            
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
                volume=volume,
                turnover=turnover,
                market_type=market_type,
                additional_context=additional_context
            )
            
            analysis = await self._call_llm(prompt, max_tokens=500)
            if analysis:
                logger.info(f"LLM analysis generated for {symbol}")
            return analysis
                    
        except Exception as e:
            logger.error(f"LLM analysis failed for {symbol}: {e}")
            return None
    
    async def generate_daily_market_report(
        self,
        alerted_stocks: List[Dict[str, Any]],
        market_type: str = "US"
    ) -> Optional[str]:
        """
        Generate a daily market report aggregating all alerted stocks.
        
        Args:
            alerted_stocks: List of dicts containing stock alert data
                [{symbol, last_price, change_rate, volume, turnover, analysis}, ...]
            market_type: "US" or "HK"
            
        Returns: 300-word market report or None.
        """
        if not self.enabled:
            logger.debug("LLM report generation disabled: no API key configured")
            return None
            
        if not alerted_stocks:
            logger.debug("No alerted stocks to generate report")
            return None
            
        try:
            prompt = self._build_daily_report_prompt(alerted_stocks, market_type)
            
            report = await self._call_llm(prompt, max_tokens=800)
            if report:
                logger.info(f"Daily market report generated with {len(alerted_stocks)} stocks")
            return report
                    
        except Exception as e:
            logger.error(f"Daily report generation failed: {e}")
            return None
    
    async def _call_llm(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        """Internal method to call Kimi API."""
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
                            "content": "你是一位专业的股票分析师，擅长宏观经济分析和个股异动解读。"
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": max_tokens
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0]["message"]["content"]
            else:
                logger.warning(f"Unexpected LLM response format: {data}")
                return None
    
    def _build_analysis_prompt(
        self,
        symbol: str,
        last_price: float,
        change_rate: float,
        prev_close: float,
        volume: int = 0,
        turnover: float = 0.0,
        market_type: str = "US",
        additional_context: Optional[str] = None
    ) -> str:
        """Build rich analysis prompt for single stock."""
        direction = "上涨" if change_rate > 0 else "下跌"
        market_name = "美股" if market_type == "US" else "港股" if market_type == "HK" else market_type
        
        # Calculate additional metrics
        turnover_str = f"{turnover/100000000:.2f}亿" if turnover > 100000000 else f"{turnover/10000:.2f}万"
        
        prompt = f"""请作为专业股票分析师，基于以下技术面数据进行深度分析：

**【股票基本信息】**
- 标的代码：{symbol}
- 市场：{market_name}
- 当前价格：${last_price:.2f}
- 涨跌幅：{change_rate:+.2f}%（{direction}）
- 昨收价：${prev_close:.2f}

**【成交数据】**
- 成交量：{volume:,} 股
- 成交额：{turnover_str}

**【分析维度要求】**
1. **技术面分析**：结合成交量和涨跌幅，判断是放量突破还是缩量回调
2. **异动归因**：分析可能驱动因素（大盘联动、板块效应、个股利好/利空、技术面突破/破位）
3. **市场情绪**：解读当前多空力量对比
4. **操作建议**：提示投资者关注的风险点或机会点

**【输出要求】**
- 用中文回答，专业但不晦涩
- 控制在180字以内
- 直接给出结论，不要套话
"""
        
        if additional_context:
            prompt += f"\n**【补充信息】**：{additional_context}"
        
        return prompt
    
    def _build_daily_report_prompt(
        self,
        alerted_stocks: List[Dict[str, Any]],
        market_type: str = "US"
    ) -> str:
        """Build prompt for daily market report."""
        market_name = "美股" if market_type == "US" else "港股" if market_type == "HK" else market_type
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Build stock list string
        stock_details = []
        for i, stock in enumerate(alerted_stocks[:15], 1):  # Limit to 15 stocks
            symbol = stock.get('symbol', 'Unknown')
            price = stock.get('last_price', 0)
            change = stock.get('change_rate', 0)
            direction = "📈" if change > 0 else "📉"
            stock_details.append(f"{i}. {symbol} ${price:.2f} ({change:+.2f}%) {direction}")
        
        stocks_text = "\n".join(stock_details)
        
        # Calculate market statistics
        up_count = sum(1 for s in alerted_stocks if s.get('change_rate', 0) > 0)
        down_count = len(alerted_stocks) - up_count
        avg_change = sum(s.get('change_rate', 0) for s in alerted_stocks) / len(alerted_stocks) if alerted_stocks else 0
        
        prompt = f"""请作为资深市场分析师，撰写一份{market_name}异动观察日报。

**【报告时间】**：{current_time}

**【当日异动概览】**
- 异动标的总数：{len(alerted_stocks)} 只
- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只
- 平均涨跌幅：{avg_change:+.2f}%

**【异动标的列表】**
{stocks_text}

**【研报撰写要求】**
1. **市场整体研判**：基于涨跌分布和平均涨跌，给出市场整体情绪判断（乐观/谨慎/观望）
2. **板块/热点分析**：识别是否有明显的板块集中异动特征
3. **重点个股点评**：挑选2-3只异动最剧烈或最具代表性的股票进行简要点评
4. **次日展望**：基于当前市场状态，给出简要的投资建议或风险提示

**【格式要求】**
- 标题：{market_name}异动观察日报（{current_time}）
- 正文：300字左右
- 结构：市场综述 → 热点分析 → 重点点评 → 投资提示
- 语言：专业、简洁、有洞察
"""
        return prompt


# Global instance
llm_analyzer = LLMAnalyzer()
