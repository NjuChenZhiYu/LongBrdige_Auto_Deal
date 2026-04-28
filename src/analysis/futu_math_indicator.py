import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def calculate_ema_derivatives(df: pd.DataFrame, current_price: float) -> dict:
    """
    计算港股均线衍生指标与多周期共振量化标签 (EMA MTF & V-Reversal Spec)
    结合盘中实时价格，消除指标滞后性。
    
    参数:
        df: pd.DataFrame, 必须包含 'close' 列，且按时间升序排列（历史日K线数据）
        current_price: float, 盘中实时价格
        
    返回:
        dict: 包含 'tag', 'v5', 'a5', 'bias20' 等计算结果的字典
    """
    if df is None or df.empty or 'close' not in df.columns or len(df) < 20:
        logger.warning("Data too short or missing 'close' column for EMA derivatives calculation.")
        return {"tag": "数据不足", "v5": 0.0, "a5": 0.0, "bias20": 0.0}

    # 0. 拼接或更新最新价格
    # 强制将最后一行（如果代表今天）或新增一行作为实时数据，以确保最新价格权重最大
    # 为了简化且不依赖具体日期列格式，直接用 current_price 更新或追加到最后
    # 假设 df 已经是处理好的历史K线，如果最后一条不是当前价格，我们将其追加或覆盖
    # 为保证安全，如果最后一行与当前价格差别极大（不是同一天），通常我们直接追加
    # 这里采用统一的简单策略：始终将 current_price 作为最新收盘价拼接到最后计算
    df_calc = df.copy()
    df_calc.loc[len(df_calc)] = {'close': current_price} # 增加一行代表当下

    # 1. 计算机构级 EMA
    df_calc['EMA5'] = df_calc['close'].ewm(span=5, adjust=False).mean()
    df_calc['EMA20'] = df_calc['close'].ewm(span=20, adjust=False).mean()

    # 2. 计算一阶导数 V (百分比变化率)
    df_calc['V5'] = df_calc['EMA5'].pct_change() * 100
    df_calc['V20'] = df_calc['EMA20'].pct_change() * 100

    # 3. 计算二阶导数 A (速度的差分)
    df_calc['A5'] = df_calc['V5'].diff()

    # 4. 计算实时 Bias 乖离率
    df_calc['Bias20'] = (df_calc['close'] - df_calc['EMA20']) / df_calc['EMA20'] * 100

    # 获取最后一行数据（最新盘中状态）
    latest = df_calc.iloc[-1]
    
    v5 = latest['V5']
    v20 = latest['V20']
    a5 = latest['A5']
    bias20 = latest['Bias20']
    
    tag = "【震荡市：方向不明】"

    # 优先判断 3.1 节的 Bias 极限值场景 (左侧中和策略)
    if bias20 <= -12.0 and a5 > 0:
        tag = "【极度超跌：V型反转预备】"
    elif bias20 >= 12.0 and a5 < 0:
        tag = "【极度超买：估值透支预警】"
        
    # 若未触发左侧信号，再进行 3.2 节的右侧共振判定及 3.3 节的拐点判定
    elif v20 > 0 and v5 > 0 and a5 > 0:
        tag = "【主升浪加速：长短共振】"
    elif v20 > 0 and v5 > 0 and a5 < 0:
        tag = "【主升浪降速：高位震荡/诱多】"
    elif v20 < 0 and v5 < 0 and a5 < 0:
        tag = "【主跌浪加速：空头长短共振】"
    elif v20 < 0 and v5 < 0 and a5 > 0:
        tag = "【跌势放缓：左侧建仓观察区】"
    elif v20 < 0 and v5 > 0:
        tag = "【短期趋势转多：均线金叉预备】"
    elif v20 > 0 and v5 < 0:
        tag = "【短期趋势转空：均线死叉预备】"
        
    return {
        "tag": tag,
        "v5": round(v5, 2) if not pd.isna(v5) else 0.0,
        "v20": round(v20, 2) if not pd.isna(v20) else 0.0,
        "a5": round(a5, 2) if not pd.isna(a5) else 0.0,
        "bias20": round(bias20, 2) if not pd.isna(bias20) else 0.0
    }
    
def extract_pivots(prices: List[float], order: int = 3) -> tuple[List[float], List[float]]:
    """Extract local pivot highs/lows without scipy dependency."""
    if len(prices) < (2 * order + 1):
        return [], []
    peaks, troughs = [], []
    for i in range(order, len(prices) - order):
        window = prices[i - order:i + order + 1]
        value = prices[i]
        if value == max(window):
            peaks.append(value)
        if value == min(window):
            troughs.append(value)
    return peaks[-3:], troughs[-3:]

def classify_mid_shape(peaks: List[float], troughs: List[float]) -> str:
    """Classify a coarse mid-term chart shape from pivot sequences."""
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
    """Calculate POC range/ratio with price proxy priority: VWAP > HLC3 > Close."""
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
        "price_proxy": price_proxy
    }

def build_mid_trade_features(df: pd.DataFrame, lookback_days_mid: int = 90) -> Dict:
    """Build shape-first mid-term features from 60-90 day data window."""
    if df is None or df.empty:
        return {
            "window_used": 0,
            "shape": "数据不足",
            "position_pct": 0.0,
            "peaks": [],
            "troughs": [],
            "poc_range": [0.0, 0.0],
            "poc_ratio_pct": 0.0,
            "price_proxy": "N/A",
            "ema_entangle_pct": 0.0
        }

    d = df.tail(min(lookback_days_mid, len(df))).copy()
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"])
    if d.empty:
        return {
            "window_used": 0,
            "shape": "数据不足",
            "position_pct": 0.0,
            "peaks": [],
            "troughs": [],
            "poc_range": [0.0, 0.0],
            "poc_ratio_pct": 0.0,
            "price_proxy": "N/A",
            "ema_entangle_pct": 0.0
        }

    for col in ("high", "low", "volume", "turnover", "amount", "vwap"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")

    high_series = d["high"] if "high" in d.columns else d["close"]
    low_series = d["low"] if "low" in d.columns else d["close"]
    high_n = float(high_series.max())
    low_n = float(low_series.min())
    current_price = float(d["close"].iloc[-1])
    position_pct = 50.0 if high_n <= low_n else ((current_price - low_n) / (high_n - low_n) * 100.0)
    position_pct = max(0.0, min(100.0, position_pct))

    peaks, troughs = extract_pivots(d["close"].tolist(), order=3 if len(d) >= 21 else 2)
    shape = classify_mid_shape(peaks, troughs)

    poc = calc_poc(d, lookback_days_mid=lookback_days_mid, bins=10)

    span_long = 60 if len(d) >= 60 else 30
    ema20 = float(d["close"].ewm(span=20, adjust=False).mean().iloc[-1])
    ema_long = float(d["close"].ewm(span=span_long, adjust=False).mean().iloc[-1])
    ema_entangle_pct = abs(ema20 - ema_long) / max(abs(ema_long), 1e-6) * 100.0

    return {
        "window_used": int(len(d)),
        "shape": shape,
        "position_pct": round(position_pct, 2),
        "peaks": [round(float(v), 2) for v in peaks],
        "troughs": [round(float(v), 2) for v in troughs],
        "poc_range": poc["poc_range"],
        "poc_ratio_pct": poc["poc_ratio_pct"],
        "price_proxy": poc["price_proxy"],
        "ema_entangle_pct": round(ema_entangle_pct, 2)
    }

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)
    except Exception:
        return default


def _format_rt_time_label(base_time_value: Any) -> str:
    """Format RT timestamp with hh:mm:ss suffix, preserving trade date when possible."""
    now_dt = datetime.now()
    now_time = now_dt.strftime("%H:%M:%S")
    base_text = str(base_time_value) if base_time_value is not None else ""
    base_date = base_text.split(" ")[0] if base_text else now_dt.strftime("%Y-%m-%d")
    return f"{base_date} {now_time}(RT)"

def _calculate_tag_today_by_derivatives(
    d_current: pd.DataFrame,
    current_price: float,
    lookback_days_short: int
) -> str:
    """
    统一通过 calculate_ema_derivatives 计算当日标签（tag_today）。
    使用“前置历史 + 当日实时价格”口径，避免直接复用窗口统计字段。
    """
    history_for_today = d_current.iloc[:-1].copy()
    history_for_today = history_for_today.tail(min(len(history_for_today), max(20, lookback_days_short)))
    return calculate_ema_derivatives(history_for_today, current_price).get("tag", "数据不足")


def build_current_day_indicator(
    today_row: pd.Series,
    stock_snapshot: Dict[str, Any],
    date_col: str,
    vol_col: str,
    total_recent_volume: float,
    latest_tag: str
) -> Dict[str, Any]:
    """Build compact current-day snapshot fields."""
    day_volume = _safe_float(today_row.get(vol_col, 0.0))
    volume_ratio = (day_volume / total_recent_volume) if total_recent_volume > 0 else 0.0

    preclose = _safe_float(
        stock_snapshot.get("prev_close")
        or stock_snapshot.get("prev_close_price")
        or stock_snapshot.get("pre_close"),
        0.0,
    )
    intraday_den = preclose if preclose > 0 else max(_safe_float(today_row.get("close"), 0.0), 1e-6)
    intraday_range_pct = (_safe_float(today_row.get("high")) - _safe_float(today_row.get("low"))) / intraday_den * 100.0
    rt_price = _safe_float(stock_snapshot.get("last_price"), _safe_float(today_row.get("close"), 0.0))

    return {
        "date": str(today_row.get(date_col, "")),
        "rt_price": round(rt_price, 3),
        "open": round(_safe_float(today_row.get("open")), 3),
        "high": round(_safe_float(today_row.get("high")), 3),
        "low": round(_safe_float(today_row.get("low")), 3),
        "close": round(_safe_float(today_row.get("close")), 3),
        "change_rate": round(_safe_float(today_row.get("change_rate")), 2),
        "bias20": round(_safe_float(today_row.get("bias20")), 2),
        "volume_ratio": round(max(0.0, volume_ratio), 4),
        "tag_today": latest_tag,
        "intraday_range_pct": round(intraday_range_pct, 2),
    }


def _calculate_price_range_metrics(high_series, low_series, close_t):
    """计算10日内部形态判定所需的振幅与水位（不对外单独暴露）。"""
    high_10d_max = _safe_float(high_series.max())
    low_10d_min = _safe_float(low_series.min())
    amp_den = max(low_10d_min, 1e-6)
    amp_10d_pct = (high_10d_max - low_10d_min) / amp_den * 100.0

    close_percentile_10d = 0.5
    if high_10d_max > low_10d_min:
        close_percentile_10d = (close_t - low_10d_min) / (high_10d_max - low_10d_min)
    close_percentile_10d = max(0.0, min(1.0, close_percentile_10d))
    
    return amp_10d_pct, close_percentile_10d, high_10d_max, low_10d_min

def _calculate_max_contiguous_drop_pct(close_series: pd.Series) -> float:
    """
    计算窗口内“连续最大跌幅”（单位：pct 点，负值）。
    示例: [+1, -3, -4, +2, -5] -> -7（对应 -3 + -4）。
    """
    changes = pd.to_numeric(close_series, errors="coerce").pct_change().dropna() * 100.0
    if changes.empty:
        return 0.0

    min_ending_here = float(changes.iloc[0])
    min_so_far = float(changes.iloc[0])
    for val in changes.iloc[1:]:
        x = float(val)
        min_ending_here = min(x, min_ending_here + x)
        min_so_far = min(min_so_far, min_ending_here)
    return min(0.0, min_so_far)


def _calculate_max_contiguous_up_pct(close_series: pd.Series) -> float:
    """
    计算窗口内“连续最大涨幅”（单位：pct 点，正值）。
    示例: [+1, -3, -4, +2, +5] -> +7（对应 +2 + +5）。
    """
    changes = pd.to_numeric(close_series, errors="coerce").pct_change().dropna() * 100.0
    if changes.empty:
        return 0.0

    max_ending_here = float(changes.iloc[0])
    max_so_far = float(changes.iloc[0])
    for val in changes.iloc[1:]:
        x = float(val)
        max_ending_here = max(x, max_ending_here + x)
        max_so_far = max(max_so_far, max_ending_here)
    return max(0.0, max_so_far)


def _calculate_risk_metrics(high_series, low_series, close_series):
    """计算风险统计指标（连续最大涨幅 + 连续最大跌幅 + 最大回撤）。"""
    max_cum_up_10d_pct = _calculate_max_contiguous_up_pct(close_series)
    max_cum_drop_10d_pct = _calculate_max_contiguous_drop_pct(close_series)

    rolling_peak_high = high_series.cummax()
    drawdown_series = (rolling_peak_high - low_series) / rolling_peak_high.replace(0, np.nan)
    max_drawdown_10d_pct = _safe_float(drawdown_series.max(), 0.0) * 100.0
    
    return max_cum_up_10d_pct, max_cum_drop_10d_pct, max_drawdown_10d_pct

def _derive_shape_10d_tag(amp_10d_pct: float, close_percentile_10d: float) -> str:
    """10日形态标签：只保留一个结构化输出字段。"""
    if amp_10d_pct < 4 and close_percentile_10d >= 0.7:
        return "窄幅压缩后上沿试探"
    if amp_10d_pct < 4 and close_percentile_10d <= 0.3:
        return "窄幅压缩后下沿承压"
    if amp_10d_pct >= 10 and close_percentile_10d >= 0.6:
        return "高波动上行推进"
    if amp_10d_pct >= 10 and close_percentile_10d <= 0.4:
        return "高波动下行探底"
    return "区间震荡"

def _build_short_window_price_distribute(
    last_n: pd.DataFrame,
    bucket_count: int = 5,
    top_k: int = 3
) -> Dict[str, Any]:
    """
    计算短窗口筹码分布（10日）。
    映射口径：VWAP > HLC3 > OHLC4（禁止 close->volume 单点映射）。
    """
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

    # price proxy priority: VWAP > HLC3 > OHLC4
    if "vwap" in d.columns and d["vwap"].notna().any():
        d["px_proxy"] = d["vwap"]
    elif {"high", "low", "close"}.issubset(d.columns):
        d["px_proxy"] = (d["high"] + d["low"] + d["close"]) / 3.0
    elif {"open", "high", "low", "close"}.issubset(d.columns):
        d["px_proxy"] = (d["open"] + d["high"] + d["low"] + d["close"]) / 4.0
    else:
        # 极端缺字段兜底，仍保持非 close-only 设计目标，退化为可用均值
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
        bucket_items.append({
            "bucket_range": f"{edges[i]:.2f}-{edges[i+1]:.2f}",
            "volume_ratio_pct": round(ratio, 2),
        })
    bucket_items.sort(key=lambda x: x["volume_ratio_pct"], reverse=True)
    top_buckets = bucket_items[:max(1, min(top_k, len(bucket_items)))]

    poc_idx = int(np.argmax(vol_bin))
    poc_ratio = float(vol_bin[poc_idx] / vol_sum * 100.0)
    poc_range = f"{edges[poc_idx]:.2f}-{edges[poc_idx + 1]:.2f}"

    return {
        "short_window_price_distribute": top_buckets,
        "poc_range_10d": poc_range,
        "poc_ratio_10d_pct": round(poc_ratio, 2),
    }

def build_short_window_indicator(
    last_n: pd.DataFrame,
    window_target: int = 10,
) -> Dict[str, Any]:
    """Build simplified 10-day summary: up/down risk + shape tag only."""
    window_used = int(len(last_n))

    high_series = pd.to_numeric(last_n.get("high", last_n["close"]), errors="coerce").fillna(last_n["close"])
    low_series = pd.to_numeric(last_n.get("low", last_n["close"]), errors="coerce").fillna(last_n["close"])
    close_series = pd.to_numeric(last_n["close"], errors="coerce").fillna(0.0)
    close_t = _safe_float(close_series.iloc[-1]) if len(close_series) > 0 else 0.0

    amp_10d_pct, close_percentile_10d, high_10d_max, _ = _calculate_price_range_metrics(
        high_series, low_series, close_t
    )
    max_cum_up_10d_pct, max_cum_drop_10d_pct, max_drawdown_10d_pct = _calculate_risk_metrics(
        high_series, low_series, close_series
    )
    shape_10d_tag = _derive_shape_10d_tag(amp_10d_pct, close_percentile_10d)
    chip_dist = _build_short_window_price_distribute(last_n, bucket_count=5, top_k=3)

    return {
        "window_target": int(window_target),
        "window_used": window_used,
        "short_window_incomplete": window_used < window_target,
        "max_cum_up_10d_pct": round(max_cum_up_10d_pct, 2),
        "max_cum_drop_10d_pct": round(max_cum_drop_10d_pct, 2),
        "max_drawdown_10d_pct": round(max_drawdown_10d_pct, 2),
        "shape_10d_tag": shape_10d_tag,
        "short_window_price_distribute": chip_dist["short_window_price_distribute"],
        "poc_range_10d": chip_dist["poc_range_10d"],
        "poc_ratio_10d_pct": chip_dist["poc_ratio_10d_pct"],
    }

def _empty_short_term_payload(lookback_days_short: int, flow_label: str, smart_net: float, retail_net: float) -> Dict[str, Any]:
    today = {
        "date": "",
        "rt_price": 0.0,
        "open": 0.0,
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
        "change_rate": 0.0,
        "bias20": 0.0,
        "volume_ratio": 0.0,
        "tag_today": "数据不足",
        "intraday_range_pct": 0.0
    }
    summary_10d = {
        "max_cum_up_10d_pct": 0.0,
        "max_cum_drop_10d_pct": 0.0,
        "max_drawdown_10d_pct": 0.0,
        "shape_10d_tag": "数据不足",
        "short_window_price_distribute": [],
        "poc_range_10d": "",
        "poc_ratio_10d_pct": 0.0,
    }
    return {
        "window_target": lookback_days_short,
        "window_used": 0,
        "short_window_incomplete": True,
        "current_price": 0.0,
        "price_source": "NO_DATA_FALLBACK",
        "flow_label": flow_label,
        "smart_net_wan": smart_net,
        "retail_net_wan": retail_net,
        "latest_tech_tag": "数据不足",
        "today": today,
        "summary_10d": summary_10d,
        "recent_days": {"today": today, "summary_10d": summary_10d},
    }

def _prepare_short_term_dataset(
    klines_df: pd.DataFrame,
    stock_snapshot: Dict[str, Any],
    lookback_days_short: int
) -> Dict[str, Any]:
    """
    准备短期分析所需数据：
    1) 清洗并补齐OHLC基础列；
    2) 融合实时价格生成 d_current；
    3) 计算短期技术衍生列；
    4) 识别成交量权重列并切片 last_n。
    """
    d = klines_df.copy()
    date_col = "time_key" if "time_key" in d.columns else ("date" if "date" in d.columns else None)
    if date_col is None:
        d["time_key"] = d.index.astype(str)
        date_col = "time_key"
    d = d.sort_values(by=date_col).reset_index(drop=True)

    for col in ("open", "close", "high", "low", "pre_close", "preclose", "prev_close", "last_close", "vwap"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    if "open" not in d.columns:
        d["open"] = d["close"]
    if "high" not in d.columns:
        d["high"] = d["close"]
    if "low" not in d.columns:
        d["low"] = d["close"]

    d = d.dropna(subset=["close"])
    if d.empty:
        raise ValueError("EMPTY_KLINES")

    current_price = float(stock_snapshot.get("last_price", 0.0))
    if current_price == 0.0:
        current_price = float(d["close"].iloc[-1])

    short_calc_window = max(lookback_days_short + 20, 30)
    d = d.tail(min(len(d), short_calc_window)).copy()

    d_current = d.copy()
    latest_row = d_current.iloc[-1].copy()
    # 强制将实时价格作为“当前时刻”样本追加到序列末端，
    # 保证 short 侧指标不再停留在前一交易日收盘口径。
    latest_row["open"] = _safe_float(latest_row.get("open"), _safe_float(latest_row.get("close"), current_price))
    latest_row["close"] = current_price
    latest_row["high"] = max(_safe_float(latest_row.get("high"), current_price), current_price)
    latest_row["low"] = min(_safe_float(latest_row.get("low"), current_price), current_price)
    if date_col in d_current.columns:
        latest_row[date_col] = _format_rt_time_label(latest_row.get(date_col))
    d_current.loc[len(d_current)] = latest_row

    close = d_current["close"]
    d_current["change_rate"] = close.pct_change() * 100.0
    d_current["ema12"] = close.ewm(span=12, adjust=False).mean()
    d_current["ema26"] = close.ewm(span=26, adjust=False).mean()
    d_current["dif"] = d_current["ema12"] - d_current["ema26"]
    d_current["dea"] = d_current["dif"].ewm(span=9, adjust=False).mean()
    d_current["macd"] = (d_current["dif"] - d_current["dea"]) * 2.0
    d_current["ema5"] = close.ewm(span=5, adjust=False).mean()
    d_current["ema20"] = close.ewm(span=20, adjust=False).mean()
    d_current["v5"] = d_current["ema5"].pct_change() * 100.0
    d_current["v20"] = d_current["ema20"].pct_change() * 100.0
    d_current["a5"] = d_current["v5"].diff()
    d_current["a20"] = d_current["v20"].diff()
    d_current["bias20"] = (close - d_current["ema20"]) / d_current["ema20"] * 100.0

    vol_col = None
    for candidate in ("volume", "turnover", "amount"):
        if candidate in d_current.columns:
            d_current[candidate] = pd.to_numeric(d_current[candidate], errors="coerce")
            if d_current[candidate].notna().any():
                vol_col = candidate
                break
    if vol_col is None:
        d_current["_volume_proxy"] = 1.0
        vol_col = "_volume_proxy"
    d_current[vol_col] = pd.to_numeric(d_current[vol_col], errors="coerce").fillna(0.0).clip(lower=0.0)

    last_n = d_current.tail(min(lookback_days_short, len(d_current))).copy().reset_index(drop=True)
    total_recent_volume = float(last_n[vol_col].sum()) if vol_col in last_n.columns else 0.0

    return {
        "date_col": date_col,
        "current_price": current_price,
        "d_current": d_current,
        "vol_col": vol_col,
        "last_n": last_n,
        "total_recent_volume": total_recent_volume,
    }


def build_short_term_memory(
    klines_df: Optional[pd.DataFrame],
    stock_snapshot: Dict[str, Any],
    capital_data: Optional[pd.DataFrame],
    lookback_days_short: int = 10
) -> Dict[str, Any]:
    """Build short-term memory by composing current-day and short-window indicators."""
    from src.api.futu.client import futu_client

    if klines_df is None or klines_df.empty:
        flow_label, smart_net, retail_net = futu_client.analyze_capital_flow(
            capital_data, float(stock_snapshot.get("change_rate", 0.0))
        )
        return _empty_short_term_payload(lookback_days_short, flow_label, smart_net, retail_net)

    try:
        prepared = _prepare_short_term_dataset(klines_df, stock_snapshot, lookback_days_short)
    except ValueError:
        return _empty_short_term_payload(lookback_days_short, "数据缺失", 0.0, 0.0)

    date_col = prepared["date_col"]
    current_price = prepared["current_price"]
    d_current = prepared["d_current"]
    vol_col = prepared["vol_col"]
    last_n = prepared["last_n"]
    total_recent_volume = prepared["total_recent_volume"]

    flow_label, smart_net, retail_net = futu_client.analyze_capital_flow(
        capital_data, float(stock_snapshot.get("change_rate", 0.0))
    )

    latest_tag = _calculate_tag_today_by_derivatives(
        d_current=d_current,
        current_price=current_price,
        lookback_days_short=lookback_days_short,
    )

    today = build_current_day_indicator(
        today_row=last_n.iloc[-1],
        stock_snapshot=stock_snapshot,
        date_col=date_col,
        vol_col=vol_col,
        total_recent_volume=total_recent_volume,
        latest_tag=latest_tag,
    )
    summary_10d = build_short_window_indicator(
        last_n=last_n,
        window_target=lookback_days_short,
    )

    return {
        # Keep top-level compatibility for prompt consumers, but source from summary_10d only.
        "window_target": summary_10d["window_target"],
        "window_used": summary_10d["window_used"],
        "short_window_incomplete": summary_10d["short_window_incomplete"],
        "current_price": round(float(current_price), 3),
        "price_source": "REALTIME_LAST_PRICE_APPEND",
        "flow_label": flow_label,
        "smart_net_wan": smart_net,
        "retail_net_wan": retail_net,
        "latest_tech_tag": latest_tag,
        "today": today,
        "summary_10d": summary_10d,
        "recent_days": {"today": today, "summary_10d": summary_10d},
    }

def hk_basic_finance_data(stock_snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据 Futu API 的快照提取基本面估值与财务数据。
    """
    if not stock_snapshot:
        stock_snapshot = {}

    def _is_missing(raw: Any) -> bool:
        if raw is None:
            return True
        try:
            return bool(pd.isna(raw))
        except Exception:
            return False

    def _fmt_amount(val: float, raw: Any) -> str:
        if _is_missing(raw):
            return "无数据"
        if abs(val) > 1_0000_0000:
            return f"{round(val / 1_0000_0000.0, 2)}亿"
        return f"{round(val / 1_0000.0, 2)}万"

    def _fmt_ratio(val: float, raw: Any) -> str:
        if _is_missing(raw):
            return "无数据"
        return f"{round(val, 2)}"

    total_market_val_raw = stock_snapshot.get("total_market_val")
    circular_market_val_raw = stock_snapshot.get("circular_market_val")
    net_profit_raw = stock_snapshot.get("net_profit")
    pe_ratio_raw = stock_snapshot.get("pe_ratio")
    pe_ttm_ratio_raw = stock_snapshot.get("pe_ttm_ratio")
    pb_ratio_raw = stock_snapshot.get("pb_ratio")

    total_market_val = _safe_float(total_market_val_raw, 0.0)
    circular_market_val = _safe_float(circular_market_val_raw, 0.0)
    net_profit = _safe_float(net_profit_raw, 0.0)
    pe_ratio = _safe_float(pe_ratio_raw, 0.0)
    pe_ttm_ratio = _safe_float(pe_ttm_ratio_raw, 0.0)
    pb_ratio = _safe_float(pb_ratio_raw, 0.0)

    return {
        "total_market_val": _fmt_amount(total_market_val, total_market_val_raw),
        "circular_market_val": _fmt_amount(circular_market_val, circular_market_val_raw),
        "net_profit": _fmt_amount(net_profit, net_profit_raw),
        "pe_ratio": _fmt_ratio(pe_ratio, pe_ratio_raw),
        "pe_ttm_ratio": _fmt_ratio(pe_ttm_ratio, pe_ttm_ratio_raw),
        "pb_ratio": _fmt_ratio(pb_ratio, pb_ratio_raw),
    }


def build_mid_term_trend(
    klines_df: Optional[pd.DataFrame],
    current_price: float,
    lookback_days_mid: int = 90
) -> Dict[str, Any]:
    """Build shape-first mid-term trend summary with sample-size fallback."""
    default = {
        "mode": "INSUFFICIENT_LT30",
        "window_target": lookback_days_mid,
        "window_used": 0,
        "summary": "趋势样本不足，仅可参考实时快照。",
        "shape": "数据不足",
        "position_pct": 0.0,
        "peaks": [],
        "troughs": [],
        "poc_range": [0.0, 0.0],
        "poc_ratio_pct": 0.0,
        "price_proxy": "N/A",
        "macd_cross_count": 0,
        "volatility_state": "数据不足",
        "latest_tech_tag": "数据不足"
    }
    if klines_df is None or klines_df.empty:
        return default

    d = klines_df.copy()
    if "time_key" in d.columns:
        d = d.sort_values("time_key")
    for col in ("close", "high", "low"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["close"])
    if d.empty:
        return default

    d = d.tail(min(lookback_days_mid, len(d))).copy()
    if d.empty:
        return default

    # 融合实时价格到中期窗口末端，用于更新形态位置与波动判断。
    d_current = d.copy()
    latest_row = d_current.iloc[-1].copy()
    rt_price = float(current_price) if current_price and current_price > 0 else float(d_current["close"].iloc[-1])
    latest_row["close"] = rt_price
    if "high" in d_current.columns:
        latest_row["high"] = max(float(latest_row.get("high", rt_price)), rt_price)
    if "low" in d_current.columns:
        latest_row["low"] = min(float(latest_row.get("low", rt_price)), rt_price)
    if "time_key" in d_current.columns:
        latest_row["time_key"] = _format_rt_time_label(latest_row.get("time_key"))
    d_current.loc[len(d_current)] = latest_row

    used = len(d_current)
    mid_features = build_mid_trade_features(d_current, lookback_days_mid=lookback_days_mid)
    poc = calc_poc(d_current, lookback_days_mid=lookback_days_mid, bins=10)
    ema_rt = calculate_ema_derivatives(d, rt_price)

    close = d_current["close"]
    returns = close.pct_change().dropna()
    vol_pct = float(returns.std() * np.sqrt(252) * 100.0) if not returns.empty else 0.0
    if vol_pct >= 45:
        vol_state = "高波动"
    elif vol_pct >= 25:
        vol_state = "中波动"
    else:
        vol_state = "低波动/压缩"

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    sign = np.sign((dif - dea).fillna(0.0).to_numpy())
    macd_cross = int(np.sum(sign[1:] * sign[:-1] < 0)) if len(sign) > 1 else 0

    base_used = len(d)
    mode = "FULL_90" if base_used >= lookback_days_mid else ("REDUCED_30_89" if base_used >= 30 else "INSUFFICIENT_LT30")
    if mode == "FULL_90":
        summary = (
            f"近{base_used}日形态为{mid_features['shape']}，已融合实时价格，当前位于90日空间{mid_features['position_pct']}%，"
            f"POC区间{poc['poc_range'][0]}-{poc['poc_range'][1]}（占比{poc['poc_ratio_pct']}%），"
            f"短期动量标签{ema_rt.get('tag', '数据不足')}。"
        )
    elif mode == "REDUCED_30_89":
        summary = (
            f"中期样本不足90日（实际{base_used}日），采用压缩版规则并融合实时价格。形态倾向{mid_features['shape']}，"
            f"MACD交叉{macd_cross}次，波动状态{vol_state}，短期动量标签{ema_rt.get('tag', '数据不足')}。"
        )
    else:
        summary = (
            f"可用历史仅{base_used}日（已融合实时价格），中期趋势样本不足，谨慎解读。"
            f"当前动量标签{ema_rt.get('tag', '数据不足')}。"
        )

    return {
        "mode": mode,
        "window_target": lookback_days_mid,
        "window_used": int(base_used),
        "price_source": "REALTIME_LAST_PRICE_APPEND",
        "summary": summary,
        "shape": mid_features.get("shape", "数据不足"),
        "position_pct": mid_features.get("position_pct", 0.0),
        "peaks": mid_features.get("peaks", []),
        "troughs": mid_features.get("troughs", []),
        "poc_range": poc["poc_range"],
        "poc_ratio_pct": poc["poc_ratio_pct"],
        "price_proxy": poc["price_proxy"],
        "macd_cross_count": macd_cross,
        "volatility_state": vol_state,
        "latest_tech_tag": ema_rt.get("tag", "数据不足"),
        "current_price": round(float(current_price), 3),
    }
