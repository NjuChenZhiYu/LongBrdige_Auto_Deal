"""
Kimi-powered Real-time Option Strategy Analyzer
使用 Moonshot Kimi 进行实时期权策略分析
"""

import logging
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime
from openai import AsyncOpenAI
from config.settings import Settings
from src.services.signal_recorder import signal_recorder
from src.api.notification import AlertManager

logger = logging.getLogger(__name__)


class KimiOptionAnalyzer:
    """
    Kimi (Moonshot) LLM 期权策略实时分析器
    
    功能：
    1. 实时分析单个期权异动信号
    2. 批量分析多信号组合
    3. 飞书富文本推送
    4. 支持盘中实时预警（非仅日终报告）
    """
    
    def __init__(self):
        # Kimi (Moonshot) Configuration
        self.api_key = Settings.LLM_API_KEY
        # 使用 Moonshot API
        self.base_url = Settings.LLM_BASE_URL or "https://api.moonshot.cn/v1"
        self.model = Settings.LLM_MODEL or "kimi-k2.5"
        
        # 初始化 OpenAI 兼容客户端
        self.client = None
        if self.api_key:
            self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(f"Kimi Analyzer initialized with model: {self.model}")
        else:
            logger.warning("Kimi Analyzer: LLM_API_KEY not configured")
        
        # 实时分析系统提示词 - 针对单个信号快速分析
        self.realtime_system_prompt = """你是一位华尔街资深期权交易员，专注于生物医药LEAPS期权。

任务：对盘中触发的期权异动信号进行快速专业分析（100字以内）。

分析维度：
1. 信号含义（IV飙升/量能异常/Delta突破意味着什么）
2. 可能的驱动事件（临床数据、FDA审批、财报等）
3. 风险提示（流动性、时间损耗、方向风险）
4. 操作建议（观望/小仓位跟进/避免追高）

风格要求：
- 专业、直接、不废话
- 使用中文
- 禁用"可能""也许"等模糊词，给出确定性判断
- 如果有明确结论，直接说"建议X""避免Y"

输出格式（严格遵循）：
【信号解读】一句话说明异动含义
【事件推测】最可能的催化事件
【风险提示】最大风险点
【操作建议】具体操作建议"""

        # 批量分析报告系统提示词
        self.batch_system_prompt = """你是一位华尔街资深生物医药期权交易员。

任务：基于今日盘中多个LEAPS期权异动信号，撰写专业复盘分析。

要求：
1. 识别Smart Money动向（建仓/平仓/调仓）
2. 分析IV变动隐含的潜在事件定价
3. 评估整体市场情绪（恐慌/贪婪/预期兑现）
4. 给出明日交易策略建议

格式：
- Markdown 格式
- 字数 200-300 字
- 分点清晰，直接给出结论
- 中文输出"""

    async def analyze_signal_realtime(self, signal: Dict[str, Any], 
                                     option_details: Optional[Dict] = None) -> Optional[str]:
        """
        对单个信号进行实时 Kimi 分析
        
        Args:
            signal: 信号字典，包含 type, symbol, value, threshold 等
            option_details: 期权详细信息（标的价、到期日、IV历史等）
        
        Returns:
            分析报告文本，失败返回 None
        """
        if not self.client:
            logger.error("Kimi client not initialized")
            return None
        
        # 构建提示词
        prompt = self._build_realtime_prompt(signal, option_details)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.realtime_system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3  # 较低温度，更确定性
            )
            
            analysis = response.choices[0].message.content
            logger.info(f"Kimi realtime analysis generated for {signal['symbol']}")
            return analysis
            
        except Exception as e:
            logger.error(f"Kimi realtime analysis failed: {e}")
            return None
    
    async def analyze_batch_signals(self, signals: List[Dict[str, Any]]) -> Optional[str]:
        """
        批量分析当日所有信号（日终报告）
        
        Args:
            signals: 当日所有信号列表
        
        Returns:
            批量分析报告
        """
        if not self.client:
            logger.error("Kimi client not initialized")
            return None
        
        if not signals:
            logger.info("No signals to analyze")
            return None
        
        # 格式化信号数据
        signal_text = self._format_signals_for_analysis(signals)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.batch_system_prompt},
                    {"role": "user", "content": signal_text}
                ],
                max_tokens=800,
                temperature=0.5
            )
            
            report = response.choices[0].message.content
            logger.info(f"Kimi batch report generated for {len(signals)} signals")
            return report
            
        except Exception as e:
            logger.error(f"Kimi batch analysis failed: {e}")
            return None
    
    async def push_realtime_alert(self, signal: Dict[str, Any], 
                                  option_details: Optional[Dict] = None):
        """
        实时分析并推送飞书告警
        
        Args:
            signal: 触发信号
            option_details: 期权详情
        """
        # 1. 生成 Kimi 分析
        analysis = await self.analyze_signal_realtime(signal, option_details)
        
        if not analysis:
            # 降级：推送原始信号
            await self._push_fallback_alert(signal)
            return
        
        # 2. 飞书富文本推送
        await self._push_feishu_rich_alert(signal, analysis, option_details)
    
    async def push_daily_summary(self):
        """
        推送日终汇总报告
        """
        signals = signal_recorder.get_daily_signals()
        
        if not signals:
            logger.info("No signals for daily summary")
            return
        
        # 生成批量分析
        report = await self.analyze_batch_signals(signals)
        
        if report:
            # 飞书推送日终报告
            await self._push_feishu_daily_report(signals, report)
        else:
            # 降级推送
            await self._push_fallback_daily_report(signals)
        
        # 清空当日信号
        signal_recorder.clear_signals()
    
    def _build_realtime_prompt(self, signal: Dict[str, Any], 
                               option_details: Optional[Dict]) -> str:
        """构建实时分析提示词"""
        symbol = signal['symbol']
        signal_type = signal['type']
        value = signal['value']
        threshold = signal['threshold']
        timestamp = signal.get('timestamp', datetime.now().strftime("%H:%M:%S"))
        details = signal.get('details', '')
        
        prompt = f"""期权异动信号：

标的：{symbol}
时间：{timestamp}
信号类型：{signal_type}
触发值：{value}
阈值：{threshold}
详情：{details}
"""
        
        if option_details:
            prompt += f"""
期权信息：
- 标的股价：{option_details.get('underlying_price', 'N/A')}
- 行权价：{option_details.get('strike_price', 'N/A')}
- 到期日：{option_details.get('expiry_date', 'N/A')}
- 当前IV：{option_details.get('implied_volatility', 'N/A')}
- 成交量：{option_details.get('volume', 'N/A')}
- 持仓量：{option_details.get('open_interest', 'N/A')}
- Delta：{option_details.get('delta', 'N/A')}
"""
        
        return prompt
    
    def _format_signals_for_analysis(self, signals: List[Dict[str, Any]]) -> str:
        """格式化信号用于批量分析"""
        text = f"今日期权异动信号汇总（共{len(signals)}条）：\n\n"
        
        # 按类型分组统计
        iv_spikes = [s for s in signals if 'IV' in s['type']]
        volume_spikes = [s for s in signals if 'VOLUME' in s['type']]
        delta_cross = [s for s in signals if 'DELTA' in s['type']]
        
        text += f"【IV异动】{len(iv_spikes)}条\n"
        for s in iv_spikes[:5]:  # 最多显示5条
            text += f"  - {s['symbol']}: IV={s['value']:.2f}\n"
        
        text += f"\n【量能异常】{len(volume_spikes)}条\n"
        for s in volume_spikes[:5]:
            text += f"  - {s['symbol']}: 成交量={s['value']}, OI阈值={s['threshold']:.0f}\n"
        
        text += f"\n【Delta突破】{len(delta_cross)}条\n"
        for s in delta_cross[:5]:
            text += f"  - {s['symbol']}: Delta={s['value']:.2f}\n"
        
        return text
    
    async def _push_feishu_rich_alert(self, signal: Dict[str, Any], 
                                      analysis: str,
                                      option_details: Optional[Dict] = None):
        """飞书富文本实时告警"""
        symbol = signal['symbol']
        signal_type = signal['type']
        timestamp = signal.get('timestamp', datetime.now().strftime("%H:%M:%S"))
        
        # 信号类型中文映射
        type_map = {
            'IV_SPIKE': 'IV飙升',
            'SMART_MONEY_VOLUME': '量能异常',
            'DELTA_CROSS_0.5': 'Delta突破'
        }
        type_cn = type_map.get(signal_type, signal_type)
        
        # 构建富文本消息
        content = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"🚨 期权异动预警 | {symbol} | {type_cn}",
                        "content": [
                            [
                                {"tag": "text", "text": f"⏰ 触发时间：{timestamp}\n"},
                                {"tag": "text", "text": f"📊 信号类型：{type_cn}\n"},
                                {"tag": "text", "text": f"💡 触发值：{signal['value']}\n"},
                                {"tag": "text", "text": f"📈 阈值：{signal['threshold']}\n\n"}
                            ],
                            [
                                {"tag": "text", "text": "🤖 Kimi AI 分析：\n", "style": ["bold"]},
                                {"tag": "text", "text": analysis}
                            ]
                        ]
                    }
                }
            }
        }
        
        # 添加期权详情（如果有）
        if option_details:
            detail_text = f"\n\n📋 期权详情：\n"
            detail_text += f"• 标的股价：{option_details.get('underlying_price', 'N/A')}\n"
            detail_text += f"• 行权价：{option_details.get('strike_price', 'N/A')}\n"
            detail_text += f"• 到期日：{option_details.get('expiry_date', 'N/A')}\n"
            detail_text += f"• IV：{option_details.get('implied_volatility', 'N/A')}%\n"
            
            content["content"]["post"]["zh_cn"]["content"].append([
                {"tag": "text", "text": detail_text}
            ])
        
        await self._send_feishu(content)
    
    async def _push_feishu_daily_report(self, signals: List[Dict], report: str):
        """飞书日终汇总报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        content = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"📊 期权日终复盘 | {today} | 共{len(signals)}条信号",
                        "content": [
                            [
                                {"tag": "text", "text": "🤖 Kimi AI 深度分析\n\n", "style": ["bold"]},
                                {"tag": "text", "text": report}
                            ]
                        ]
                    }
                }
            }
        }
        
        await self._send_feishu(content)
    
    async def _push_fallback_alert(self, signal: Dict[str, Any]):
        """降级推送（Kimi失败时）"""
        message = f"""⚠️ 期权异动信号（AI分析失败）

标的：{signal['symbol']}
类型：{signal['type']}
值：{signal['value']}
时间：{signal.get('timestamp', 'N/A')}
"""
        AlertManager.send_alert("期权异动信号", message)
    
    async def _push_fallback_daily_report(self, signals: List[Dict]):
        """降级日终报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        message = f"📊 {today} 期权信号汇总\n\n"
        for s in signals:
            message += f"• {s['symbol']} - {s['type']} - {s['timestamp']}\n"
        
        AlertManager.send_alert("日终信号汇总", message)
    
    async def _send_feishu(self, content: Dict):
        """发送飞书消息"""
        import aiohttp
        
        webhook = Settings.FEISHU_WEBHOOK
        if not webhook:
            logger.warning("Feishu webhook not configured")
            return
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook, json=content, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info("Feishu rich alert sent successfully")
                    else:
                        logger.error(f"Feishu alert failed: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send Feishu alert: {e}")


# 全局实例
kimi_analyzer = KimiOptionAnalyzer()
