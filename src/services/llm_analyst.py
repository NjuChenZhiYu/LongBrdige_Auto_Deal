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
from src.api.adanos_client import adanos_client

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
        
        # Options report prompt (merged)
        self.options_prompt_template = """你是一位华尔街资深的生物医药期权交易员。我将提供今天盘中触发异动报警的远期期权 (LEAPS) 数据。
请根据这些数据（如 IV 飙升、成交量激增突破 OI 的 20%、Delta 突破 0.5），为我撰写一份专业的市场复盘报告。

要求：
1. 识别出是否有机构(Smart Money)在大量建仓或平仓。
2. 分析 IV 的变化意味着市场在定价什么潜在事件（如临床数据发布、财报等）。
3. 语言风格要专业、精炼，直接给出结论和潜在的交易风险。
4. 使用 Markdown 格式输出，字数控制在 300 字以内。

今日期权异动数据:
{signal_text}"""

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
        signal_text = ""
        for i, s in enumerate(signals, 1):
            signal_text += f"{i}. {s['timestamp']} - {s['symbol']} - {s['type']} - Value: {s['value']} (Threshold: {s['threshold']})\n"
            
        prompt = self.options_prompt_template.format(signal_text=signal_text)

        try:
            if not self.us_client:
                raise ValueError("US LLM client not initialized (missing API Key)")

            report_content = ""
            for attempt in range(3):
                try:
                    stream = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=3000,
                        temperature=0.7,
                        stream=True
                    )
                    
                    full_content = ""
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            full_content += content
                    
                    report_content = full_content
                    if report_content and len(report_content) > 50:
                        break
                    
                    logger.warning(f"[Gemini/Options] Attempt {attempt+1}: Empty or short content, retrying...")
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"[Gemini/Options] Attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(2)

            if not report_content:
                raise ValueError("Failed to generate options report after 3 attempts")
            
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

    async def generate_longport_us_report(self, trigger_type: str = 'CRON'):
        """
        Generate daily US stock market report using real-time data from LongPort watchlist.
        Fetches watchlist stocks that exceed threshold and generates analysis.
        """
        market_name = "美股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        today_date = datetime.now().strftime("%Y-%m-%d")
        
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
                
                # Still record empty report if triggered manually or at specific time? 
                # Spec says "daily_reports -> Append". Maybe skip if empty content?
                # But for anomaly_stocks, nothing to save.
                return
            
            # Save anomaly stocks if requested
            # Calculate stats
            up_count = sum(1 for s in threshold_stocks if s['change_rate'] > 0)
            down_count = len(threshold_stocks) - up_count
            avg_change = sum(s['change_rate'] for s in threshold_stocks) / len(threshold_stocks) if threshold_stocks else 0.0

            # Build stock details with names
            stock_details = []
            
            for i, stock in enumerate(threshold_stocks[:15], 1):
                symbol = stock.get('symbol', 'Unknown')
                price = stock['last_price']
                change = stock['change_rate']
                direction = "📈" if change > 0 else "📉"
                
                # Fetch sentiment labels from Adanos API
                sentiment_labels = await adanos_client.get_sentiment_labels(symbol)
                sentiment_text = f" [{', '.join(sentiment_labels)}]" if sentiment_labels else ""
                
                # Fetch capital flow data from LongPort
                try:
                    capital_data = await longport_client.get_capital_flow(symbol)
                    flow_label, smart_net, retail_net = longport_client.analyze_us_capital_flow(capital_data, change)
                except Exception as e:
                    logger.error(f"Failed to get US capital flow for {symbol}: {e}")
                    flow_label, smart_net, retail_net = "分析不可用", 0, 0
                
                stock_details.append(
                    f"{i}. {symbol} 现价${price:.2f} ({change:+.2f}%) {direction}{sentiment_text}\n"
                    f"   - 【内部量化系统研判】：{flow_label}\n"
                    f"   - (资金支撑：主力净流 {smart_net}万, 散户净流 {retail_net}万)"
                )
            
            stocks_text = "\n".join(stock_details)
            
            # Build prompt for Gemini
            prompt = f"""你是一个顶级的量化分析师。以下是触发监控阈值的异动美股股票列表及【底层资金流向数据】与【市场情绪标签】：

【报告时间】{current_time}

【市场整体概况】
- 异动标的总数：{len(threshold_stocks)} 只
- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只
- 平均涨跌幅：{avg_change:+.2f}%
- 监控阈值：涨跌幅绝对值 ≥ {threshold}%

【异动标的详情】
{stocks_text}

请严格按照以下结构和字数要求，生成一份专业的市场快报：
1. **市场综述**（80-100字）：基于涨跌分布判断市场整体情绪。
2. **板块热点**（80-100字）：识别是否有生物医药、机器人、AI、半导体等板块的集中异动。
3. **重点个股深度剖析**（200-350字）：必须将【内部量化系统研判】（代表真实的资金博弈，如主力洗盘、机构出逃）与附带的【情绪标签】（代表市场舆情和散户情绪）结合分析。重点寻找二者的“共振”（如情绪高涨且主力资金净流入，强化上涨逻辑）或“背离”（如情绪高涨但主力暗中出逃，提示诱多陷阱；情绪低迷但主力暗中吸筹，提示洗盘机会）。深度点评主散博弈状态，刺穿涨跌幅的表象，揭示背后的真实交易逻辑。
4. **具体交易策略**（100-150字）：拒绝宏观套话（如“谨慎乐观”、“重个股轻指数”），必须**直接点名上述异动标的**给出具体的实操建议。明确指出哪些标的（结合资金与情绪数据）可顺势跟多，哪些标的（如主力暗中出逃）存在诱多风险需坚决规避或逢高做空，哪些建议观望。要求观点鲜明、一针见血。

语言要求：专业、简洁、有美股特色，使用 Markdown 格式，字数350-450字。"""
            # Call LLM with retry
            if not self.us_client:
                raise ValueError("US LLM client not initialized")
            
            report_content = None
            # Define valid completion endings
            valid_endings = ('.', '。', '!', '！', '?', '？', ']', '】', '）')
            
            for attempt in range(3):  # Retry 3 times
                try:
                    logger.info(f"Attempt {attempt+1} to generate US report...")
                    stream = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=4000,  # Increased max_tokens
                        temperature=1.0,
                        stream=True
                    )
                    
                    full_content = ""
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            full_content += content
                    
                    # Validate content
                    content = full_content.strip()
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
            import traceback
            logger.error(f"US Stock report generation failed: {e}\n{traceback.format_exc()}")
            # Send fallback
            error_msg = f"AI 研报生成失败: {str(e)[:200]}"
            await DingTalkAlert.send_alert(
                title=f"[Error] {market_name}研报生成失败",
                content=error_msg,
                symbol="MARKET_REPORT",
                reason="error"
            )

    async def generate_futu_hk_report(self, threshold: float = None, trigger_type: str = 'CRON'):
        """
        Generate HK market report specifically for Futu data using Kimi.
        This is the dedicated method for Futu HK stock analysis.
        
        Args:
            threshold: Price change threshold percentage. Uses config default if None.
        """
        from src.api.futu.client import futu_client
        
        market_name = "港股"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        today_date = datetime.now().strftime("%Y-%m-%d")
        
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
                code = stock.get('code')
                price = stock['last_price']
                change = stock['change_rate']
                direction = "📈" if change > 0 else "📉"
                
                # Fetch capital flow data
                try:
                    capital_data = await asyncio.to_thread(futu_client.get_capital_flow, code)
                    flow_label, smart_net, retail_net = futu_client.analyze_capital_flow(capital_data, change)
                except Exception as e:
                    logger.error(f"Failed to get capital flow for {code}: {e}")
                    flow_label, smart_net, retail_net = "分析不可用", 0, 0
                    
                # Fetch historical k-lines and calculate EMA derivatives
                try:
                    klines_df = await asyncio.to_thread(futu_client.get_hk_historical_klines, code, 60)
                    if klines_df is not None and not klines_df.empty:
                        from src.analysis.futu_math_indicator import calculate_ema_derivatives
                        ema_data = calculate_ema_derivatives(klines_df)
                        ema_tag = ema_data['tag']
                        v5, a5, bias20 = ema_data['v5'], ema_data['a5'], ema_data['bias20']
                        ema_text = f"   - 【量化技术面】：{ema_tag} (V5: {v5}%, A5: {a5}%, Bias20: {bias20}%)"
                    else:
                        ema_text = f"   - 【量化技术面】：数据缺失"
                except Exception as e:
                    logger.error(f"Failed to calculate EMA for {code}: {e}")
                    ema_text = f"   - 【量化技术面】：计算错误"
                
                stock_details.append(
                    f"{i}. {symbol} 现价${price:.2f} ({change:+.2f}%) {direction}\n"
                    f"   - 【内部量化系统研判】：{flow_label}\n"
                    f"   - (资金支撑：主力净流 {smart_net}万, 散户净流 {retail_net}万)\n"
                    f"{ema_text}"
                )
            
            stocks_text = "\n".join(stock_details)
            
            # Build prompt for Gemini
            prompt = f"""你是一个顶级的量化分析师。以下是触发监控阈值的异动香港股票列表及【底层资金流向数据】与【量化技术面数据】：

【报告时间】{current_time}

【市场整体概况】
- 异动标的总数：{len(threshold_stocks)} 只
- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只
- 平均涨跌幅：{avg_change:+.2f}%
- 监控阈值：涨跌幅绝对值 ≥ {threshold}%

【异动标的详情】
{stocks_text}

请严格按照以下结构和字数要求，生成一份专业的市场快报：
1. **市场综述**（80-100字）：基于涨跌分布判断市场整体情绪。
2. **板块热点**（80-100字）：识别是否有机器人、物流、航天、能源、半导体等板块的集中异动。
3. **重点个股深度剖析**（200-350字）：必须将【内部量化系统研判】（代表真实的资金博弈，如主力洗盘、机构出逃）与【量化技术面】（基于多周期EMA均线与乖离率的数学引擎结果，如V型反转预备、长短共振等）结合分析。深度点评主力和散户的博弈状态，刺穿涨跌幅的表象。若出现左侧极端信号（如极度超跌）或右侧共振信号，需重点提示其背后的均值回归或顺势加速逻辑。
4. **具体交易策略**（100-150字）：拒绝宏观套话（如“谨慎乐观”、“重个股轻指数”），必须**直接点名上述异动标的**给出具体的实操建议。明确指出哪些标的（结合资金数据与技术面信号）可顺势跟多或左侧抄底，哪些标的（如机构出逃或估值透支）存在诱多风险需坚决规避或逢高做空，哪些建议观望。要求观点鲜明、一针见血。

语言要求：专业、简洁、有港股特色，使用 Markdown 格式，字数350-450字。"""

            # Use US Client (Gemini) instead of HK Client (Kimi)
            if not self.us_client:
                raise ValueError("US LLM client (Gemini) not initialized")
            
            # Call Gemini API with streaming
            report_content = ""
            for attempt in range(3):
                try:
                    stream = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=4000,
                        temperature=0.7,
                        stream=True
                    )
                    
                    full_content = ""
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            full_content += content
                            
                    report_content = full_content
                    if report_content and len(report_content) > 100:
                        break
                    
                    logger.warning(f"[Gemini/Futu] Attempt {attempt+1}: Empty or short content ({len(report_content) if report_content else 0} chars), retrying...")
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
            import traceback
            logger.error(f"[Gemini/Futu] Failed to generate HK report: {e}\n{traceback.format_exc()}")
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
