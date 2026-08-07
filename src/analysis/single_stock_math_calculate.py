import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from config.settings import Settings

logger = logging.getLogger(__name__)


def _revenue_breakdown_type_name(type_value: Any) -> str:
    text = str(type_value or "").upper()
    if "PRODUCT" in text or text in ("1", "REV_BREAKDOWN_PRODUCT"):
        return "产品"
    if "INDUSTRY" in text or text in ("2", "REV_BREAKDOWN_INDUSTRY"):
        return "行业"
    if "REGION" in text or text in ("4", "REV_BREAKDOWN_REGION"):
        return "地区"
    if "BUSINESS" in text or text in ("8", "REV_BREAKDOWN_BUSINESS"):
        return "业务"
    return text if text else "未知维度"


def _format_revenue_breakdown_amount(val: float, raw: Any) -> str:
    if raw is None:
        return "无数据"
    try:
        if pd.isna(raw):
            return "无数据"
    except Exception:
        pass
    if abs(val) > 1_0000_0000:
        return f"{round(val / 1_0000_0000.0, 2)}亿"
    return f"{round(val / 1_0000.0, 2)}万"


def _format_revenue_breakdown_pct(value: Any) -> str:
    try:
        val = float(value)
        if pd.isna(val):
            return "无数据"
    except Exception:
        return "无数据"
    sign = "+" if val > 0 else ""
    return f"{sign}{round(val, 2)}%"


def build_revenue_breakdown_profile(symbol: str, top_n: int = 3, log_prefix: str = "SingleStock") -> str:
    """Build compact revenue composition profile from Futu revenue breakdown data."""
    from src.api.futu.client import futu_client

    try:
        quote_ctx = futu_client.get_quote_context()
        method = getattr(quote_ctx, "get_financials_revenue_breakdown", None)
        if method is None:
            return "当前 Futu SDK 未暴露 get_financials_revenue_breakdown，无法获取主营构成。"

        ret, data = method(symbol)
        if ret != 0 or not isinstance(data, dict):
            logger.warning(f"[{log_prefix}/RevenueBreakdown] get_financials_revenue_breakdown failed for {symbol}: {data}")
            return "无数据"

        breakdown_list = data.get("breakdown_list") or []
        period = str(data.get("period") or "未知期间").strip()
        currency_code = str(data.get("currency_code") or "").strip()
        currency_suffix = f" {currency_code}" if currency_code else ""
        parts = []
        for breakdown in breakdown_list:
            if not isinstance(breakdown, dict):
                continue
            dimension = _revenue_breakdown_type_name(breakdown.get("type"))
            item_list = breakdown.get("item_list") or []
            rows = []
            for item in item_list[:top_n]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "未知").strip()
                ratio = _format_revenue_breakdown_pct(item.get("ratio")).lstrip("+")
                income_raw = item.get("main_oper_income")
                income = _safe_float(income_raw, 0.0)
                rows.append(f"{name} {ratio}（收入{_format_revenue_breakdown_amount(income, income_raw)}{currency_suffix}）")
            if rows:
                parts.append(f"{dimension}Top{top_n}：" + "；".join(rows))

        if not parts:
            return "无数据"
        return f"{period}：" + " | ".join(parts)
    except Exception as e:
        logger.warning(f"[{log_prefix}/RevenueBreakdown] Failed to build revenue breakdown for {symbol}: {e}")
        return "无数据"


def calculate_bollinger_bands(
    df: pd.DataFrame,
    current_price: float,
    window: int = 20,
    num_std: float = 2.0,
    current_date: Optional[Any] = None,
) -> Dict[str, Any]:
    """Calculate Bollinger Band levels and current price position with realtime price included."""
    default = {
        "bb_mid": 0.0,
        "bb_upper": 0.0,
        "bb_lower": 0.0,
        "bb_pos": 0.0,
        "bb_width": 0.0,
        "bb_tag": "布林数据不足",
    }
    if df is None or df.empty or "close" not in df.columns or len(df) < window:
        return default

    close = _prepare_realtime_close_series(df, current_price, current_date=current_date)
    if len(close) < window:
        return default

    current_price_num = _safe_float(current_price, 0.0)
    if current_price_num <= 0:
        current_price_num = float(close.iloc[-1])

    close_values = close.to_numpy(dtype=float)
    latest_window = close_values[-window:]
    mid = float(np.mean(latest_window))
    std = float(np.std(latest_window, ddof=0))
    upper = mid + num_std * std
    lower = mid - num_std * std
    band_width = upper - lower

    if not np.isfinite(mid) or not np.isfinite(upper) or not np.isfinite(lower) or band_width <= 0:
        return default

    bb_pos = (current_price_num - lower) / band_width
    bb_width = band_width / mid * 100.0 if mid else 0.0

    if bb_pos > 1:
        bb_tag = "【布林上轨突破：短线强势/可能过热】"
    elif bb_pos >= 0.8:
        bb_tag = "【布林强势区：接近上轨】"
    elif bb_pos >= 0.5:
        bb_tag = "【布林中轨上方：修复转强】"
    elif bb_pos >= 0.2:
        bb_tag = "【布林中轨下方：弱势修复】"
    elif bb_pos >= 0:
        bb_tag = "【布林下轨附近：弱势/超跌观察】"
    else:
        bb_tag = "【跌破布林下轨：超跌或破位】"

    return {
        "bb_mid": round(mid, 2),
        "bb_upper": round(upper, 2),
        "bb_lower": round(lower, 2),
        "bb_pos": round(float(bb_pos), 3),
        "bb_width": round(float(bb_width), 2),
        "bb_tag": bb_tag,
    }


def _prepare_realtime_close_series(
    df: pd.DataFrame,
    current_price: float,
    current_date: Optional[Any] = None,
) -> pd.Series:
    """Return close history with exactly one sample for the current trading day."""
    close = pd.Series(pd.to_numeric(df["close"], errors="coerce"), dtype="float64")
    valid_mask = close.notna()
    close = close.loc[valid_mask].reset_index(drop=True)
    if close.empty:
        return close

    current_price_num = _safe_float(current_price, 0.0)
    if current_price_num <= 0:
        current_price_num = float(close.iloc[-1])

    date_col = "time_key" if "time_key" in df.columns else ("date" if "date" in df.columns else None)
    replace_latest = False
    if date_col is not None:
        valid_dates = pd.to_datetime(df.loc[valid_mask, date_col], errors="coerce").dropna()
        target_date = pd.to_datetime(
            current_date if current_date is not None else datetime.now().date(),
            errors="coerce",
        )
        if not valid_dates.empty and not pd.isna(target_date):
            replace_latest = valid_dates.iloc[-1].date() == target_date.date()

    if replace_latest:
        close.iloc[-1] = current_price_num
        return close

    return pd.concat(
        [close, pd.Series([current_price_num], dtype="float64")],
        ignore_index=True,
    )


def _combine_price_action_tag(
    tag_combined: str,
    current_change_rate: Optional[float],
    volume_regime: str,
    v20: float,
    v5: float,
    a5: float,
) -> str:
    """Override the display tag when daily price action conflicts with EMA direction."""
    change_rate_num = pd.to_numeric(pd.Series([current_change_rate]), errors="coerce").iloc[0]
    if pd.isna(change_rate_num):
        return tag_combined

    change_rate = float(change_rate_num)
    volume_suffix = f"+【{volume_regime}】" if volume_regime in ("放量", "缩量") else ""
    if change_rate < 0 and v20 > 0 and v5 > 0:
        phase = "当日转弱/动能降速" if a5 < 0 else "当日回撤/趋势未破"
        return (
            f"【上升趋势回调：{phase}】{volume_suffix}⚠️ "
            "当日价格下跌但 EMA 趋势尚未完全转空；若主力同步流出，不按洗筹处理 "
            "→ 等待止跌或资金回流确认"
        )
    if change_rate > 0 and v20 < 0 and v5 < 0:
        phase = "当日反弹/跌势放缓" if a5 > 0 else "当日反弹/空头结构未改"
        return (
            f"【下跌趋势反弹：{phase}】{volume_suffix}⚠️ "
            "当日价格上涨但 EMA 趋势尚未转多 → 等待 V5/V20 或资金进一步确认"
        )
    if change_rate < 0 and v20 < 0 and v5 > 0:
        phase = "当日回落/修复动能转弱" if a5 < 0 else "当日回落/短期修复尚存"
        return (
            f"【短期修复受阻：{phase}】{volume_suffix}⚠️ "
            "短期 EMA 虽已回升，但当日价格下跌且中期趋势仍弱 "
            "→ 等待价格止跌及 V20 转正确认"
        )
    if change_rate > 0 and v20 > 0 and v5 < 0:
        phase = "当日回升/下行动能缓和" if a5 > 0 else "当日反弹/短期结构仍弱"
        return (
            f"【短期转弱中的反弹：{phase}】{volume_suffix}⚠️ "
            "当日价格上涨但短期 EMA 尚未恢复，中期上行结构仍在 "
            "→ 等待 V5 重新转正确认"
        )
    return tag_combined


def calculate_ema_derivatives(
    df: pd.DataFrame,
    current_price: float,
    current_volume: Optional[float] = None,
    current_turnover: Optional[float] = None,
    current_change_rate: Optional[float] = None,
    current_date: Optional[Any] = None,
) -> dict:
    """计算均线衍生指标、当日技术标签及成交量 regime。

    价格/趋势侧（实时）：EMA5/EMA20/V5/V20/A5/Bias20 均含盘中 current_price。
    成交量侧默认使用 T-1 锚；当调用方确认当日成交量已具备可比性
        （例如港股 15:00 后、美股 15:00 ET 后或盘后）时，可传入 current_volume/current_turnover。

    Returns:
        tag            : 价格趋势形态标签（6 种，不受成交量影响）
        tag_combined   : tag + 当日涨跌 + volume_regime 的唯一展示标签
        v5 / v20 / a5  : EMA 一阶/二阶导数（%）
        bias20         : 乖离率，仅观测，不参与标签决策
        volume_regime  : 放量 / 中性 / 缩量（双确认或短/中期极端阈值，见文档 §2.5.3）
        volume_ratio_target_ema5  : V_target / V_ema5
        volume_ratio_target_ema20 : V_target / V_ema20
    """
    _empty = {
        "tag": "数据不足",
        "tag_combined": "数据不足",
        "v5": 0.0, "v20": 0.0, "a5": 0.0, "bias20": 0.0,
        **calculate_bollinger_bands(df, current_price, current_date=current_date),
        "volume_regime": "中性",
        "volume_ratio_target_ema5": 1.0,
        "volume_ratio_target_ema20": 1.0,
    }
    if df is None or df.empty or "close" not in df.columns or len(df) < 20:
        logger.warning("Data too short or missing 'close' column for EMA derivatives calculation.")
        return _empty

    # --- 成交量 regime（默认 T-1 锚，必须在拼接 current_price 行之前计算）---
    volume_regime = "中性"
    r_target_ema5 = 1.0
    r_target_ema20 = 1.0
    vol_col = None
    current_vol_value = None
    closed_vol = pd.Series(dtype="float64")
    for candidate, current_candidate in (
        ("turnover", current_turnover),
        ("amount", current_turnover),
        ("volume", current_volume),
    ):
        if candidate in df.columns:
            series = pd.Series(pd.to_numeric(df[candidate], errors="coerce")).dropna()
            if len(series) >= 6:
                vol_col = candidate
                closed_vol = series
                current_vol_value = current_candidate
                break

    if vol_col is not None:
        current_volume_num = pd.Series(
            pd.to_numeric(pd.Series([current_vol_value]), errors="coerce")
        ).iloc[0]
        use_current_volume = (
            current_vol_value is not None
            and not pd.isna(current_volume_num)
            and float(current_volume_num) > 0
        )
        if use_current_volume:
            target_vol = float(current_volume_num)
            baseline_vol = closed_vol
        else:
            target_vol = float(closed_vol.iloc[-1])
            baseline_vol = closed_vol.iloc[:-1] if len(closed_vol) > 6 else closed_vol

        if len(baseline_vol) >= 5:
            v_ema5 = float(baseline_vol.ewm(span=5, adjust=False).mean().iloc[-1])
            v_ema20 = float(baseline_vol.ewm(span=20, adjust=False).mean().iloc[-1])
            if v_ema5 > 0 and v_ema20 > 0:
                raw_r_target_ema5 = target_vol / v_ema5
                raw_r_target_ema20 = target_vol / v_ema20

                r_target_ema5 = round(raw_r_target_ema5, 3)
                r_target_ema20 = round(raw_r_target_ema20, 3)

                is_expand_double_confirm = (
                    raw_r_target_ema20 >= Settings.VOLUME_EXPAND_DOUBLE_EMA20_THRESHOLD
                    and raw_r_target_ema5 >= Settings.VOLUME_EXPAND_DOUBLE_EMA5_THRESHOLD
                )
                is_shrink_double_confirm = (
                    raw_r_target_ema20 <= Settings.VOLUME_SHRINK_DOUBLE_EMA20_THRESHOLD
                    and raw_r_target_ema5 <= Settings.VOLUME_SHRINK_DOUBLE_EMA5_THRESHOLD
                )
                is_expand_short_extreme = (
                    raw_r_target_ema5 >= Settings.VOLUME_EXPAND_SHORT_EMA5_THRESHOLD
                )
                is_expand_long_extreme = (
                    raw_r_target_ema20 >= Settings.VOLUME_EXPAND_LONG_EMA20_EXTREME_THRESHOLD
                )
                is_shrink_short_extreme = (
                    raw_r_target_ema5 <= Settings.VOLUME_SHRINK_SHORT_EMA5_THRESHOLD
                )
                is_shrink_long_extreme = (
                    raw_r_target_ema20 <= Settings.VOLUME_SHRINK_LONG_EMA20_EXTREME_THRESHOLD
                )

                volume_rule_hits = []
                if is_expand_double_confirm:
                    volume_rule_hits.append("expand_double_confirm")
                if is_expand_short_extreme:
                    volume_rule_hits.append("expand_short_ema5_extreme")
                if is_expand_long_extreme:
                    volume_rule_hits.append("expand_long_ema20_extreme")
                if is_shrink_double_confirm:
                    volume_rule_hits.append("shrink_double_confirm")
                if is_shrink_short_extreme:
                    volume_rule_hits.append("shrink_short_ema5_extreme")
                if is_shrink_long_extreme:
                    volume_rule_hits.append("shrink_long_ema20_extreme")

                if is_expand_double_confirm or is_expand_short_extreme or is_expand_long_extreme:
                    volume_regime = "放量"
                elif is_shrink_double_confirm or is_shrink_short_extreme or is_shrink_long_extreme:
                    volume_regime = "缩量"

                logger.warning(
                    "[VolumeRegime] col=%s source=%s target=%.2f ema5=%.2f ema20=%.2f "
                    "r5=%.3f r20=%.3f regime=%s rules=%s",
                    vol_col,
                    "current" if use_current_volume else "last_closed",
                    target_vol,
                    v_ema5,
                    v_ema20,
                    raw_r_target_ema5,
                    raw_r_target_ema20,
                    volume_regime,
                    ",".join(volume_rule_hits) if volume_rule_hits else "none",
                )

    # --- EMA 衍生指标（含当日实时价格）---
    close_calc = _prepare_realtime_close_series(df, current_price, current_date=current_date)
    df_calc = pd.DataFrame({"close": close_calc})

    df_calc["EMA5"] = df_calc["close"].ewm(span=5, adjust=False).mean()
    df_calc["EMA20"] = df_calc["close"].ewm(span=20, adjust=False).mean()
    df_calc["V5"] = df_calc["EMA5"].pct_change() * 100
    df_calc["V20"] = df_calc["EMA20"].pct_change() * 100
    df_calc["A5"] = df_calc["V5"].diff()
    df_calc["Bias20"] = (df_calc["close"] - df_calc["EMA20"]) / df_calc["EMA20"] * 100
    bollinger = calculate_bollinger_bands(df, current_price, current_date=current_date)

    latest = df_calc.iloc[-1]
    v5 = latest["V5"]
    v20 = latest["V20"]
    a5 = latest["A5"]
    bias20 = latest["Bias20"]

    # --- 价格趋势标签（6 种形态，不受成交量影响）---
    tag = "【震荡市：方向不明】"
    if v20 > 0 and v5 > 0 and a5 > 0:
        tag = "【主升浪加速：长短共振】"
    elif v20 > 0 and v5 > 0 and a5 < 0:
        tag = "【上行降速：短线分歧/追高风险】"
    elif v20 < 0 and v5 < 0 and a5 < 0:
        tag = "【主跌浪加速：空头长短共振】"
    elif v20 < 0 and v5 < 0 and a5 > 0:
        tag = "【跌势放缓：左侧建仓观察区】"
    elif v20 < 0 and v5 > 0:
        tag = "【短期趋势转多：均线金叉预备】"
    elif v20 > 0 and v5 < 0:
        tag = "【短期趋势转空：均线死叉预备】"

    # --- tag + volume_regime 量价二次研判（§3.3，仅放量/缩量生效，中性直通）---
    _TV_MAP: dict[tuple[str, str], str] = {
        ("【主升浪加速：长短共振】",       "放量"): "【主升浪加速：长短共振】+【放量】✅ 突破有效性较高，资金承接增强 → 顺势跟踪，避免脱离位置追高",
        ("【主升浪加速：长短共振】",       "缩量"): "【主升浪加速：长短共振】+【缩量】✅ 惜售加速特征，抛压较轻 → 持有观察，关注后续是否补量",
        ("【上行降速：短线分歧/追高风险】", "放量"): "【上行降速：短线分歧/追高风险】+【放量】❌ 派发风险增强，需看位置和资金方向 → 高位主力流出则减仓/清仓，主力流入则减仓观察",
        ("【上行降速：短线分歧/追高风险】", "缩量"): "【上行降速：短线分歧/追高风险】+【缩量】⚠️ 强势整理/回调洗筹特征，抛压不重 → 持有观察，接近支撑且主力未流出可低吸",
        ("【主跌浪加速：空头长短共振】",   "放量"): "【主跌浪加速：空头长短共振】+【放量】❌ 破位风险增强，抛压释放更充分 → 控制仓位，避免过早抄底",
        ("【主跌浪加速：空头长短共振】",   "缩量"): "【主跌浪加速：空头长短共振】+【缩量】⚠️ 需区分位置：低位疑似假破位，中高位可能弱势延续 → 低位/超跌且主力未流出才视为疑似低吸区",
        ("【跌势放缓：左侧建仓观察区】",   "缩量"): "【跌势放缓：左侧建仓观察区】+【缩量】✅ 抛压衰减，左侧观察区 → 小仓分批观察，等待资金或结构确认",
        ("【跌势放缓：左侧建仓观察区】",   "放量"): "【跌势放缓：左侧建仓观察区】+【放量】⚠️ 多空分歧/下跌末端换手 → 观望或轻仓试探，等待缩量企稳或资金转强",
        ("【短期趋势转多：均线金叉预备】", "放量"): "【短期趋势转多：均线金叉预备】+【放量】✅ 转多有效性较高，短期成交认可 → 轻仓介入，等待 V20 转正确认",
        ("【短期趋势转多：均线金叉预备】", "缩量"): "【短期趋势转多：均线金叉预备】+【缩量】⚠️ 弱修复，量能不足 → 观望为主，不追高",
        ("【短期趋势转空：均线死叉预备】", "放量"): "【短期趋势转空：均线死叉预备】+【放量】❌ 回调风险增强，分歧/抛压放大 → 减仓观察，等待回调结束",
        ("【短期趋势转空：均线死叉预备】", "缩量"): "【短期趋势转空：均线死叉预备】+【缩量】⚠️ 弱回调/洗盘观察 → 仅在中期仍多、接近 POC/支撑且主力未流出时视为疑似低吸区",
    }
    if volume_regime in ("放量", "缩量"):
        tag_combined = _TV_MAP.get((tag, volume_regime), f"{tag}+【{volume_regime}】")
    else:
        tag_combined = tag

    # 当日涨跌描述当前 K 线，EMA 导数描述原有趋势。只有二者方向冲突时才改写展示标签，
    # 避免把单日回调误报成完整下跌趋势，也避免用“洗筹/低吸”掩盖当日明显走弱。
    tag_combined = _combine_price_action_tag(
        tag_combined=tag_combined,
        current_change_rate=current_change_rate,
        volume_regime=volume_regime,
        v20=v20,
        v5=v5,
        a5=a5,
    )

    def _sf(x: float) -> float:
        return round(x, 2) if not pd.isna(x) else 0.0

    return {
        "tag": tag,
        "tag_combined": tag_combined,
        "v5": _sf(v5),
        "v20": _sf(v20),
        "a5": _sf(a5),
        "bias20": _sf(bias20),
        **bollinger,
        "volume_regime": volume_regime,
        "volume_ratio_target_ema5": r_target_ema5,
        "volume_ratio_target_ema20": r_target_ema20,
    }


def extract_pivots(prices: List[float], order: int = 3) -> tuple[List[float], List[float]]:
    if len(prices) < (2 * order + 1):
        return [], []
    peaks, troughs = [], []
    for i in range(order, len(prices) - order):
        window = prices[i - order : i + order + 1]
        value = prices[i]
        if value == max(window):
            peaks.append(value)
        if value == min(window):
            troughs.append(value)
    return peaks[-3:], troughs[-3:]


def classify_mid_shape(peaks: List[float], troughs: List[float]) -> str:
    if len(peaks) < 2 or len(troughs) < 2:
        return "形态样本不足"

    def downtrend(arr: List[float]) -> bool:
        return all(arr[i] >= arr[i + 1] for i in range(len(arr) - 1))

    def uptrend(arr: List[float]) -> bool:
        return all(arr[i] <= arr[i + 1] for i in range(len(arr) - 1))

    peak_down = downtrend(peaks)
    peak_up = uptrend(peaks)
    trough_down = downtrend(troughs)
    trough_up = uptrend(troughs)

    if peak_down and trough_up:
        return "收敛三角形/下降楔形"
    if peak_down and trough_down:
        return "下跌中继/下降通道"
    if peak_up and trough_up:
        return "上升通道"

    peak_range = (max(peaks) - min(peaks)) / max(np.mean(peaks), 1e-6)
    trough_range = (max(troughs) - min(troughs)) / max(np.mean(troughs), 1e-6)
    if peak_range <= 0.03 and trough_range <= 0.03:
        return "矩形震荡箱体"
    return "混合震荡结构"


def calc_poc(df: pd.DataFrame, lookback_days_mid: int = 90, bins: int = 10) -> Dict[str, Any]:
    default = {"poc_range": [0.0, 0.0], "poc_ratio_pct": 0.0, "price_proxy": "N/A"}
    if df is None or df.empty:
        return default

    d = df.tail(min(lookback_days_mid, len(df))).copy()
    for col in ("high", "low", "close", "vwap", "volume", "turnover", "amount"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["close"])
    if d.empty:
        return default

    if "vwap" in d.columns and d["vwap"].notna().any():
        d["px_proxy"] = d["vwap"].fillna(d["close"])
        price_proxy = "vwap"
    elif {"high", "low", "close"}.issubset(d.columns):
        d["px_proxy"] = (d["high"] + d["low"] + d["close"]) / 3.0
        price_proxy = "hlc3"
    else:
        d["px_proxy"] = d["close"]
        price_proxy = "close"

    vol_col = None
    for candidate in ("volume", "turnover", "amount"):
        if candidate in d.columns and d[candidate].notna().any():
            vol_col = candidate
            break
    if vol_col:
        weights = pd.to_numeric(d[vol_col], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    else:
        weights = np.ones(len(d), dtype=float)

    low_n = float(pd.to_numeric(d["low"], errors="coerce").min()) if "low" in d.columns else float(d["close"].min())
    high_n = float(pd.to_numeric(d["high"], errors="coerce").max()) if "high" in d.columns else float(d["close"].max())
    if high_n <= low_n:
        high_n = low_n + 1e-6

    edges = np.linspace(low_n, high_n, bins + 1)
    px = pd.to_numeric(d["px_proxy"], errors="coerce").fillna(d["close"]).to_numpy(dtype=float)
    idx = np.clip(np.digitize(px, edges, right=True) - 1, 0, bins - 1)
    vol_bin = np.bincount(idx, weights=weights, minlength=bins)
    poc_idx = int(np.argmax(vol_bin)) if len(vol_bin) else 0
    vol_sum = float(vol_bin.sum()) if len(vol_bin) else 0.0
    poc_ratio = float(vol_bin[poc_idx] / vol_sum * 100.0) if vol_sum > 0 else 0.0

    return {
        "poc_range": [round(float(edges[poc_idx]), 2), round(float(edges[poc_idx + 1]), 2)],
        "poc_ratio_pct": round(poc_ratio, 2),
        "price_proxy": price_proxy,
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def _format_rt_time_label(base_time_value: Any) -> str:
    now_dt = datetime.now()
    now_time = now_dt.strftime("%H:%M:%S")
    base_text = str(base_time_value) if base_time_value is not None else ""
    base_date = base_text.split(" ")[0] if base_text else now_dt.strftime("%Y-%m-%d")
    return f"{base_date} {now_time}(RT)"


def _calculate_max_contiguous_drop_pct(close_series: pd.Series) -> float:
    returns = pd.to_numeric(close_series, errors="coerce").pct_change().dropna()
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return 0.0
    returns = returns[returns > -0.999999]
    if returns.empty:
        return 0.0
    log_returns = np.log1p(returns).to_numpy(dtype=float)

    min_ending_here = float(log_returns[0])
    min_so_far = float(log_returns[0])
    for x in log_returns[1:]:
        min_ending_here = min(float(x), min_ending_here + float(x))
        min_so_far = min(min_so_far, min_ending_here)

    compounded = np.expm1(min_so_far) * 100.0
    return min(0.0, float(compounded))


def _calculate_max_contiguous_up_pct(close_series: pd.Series) -> float:
    returns = pd.to_numeric(close_series, errors="coerce").pct_change().dropna()
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return 0.0
    returns = returns[returns > -0.999999]
    if returns.empty:
        return 0.0
    log_returns = np.log1p(returns).to_numpy(dtype=float)

    max_ending_here = float(log_returns[0])
    max_so_far = float(log_returns[0])
    for x in log_returns[1:]:
        max_ending_here = max(float(x), max_ending_here + float(x))
        max_so_far = max(max_so_far, max_ending_here)

    compounded = np.expm1(max_so_far) * 100.0
    return max(0.0, float(compounded))


def _calculate_risk_metrics(high_series: pd.Series, low_series: pd.Series, close_series: pd.Series):
    max_cum_up_10d_pct = _calculate_max_contiguous_up_pct(close_series)
    max_cum_drop_10d_pct = _calculate_max_contiguous_drop_pct(close_series)

    rolling_peak_high = high_series.cummax()
    drawdown_series = (rolling_peak_high - low_series) / rolling_peak_high.replace(0, np.nan)
    max_drawdown_10d_pct = _safe_float(drawdown_series.max(), 0.0) * 100.0

    return max_cum_up_10d_pct, max_cum_drop_10d_pct, max_drawdown_10d_pct


def _build_short_window_price_distribute(
    last_n: pd.DataFrame,
    bucket_count: int = 5,
    top_k: int = 3,
) -> Dict[str, Any]:
    if last_n is None or last_n.empty:
        return {
            "short_window_price_distribute": [],
            "poc_range_10d": "",
            "poc_ratio_10d_pct": 0.0,
        }

    d = last_n.copy()
    for col in ("open", "high", "low", "close", "vwap", "volume", "turnover", "amount"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")

    if "vwap" in d.columns and d["vwap"].notna().any():
        d["px_proxy"] = d["vwap"]
    elif {"high", "low", "close"}.issubset(d.columns):
        d["px_proxy"] = (d["high"] + d["low"] + d["close"]) / 3.0
    elif {"open", "high", "low", "close"}.issubset(d.columns):
        d["px_proxy"] = (d["open"] + d["high"] + d["low"] + d["close"]) / 4.0
    else:
        d["px_proxy"] = d[[c for c in ("open", "high", "low", "close") if c in d.columns]].mean(axis=1)

    vol_col = None
    for candidate in ("volume", "turnover", "amount"):
        if candidate in d.columns and d[candidate].notna().any():
            vol_col = candidate
            break
    if vol_col is None:
        d["_vol_proxy"] = 1.0
        vol_col = "_vol_proxy"
    d[vol_col] = pd.to_numeric(d[vol_col], errors="coerce").fillna(0.0).clip(lower=0.0)

    low_n = float(pd.to_numeric(d["low"], errors="coerce").min()) if "low" in d.columns else float(d["px_proxy"].min())
    high_n = float(pd.to_numeric(d["high"], errors="coerce").max()) if "high" in d.columns else float(d["px_proxy"].max())
    if not np.isfinite(low_n) or not np.isfinite(high_n):
        return {
            "short_window_price_distribute": [],
            "poc_range_10d": "",
            "poc_ratio_10d_pct": 0.0,
        }
    if high_n <= low_n:
        high_n = low_n + 1e-6

    edges = np.linspace(low_n, high_n, bucket_count + 1)
    proxy_np = pd.to_numeric(d["px_proxy"], errors="coerce").fillna((low_n + high_n) / 2).to_numpy(dtype=float)
    idx_np = np.clip(np.digitize(proxy_np, edges, right=True) - 1, 0, bucket_count - 1)
    vol_bin = np.bincount(idx_np, weights=d[vol_col].to_numpy(dtype=float), minlength=bucket_count)
    vol_sum = float(vol_bin.sum())
    if vol_sum <= 0:
        vol_bin = np.ones(bucket_count, dtype=float)
        vol_sum = float(vol_bin.sum())

    bucket_items = []
    for i in range(bucket_count):
        ratio = float(vol_bin[i] / vol_sum * 100.0)
        bucket_items.append(
            {
                "bucket_range": f"{edges[i]:.2f}-{edges[i+1]:.2f}",
                "volume_ratio_pct": round(ratio, 2),
            }
        )
    bucket_items.sort(key=lambda x: x["volume_ratio_pct"], reverse=True)
    top_buckets = bucket_items[: max(1, min(top_k, len(bucket_items)))]

    poc_idx = int(np.argmax(vol_bin))
    poc_ratio = float(vol_bin[poc_idx] / vol_sum * 100.0)
    poc_range = f"{edges[poc_idx]:.2f}-{edges[poc_idx + 1]:.2f}"

    return {
        "short_window_price_distribute": top_buckets,
        "poc_range_10d": poc_range,
        "poc_ratio_10d_pct": round(poc_ratio, 2),
    }
