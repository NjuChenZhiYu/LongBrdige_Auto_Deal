from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional

import pandas as pd

from src.analysis.single_stock_math_calculate import (
    _build_short_window_price_distribute,
    _format_rt_time_label as common_format_rt_time_label,
    _safe_float as common_safe_float,
    _calculate_risk_metrics,
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
            "peaks": [],
            "troughs": [],
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

    return {
        "shape": shape,
        "position_pct": round(position_pct, 2),
        "peaks": [round(float(v), 2) for v in peaks],
        "troughs": [round(float(v), 2) for v in troughs],
    }


def build_current_day_indicator(
    today_row: pd.Series,
    stock_snapshot: Dict[str, Any],
    date_col: str,
    latest_tag: str,
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

    return {
        "date": str(today_row.get(date_col, "")),
        "rt_price": round(rt_price, 3),
        "change_rate": round(change_rate, 2),
        "bias20": round(safe_float(today_row.get("bias20"), 0.0), 2),
        "tag_today": latest_tag,
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
