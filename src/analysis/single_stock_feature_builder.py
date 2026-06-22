from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from src.analysis.single_stock_math_calculate import (
    _build_short_window_price_distribute,
    _format_rt_time_label as common_format_rt_time_label,
    _safe_float as common_safe_float,
    _calculate_risk_metrics,
    calc_poc,
    calculate_ema_derivatives as common_calculate_ema_derivatives,
    classify_mid_shape,
    extract_pivots,
)


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    first_day = date(year, month, 1)
    offset = (weekday - first_day.weekday()) % 7
    return first_day + timedelta(days=offset + (n - 1) * 7)


def _fallback_us_eastern_tz(now_utc: datetime) -> timezone:
    """US Eastern DST: second Sunday in March to first Sunday in November."""
    year = now_utc.year
    dst_start_day = _nth_weekday_of_month(year, 3, 6, 2)
    dst_end_day = _nth_weekday_of_month(year, 11, 6, 1)
    dst_start_utc = datetime(year, 3, dst_start_day.day, 7, 0, tzinfo=timezone.utc)
    dst_end_utc = datetime(year, 11, dst_end_day.day, 6, 0, tzinfo=timezone.utc)
    return timezone(timedelta(hours=-4 if dst_start_utc <= now_utc < dst_end_utc else -5))


def _should_append_realtime_sample(
    d: pd.DataFrame,
    stock_snapshot: Dict[str, Any],
    date_col: str,
    now_dt: Optional[datetime] = None,
    realtime_session_checker: Optional[Callable[[Dict[str, Any]], Optional[bool]]] = None,
) -> bool:
    """
    Decide whether the short-term window should add an intraday synthetic row.
    Off-session runs must stay anchored to the latest completed trading day.
    """
    now_dt = now_dt or datetime.now()
    code = str(stock_snapshot.get("code") or stock_snapshot.get("symbol") or "").strip().upper()

    if realtime_session_checker is not None:
        try:
            is_realtime_session = realtime_session_checker(stock_snapshot)
        except Exception:
            return False
        if is_realtime_session is not None:
            return bool(is_realtime_session)

    if code.startswith("HK."):
        return False

    # Generic fallback: avoid creating a fake "today" row during weekends.
    return now_dt.weekday() < 5


def _parse_snapshot_date(value: Any) -> Optional[date]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _now_us_eastern(now_dt: Optional[datetime] = None) -> datetime:
    """Return current US Eastern time; fall back conservatively if tzdata is unavailable."""
    try:
        from zoneinfo import ZoneInfo

        eastern = ZoneInfo("America/New_York")
        if now_dt is not None and now_dt.tzinfo is not None:
            return now_dt.astimezone(eastern)
        if now_dt is not None:
            return now_dt
        return datetime.now(eastern)
    except Exception:
        if now_dt is not None and now_dt.tzinfo is not None:
            now_utc = now_dt.astimezone(timezone.utc)
            return now_utc.astimezone(_fallback_us_eastern_tz(now_utc))
        if now_dt is not None:
            return now_dt
        now_utc = datetime.now(timezone.utc)
        return now_utc.astimezone(_fallback_us_eastern_tz(now_utc))


def _should_use_current_volume(stock_snapshot: Dict[str, Any], now_dt: Optional[datetime] = None) -> bool:
    """Use same-day volume only when the current session is close enough to complete."""
    code = str(stock_snapshot.get("code") or stock_snapshot.get("symbol") or "").strip().upper()
    if code.startswith("HK."):
        now_dt = now_dt or datetime.now()
        if (now_dt.hour, now_dt.minute) < (15, 0):
            return False

        for key in ("update_time", "data_date", "last_trade_time"):
            if _parse_snapshot_date(stock_snapshot.get(key)) == now_dt.date():
                return True
        return False

    if code.startswith("US."):
        us_now = _now_us_eastern(now_dt)
        if (us_now.hour, us_now.minute) < (15, 0):
            return False

        for key in ("update_time", "data_date", "last_trade_time"):
            if _parse_snapshot_date(stock_snapshot.get(key)) == us_now.date():
                return True
        return False

    return False


def _add_short_technical_columns(d: pd.DataFrame) -> pd.DataFrame:
    close = d["close"]
    d["change_rate"] = close.pct_change() * 100.0
    d["ema12"] = close.ewm(span=12, adjust=False).mean()
    d["ema26"] = close.ewm(span=26, adjust=False).mean()
    d["dif"] = d["ema12"] - d["ema26"]
    d["dea"] = d["dif"].ewm(span=9, adjust=False).mean()
    d["macd"] = (d["dif"] - d["dea"]) * 2.0
    d["ema5"] = close.ewm(span=5, adjust=False).mean()
    d["ema20"] = close.ewm(span=20, adjust=False).mean()
    d["v5"] = d["ema5"].pct_change() * 100.0
    d["v20"] = d["ema20"].pct_change() * 100.0
    d["a5"] = d["v5"].diff()
    d["a20"] = d["v20"].diff()
    d["bias20"] = (close - d["ema20"]) / d["ema20"] * 100.0
    return d


def build_short_window_indicator(
    last_n: pd.DataFrame,
    window_target: int = 10,
) -> Dict[str, Any]:
    """Build simplified 10-day summary: risk + chip distribution."""
    window_used = int(len(last_n))

    high_series = pd.to_numeric(last_n.get("high", last_n["close"]), errors="coerce").fillna(last_n["close"])
    low_series = pd.to_numeric(last_n.get("low", last_n["close"]), errors="coerce").fillna(last_n["close"])
    close_series = pd.to_numeric(last_n["close"], errors="coerce").fillna(0.0)
    max_cum_up_10d_pct, max_cum_drop_10d_pct, max_drawdown_10d_pct = _calculate_risk_metrics(
        high_series, low_series, close_series
    )
    chip_dist = _build_short_window_price_distribute(last_n, bucket_count=5, top_k=3)

    return {
        "window_target": int(window_target),
        "window_used": window_used,
        "short_window_incomplete": window_used < window_target,
        "max_cum_up_10d_pct": round(max_cum_up_10d_pct, 2),
        "max_cum_drop_10d_pct": round(max_cum_drop_10d_pct, 2),
        "max_drawdown_10d_pct": round(-abs(max_drawdown_10d_pct), 2),
        "short_window_price_distribute": chip_dist["short_window_price_distribute"],
        "poc_range_10d": chip_dist["poc_range_10d"],
        "poc_ratio_10d_pct": chip_dist["poc_ratio_10d_pct"],
    }


def build_mid_trade_features(df: pd.DataFrame, lookback_days_mid: int = 90) -> Dict[str, Any]:
    """Build shape-first mid-term features from 60-90 day data window."""
    if df is None or df.empty:
        return {
            "shape": "数据不足",
            "position_pct": 0.0,
            "window_high": 0.0,
            "window_low": 0.0,
            "top_highs": [],
            "bottom_lows": [],
            "peaks": [],
            "troughs": [],
        }

    d = df.tail(min(lookback_days_mid, len(df))).copy()
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"])
    if d.empty:
        return {
            "shape": "数据不足",
            "position_pct": 0.0,
            "window_high": 0.0,
            "window_low": 0.0,
            "top_highs": [],
            "bottom_lows": [],
            "peaks": [],
            "troughs": [],
        }

    for col in ("high", "low", "volume", "turnover", "amount", "vwap"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")

    high_series = d["high"] if "high" in d.columns else d["close"]
    low_series = d["low"] if "low" in d.columns else d["close"]
    high_n = common_safe_float(high_series.max())
    low_n = common_safe_float(low_series.min())
    current_price = float(d["close"].iloc[-1])
    position_pct = 50.0 if high_n <= low_n else ((current_price - low_n) / (high_n - low_n) * 100.0)
    position_pct = max(0.0, min(100.0, position_pct))

    peaks, troughs = extract_pivots(d["close"].tolist(), order=3 if len(d) >= 21 else 2)
    shape = classify_mid_shape(peaks, troughs)

    return {
        "shape": shape,
        "position_pct": round(position_pct, 2),
        "window_high": round(high_n, 2),
        "window_low": round(low_n, 2),
        "top_highs": _extract_window_extremes(d, "high", ascending=False),
        "bottom_lows": _extract_window_extremes(d, "low", ascending=True),
        "peaks": [round(float(v), 2) for v in peaks],
        "troughs": [round(float(v), 2) for v in troughs],
    }


def _extract_window_extremes(
    d: pd.DataFrame,
    price_col: str,
    ascending: bool,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Return top/bottom price anchors with their occurrence dates."""
    if d is None or d.empty:
        return []

    date_col = "time_key" if "time_key" in d.columns else ("date" if "date" in d.columns else None)
    price_source_col = price_col if price_col in d.columns else "close"
    if price_source_col not in d.columns:
        return []

    cols = [price_source_col] + ([date_col] if date_col else [])
    values = d[cols].copy()
    values[price_source_col] = pd.Series(
        pd.to_numeric(values[price_source_col], errors="coerce"),
        index=values.index,
        dtype="float64",
    )
    values = values[values[price_source_col].notna()].copy()
    if values.empty:
        return []

    if date_col:
        values["_extreme_date"] = values[date_col].map(lambda value: str(value).split(" ")[0])
        values = values.sort_values(price_source_col, ascending=ascending)
        values = values.drop_duplicates(subset=["_extreme_date"], keep="first").head(top_k)
    else:
        values = values.sort_values(price_source_col, ascending=ascending).head(top_k)

    points: List[Dict[str, Any]] = []
    for idx, row in values.iterrows():
        date_value = row.get(date_col) if date_col else idx
        points.append({
            "date": str(date_value),
            "price": round(common_safe_float(row.get(price_source_col)), 2),
        })
    return points


def _prepare_trend_window_df(
    klines_df: pd.DataFrame,
    current_price: float,
    window_days: int,
) -> pd.DataFrame:
    d = klines_df.copy()
    date_col = "time_key" if "time_key" in d.columns else ("date" if "date" in d.columns else None)
    if date_col:
        d = d.sort_values(date_col)
    for col in ("open", "close", "high", "low", "volume", "turnover", "amount", "vwap"):
        if col in d.columns:
            d[col] = pd.Series(pd.to_numeric(d[col], errors="coerce"), index=d.index, dtype="float64")
    d = d.dropna(subset=["close"]).tail(min(max(window_days - 1, 1), len(d))).reset_index(drop=True).copy()
    if d.empty:
        return d

    rt_price = common_safe_float(current_price, common_safe_float(d["close"].iloc[-1]))
    if rt_price <= 0:
        rt_price = common_safe_float(d["close"].iloc[-1])

    latest_row = d.iloc[-1].copy()
    if "open" in d.columns:
        latest_row["open"] = rt_price
    latest_row["close"] = rt_price
    if "high" in d.columns:
        latest_row["high"] = rt_price
    if "low" in d.columns:
        latest_row["low"] = rt_price
    for vol_col in ("volume", "turnover", "amount"):
        if vol_col in d.columns:
            latest_row[vol_col] = 0.0
    if date_col:
        latest_row[date_col] = datetime.now().strftime("%Y-%m-%d %H:%M:%S(RT)")
    d.loc[len(d)] = latest_row
    return d.reset_index(drop=True)


def _max_drawdown_pct(close: pd.Series) -> float:
    if close.empty:
        return 0.0
    running_high = close.cummax()
    drawdown = close / running_high - 1.0
    return round(float(drawdown.min() * 100.0), 2)


def build_window_trend(
    klines_df: Optional[pd.DataFrame],
    current_price: float,
    window_days: int,
) -> Dict[str, Any]:
    """Build a single trend window with realtime price fused into the last sample."""
    default = {
        "window_days": int(window_days),
        "window_used": 0,
        "mode": "INSUFFICIENT",
        "summary": "样本不足，无法形成稳定趋势判断。",
        "shape": "数据不足",
        "position_pct": 0.0,
        "return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "volatility_pct": 0.0,
        "poc_range": [0.0, 0.0],
        "poc_ratio_pct": 0.0,
        "window_high": 0.0,
        "window_low": 0.0,
        "top_highs": [],
        "bottom_lows": [],
        "peaks": [],
        "troughs": [],
    }
    if klines_df is None or klines_df.empty:
        return default

    d = _prepare_trend_window_df(klines_df, current_price, window_days)
    if d.empty:
        return default

    close = pd.to_numeric(d["close"], errors="coerce").dropna()
    if close.empty:
        return default

    features = build_mid_trade_features(d, lookback_days_mid=window_days)
    poc = calc_poc(d, lookback_days_mid=window_days, bins=10)
    returns = close.pct_change().dropna()
    volatility_pct = float(returns.std() * (252 ** 0.5) * 100.0) if not returns.empty else 0.0
    return_pct = (float(close.iloc[-1]) / float(close.iloc[0]) - 1.0) * 100.0 if close.iloc[0] else 0.0
    max_drawdown = _max_drawdown_pct(close)

    if len(close) >= window_days:
        mode = f"FULL_{window_days}"
    elif len(close) >= max(20, window_days // 2):
        mode = f"REDUCED_{len(close)}"
    else:
        mode = "INSUFFICIENT"

    summary = (
        f"近{window_days}日实际样本{len(close)}日，区间涨跌{round(return_pct, 2)}%，最大回撤{max_drawdown}%，"
        f"当前位置位于区间{features.get('position_pct', 0.0)}%。"
    )

    return {
        "window_days": int(window_days),
        "window_used": int(len(close)),
        "mode": mode,
        "summary": summary,
        "shape": features.get("shape", "数据不足"),
        "position_pct": features.get("position_pct", 0.0),
        "return_pct": round(return_pct, 2),
        "max_drawdown_pct": max_drawdown,
        "volatility_pct": round(volatility_pct, 2),
        "poc_range": poc.get("poc_range", [0.0, 0.0]),
        "poc_ratio_pct": poc.get("poc_ratio_pct", 0.0),
        "window_high": features.get("window_high", 0.0),
        "window_low": features.get("window_low", 0.0),
        "top_highs": features.get("top_highs", []),
        "bottom_lows": features.get("bottom_lows", []),
        "peaks": features.get("peaks", []),
        "troughs": features.get("troughs", []),
    }


def build_multi_window_trends(
    klines_df: Optional[pd.DataFrame],
    current_price: float,
    windows: Sequence[int] = (30, 90, 180),
) -> List[Dict[str, Any]]:
    """Build stock trend snapshots across multiple horizons for prompt consumption."""
    normalized_windows = sorted({max(1, int(window)) for window in windows})
    return [
        build_window_trend(klines_df, current_price, window_days)
        for window_days in normalized_windows
    ]


def _classify_liquidity_ratio(window_days: int, ratio: float) -> str:
    if window_days == 20:
        low, high = 0.80, 1.25
    elif window_days == 60:
        low, high = 0.70, 1.40
    else:
        low, high = 0.60, 1.60

    if ratio < low:
        return "偏低"
    if ratio > high:
        return "偏高"
    return "安全"


def _format_liquidity_target(value: float, metric_name: str) -> str:
    if metric_name == "turnover_rate":
        return f"{round(value, 3)}%"
    if abs(value) >= 1_0000_0000:
        return f"{round(value / 1_0000_0000.0, 2)}亿"
    if abs(value) >= 1_0000:
        return f"{round(value / 1_0000.0, 2)}万"
    return f"{round(value, 2)}"


def _liquidity_market_today(stock_snapshot: Dict[str, Any], now_dt: Optional[datetime] = None) -> date:
    now_dt = now_dt or datetime.now()
    code = str(stock_snapshot.get("code") or stock_snapshot.get("symbol") or "").strip().upper()
    if code.startswith("US."):
        return _now_us_eastern(now_dt).date()
    return now_dt.date()


def _drop_current_session_liquidity_rows(
    d: pd.DataFrame,
    date_col: Optional[str],
    stock_snapshot: Dict[str, Any],
    now_dt: Optional[datetime] = None,
) -> pd.DataFrame:
    """Keep historical liquidity baselines anchored to completed trading days."""
    if not date_col or date_col not in d.columns:
        return d

    row_dates = pd.to_datetime(d[date_col], errors="coerce").dt.date
    market_today = _liquidity_market_today(stock_snapshot, now_dt=now_dt)
    return d.loc[row_dates != market_today].copy()


def _normalize_turnover_rate_pct(value: float, source_col: str) -> float:
    if source_col == "turnover_rate":
        return value * 100.0
    return value


def _normalize_snapshot_turnover_rate_pct(value: float, source_key: str) -> float:
    if source_key == "turnover_rate":
        return value
    return _normalize_turnover_rate_pct(value, source_key)


def _build_single_liquidity_profile(
    klines_df: Optional[pd.DataFrame],
    stock_snapshot: Dict[str, Any],
    metric_name: str,
    candidate_cols: Sequence[str],
    current_snapshot_keys: Sequence[str],
    now_dt: Optional[datetime] = None,
) -> str:
    if klines_df is None or klines_df.empty:
        return "无数据（缺少历史K线）"

    d = klines_df.copy()
    date_col = "time_key" if "time_key" in d.columns else ("date" if "date" in d.columns else None)
    if date_col:
        d = d.sort_values(date_col)
    d = _drop_current_session_liquidity_rows(d, date_col, stock_snapshot, now_dt=now_dt)
    if d.empty:
        return "样本不足（缺少已完成交易日K线）"

    metric_col = next((col for col in candidate_cols if col in d.columns), None)
    if metric_col is None:
        outstanding_shares = common_safe_float(stock_snapshot.get("outstanding_shares"), 0.0)
        if metric_name == "turnover_rate" and "volume" in d.columns and outstanding_shares > 0:
            metric_col = "_derived_turnover_rate"
            volume_series = pd.Series(
                pd.to_numeric(d["volume"], errors="coerce"),
                index=d.index,
                dtype="float64",
            )
            d[metric_col] = volume_series / outstanding_shares * 100.0
        else:
            return f"无数据（缺少{metric_name}历史列）"

    series: pd.Series = pd.Series(
        pd.to_numeric(d[metric_col], errors="coerce"),
        dtype="float64",
    ).dropna()
    if metric_name == "turnover_rate":
        series = series.map(lambda value: _normalize_turnover_rate_pct(float(value), metric_col))
    series = pd.Series(series[series > 0], dtype="float64")
    if len(series) < 20:
        return f"样本不足（{metric_name}有效样本{len(series)}日）"

    current_value = None
    if _should_use_current_volume(stock_snapshot, now_dt=now_dt):
        for key in current_snapshot_keys:
            raw_value = stock_snapshot.get(key)
            parsed_series = pd.Series(
                pd.to_numeric(pd.Series([raw_value]), errors="coerce"),
                dtype="float64",
            )
            parsed = parsed_series.iloc[0]
            if not pd.isna(parsed) and float(parsed) > 0:
                current_value = (
                    _normalize_snapshot_turnover_rate_pct(float(parsed), key)
                    if metric_name == "turnover_rate"
                    else float(parsed)
                )
                break
        if current_value is None and metric_name == "turnover_rate":
            outstanding_shares = common_safe_float(stock_snapshot.get("outstanding_shares"), 0.0)
            current_volume = common_safe_float(stock_snapshot.get("volume"), 0.0)
            if outstanding_shares > 0 and current_volume > 0:
                current_value = current_volume / outstanding_shares * 100.0

    if current_value is not None:
        target_value = current_value
        baseline: pd.Series = series
        target_label = "当日累计"
    else:
        target_value = float(series.iloc[-1])
        baseline = series.iloc[:-1] if len(series) > 20 else series
        target_label = "最近完整交易日"

    if baseline.empty:
        return f"样本不足（{metric_name}基线为空）"

    parts = []
    for window_days in (20, 60, 180):
        ema_value = float(baseline.ewm(span=window_days, adjust=False).mean().iloc[-1])
        if ema_value <= 0:
            parts.append(f"{window_days}日=无效")
            continue
        ratio = target_value / ema_value
        level = _classify_liquidity_ratio(window_days, ratio)
        parts.append(f"{window_days}日={round(ratio, 2)}x({level})")

    target_text = _format_liquidity_target(target_value, metric_name)
    return f"{target_label} {target_text}；" + "，".join(parts)


def build_liquidity_profiles(
    klines_df: Optional[pd.DataFrame],
    stock_snapshot: Dict[str, Any],
    now_dt: Optional[datetime] = None,
) -> Dict[str, str]:
    """Build compact turnover/turnover-rate profiles for the LLM liquidity block."""
    return {
        "turnover_liquidity_profile": _build_single_liquidity_profile(
            klines_df,
            stock_snapshot,
            metric_name="turnover",
            candidate_cols=("turnover", "amount"),
            current_snapshot_keys=("turnover", "amount"),
            now_dt=now_dt,
        ),
        "turnover_rate_liquidity_profile": _build_single_liquidity_profile(
            klines_df,
            stock_snapshot,
            metric_name="turnover_rate",
            candidate_cols=("turnover_rate",),
            current_snapshot_keys=("turnover_rate",),
            now_dt=now_dt,
        ),
    }


def build_current_day_indicator(
    today_row: pd.Series,
    stock_snapshot: Dict[str, Any],
    date_col: str,
    latest_tag: str,
    technical_result: Optional[Dict[str, Any]] = None,
    safe_float_fn: Optional[Callable[[Any, float], float]] = None,
    use_realtime_price: bool = True,
) -> Dict[str, Any]:
    """
    Build compact current-day snapshot fields.
    safe_float_fn 允许由市场层注入，避免这里依赖外部 client 或全局状态。
    """
    safe_float = safe_float_fn or (lambda v, d=0.0: float(v) if v is not None else d)
    close_price = safe_float(today_row.get("close"), 0.0)
    rt_price = safe_float(stock_snapshot.get("last_price"), close_price) if use_realtime_price else close_price
    row_change_rate = safe_float(today_row.get("change_rate"), 0.0)
    change_rate = (
        safe_float(stock_snapshot.get("change_rate"), row_change_rate)
        if use_realtime_price
        else row_change_rate
    )
    technical_result = technical_result or {}
    bb_tag = str(technical_result.get("bb_tag", "布林数据不足"))
    bb_pos = round(safe_float(technical_result.get("bb_pos"), 0.0), 3)
    bb_mid = round(safe_float(technical_result.get("bb_mid"), 0.0), 2)
    bb_upper = round(safe_float(technical_result.get("bb_upper"), 0.0), 2)
    bb_lower = round(safe_float(technical_result.get("bb_lower"), 0.0), 2)
    bb_width = round(safe_float(technical_result.get("bb_width"), 0.0), 2)
    bb_summary = f"{bb_tag}，bb_pos={bb_pos}，轨道={bb_lower}/{bb_mid}/{bb_upper}，带宽={bb_width}%"
    day_high = safe_float(stock_snapshot.get("high_price"), safe_float(today_row.get("high"), rt_price)) if use_realtime_price else safe_float(today_row.get("high"), rt_price)
    day_low = safe_float(stock_snapshot.get("low_price"), safe_float(today_row.get("low"), rt_price)) if use_realtime_price else safe_float(today_row.get("low"), rt_price)
    if day_high > day_low:
        intraday_position_pct = round((rt_price - day_low) / (day_high - day_low) * 100.0, 1)
        intraday_position = f"{intraday_position_pct}%"
    else:
        intraday_position_pct = 0.0
        intraday_position = "日内波动不足"

    return {
        "date": str(today_row.get(date_col, "")),
        "rt_price": round(rt_price, 3),
        "change_rate": round(change_rate, 2),
        "bias20": round(safe_float(today_row.get("bias20"), 0.0), 2),
        "tag_today": latest_tag,
        "day_high_low": f"{round(day_high, 3)} / {round(day_low, 3)}",
        "intraday_position": intraday_position,
        "intraday_position_pct": intraday_position_pct,
        "volume_regime": str(technical_result.get("volume_regime", "中性")),
        "bb_summary": bb_summary,
        "bb_tag": bb_tag,
        "bb_pos": bb_pos,
        "bb_mid": bb_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
    }


def calculate_tag_today_by_derivatives(
    d_current: pd.DataFrame,
    current_price: float,
    lookback_days_short: int,
) -> str:
    """
    统一通过 calculate_ema_derivatives 计算当日标签（tag_today）。
    使用“前置历史 + 当日实时价格”口径，避免直接复用窗口统计字段。
    """
    history_for_today = d_current.iloc[:-1].copy()
    history_for_today = history_for_today.tail(min(len(history_for_today), max(20, lookback_days_short)))
    return common_calculate_ema_derivatives(history_for_today, current_price).get("tag", "数据不足")


def empty_short_term_payload(lookback_days_short: int, smart_net: float, retail_net: float) -> Dict[str, Any]:
    today = {
        "date": "",
        "rt_price": 0.0,
        "bias20": 0.0,
        "tag_today": "数据不足",
        "day_high_low": "0.0 / 0.0",
        "intraday_position": "日内波动不足",
        "intraday_position_pct": 0.0,
        "volume_regime": "中性",
        "bb_summary": "布林数据不足",
        "bb_tag": "布林数据不足",
        "bb_pos": 0.0,
        "bb_mid": 0.0,
        "bb_upper": 0.0,
        "bb_lower": 0.0,
        "bb_width": 0.0,
    }
    summary_10d = {
        "max_cum_up_10d_pct": 0.0,
        "max_cum_drop_10d_pct": 0.0,
        "max_drawdown_10d_pct": 0.0,
        "short_window_price_distribute": [],
        "poc_range_10d": "",
        "poc_ratio_10d_pct": 0.0,
    }
    return {
        "window_used": 0,
        "short_window_incomplete": True,
        "smart_net_wan": smart_net,
        "retail_net_wan": retail_net,
        "today": today,
        "summary_10d": summary_10d,
    }


def prepare_short_term_dataset(
    klines_df: pd.DataFrame,
    stock_snapshot: Dict[str, Any],
    lookback_days_short: int,
    realtime_session_checker: Optional[Callable[[Dict[str, Any]], Optional[bool]]] = None,
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

    use_realtime_sample = _should_append_realtime_sample(
        d,
        stock_snapshot,
        date_col,
        realtime_session_checker=realtime_session_checker,
    )
    use_current_volume = use_realtime_sample and _should_use_current_volume(stock_snapshot)
    current_volume = common_safe_float(stock_snapshot.get("volume"), 0.0) if use_current_volume else None
    current_turnover = common_safe_float(stock_snapshot.get("turnover"), 0.0) if use_current_volume else None
    if not use_realtime_sample:
        current_price = float(d["close"].iloc[-1])
        current_volume = common_safe_float(d["volume"].iloc[-1], 0.0) if "volume" in d.columns else None
        if "turnover" in d.columns:
            current_turnover = common_safe_float(d["turnover"].iloc[-1], 0.0)
        elif "amount" in d.columns:
            current_turnover = common_safe_float(d["amount"].iloc[-1], 0.0)
        else:
            current_turnover = None
        d = _add_short_technical_columns(d)
        last_n = d.tail(min(lookback_days_short, len(d))).copy().reset_index(drop=True)
        return {
            "date_col": date_col,
            "current_price": current_price,
            "d_current": d,
            "last_n": last_n,
            "use_realtime_price": False,
            "current_volume": current_volume,
            "current_turnover": current_turnover,
        }

    d_current = d.copy()
    latest_row = d_current.iloc[-1].copy()
    # 强制将实时价格作为“当前时刻”样本追加到序列末端，
    # 保证 short 侧指标不再停留在前一交易日收盘口径。
    latest_row["open"] = common_safe_float(latest_row.get("open"), common_safe_float(latest_row.get("close"), current_price))
    latest_row["close"] = current_price
    latest_row["high"] = max(common_safe_float(latest_row.get("high"), current_price), current_price)
    latest_row["low"] = min(common_safe_float(latest_row.get("low"), current_price), current_price)
    if current_volume is not None and "volume" in d_current.columns:
        latest_row["volume"] = current_volume
    if current_turnover is not None:
        if "turnover" in d_current.columns:
            latest_row["turnover"] = current_turnover
        elif "amount" in d_current.columns:
            latest_row["amount"] = current_turnover
    if date_col in d_current.columns:
        latest_row[date_col] = common_format_rt_time_label(latest_row.get(date_col))
    d_current.loc[len(d_current)] = latest_row

    d_current = _add_short_technical_columns(d_current)

    last_n = d_current.tail(min(lookback_days_short, len(d_current))).copy().reset_index(drop=True)

    return {
        "date_col": date_col,
        "current_price": current_price,
        "d_current": d_current,
        "last_n": last_n,
        "use_realtime_price": True,
        "current_volume": current_volume,
        "current_turnover": current_turnover,
    }
