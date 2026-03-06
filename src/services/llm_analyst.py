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
        # US/LongPort Client (Gemini)
        self.us_api_key = Settings.LLM_API_KEY
        self.us_base_url = Settings.LLM_BASE_URL
        self.us_model = Settings.LLM_MODEL
        self.us_client = AsyncOpenAI(api_key=self.us_api_key, base_url=self.us_base_url) if self.us_api_key else None

        # HK/Futu Client (Kimi)
        self.hk_api_key = Settings.KIMI_API_KEY
        self.hk_base_url = Settings.KIMI_LLM_BASE_URL
        self.hk_model = Settings.KIMI_LLM_MODEL
        self.hk_client = AsyncOpenAI(api_key=self.hk_api_key, base_url=self.hk_base_url) if self.hk_api_key else None
        
        # Options report system prompt (existing)
        self.options_system_prompt = """你是一位华尔街资深的生物医药期权交易员。我将提供今天盘中触发异动报警的远期期权 (LEAPS) 数据。
请根据这些数据（如 IV 飙升、成交量激增突破 OI 的 20%、Delta 突破 0.5），为我撰写一份专业的市场复盘报告。
        要求：
        1. 识别出是否有机构(Smart Money)在大量建仓或平仓。
        2. 分析 IV 的变化意味着市场在定价什么潜在事件（如临床数据发布、财报等）。
        3. 语言风格要专业、精炼，直接给出结论和潜在的交易风险。
        4. 使用 Markdown 格式输出，字数控制在 300 字以内。
        """
        
        # HK Stock report system prompt (optimized for Kimi)
        self.hk_stock_system_prompt = """你是一位资深的港股市场分析师，擅长港股通、科技股和中资股的异动分析。
请基于提供的港股数据撰写专业的市场观察日报。
要求：
1. 市场整体研判：基于涨跌分布和平均涨跌，判断港股市场情绪（乐观/谨慎/观望/恐慌）。
2. 板块/热点分析：识别是否有明显的板块集中异动（如科技股、金融股、地产股的集体异动）。
3. 重点个股点评：挑选2-3只最具代表性的港股进行简要点评，包括代码和名称。
4. 资金流向：分析是否有明显的南向资金或机构资金动向。
5. 次日展望：基于当前港股状态，给出简要的投资策略建议或风险提示。
6. 语言风格：专业、有洞察，结合港股特有的市场环境（如受美股影响、A股联动等）。
7. 格式：使用 Markdown，字数控制在 350-450 字之间。
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
            if not self.us_client:
                raise ValueError("US LLM client not initialized (missing API Key)")

            response = await self.us_client.chat.completions.create(
                model=self.us_model,
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

    async def generate_longport_us_report(self):
        """
        Generate daily US stock market report using real-time data from LongPort watchlist.
        Fetches watchlist stocks that exceed threshold and generates analysis.
        """
        market_name = "美股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Get threshold from US market config
        default_threshold = getattr(Settings, 'PRICE_CHANGE_THRESHOLD', 5.0)
        config = getattr(Settings, 'LONGPORT_SYMBOLS_CONFIG', {})
        threshold = float(config.get('thresholds', {}).get('price_change', default_threshold))
            
        try:
            logger.info(f"Generating {market_name} report for stocks exceeding {threshold}% threshold...")
            
            # US Market - Use LongPort
            threshold_stocks = await longport_client.get_threshold_quotes(threshold)
            
            # Sort by absolute change rate (most significant first)
            if threshold_stocks:
                threshold_stocks.sort(key=lambda x: abs(x['change_rate']), reverse=True)
            
            if not threshold_stocks:
                logger.info(f"No stocks exceeded {threshold}% threshold for US")
                # Send notification that no stocks triggered
                title = f"[AI Analyst] {market_name}研报 ({current_time})"
                content = f"当前自选股中无标的涨跌幅超过 {threshold}% 阈值，暂无显著异动。"
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
            
            # US market - use standard prompt
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
            system_prompt = "你是一位资深的股票分析师，擅长基于具体数据进行市场研判。"

            # Call LLM with retry
            if not self.us_client:
                raise ValueError("US LLM client not initialized")
            
            report_content = None
            # Define valid completion endings
            valid_endings = ('.', '。', '!', '！', '?', '？', ']', '】', '）')
            
            for attempt in range(3):  # Retry 3 times
                try:
                    logger.info(f"Attempt {attempt+1} to generate US report...")
                    response = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=3000,  # Increased max_tokens
                        temperature=1.0
                    )
                    
                    # Validate content
                    content = response.choices[0].message.content.strip() if response.choices else ""
                    if content and len(content) > 150 and content.endswith(valid_endings):
                        report_content = content
                        logger.info(f"Attempt {attempt+1} successful.")
                        break
                    
                    logger.warning(f"Attempt {attempt+1}: Invalid content received (length: {len(content)}, ends with: '{content[-5:]}'). Retrying...")
                    await asyncio.sleep(2 * (attempt + 1)) # Increase sleep time for each retry
                    
                except Exception as e:
                    logger.error(f"Attempt {attempt+1} failed with exception: {e}")
                    if attempt < 2:
                        await asyncio.sleep(3 * (attempt + 1)) # Longer sleep on exception
            
            # If all retries failed
            if not report_content:
                logger.error("All retry attempts failed to get a valid report.")
                # Send a specific failure message instead of raising an exception
                error_msg = f"AI 研报生成失败：模型服务暂时过载或不稳定 (API返回503或内容不完整)。请稍后重试。"
                title = f"[Error] {market_name}研报生成失败 ({current_time})"
                await DingTalkAlert.send_alert(title, error_msg, "MARKET_REPORT", "generation_failed")
                return # Stop execution to avoid sending partial report
            
            logger.info(f"{market_name} report generated successfully with {len(threshold_stocks)} stocks.")
            
            # Push to channel
            title = f"[AI Analyst] {market_name}实时研报 ({current_time})"
            
            await DingTalkAlert.send_alert(
                title=title,
                content=report_content,
                symbol="MARKET_REPORT",
                reason="live_analysis"
            )
                
        except Exception as e:
            logger.error(f"US Stock report generation failed: {e}")
            # Send fallback
            error_msg = f"AI 研报生成失败: {str(e)[:200]}"
            await DingTalkAlert.send_alert(
                title=f"[Error] {market_name}研报生成失败",
                content=error_msg,
                symbol="MARKET_REPORT",
                reason="error"
            )

    async def generate_futu_hk_report(self, threshold: float = None):
        """
        Generate HK market report specifically for Futu data using Kimi.
        This is the dedicated method for Futu HK stock analysis.
        
        Args:
            threshold: Price change threshold percentage. Uses config default if None.
        """
        from src.api.futu.client import futu_client
        
        market_name = "港股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Get threshold from config
        if threshold is None:
            default_threshold = getattr(Settings, 'PRICE_CHANGE_THRESHOLD', 5.0)
            config = getattr(Settings, 'FUTU_SYMBOLS_CONFIG', {})
            threshold = float(config.get('thresholds', {}).get('price_change', default_threshold))
        
        try:
            logger.info(f"[Gemini/Futu] Generating HK report for stocks exceeding {threshold}% threshold...")
            
            # Fetch threshold stocks from Futu
            threshold_stocks = await asyncio.to_thread(futu_client.get_threshold_quotes, threshold)
            
            if not threshold_stocks:
                logger.info(f"[Gemini/Futu] No HK stocks exceeded {threshold}% threshold")
                title = f"[Gemini研报] 港股市场观察 ({current_time})"
                content = f"📊 **港股市场观察**\n\n当前富途自选股中无标的涨跌幅超过 **{threshold}%** 阈值，暂无显著异动。\n\n> 监控时间：{current_time}"
                await FeishuAlert.send_alert(title, content)
                return
            
            # Sort by absolute change rate
            threshold_stocks.sort(key=lambda x: abs(x['change_rate']), reverse=True)
            
            # Calculate stats
            up_count = sum(1 for s in threshold_stocks if s['change_rate'] > 0)
            down_count = len(threshold_stocks) - up_count
            avg_change = sum(s['change_rate'] for s in threshold_stocks) / len(threshold_stocks)
            
            # Build stock details with names
            stock_details = []
            for i, stock in enumerate(threshold_stocks[:15], 1):
                symbol = stock.get('symbol', stock.get('code', 'Unknown'))
                price = stock['last_price']
                change = stock['change_rate']
                direction = "📈" if change > 0 else "📉"
                stock_details.append(f"{i}. {symbol} 现价${price:.2f} ({change:+.2f}%) {direction}")
            
            stocks_text = "\n".join(stock_details)
            
            # Build prompt for Gemini
            prompt = f"""请基于以下港股市场数据，生成一份专业的港股异动观察报告。

【报告时间】{current_time}

【市场整体概况】
- 异动标的总数：{len(threshold_stocks)} 只
- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只
- 平均涨跌幅：{avg_change:+.2f}%
- 监控阈值：涨跌幅绝对值 ≥ {threshold}%

【异动标的详情】
{stocks_text}

【报告要求】
1. **市场综述**（80-100字）：基于涨跌分布判断港股整体情绪
2. **板块热点**（80-100字）：识别是否有机器人、物流、航天、能源等板块的集中异动
3. **重点个股**（100-150字）：点评2-3只最具代表性的港股异动
4. **策略建议**（70-100字）：结合港股通、南向资金等角度给出投资建议

语言要求：专业、简洁、有港股特色，使用 Markdown 格式，字数350-450字。"""

            # Use US Client (Gemini) instead of HK Client (Kimi)
            if not self.us_client:
                raise ValueError("US LLM client (Gemini) not initialized")
            
            # Call Gemini API
            report_content = None
            for attempt in range(3):
                try:
                    response = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[
                            {"role": "system", "content": self.hk_stock_system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=1500,
                        temperature=0.7
                    )
                    report_content = response.choices[0].message.content
                    if report_content and len(report_content) > 100:
                        break
                    logger.warning(f"[Gemini/Futu] Attempt {attempt+1}: Empty or short content, retrying...")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"[Gemini/Futu] Attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)
            
            if not report_content:
                raise ValueError("Failed to generate report after 3 attempts")
            
            logger.info(f"[Gemini/Futu] HK report generated successfully with {len(threshold_stocks)} stocks")
            
            # Add header to report
            full_report = f"""🦞 **Gemini 智能研报** | 港股市场观察 | {current_time}

---

{report_content}

---

📊 **数据统计**：异动{len(threshold_stocks)}只 | 涨{up_count}只 | 跌{down_count}只 | 平均{avg_change:+.2f}%
🔔 **数据来源**：富途自选股 | **AI模型**：Gemini"""
            
            # Send to Feishu
            title = f"[Gemini研报] 港股市场观察 ({current_time})"
            await FeishuAlert.send_alert(title, full_report)
            logger.info(f"[Gemini/Futu] Report sent to Feishu successfully")
            
        except Exception as e:
            logger.error(f"[Gemini/Futu] Failed to generate HK report: {e}")
            # Send error notification
            error_title = f"[Gemini研报] 港股报告生成失败 ({current_time})"
            error_content = f"❌ **报告生成失败**\n\n错误信息：{str(e)[:200]}\n\n请检查：\n1. LLM_API_KEY (Gemini) 是否配置正确\n2. 富途API连接是否正常\n3. 网络连接状态"
            await FeishuAlert.send_alert(error_title, error_content)

    async def generate_report(self):
        """
        Main entry point for scheduled report generation.
        Generates both options and stock reports.
        """
        # Generate options report
        await self.generate_options_report()
        
        # Generate stock reports for both markets
        await self.generate_longport_us_report()
        await self.generate_futu_hk_report()
        
        # Clear all recorded data after reports are sent
        signal_recorder.clear_all()

llm_analyst = LLMAnalyst()
