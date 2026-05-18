"""LLM Analyst service for generating daily market reports."""
import logging
import asyncio
import re
from typing import Optional, Dict, List, Any
import numpy as np
import pandas as pd
from openai import AsyncOpenAI
from config.settings import Settings
from src.services.signal_recorder import signal_recorder
from src.api.dingtalk import DingTalkAlert
from src.api.feishu import FeishuAlert
from datetime import datetime
from src.api.longport.personalized.watchlist import get_watchlist
from src.api.longport.client import longport_client
from src.api.adanos_client import adanos_client
from src.services.gemini_grounded_client import GeminiGroundedClient

logger = logging.getLogger(__name__)

class LLMAnalyst:
    MAX_WATCH_STOCKS = 10  # 限制分析的最大股票数量
    
    def __init__(self):
        # US/LongPort Client (Gemini)
        self.us_api_key = Settings.LLM_API_KEY
        self.us_base_url = Settings.LLM_BASE_URL
        self.us_model = Settings.LLM_MODEL
        self.us_client = AsyncOpenAI(api_key=self.us_api_key, base_url=self.us_base_url, timeout=60.0) if self.us_api_key else None

        # HK/Futu Client (Kimi)
        self.hk_api_key = Settings.KIMI_API_KEY
        self.hk_base_url = Settings.KIMI_LLM_BASE_URL
        self.hk_model = Settings.KIMI_LLM_MODEL
        self.hk_client = AsyncOpenAI(api_key=self.hk_api_key, base_url=self.hk_base_url, timeout=60.0) if self.hk_api_key else None
        self.grounded_client = GeminiGroundedClient()
        
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

    def _build_single_stock_prompt(
        self,
        symbol: str,
        current_time: str,
        fundamental_data: Dict[str, Any],
        short_memory: Dict[str, Any],
        mid_trend: Dict[str, Any],
    ) -> str:
        """Build final LLM prompt from structured short/mid features."""
        today = short_memory.get("today", {}) or {}
        summary_10d = short_memory.get("summary_10d", {}) or {}
        drawdown_raw = summary_10d.get("max_drawdown_10d_pct", 0.0)
        try:
            drawdown_10d_fmt = f"-{abs(float(drawdown_raw))}%"
        except Exception:
            drawdown_10d_fmt = "无数据"
        return f"""你是港股量化深度分析师。请基于下面结构化数据生成单股研报。
    【报告时间】
    {current_time}

    【标的】
    {symbol}

    【基本面与估值快照】
    - 所属板块：{fundamental_data.get('plate_info', '无数据')}
    - 总市值：{fundamental_data.get('total_market_val', '无数据')}
    - 流通市值：{fundamental_data.get('circular_market_val', '无数据')}
    - 总股本：{fundamental_data.get('issued_shares', '无数据')}
    - 流通股本：{fundamental_data.get('outstanding_shares', '无数据')}
    - 资产净值：{fundamental_data.get('net_asset', '无数据')}
    - 每股盈利(EPS)：{fundamental_data.get('earning_per_share', '无数据')}
    - 每股净资产(BPS)：{fundamental_data.get('net_asset_per_share', '无数据')}
    - PB：{fundamental_data.get('pb_ratio', '无数据')}
    - 市盈率TTM：{fundamental_data.get('pe_ttm', '无数据')}
    
    【筹码与流动性档案】
    - 当日资金（实时）：主力大单净流入 {fundamental_data.get('main_in_flow_today', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_today', '无数据')}
    - 近5日资金：主力大单净流入 {fundamental_data.get('main_in_flow_5d', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_5d', '无数据')}
    - 近10日资金：主力大单净流入 {fundamental_data.get('main_in_flow_10d', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_10d', '无数据')}
    - 近90日资金：主力大单净流入 {fundamental_data.get('main_in_flow_90d', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_90d', '无数据')}

    【短期记忆（近10日）】
    - window_used (实际可用天数): {short_memory.get('window_used')}
    - short_window_incomplete (是否不足10日): {short_memory.get('short_window_incomplete')}
    - 主力净流(万): {short_memory.get('smart_net_wan')}
    - 散户净流(万): {short_memory.get('retail_net_wan')}
    - 当日快照:
      - date (日期): {today.get('date')}
      - rt_price (此刻价格): {today.get('rt_price')}
      - bias20 (乖离率，仅观测指标): {today.get('bias20')}%
      - tag_today (当日结构信号): {today.get('tag_today')}
    - 10日压缩画像:
      - max_cum_up_10d_pct (10日累计最大涨幅): {summary_10d.get('max_cum_up_10d_pct')}%
      - max_cum_drop_10d_pct (10日累计最大跌幅): {summary_10d.get('max_cum_drop_10d_pct')}%
      - max_drawdown_10d_pct (10日最大回撤): {drawdown_10d_fmt}
      - short_window_price_distribute (筹码集中区前三名): {summary_10d.get('short_window_price_distribute')}
      - poc_range_10d (主峰价格区间): {summary_10d.get('poc_range_10d')}
      - poc_ratio_10d_pct (主峰成交量占比): {summary_10d.get('poc_ratio_10d_pct')}%

    【中期趋势（近90日）】
    - mode (数据完整度): {mid_trend.get('mode')}
    - window_used (实际可用天数): {mid_trend.get('window_used')}
    - summary (规则引擎总结): {mid_trend.get('summary')}
    - shape (中期形态结构): {mid_trend.get('shape')}
    - position_pct (当前价格处于90日高低点的百分位): {mid_trend.get('position_pct')}
    - peaks (近期波峰序列): {mid_trend.get('peaks')}
    - troughs (近期波谷序列): {mid_trend.get('troughs')}
    - poc_range (90日主筹码峰区间): {mid_trend.get('poc_range')}
    - poc_ratio_pct (90日主筹码峰占比): {mid_trend.get('poc_ratio_pct')}

    请按以下结构输出（Markdown）：
    1. 核心结论（先给方向，40-80字，必须含量化打分）
       * 第一行固定格式：`【量化综合做多指数：评级(如★★★★☆) (X/100) - 一句话方向总结】`
       * “-”右侧的“一句话方向总结”必填，不可省略；示例：`右侧爆发临界点，强烈买入`
       * `X` 取值 0-100（整数）；`0-39=★`，`40-59=★★`，`60-74=★★★`，`75-89=★★★★`，`90-100=★★★★★`
       * 第二行用 40-80 字给出方向结论，并解释该分数最关键的 1-2 个驱动因子；需与第一行方向保持一致。
    2. 基本面与估值透视（中长期推演，250-300字）
         * 严禁单纯罗列数据，必须穿透财务快照形成定价逻辑。
         * 【买方四大公理映射】：必须审视标的业务契合了以下哪几条底层公理，并据此定性资产属性（防御型现金奶牛 vs 进攻型高爆发成长）。公理存在权重差异：1.出海与全球化能力(40%，即中外剪刀差：成本RMB化，收益外汇化，这是硬科技公司活下去的首要条件)；2.AI产业层级与关联度(30%，精准定位标的在AI产业链上下游传导的位置，区分是算力基建Tier1/核心模型与强关联组件Tier2/深度赋能Tier3，还是仅仅作为辅助工具的边缘应用Tier4，只有Tier1-3才能享受高赔率期权溢价)；4.老龄化不可逆(20%)；3.物理世界运转效率跃升(10%)。若不符合任何一条，直接给出“不予买入”结论；若同时满足1和2（双核驱动），必须给予极高溢价并大幅上调中长期评分；满足其他组合则适度上调。
         * 重塑估值锚：对于轻资产科技股（18C等），严禁使用 BPS/PB 评估安全边际，必须使用 PS (市销率)；并通过联网检索全球1-2家最可比公司（优先美股）PS做对标，明确给出“稀缺性溢价”或“严重低估”结论。
         * 筹码与流动性：直接基于【筹码与流动性档案】中明确的短中长期“主力”与“整体”资金流向数据进行研判，结合【总/流通市值】定性真实的盘口博弈状态（如：主力托底散户抛售、主力出逃散户接盘等），无需主观猜测机构动向。
     3. 技术面证据链（短期当日信号 + 10日风险收益 + 10日筹码分布 + 中期形态，200字左右）
     4. 交易计划（入场条件、止损位、失效条件，100-150字）
    5. 核心风险/证伪条件（除常规止损外，必须给出1条可导致逻辑瞬间崩塌的非结构化风险触发，如宏观事件/产业政策，40-80字）
    6. 联网检索证据（固定三行）
       * 检索时间：YYYY-MM-DD HH:MM（北京时间）
       * 对标来源域名：至少3个，格式示例 finance.yahoo.com | companiesmarketcap.com | wsj.com
       * 对标公司与PS时点：公司A(代码) PS=xx（时点）；公司B(代码) PS=yy（时点）

    要求：
    - 结论必须可交易，禁止空泛表述。
    - 必须主动寻找“反面逻辑”，禁止只做线性外推（单边看多或单边看空）。
    - 若样本不足（short_window_incomplete=true 或 mode!=FULL_90），必须显式提示不确定性。"""

    async def _call_llm_with_retry(
        self,
        prompt: str,
        max_tokens: int = 5000,
        temperature: float = 0.9,
        enable_grounded_search: bool = False,
    ) -> Optional[str]:
        """Call LLM with streaming and retry validation (simplified)."""
        for attempt in range(3):
            try:
                if enable_grounded_search and self.grounded_client.enabled:
                    grounded_result = await asyncio.to_thread(
                        self.grounded_client.generate_grounded_content,
                        prompt,
                    )
                    if grounded_result.get("ok"):
                        report_content = (grounded_result.get("text") or "").strip()
                    else:
                        logger.warning(
                            f"[Gemini/SingleStock] grounded single-call failed, fallback openai-compatible: {grounded_result.get('error')}"
                        )
                        enable_grounded_search = False
                        report_content = ""
                else:
                    if not self.us_client:
                        raise ValueError("US LLM client (Gemini) not initialized")
                    stream = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                        temperature=temperature,
                        stream=True,
                        timeout=90.0
                    )
                    full_content = ""
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            full_content += content
                    report_content = full_content.strip()
                if report_content and len(report_content) > 120:
                    return report_content
                    
                logger.warning(f"[Gemini/SingleStock] Attempt {attempt+1}: Empty or short content, retrying...")
                await asyncio.sleep(2 * (attempt + 1))
            except Exception as e:
                logger.error(f"[Gemini/SingleStock] Attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    
        return None

    def _build_us_single_stock_prompt(
        self,
        symbol: str,
        current_time: str,
        fundamental_data: Dict[str, Any],
        short_memory: Dict[str, Any],
        mid_trend: Dict[str, Any],
    ) -> str:
        """Build US-market LLM prompt (Futu data source, tech-stock focused)."""
        today = short_memory.get("today", {}) or {}
        summary_10d = short_memory.get("summary_10d", {}) or {}
        drawdown_raw = summary_10d.get("max_drawdown_10d_pct", 0.0)
        try:
            drawdown_10d_fmt = f"-{abs(float(drawdown_raw))}%"
        except Exception:
            drawdown_10d_fmt = "无数据"
        return f"""你是美股量化深度分析师。请基于下面结构化数据生成单股研报。
    【报告时间】
    {current_time}

    【标的】
    {symbol}

    【基本面与估值快照】
    - 所属板块：{fundamental_data.get('plate_info', '无数据')}
    - 总市值：{fundamental_data.get('total_market_val', '无数据')}
    - 流通市值：{fundamental_data.get('circular_market_val', '无数据')}
    - 总股本：{fundamental_data.get('issued_shares', '无数据')}
    - 流通股本：{fundamental_data.get('outstanding_shares', '无数据')}
    - 资产净值：{fundamental_data.get('net_asset', '无数据')}
    - PB：{fundamental_data.get('pb_ratio', '无数据')}
    - 52周高：{fundamental_data.get('highest_52w', '无数据')}
    - 52周低：{fundamental_data.get('lowest_52w', '无数据')}

    【夜盘行情（美股独有）】
    - 夜盘价/涨跌幅：{fundamental_data.get('overnight_price', '无数据')} / {fundamental_data.get('overnight_change_rate', '无数据')}

    【筹码与流动性档案】
    - 当日资金（实时）：主力大单净流入 {fundamental_data.get('main_in_flow_today', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_today', '无数据')}
    - 近5日资金：主力大单净流入 {fundamental_data.get('main_in_flow_5d', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_5d', '无数据')}
    - 近10日资金：主力大单净流入 {fundamental_data.get('main_in_flow_10d', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_10d', '无数据')}
    - 近90日资金：主力大单净流入 {fundamental_data.get('main_in_flow_90d', '无数据')}，整体净流入 {fundamental_data.get('total_in_flow_90d', '无数据')}

    【短期记忆（近10日）】
    - window_used (实际可用天数): {short_memory.get('window_used')}
    - short_window_incomplete (是否不足10日): {short_memory.get('short_window_incomplete')}
    - 主力净流(万): {short_memory.get('smart_net_wan')}
    - 散户净流(万): {short_memory.get('retail_net_wan')}
    - 当日快照:
      - date (日期): {today.get('date')}
      - rt_price (此刻价格): {today.get('rt_price')}
      - bias20 (乖离率): {today.get('bias20')}%
      - tag_today (当日结构信号): {today.get('tag_today')}
    - 10日压缩画像:
      - max_cum_up_10d_pct (10日累计最大涨幅): {summary_10d.get('max_cum_up_10d_pct')}%
      - max_cum_drop_10d_pct (10日累计最大跌幅): {summary_10d.get('max_cum_drop_10d_pct')}%
      - max_drawdown_10d_pct (10日最大回撤): {drawdown_10d_fmt}
      - short_window_price_distribute (筹码集中区前三名): {summary_10d.get('short_window_price_distribute')}
      - poc_range_10d (主峰价格区间): {summary_10d.get('poc_range_10d')}
      - poc_ratio_10d_pct (主峰成交量占比): {summary_10d.get('poc_ratio_10d_pct')}%

    【中期趋势（近90日）】
    - mode (数据完整度): {mid_trend.get('mode')}
    - window_used (实际可用天数): {mid_trend.get('window_used')}
    - summary (规则引擎总结): {mid_trend.get('summary')}
    - shape (中期形态结构): {mid_trend.get('shape')}
    - position_pct (当前价格处于90日高低点的百分位): {mid_trend.get('position_pct')}
    - peaks (近期波峰序列): {mid_trend.get('peaks')}
    - troughs (近期波谷序列): {mid_trend.get('troughs')}
    - poc_range (90日主筹码峰区间): {mid_trend.get('poc_range')}
    - poc_ratio_pct (90日主筹码峰占比): {mid_trend.get('poc_ratio_pct')}

    请按以下结构输出（Markdown）：
    1. 核心结论（先给方向，40-80字，必须含量化打分）
       * 第一行固定格式：`【量化综合做多指数：评级(如★★★★☆) (X/100) - 一句话方向总结】`
       * "-"右侧的"一句话方向总结"必填，不可省略；示例：`右侧爆发临界点，强烈买入`
       * `X` 取值 0-100（整数）；`0-39=★`，`40-59=★★`，`60-74=★★★`，`75-89=★★★★`，`90-100=★★★★★`
       * 第二行用 40-80 字给出方向结论，并解释该分数最关键的 1-2 个驱动因子；需与第一行方向保持一致。
    2. 基本面与估值透视（中长期推演，250-300字）
       * 严禁单纯罗列数据，必须穿透财务快照形成定价逻辑。
       * 【买方三大公理映射】：审视标的契合哪几条底层公理。公理权重：1.行业潜力与增长度(40%，所在赛道是否处于高成长阶段、市场空间有多大，公司占市场份额大概有多少)；2.AI产业层级与关联度(40%，精准定位标的在AI产业链上下游传导的位置，算力基建Tier1/核心模型与强关联组件Tier2/深度赋能Tier3/边缘辅助应用Tier4，只有Tier1-3才能享受高赔率期权溢价)；3.物理世界运转效率跃升(20%，降本增效的直接受益者)。若不符合任何一条，直接给出"不予买入"结论；若同时满足1和2（双核驱动），给予极高溢价并大幅上调中长期评分。
       * 重塑估值锚：轻资产科技股必须用 PS(市销率)评估，联网检索全球1-2家最可比美股公司 PS 做对标，明确给出"稀缺性溢价"或"严重低估"结论。
       * 筹码与流动性：直接基于【筹码与流动性档案】中明确的短中长期"主力"与"整体"资金流向数据进行研判，结合【总/流通市值】定性真实的盘口博弈状态，无需主观猜测机构动向。
    3. 技术面证据链（短期当日信号 + 10日风险收益 + 10日筹码分布 + 中期形态，200字左右）
    4. 交易计划（入场条件、止损位、失效条件，100-150字）
    5. 核心风险/证伪条件（除常规止损外，必须给出1条可导致逻辑瞬间崩塌的非结构化风险触发，如宏观事件/产业政策，40-80字）
    6. 联网检索证据（固定三行）
       * 检索时间：YYYY-MM-DD HH:MM（北京时间）
       * 对标来源域名：至少3个，格式示例 finance.yahoo.com | companiesmarketcap.com | wsj.com
       * 对标公司与PS时点：公司A(代码) PS=xx（时点）；公司B(代码) PS=yy（时点）

    要求：
    - 结论必须可交易，禁止空泛表述。
    - 必须主动寻找"反面逻辑"，禁止只做线性外推（单边看多或单边看空）。
    - 若样本不足（short_window_incomplete=true 或 mode!=FULL_90），必须显式提示不确定性。"""

    @staticmethod
    def _parse_us_symbol(symbol_input: str) -> Optional[str]:
        """Normalize user input to Futu-native US.TICKER format.

        Accepts: AAPL / AAPL.US / US.AAPL
        """
        raw = symbol_input.strip().upper()
        if raw.startswith("US."):
            return raw
        if raw.endswith(".US"):
            ticker, market = raw.rsplit(".", 1)
            return f"{market}.{ticker}"
        # bare ticker or hyphenated (e.g. BRK-B)
        if raw.replace("-", "").replace(".", "").isalnum():
            return f"US.{raw}"
        return None

    async def generate_us_single_stock_report(
        self,
        symbol_input: str,
        trigger_type: str = "MANUAL",
        lookback_days_short: int = 10,
        lookback_days_mid: int = 90,
        enable_grounded_search: bool = True,
    ) -> Dict[str, Any]:
        """Generate single-stock deep analysis report for US symbols (Futu data source).

        Data pipeline:
          1. _parse_us_symbol         → Futu-native US.TICKER format
          2. get_special_quotes       → snapshot
          3. get_capital_flow_history → capital_data (historical daily flow)
          4. get_historical_klines    → klines_df
          5. build_us_fundamental_data / build_short_term_memory / build_mid_term_trend
          6. _build_us_single_stock_prompt → prompt
          7. _call_llm_with_retry (Gemini grounded) → report_content
        """
        from src.api.futu.client import futu_client
        from src.analysis.us_single_stock_indicator import (
            build_us_fundamental_data,
            build_short_term_memory,
            build_mid_term_trend,
        )

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            futu_symbol = self._parse_us_symbol(symbol_input)
            if not futu_symbol:
                msg = "未匹配到有效美股代码（支持 AAPL / AAPL.US / US.AAPL）"
                return {"ok": False, "symbol": symbol_input, "title": None, "report": None, "error": msg}

            logger.info(
                f"[Gemini/USSingleStock] start symbol_input={symbol_input}, parsed={futu_symbol}, trigger={trigger_type}"
            )

            snapshot_list = await asyncio.to_thread(futu_client.get_special_quotes, [futu_symbol])
            if not snapshot_list:
                msg = "未获取到股票快照数据，请确认代码或行情权限（需美股行情权限）。"
                return {"ok": False, "symbol": futu_symbol, "title": None, "report": None, "error": msg}

            stock = snapshot_list[0]
            price = float(stock.get("last_price", 0.0))
            stock_name = str(stock.get("name", "") or "").strip()
            ticker = futu_symbol.split(".", 1)[1] if "." in futu_symbol else futu_symbol
            standard_symbol = f"{ticker}.US"
            symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol

            capital_data = await asyncio.to_thread(
                futu_client.get_capital_flow_history, futu_symbol, 90
            )

            klines_df = await asyncio.to_thread(
                futu_client.get_historical_klines,
                futu_symbol,
                max(lookback_days_mid + 30, 120),
            )
            if klines_df is None or klines_df.empty:
                msg = f"未获取到 {futu_symbol} 历史K线数据，无法生成短中期分析。"
                logger.warning(f"[Gemini/USSingleStock] {msg}")
                return {"ok": False, "symbol": futu_symbol, "title": None, "report": None, "error": msg}

            short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
            mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
            fundamental_data = await asyncio.to_thread(
                build_us_fundamental_data,
                futu_symbol,
                stock,
                (5, 10, 90),
            )

            prompt = self._build_us_single_stock_prompt(
                symbol_for_prompt,
                current_time,
                fundamental_data,
                short_memory,
                mid_trend,
            )

            report_content = await self._call_llm_with_retry(
                prompt,
                enable_grounded_search=enable_grounded_search,
            )
            if not report_content:
                raise ValueError("LLM生成报告失败（3次重试后仍不满足完整性校验）")

            full_report = f"""🦅 **Gemini 美股单股深度研报** | {standard_symbol} | {current_time}

---

{report_content}

---

📊 **数据窗口**：短期{lookback_days_short}天 | 中期{lookback_days_mid}天
🔔 **触发类型**：{trigger_type}
🧠 **AI模型**：{self.us_model}"""

            title = f"[美股单股深度研报] {standard_symbol} ({current_time})"
            alert_sent = await FeishuAlert.send_alert(title, full_report)
            if alert_sent:
                logger.info(f"[Gemini/USSingleStock] report sent to Feishu successfully: {standard_symbol}")
            else:
                logger.error(f"[Gemini/USSingleStock] report generated but Feishu send failed: {standard_symbol}")

            return {
                "ok": True,
                "symbol": standard_symbol,
                "title": title,
                "report": full_report,
                "error": None,
            }
        except Exception as e:
            logger.error(f"[Gemini/USSingleStock] failed for {symbol_input}: {e}", exc_info=True)
            error_title = f"[美股单股研报错误] {symbol_input} ({current_time})"
            error_content = f"❌ 分析失败：{str(e)}"
            await FeishuAlert.send_alert(error_title, error_content)
            return {"ok": False, "symbol": symbol_input, "title": None, "report": None, "error": str(e)}

    async def generate_hk_single_stock_report(
        self,
        symbol_input: str,
        trigger_type: str = "MANUAL",
        lookback_days_short: int = 10,
        lookback_days_mid: int = 90,
        enable_grounded_search: bool = True,
    ) -> Dict[str, Any]:
        """Generate single-stock deep analysis report for HK symbols."""
        from src.api.futu.client import futu_client

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            standard_symbol = futu_client.parse_symbol_input(symbol_input)
            if not standard_symbol:
                msg = "未匹配到有效港股代码（支持 HK.XXXXX / 纯数字 / 配置内中文简称）"
                return {"ok": False, "symbol": symbol_input, "title": None, "report": None, "error": msg}

            logger.info(
                f"[Gemini/SingleStock] start report symbol_input={symbol_input}, parsed={standard_symbol}, trigger={trigger_type}"
            )

            # 串行收集数据，确保前置数据就绪后再进入后续分析，避免并发时空数据继续流入分析链路。
            snapshot_list = await asyncio.to_thread(futu_client.get_special_quotes, [standard_symbol])

            if not snapshot_list:
                msg = "未获取到股票快照数据，请确认代码或行情权限。"
                return {"ok": False, "symbol": standard_symbol, "title": None, "report": None, "error": msg}

            stock = snapshot_list[0]
            price = float(stock.get("last_price", 0.0))
            stock_name = str(stock.get("name", "") or "").strip()
            symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol
            capital_data = await asyncio.to_thread(futu_client.get_capital_flow, standard_symbol)
                
            klines_df = await asyncio.to_thread(
                futu_client.get_hk_historical_klines,
                standard_symbol,
                max(lookback_days_mid + 30, 120),
            )
            if klines_df is None or klines_df.empty:
                msg = f"未获取到 {standard_symbol} 历史K线数据，无法生成短中期分析。"
                logger.warning(f"[Gemini/SingleStock] {msg}")
                return {"ok": False, "symbol": standard_symbol, "title": None, "report": None, "error": msg}

            from src.analysis.futu_math_indicator import (
                build_short_term_memory,
                build_mid_term_trend,
                build_hk_fundamental_data,
            )
            short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
            mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
            fundamental_data = await asyncio.to_thread(
                build_hk_fundamental_data,
                standard_symbol,
                stock,
                (5, 10, 90),
            )
            prompt = self._build_single_stock_prompt(
                symbol_for_prompt,
                current_time,
                fundamental_data,
                short_memory,
                mid_trend,
            )

            report_content = await self._call_llm_with_retry(
                prompt,
                enable_grounded_search=enable_grounded_search,
            )
            if not report_content:
                raise ValueError("LLM生成报告失败（3次重试后仍不满足完整性校验）")

            full_report = f"""🦞 **Gemini 单股深度研报** | {standard_symbol} | {current_time}

---

{report_content}

---

📊 **数据窗口**：短期{lookback_days_short}天 | 中期{lookback_days_mid}天
🔔 **触发类型**：{trigger_type}
🧠 **AI模型**：{self.us_model}"""

            title = f"[单股深度研报] {standard_symbol} ({current_time})"
            alert_sent = await FeishuAlert.send_alert(title, full_report)
            if alert_sent:
                logger.info(f"[Gemini/SingleStock] report sent to Feishu successfully: {standard_symbol}")
            else:
                logger.error(f"[Gemini/SingleStock] report generated but Feishu send failed: {standard_symbol}")

            return {
                "ok": True,
                "symbol": standard_symbol,
                "title": title,
                "report": full_report,
                "error": None
            }
        except Exception as e:
            logger.error(f"[Gemini/SingleStock] failed for {symbol_input}: {e}", exc_info=True)
            error_title = f"[单股研报错误] {symbol_input} ({current_time})"
            error_content = f"❌ 分析失败：{str(e)}"
            await FeishuAlert.send_alert(error_title, error_content)
            return {"ok": False, "symbol": symbol_input, "title": None, "report": None, "error": str(e)}

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
            
            async def fetch_us_stock_data(stock, index):
                symbol = stock.get('symbol', 'Unknown')
                price = stock['last_price']
                change = stock['change_rate']
                direction = "📈" if change > 0 else "📉"
                
                # Fetch sentiment and capital flow concurrently
                sentiment_task = asyncio.create_task(adanos_client.get_sentiment_labels(symbol))
                capital_task = asyncio.create_task(longport_client.get_capital_flow(symbol))
                
                try:
                    sentiment_labels, capital_data = await asyncio.gather(sentiment_task, capital_task)
                except Exception as e:
                    logger.error(f"Failed to get US data concurrently for {symbol}: {e}")
                    sentiment_labels, capital_data = [], None
                
                sentiment_text = f" [{', '.join(sentiment_labels)}]" if sentiment_labels else ""
                
                try:
                    flow_label, smart_net, retail_net = longport_client.analyze_us_capital_flow(capital_data, change)
                except Exception as e:
                    logger.error(f"Failed to analyze US capital flow for {symbol}: {e}")
                    flow_label, smart_net, retail_net = "分析不可用", 0, 0
                
                return (
                    f"{index}. {symbol} 现价${price:.2f} ({change:+.2f}%) {direction}{sentiment_text}\n"
                    f"   - 【内部量化系统研判】：{flow_label}\n"
                    f"   - (资金支撑：主力净流 {smart_net}万, 散户净流 {retail_net}万)"
                )

            tasks = [fetch_us_stock_data(stock, i) for i, stock in enumerate(threshold_stocks[:15], 1)]
            stock_details = await asyncio.gather(*tasks)
            
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
            # Define valid completion endings (expanded for markdown)
            valid_endings = ('.', '。', '!', '！', '?', '？', ']', '】', '）', '*', '`', '"', "'", '>', '~')
            
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
                    if content and len(content) > 150 and (content.endswith(valid_endings) or content[-1].isalnum()):
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
            logger.info(f"[Gemini/Futu] Generating HK report for stocks exceeding {threshold}% threshold and special symbols...")
            
            # 1 & 2. Fetch threshold stocks and special stocks concurrently
            special_symbols = config.get('special_symbols', [])
            special_stock_codes = [s.split(' ')[0] for s in special_symbols] if special_symbols else []
            
            threshold_task = asyncio.to_thread(futu_client.get_threshold_quotes, threshold)
            special_task = asyncio.to_thread(futu_client.get_special_quotes, special_stock_codes)
            
            threshold_stocks, special_stocks = await asyncio.gather(threshold_task, special_task)
            
            # 3. Merge and deduplicate
            merged_stocks = []
            seen_codes = set()
            
            # First, add all special stocks
            for stock in special_stocks:
                code = stock.get('code', stock.get('symbol'))
                if code and code not in seen_codes:
                    merged_stocks.append(stock)
                    seen_codes.add(code)
            
            # Sort threshold_stocks by absolute change rate descending
            threshold_stocks.sort(key=lambda x: abs(x['change_rate']), reverse=True)
            
            # Add threshold stocks until we reach MAX_WATCH_STOCKS
            for stock in threshold_stocks:
                if len(merged_stocks) >= self.MAX_WATCH_STOCKS:
                    break
                code = stock.get('code', stock.get('symbol'))
                if code and code not in seen_codes:
                    merged_stocks.append(stock)
                    seen_codes.add(code)
            
            if not merged_stocks:
                logger.info(f"[Gemini/Futu] No HK stocks exceeded {threshold}% threshold and no special symbols found")
                title = f"[Gemini研报] 港股市场观察 ({current_time})"
                content = f"📊 **港股市场观察**\n\n当前富途自选股中无标的涨跌幅超过 **{threshold}%** 阈值，且无特殊关注标的异动。\n\n> 监控时间：{current_time}"
                await FeishuAlert.send_alert(title, content)
                return
            
            # Update threshold_stocks to be our merged and limited list for downstream processing
            threshold_stocks = merged_stocks
            
            # Calculate stats (using the selected stocks)
            up_count = sum(1 for s in threshold_stocks if s['change_rate'] > 0)
            down_count = len(threshold_stocks) - up_count
            avg_change = sum(s['change_rate'] for s in threshold_stocks) / len(threshold_stocks) if threshold_stocks else 0
            
            # Build stock details with names
            stock_details = []
            
            # Helper function to fetch data for a single stock concurrently
            async def fetch_stock_data(stock, index):
                symbol = stock.get('symbol', stock.get('code', 'Unknown'))
                code = stock.get('code')
                price = stock['last_price']
                change = stock['change_rate']
                direction = "📈" if change > 0 else "📉"
                
                # Fetch capital flow and klines concurrently for this stock
                capital_task = asyncio.to_thread(futu_client.get_capital_flow, code)
                klines_task = asyncio.to_thread(futu_client.get_hk_historical_klines, code, 60)
                
                try:
                    capital_data, klines_df = await asyncio.gather(capital_task, klines_task)
                except Exception as e:
                    logger.error(f"Failed to get data concurrently for {code}: {e}")
                    capital_data, klines_df = None, None

                # Process capital flow
                try:
                    flow_label, smart_net, retail_net = futu_client.analyze_capital_flow(capital_data, change)
                except Exception as e:
                    logger.error(f"Failed to analyze capital flow for {code}: {e}")
                    flow_label, smart_net, retail_net = "分析不可用", 0, 0
                    
                # Process EMA derivatives
                try:
                    if klines_df is not None and not klines_df.empty:
                        from src.analysis.futu_math_indicator import calculate_ema_derivatives
                        ema_data = calculate_ema_derivatives(klines_df, price)
                        ema_tag = ema_data.get('tag_combined', ema_data['tag'])
                        v5, v20, a5, bias20 = ema_data['v5'], ema_data.get('v20', 0.0), ema_data['a5'], ema_data.get('bias20', 0.0)
                        ema_text = f"   - 【量化技术面】：{ema_tag} (V5: {v5}%, V20: {v20}%, A5: {a5}%, Bias20: {bias20}%)"
                    else:
                        ema_text = f"   - 【量化技术面】：数据缺失"
                except Exception as e:
                    logger.error(f"Failed to calculate EMA for {code}: {e}")
                    ema_text = f"   - 【量化技术面】：计算错误"
                
                return (
                    f"{index}. {symbol} 现价${price:.2f} ({change:+.2f}%) {direction}\n"
                    f"   - 【内部量化系统研判】：{flow_label}\n"
                    f"   - (资金支撑：主力净流 {smart_net}万, 散户净流 {retail_net}万)\n"
                    f"{ema_text}"
                )

            # Run all stock data fetching tasks concurrently
            tasks = [fetch_stock_data(stock, i) for i, stock in enumerate(threshold_stocks, 1)]
            stock_details = await asyncio.gather(*tasks)
            
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
            last_error = None
            for attempt in range(3):
                try:
                    logger.info(f"[Gemini/Futu] Attempt {attempt+1} to generate HK report...")
                    stream = await self.us_client.chat.completions.create(
                        model=self.us_model,
                        messages=[
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=4000,
                        temperature=1.0, # Increased temperature to avoid repetitive generation loop
                        stream=True,
                        timeout=90.0
                    )
                    
                    full_content = ""
                    async for chunk in stream:
                        content = chunk.choices[0].delta.content
                        if content:
                            full_content += content
                            
                    # Validate content ending and length
                    content = full_content.strip()
                    valid_endings = ('.', '。', '!', '！', '?', '？', ']', '】', '）', '*', '`', '"', "'", '>', '~')
                    if content and len(content) > 150 and (content.endswith(valid_endings) or content[-1].isalnum()):
                        report_content = content
                        logger.info(f"[Gemini/Futu] Attempt {attempt+1} successful.")
                        break
                    
                    logger.warning(f"[Gemini/Futu] Attempt {attempt+1}: Invalid content received (length: {len(content)}, ends with: '{content[-5:]}'). Retrying...")
                    await asyncio.sleep(2 * (attempt + 1))
                except Exception as e:
                    last_error = e
                    logger.error(f"[Gemini/Futu] Attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        await asyncio.sleep(3 * (attempt + 1))
            
            if not report_content:
                error_msg = f"Failed to generate report after 3 attempts."
                if last_error:
                    error_msg += f" Last specific error: {str(last_error)}"
                raise ValueError(error_msg)
            
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
            alert_sent = await FeishuAlert.send_alert(title, full_report)
            if alert_sent:
                logger.info(f"[Gemini/Futu] Report sent to Feishu successfully")
            else:
                logger.error(f"[Gemini/Futu] Report generated but Feishu send failed")
                
        except Exception as e:
            import traceback
            logger.error(f"[Gemini/Futu] Failed to generate HK report: {e}\n{traceback.format_exc()}")
            # Send error notification
            error_title = f"[Gemini研报] 港股报告生成失败 ({current_time})"
            error_content = f"❌ **报告生成失败**\n\n**具体错误原因**：\n{str(e)}\n\n(请根据上述具体报错排查，如为超时请检查网络代理，如为认证失败请检查 API Key 权限)"
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
