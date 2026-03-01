
import logging
import asyncio
from typing import Optional, Dict
from openai import AsyncOpenAI
from config.settings import Settings
from src.services.signal_recorder import signal_recorder
from src.api.dingtalk import DingTalkAlert

logger = logging.getLogger(__name__)

class LLMAnalyst:
    def __init__(self):
        self.api_key = Settings.LLM_API_KEY
        self.base_url = Settings.LLM_BASE_URL
        self.model = Settings.LLM_MODEL
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url) if self.api_key else None
        
        # System prompt from documentation
        self.system_prompt = """
        你是一位华尔街资深的生物医药期权交易员。我将提供今天盘中触发异动报警的远期期权 (LEAPS) 数据。
        请根据这些数据（如 IV 飙升、成交量激增突破 OI 的 20%、Delta 突破 0.5），为我撰写一份专业的市场复盘报告。
        要求：
        1. 识别出是否有机构(Smart Money)在大量建仓或平仓。
        2. 分析 IV 的变化意味着市场在定价什么潜在事件（如临床数据发布、财报等）。
        3. 语言风格要专业、精炼，直接给出结论和潜在的交易风险。
        4. 使用 Markdown 格式输出，字数控制在 300 字以内。
        """

    async def generate_report(self):
        """
        Generate report from daily signals using LLM and push to DingTalk.
        """
        signals = signal_recorder.get_daily_signals()
        
        if not signals:
            logger.info("No signals recorded today. Skipping report generation.")
            return

        logger.info(f"Generating report for {len(signals)} signals...")
        
        # Format signals for prompt
        signal_text = "今日异动数据:\n"
        for i, s in enumerate(signals, 1):
            signal_text += f"{i}. {s['timestamp']} - {s['symbol']} - {s['type']} - Value: {s['value']} (Threshold: {s['threshold']})\n"

        try:
            if not self.client:
                raise ValueError("LLM client not initialized (missing API Key)")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": signal_text}
                ],
                max_tokens=1000,
                temperature=0.7
            )
            
            report_content = response.choices[0].message.content
            logger.info("Report generated successfully.")
            
            # Push to DingTalk
            await DingTalkAlert.send_alert(
                title="[AI Analyst] 期权异动复盘报告",
                content=report_content,
                symbol="MARKET_REPORT",
                reason="daily_summary"
            )
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback: Push raw signal list
            fallback_content = "LLM Analysis Failed. Raw Signals:\n" + signal_text
            await DingTalkAlert.send_alert(
                title="[Fallback] 期权异动原始数据",
                content=fallback_content[:2000], # Truncate if too long
                symbol="MARKET_REPORT",
                reason="daily_summary_fallback"
            )
        finally:
            # Clear signals after report (or fallback)
            signal_recorder.clear_signals()

llm_analyst = LLMAnalyst()
