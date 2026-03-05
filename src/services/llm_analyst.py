"""LLM Analyst service for generating daily market reports."""
import logging
import asyncio
from typing import Optional, Dict, List
from openai import AsyncOpenAI
from config.settings import Settings
from src.services.signal_recorder import signal_recorder
from src.api.dingtalk import DingTalkAlert
from src.api.feishu import FeishuAlert
from datetime import datetime
from src.api.longport.personalized.watchlist import get_watchlist
from src.api.longport.client import longport_client

logger = logging.getLogger(__name__)

class LLMAnalyst:
    def __init__(self):
        self.api_key = Settings.LLM_API_KEY
        self.base_url = Settings.LLM_BASE_URL
        self.model = Settings.LLM_MODEL
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else None
        
        # Options report system prompt (existing)
        self.options_system_prompt = """你是一位华尔街资深的生物医药期权交易员。我将提供今天盘中触发异动报警的远期期权 (LEAPS) 数据。
请根据这些数据（如 IV 飙升、成交量激增突破 OI 的 20%、Delta 突破 0.5），为我撰写一份专业的市场复盘报告。
        要求：
        1. 识别出是否有机构(Smart Money)在大量建仓或平仓。
        2. 分析 IV 的变化意味着市场在定价什么潜在事件（如临床数据发布、财报等）。
        3. 语言风格要专业、精炼，直接给出结论和潜在的交易风险。
        4. 使用 Markdown 格式输出，字数控制在 300 字以内。
        """

    async def generate_options_report(self):
        """
        Generate options report from daily signals using LLM and push to DingTalk.
        """
        signals = signal_recorder.get_daily_signals()
        
        if not signals:
            logger.info("No option signals recorded today. Skipping report generation.")
            return

        logger.info(f"Generating options report for {len(signals)} signals...")
        
        # Format signals for prompt
        signal_text = "今日期权异动数据:\n"
        for i, s in enumerate(signals, 1):
            signal_text += f"{i}. {s['timestamp']} - {s['symbol']} - {s['type']} - Value: {s['value']} (Threshold: {s['threshold']})\n"

        try:
            if not self.client:
                raise ValueError("LLM client not initialized (missing API Key)")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.options_system_prompt},
                    {"role": "user", "content": signal_text}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            
            report_content = response.choices[0].message.content
            logger.info("Options report generated successfully.")
            
            # Push to DingTalk
            await DingTalkAlert.send_alert(
                title="[AI Analyst] 期权异动复盘报告",
                content=report_content,
                symbol="MARKET_REPORT",
                reason="daily_summary"
            )
            
        except Exception as e:
            logger.error(f"LLM options report generation failed: {e}")
        finally:
            # Clear signals after report
            signal_recorder.clear_signals()

    async def generate_stock_report(self, market_type: str = "US"):
        """
        Generate daily stock market report using real-time data from watchlist.
        Fetches watchlist stocks that exceed threshold and generates analysis.
        
        Args:
            market_type: "US" or "HK"
        """
        market_name = "美股" if market_type == "US" else "港股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Get threshold from specific market config
        default_threshold = getattr(Settings, 'PRICE_CHANGE_THRESHOLD', 5.0)
        threshold = default_threshold
        
        if market_type == "US":
            config = getattr(Settings, 'LONGPORT_SYMBOLS_CONFIG', {})
            threshold = float(config.get('thresholds', {}).get('price_change', default_threshold))
        elif market_type == "HK":
            config = getattr(Settings, 'FUTU_SYMBOLS_CONFIG', {})
            threshold = float(config.get('thresholds', {}).get('price_change', default_threshold))
            
        try:
            logger.info(f"Generating {market_name} report for stocks exceeding {threshold}% threshold...")
            
            threshold_stocks = []
            
            if market_type == "US":
                # US Market - Use LongPort
                threshold_stocks = await longport_client.get_threshold_quotes(threshold)

            elif market_type == "HK":
                # HK Market - Use Futu
                from src.api.futu.client import futu_client
                # Run sync method in thread pool to avoid blocking
                threshold_stocks = await asyncio.to_thread(futu_client.get_threshold_quotes, threshold)
            
            # Sort by absolute change rate (most significant first)
            if threshold_stocks:
                threshold_stocks.sort(key=lambda x: abs(x['change_rate']), reverse=True)
            
            if not threshold_stocks:
                logger.info(f"No stocks exceeded {threshold}% threshold for {market_type}")
                # Send notification that no stocks triggered
                title = f"[AI Analyst] {market_name}研报 ({current_time})"
                content = f"当前自选股中无标的涨跌幅超过 {threshold}% 阈值，暂无显著异动。"
                if market_type == "HK":
                    await FeishuAlert.send_alert(title, content)
                else:
                    await DingTalkAlert.send_alert(title, content, "MARKET_REPORT", "no_trigger")
                return
            
            # Calculate stats
            up_count = sum(1 for s in threshold_stocks if s['change_rate'] > 0)
            down_count = len(threshold_stocks) - up_count
            avg_change = sum(s['change_rate'] for s in threshold_stocks) / len(threshold_stocks) if threshold_stocks else 0.0

            # Format alerts for prompt
            alert_text = f"【{market_name}市场日报 - {current_time}】\n\n"
            alert_text += f"**市场整体概况**：\n"
            alert_text += f"- 异动标的总数：{len(threshold_stocks)} 只\n"
            alert_text += f"- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只\n"
            alert_text += f"- 平均涨跌幅：{avg_change:+.2f}%\n\n"
            alert_text += f"**异动标的详情**：\n"
            
            for i, stock in enumerate(threshold_stocks[:15], 1):  # Limit to 15 stocks
                direction = "上涨" if stock['change_rate'] > 0 else "下跌"
                alert_text += f"{i}. {stock['symbol']}: 现价 ${stock['last_price']:.2f}, {direction} {stock['change_rate']:+.2f}%\n"
            
            prompt = f"""作为专业股票分析师，请基于以下{market_name}自选股中**涨跌幅超过 {threshold}% 阈值**的标的列表，生成一份投资分析研报。

【数据概览】
{alert_text}

【研报要求】（严格遵循）
1. 字数：300-500 字之间，必须完整，不要截断
2. 结构：
   - 整体研判：基于上述列表，判断当前市场情绪（50-80字）
   - 板块分析：如有明显的板块集中特征，请指出（80-100字）
   - 重点点评：挑选2-3只最具代表性的股票进行简要点评（100-150字）
   - 投资建议：基于当前数据给出策略建议或风险提示（70-100字）
3. 语言：专业、简洁、有洞察
4. 重要：必须生成完整内容，在500字内完成所有分析，不要出现未完成的句子

请直接输出研报正文，不要包含标题、格式说明或字数标注。"""

            # Call LLM with retry
            if not self.client:
                raise ValueError("LLM client not initialized")
            
            report_content = None
            for attempt in range(3):  # Retry 3 times
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "你是一位资深的股票分析师，擅长基于具体数据进行市场研判。"},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=2000,
                        temperature=1.0
                    )
                    report_content = response.choices[0].message.content
                    if report_content and len(report_content) > 50:  # Valid content
                        break
                    logger.warning(f"Attempt {attempt+1}: Empty or short content, retrying...")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)
            
            # If all retries failed
            if not report_content:
                logger.error("All retry attempts failed")
                raise ValueError("Failed to generate report content after 3 attempts")
            
            logger.info(f"{market_name} report generated successfully with {len(threshold_stocks)} stocks.")
            
            # Push to channel
            title = f"[AI Analyst] {market_name}实时研报 ({current_time})"
            
            if market_type == "HK":
                await FeishuAlert.send_alert(title, report_content)
            else:
                await DingTalkAlert.send_alert(
                    title=title,
                    content=report_content,
                    symbol="MARKET_REPORT",
                    reason="live_analysis"
                )
                
        except Exception as e:
            logger.error(f"Stock report generation failed: {e}")
            # Send fallback
            error_msg = f"AI 研报生成失败: {str(e)[:200]}"
            if market_type == "US":
                await DingTalkAlert.send_alert(
                    title=f"[Error] {market_name}研报生成失败",
                    content=error_msg,
                    symbol="MARKET_REPORT",
                    reason="error"
                )
            elif market_type == "HK":
                await FeishuAlert.send_alert(
                    title=f"[Error] {market_name}研报生成失败",
                    content=error_msg
                )

    async def generate_report(self):
        """
        Main entry point for scheduled report generation.
        Generates both options and stock reports.
        """
        # Generate options report
        await self.generate_options_report()
        
        # Generate stock reports for both markets
        await self.generate_stock_report("US")
        await self.generate_stock_report("HK")
        
        # Clear all recorded data after reports are sent
        signal_recorder.clear_all()

llm_analyst = LLMAnalyst()
