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
        
        # Stock market report system prompt (new)
        self.stock_system_prompt = """你是一位资深的股票市场分析师，擅长宏观经济研判和个股异动分析。
        我将提供当天触发价格异动告警的股票列表。
        请基于这些数据撰写一份专业的市场观察日报。
        要求：
        1. 市场整体研判：基于涨跌分布和平均涨跌，给出市场整体情绪判断（乐观/谨慎/观望）。
        2. 板块/热点分析：识别是否有明显的板块集中异动特征。
        3. 重点个股点评：挑选2-3只异动最剧烈或最具代表性的股票进行简要点评。
        4. 次日展望：基于当前市场状态，给出简要的投资建议或风险提示。
        5. 语言风格要专业、有洞察，直接给出结论。
        6. 使用 Markdown 格式输出，字数控制在 300 字左右。
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
                max_tokens=1000,
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
        Generate daily stock market report from recorded alerts.
        
        Args:
            market_type: "US" or "HK" to filter alerts
        """
        all_alerts = signal_recorder.get_daily_stock_alerts()
        
        # Filter by market type
        alerts = [a for a in all_alerts if a.get("market_type") == market_type]
        
        if not alerts:
            logger.info(f"No {market_type} stock alerts recorded today. Skipping report generation.")
            return

        logger.info(f"Generating {market_type} stock report for {len(alerts)} alerts...")
        
        # Calculate statistics
        up_count = sum(1 for a in alerts if a.get('change_rate', 0) > 0)
        down_count = len(alerts) - up_count
        avg_change = sum(a.get('change_rate', 0) for a in alerts) / len(alerts) if alerts else 0
        
        market_name = "美股" if market_type == "US" else "港股"
        current_time = datetime.now().strftime("%Y-%m-%d")
        
        # Format alerts for prompt
        alert_text = f"【{market_name}市场日报 - {current_time}】\n\n"
        alert_text += f"**市场整体概况**：\n"
        alert_text += f"- 异动标的总数：{len(alerts)} 只\n"
        alert_text += f"- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只\n"
        alert_text += f"- 平均涨跌幅：{avg_change:+.2f}%\n\n"
        alert_text += f"**异动标的详情**：\n"
        
        for i, a in enumerate(alerts[:15], 1):  # Limit to 15 stocks
            symbol = a.get('symbol', 'Unknown')
            price = a.get('last_price', 0)
            change = a.get('change_rate', 0)
            volume = a.get('volume', 0)
            direction = "📈上涨" if change > 0 else "📉下跌"
            
            alert_text += f"{i}. {symbol}: ${price:.2f}, 涨跌幅 {change:+.2f}%, {direction}, 成交量 {volume:,}\n"

        try:
            if not self.client:
                raise ValueError("LLM client not initialized (missing API Key)")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.stock_system_prompt},
                    {"role": "user", "content": alert_text}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            report_content = response.choices[0].message.content
            logger.info(f"{market_name} stock report generated successfully.")
            
            # Push to appropriate channel
            title = f"[AI Analyst] {market_name}市场日报 ({current_time})"
            
            if market_type == "HK":
                await FeishuAlert.send_alert(title, report_content)
            else:
                await DingTalkAlert.send_alert(
                    title=title,
                    content=report_content,
                    symbol="MARKET_REPORT",
                    reason="daily_stock_summary"
                )
            
        except Exception as e:
            logger.error(f"LLM {market_name} stock report generation failed: {e}")
            # Fallback: Push raw data
            fallback_content = f"AI 报告生成失败。原始数据:\n\n{alert_text[:1500]}"
            if market_type == "US":
                await DingTalkAlert.send_alert(
                    title=f"[Fallback] {market_name}市场原始数据",
                    content=fallback_content,
                    symbol="MARKET_REPORT",
                    reason="daily_summary_fallback"
                )

    async def generate_live_report(self, market_type: str = "US"):
        """
        Generate real-time report based on watchlist stocks that exceed threshold.
        Only include stocks with significant changes (>= threshold) in the analysis.
        
        Args:
            market_type: "US" or "HK"
        """
        from src.api.longport.personalized.watchlist import get_watchlist
        from src.api.longport.client import longport_client
        from config.settings import Settings
        
        market_name = "美股" if market_type == "US" else "港股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Get threshold from settings (default 5%)
        threshold = getattr(Settings, 'PRICE_CHANGE_THRESHOLD', 5.0)
        
        try:
            logger.info(f"Generating {market_name} report for stocks exceeding {threshold}% threshold...")
            
            # Get watchlist symbols (with deduplication)
            watchlist_items = await get_watchlist()
            symbols = list(set([item['symbol'] for item in watchlist_items]))
            
            if not symbols:
                logger.warning(f"No symbols in watchlist for {market_type}")
                return
            
            # Fetch real-time quotes
            ctx = await longport_client.get_quote_context()
            quotes = await ctx.quote(symbols)
            
            if not quotes:
                logger.warning(f"No quotes returned for {market_type}")
                return
            
            # Filter stocks that EXCEED threshold (with deduplication)
            threshold_stocks = []
            seen_symbols = set()  # Track seen symbols for deduplication
            
            for q in quotes:
                if q is None:
                    continue
                symbol = getattr(q, 'symbol', None)
                if not symbol or symbol in seen_symbols:  # Skip if already seen
                    continue
                prev_close = float(getattr(q, 'prev_close', 0) or 0)
                last_done = float(getattr(q, 'last_done', 0) or 0)
                if prev_close > 0:
                    change_rate = ((last_done - prev_close) / prev_close) * 100
                    if abs(change_rate) >= threshold:  # Only stocks exceeding threshold
                        threshold_stocks.append({
                            'symbol': symbol,
                            'last_price': last_done,
                            'change_rate': change_rate,
                            'prev_close': prev_close
                        })
                        seen_symbols.add(symbol)  # Mark as seen
            
            # Sort by absolute change rate (most significant first)
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
            
            # Build stock list for LLM
            stock_list_text = ""
            for i, stock in enumerate(threshold_stocks[:20], 1):  # Top 20
                direction = "上涨" if stock['change_rate'] > 0 else "下跌"
                stock_list_text += f"{i}. {stock['symbol']}: 现价 ${stock['last_price']:.2f}, {direction} {stock['change_rate']:+.2f}%\n"
            
            # Build prompt for LLM
            up_count = sum(1 for s in threshold_stocks if s['change_rate'] > 0)
            down_count = len(threshold_stocks) - up_count
            
            prompt = f"""作为专业股票分析师，请基于以下{market_name}自选股中**涨跌幅超过 {threshold}% 阈值**的标的列表，生成一份投资分析研报。

【筛选条件】
- 监控范围：自选股共 {len(symbols)} 只
- 阈值条件：|涨跌幅| >= {threshold}%
- 触发标的：{len(threshold_stocks)} 只（上涨 {up_count} 只，下跌 {down_count} 只）

【超出阈值的标的列表】
{stock_list_text}

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
                        max_tokens=4096,
                        temperature=0.7
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
            
            logger.info(f"Live {market_name} report generated successfully with {len(threshold_stocks)} stocks.")
            
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
            logger.error(f"Live report generation failed: {e}")
            # Send fallback
            error_msg = f"AI 研报生成失败: {str(e)[:200]}"
            if market_type == "US":
                await DingTalkAlert.send_alert(
                    title=f"[Error] {market_name}研报生成失败",
                    content=error_msg,
                    symbol="MARKET_REPORT",
                    reason="error"
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
