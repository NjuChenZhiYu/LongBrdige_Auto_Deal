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
        Generate real-time report from live market data (not from recorded signals).
        This allows manual report generation even when no alerts were triggered.
        
        Args:
            market_type: "US" or "HK"
        """
        from src.api.longport.personalized.watchlist import get_watchlist
        from src.api.longport.client import longport_client
        
        market_name = "美股" if market_type == "US" else "港股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        try:
            logger.info(f"Generating live {market_name} report...")
            
            # Get watchlist symbols
            watchlist_items = await get_watchlist()
            symbols = [item['symbol'] for item in watchlist_items]
            
            if not symbols:
                logger.warning(f"No symbols in watchlist for {market_type}")
                return
            
            # Fetch real-time quotes
            ctx = await longport_client.get_quote_context()
            quotes = await ctx.quote(symbols)
            
            # Filter stocks with significant changes (>3%)
            significant_changes = []
            for q in quotes:
                prev_close = float(getattr(q, 'prev_close', 0))
                last_done = float(getattr(q, 'last_done', 0))
                if prev_close > 0:
                    change_rate = ((last_done - prev_close) / prev_close) * 100
                    if abs(change_rate) >= 3.0:  # Lower threshold for report
                        significant_changes.append({
                            'symbol': q.symbol,
                            'last_price': last_done,
                            'change_rate': change_rate,
                            'prev_close': prev_close
                        })
            
            # Sort by absolute change rate
            significant_changes.sort(key=lambda x: abs(x['change_rate']), reverse=True)
            
            if not significant_changes:
                # Even if no significant changes, report top movers
                all_changes = []
                for q in quotes:
                    prev_close = float(getattr(q, 'prev_close', 0))
                    last_done = float(getattr(q, 'last_done', 0))
                    if prev_close > 0:
                        change_rate = ((last_done - prev_close) / prev_close) * 100
                        all_changes.append({
                            'symbol': q.symbol,
                            'last_price': last_done,
                            'change_rate': change_rate,
                            'prev_close': prev_close
                        })
                all_changes.sort(key=lambda x: abs(x['change_rate']), reverse=True)
                significant_changes = all_changes[:10]  # Top 10 movers
            
            # Build prompt
            up_count = sum(1 for c in significant_changes if c['change_rate'] > 0)
            down_count = len(significant_changes) - up_count
            avg_change = sum(c['change_rate'] for c in significant_changes) / len(significant_changes) if significant_changes else 0
            
            alert_text = f"【{market_name}市场实时观察 - {current_time}】\n\n"
            alert_text += f"**市场整体概况**：\n"
            alert_text += f"- 监控标的总数：{len(symbols)} 只\n"
            alert_text += f"- 显著异动标的：{len(significant_changes)} 只\n"
            alert_text += f"- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只\n"
            alert_text += f"- 平均涨跌幅：{avg_change:+.2f}%\n\n"
            alert_text += f"**重点标的详情**：\n"
            
            for i, c in enumerate(significant_changes[:15], 1):
                symbol = c['symbol']
                price = c['last_price']
                change = c['change_rate']
                direction = "📈上涨" if change > 0 else "📉下跌"
                alert_text += f"{i}. {symbol}: ${price:.2f}, 涨跌幅 {change:+.2f}%, {direction}\n"
            
            # Call LLM
            if not self.client:
                raise ValueError("LLM client not initialized")
            
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
            logger.info(f"Live {market_name} report generated successfully.")
            
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
