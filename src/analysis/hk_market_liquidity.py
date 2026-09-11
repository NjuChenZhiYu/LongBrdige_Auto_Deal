"""Hong Kong market liquidity from index turnover versus historical baselines."""

import logging
from datetime import date, datetime, time
from typing import Any, Dict, Mapping, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

HK_MARKET_LIQUIDITY_INDICES: Dict[str, str] = {
    "HK.800000": "恒生指数",
    "HK.800700": "恒生科技指数",
    "HK.800805": "恒生生物科技指数",
}
TURNOVER_WINDOWS: Tuple[int, ...] = (5, 30, 90, 180)
HEAT_WEIGHTS: Dict[int, float] = {5: 0.40, 30: 0.30, 90: 0.20, 180: 0.10}
WEIGHT_FORMULA = "5日×40% + 30日×30% + 90日×20% + 180日×10%"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_heat_level(ratio: Optional[float]) -> str:
    """Classify the weighted turnover ratio using documented boundaries."""
    if ratio is None:
        return "数据不足"
    if ratio >= 1.80:
        return "极度活跃"
    if ratio >= 1.30:
        return "明显放量"
    if ratio >= 0.80:
        return "常态成交"
    if ratio >= 0.50:
        return "明显缩量"
    return "流动性低迷"


def calculate_weighted_heat_ratio(
    ratios: Mapping[int, Optional[float]],
) -> Optional[float]:
    """Calculate weighted heat, renormalizing only when 90/180-day data is missing."""
    if ratios.get(5) is None or ratios.get(30) is None:
        return None
    available = [
        (float(ratios[window]), HEAT_WEIGHTS[window])
        for window in TURNOVER_WINDOWS
        if ratios.get(window) is not None
    ]
    total_weight = sum(weight for _, weight in available)
    if total_weight <= 0:
        return None
    return round(
        sum(ratio * weight for ratio, weight in available) / total_weight,
        4,
    )


def _hk_elapsed_trading_fraction(now_dt: datetime) -> float:
    """Return elapsed fraction of HK continuous trading (330 minutes)."""
    current = now_dt.time()
    morning_start = time(9, 30)
    morning_end = time(12, 0)
    afternoon_start = time(13, 0)
    afternoon_end = time(16, 0)
    if current < morning_start:
        return 0.0
    if current < morning_end:
        elapsed = (now_dt - datetime.combine(now_dt.date(), morning_start)).total_seconds() / 60
    elif current < afternoon_start:
        elapsed = 150.0
    elif current < afternoon_end:
        elapsed = 150.0 + (
            now_dt - datetime.combine(now_dt.date(), afternoon_start)
        ).total_seconds() / 60
    else:
        elapsed = 330.0
    return min(max(elapsed / 330.0, 0.0), 1.0)


def _parse_date(value: Any) -> Optional[date]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _normalize_history(klines_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if klines_df is None or klines_df.empty:
        return pd.DataFrame(columns=["trade_date", "turnover"])
    d = klines_df.copy()
    date_col = "time_key" if "time_key" in d.columns else "date" if "date" in d.columns else None
    if date_col is None or "turnover" not in d.columns:
        return pd.DataFrame(columns=["trade_date", "turnover"])
    d["trade_date"] = pd.to_datetime(d[date_col], errors="coerce").dt.date
    d["turnover"] = pd.to_numeric(d["turnover"], errors="coerce")
    d = d.dropna(subset=["trade_date", "turnover"])
    d = d.loc[d["turnover"] > 0].sort_values("trade_date")
    return d.drop_duplicates(subset=["trade_date"], keep="last").reset_index(drop=True)


def _resolve_comparable_turnover(
    snapshot: Mapping[str, Any],
    history: pd.DataFrame,
    now_dt: datetime,
) -> Tuple[float, Optional[date], str, bool, float]:
    """Use T-1 before 15:00; after 15:00 use confirmed same-day cumulative turnover."""
    snapshot_turnover = _safe_float(snapshot.get("turnover"))
    snapshot_date = _parse_date(snapshot.get("data_date") or snapshot.get("update_time"))
    fraction = _hk_elapsed_trading_fraction(now_dt)
    is_today = snapshot_date == now_dt.date()

    if is_today and now_dt.time() >= time(15, 0):
        mode = "CLOSED" if now_dt.time() >= time(16, 0) else "TODAY_CUMULATIVE_AFTER_1500"
        return snapshot_turnover, snapshot_date, mode, mode != "CLOSED", fraction

    completed_history = history.loc[history["trade_date"] < now_dt.date()]
    if not completed_history.empty:
        latest = completed_history.iloc[-1]
        return (
            _safe_float(latest.get("turnover")),
            latest.get("trade_date"),
            "PREVIOUS_COMPLETED_DAY",
            False,
            fraction,
        )

    if snapshot_date and snapshot_turnover > 0:
        return snapshot_turnover, snapshot_date, "LAST_COMPLETED", False, fraction

    if not history.empty:
        latest = history.iloc[-1]
        return (
            _safe_float(latest.get("turnover")),
            latest.get("trade_date"),
            "LAST_COMPLETED",
            False,
            fraction,
        )
    return 0.0, snapshot_date, "UNAVAILABLE", False, fraction


def _build_index_profile(
    code: str,
    name: str,
    snapshot: Mapping[str, Any],
    klines_df: Optional[pd.DataFrame],
    now_dt: datetime,
) -> Dict[str, Any]:
    history = _normalize_history(klines_df)
    comparable, comparison_date, mode, is_intraday, fraction = _resolve_comparable_turnover(
        snapshot,
        history,
        now_dt,
    )
    baseline = history
    if comparison_date is not None:
        baseline = history.loc[history["trade_date"] < comparison_date]

    ratios: Dict[int, Optional[float]] = {}
    averages: Dict[int, Optional[float]] = {}
    actual_days: Dict[int, int] = {}
    for window in TURNOVER_WINDOWS:
        available_days = min(window, len(baseline))
        actual_days[window] = available_days
        if len(baseline) < window or comparable <= 0:
            ratios[window] = None
            averages[window] = None
            continue
        avg_turnover = float(baseline["turnover"].tail(window).mean())
        averages[window] = round(avg_turnover, 2)
        ratios[window] = round(comparable / avg_turnover, 4) if avg_turnover > 0 else None

    weighted_ratio = calculate_weighted_heat_ratio(ratios)
    if ratios.get(5) is None or ratios.get(30) is None:
        confidence = "INSUFFICIENT"
    elif ratios.get(90) is None or ratios.get(180) is None:
        confidence = "REDUCED_CONFIDENCE"
    else:
        confidence = "NORMAL"

    return {
        "code": code,
        "name": name,
        "current_turnover": round(_safe_float(snapshot.get("turnover")), 2),
        "comparable_turnover": round(comparable, 2),
        "comparison_mode": mode,
        "comparison_date": comparison_date.isoformat() if comparison_date else None,
        "is_intraday": is_intraday,
        "elapsed_trading_fraction": round(fraction, 4),
        "change_rate": round(_safe_float(snapshot.get("change_rate")), 3),
        "ratios": {str(window): ratios[window] for window in TURNOVER_WINDOWS},
        "avg_turnovers": {str(window): averages[window] for window in TURNOVER_WINDOWS},
        "actual_days": {str(window): actual_days[window] for window in TURNOVER_WINDOWS},
        "weighted_heat_ratio": weighted_ratio,
        "heat_level": classify_heat_level(weighted_ratio),
        "confidence": confidence,
        "breadth": {
            "raise": int(_safe_float(snapshot.get("index_raise_count"))),
            "fall": int(_safe_float(snapshot.get("index_fall_count"))),
            "equal": int(_safe_float(snapshot.get("index_equal_count"))),
        },
    }


def infer_cross_index_state(indices: Mapping[str, Mapping[str, Any]]) -> str:
    if any(indices.get(code, {}).get("weighted_heat_ratio") is None for code in HK_MARKET_LIQUIDITY_INDICES):
        return "数据不完整"
    hsi = float(indices["HK.800000"]["weighted_heat_ratio"])
    tech = float(indices["HK.800700"]["weighted_heat_ratio"])
    bio = float(indices["HK.800805"]["weighted_heat_ratio"])
    hot = lambda value: value >= 1.30
    cold = lambda value: value < 0.80
    normal = lambda value: 0.80 <= value < 1.30
    if hot(hsi) and hot(tech) and hot(bio):
        return "全面共振升温"
    if hot(hsi) and hot(tech) and not hot(bio):
        return "大盘与成长共振"
    if hot(tech) and not hot(hsi) and not hot(bio):
        return "结构性科技行情"
    if hot(bio) and not hot(hsi) and not hot(tech):
        return "结构性医药行情"
    if cold(hsi) and cold(tech) and cold(bio):
        return "全面降温"
    if normal(hsi) and normal(tech) and normal(bio):
        return "整体常态"
    return "明显分化"


def _build_summary(indices: Mapping[str, Mapping[str, Any]], cross_state: str) -> str:
    parts = []
    for code, name in HK_MARKET_LIQUIDITY_INDICES.items():
        item = indices.get(code, {})
        weighted = item.get("weighted_heat_ratio")
        weighted_text = "无数据" if weighted is None else f"{float(weighted):.2f}"
        parts.append(f"{name}{weighted_text}（{item.get('heat_level', '数据不足')}）")
    return f"{'；'.join(parts)}。跨指数状态：{cross_state}。"


def build_hk_market_liquidity_profile(
    snapshots: Optional[Mapping[str, Mapping[str, Any]]] = None,
    klines_by_code: Optional[Mapping[str, pd.DataFrame]] = None,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build the three-index HK market liquidity profile."""
    now_dt = now_dt or datetime.now()
    if snapshots is None or klines_by_code is None:
        from src.api.futu.client import futu_client

        snapshots = futu_client.get_index_market_snapshots(list(HK_MARKET_LIQUIDITY_INDICES))
        klines_by_code = {
            code: futu_client.get_hk_index_historical_klines(code, 200)
            for code in HK_MARKET_LIQUIDITY_INDICES
        }

    indices = {
        code: _build_index_profile(
            code,
            name,
            (snapshots or {}).get(code, {}),
            (klines_by_code or {}).get(code),
            now_dt,
        )
        for code, name in HK_MARKET_LIQUIDITY_INDICES.items()
    }
    cross_state = infer_cross_index_state(indices)
    confidences = {item["confidence"] for item in indices.values()}
    if "INSUFFICIENT" in confidences:
        confidence = "INSUFFICIENT"
    elif "LOW_CONFIDENCE" in confidences:
        confidence = "LOW_CONFIDENCE"
    elif "REDUCED_CONFIDENCE" in confidences:
        confidence = "REDUCED_CONFIDENCE"
    else:
        confidence = "NORMAL"
    return {
        "source": "FUTU",
        "market_proxies": list(HK_MARKET_LIQUIDITY_INDICES),
        "metric": "turnover",
        "weight_formula": WEIGHT_FORMULA,
        "thresholds": "<0.50低迷；0.50-0.80缩量；0.80-1.30常态；1.30-1.80放量；>=1.80极度活跃",
        "confidence": confidence,
        "indices": indices,
        "cross_index_state": cross_state,
        "summary": _build_summary(indices, cross_state),
    }


def _format_amount(value: Any) -> str:
    amount = _safe_float(value)
    if amount <= 0:
        return "无数据"
    return f"{amount / 100_000_000:.2f}亿港元"


def format_hk_market_liquidity_prompt(profile: Mapping[str, Any]) -> str:
    """Render market liquidity with raw ratios and explicit weighted calculation."""
    lines = [
        "【港股大盘流动性与交易热度】",
        "- 统计口径：三个指数仅与各自历史成交额比较，因成分重叠严禁相加；turnover为成交额，不是成交量。",
        "- 时间口径：15:00前统一使用上一完整交易日；15:00后且快照确认为当日时使用当日累计成交额；不做盘中线性投影。",
        f"- 加权原理：{profile.get('weight_formula', WEIGHT_FORMULA)}；加权值越大，代表当前可比成交额相对历史均额越活跃。",
        f"- 分级阈值：{profile.get('thresholds', '无数据')}",
    ]
    indices = profile.get("indices", {}) or {}
    for code, name in HK_MARKET_LIQUIDITY_INDICES.items():
        item = indices.get(code, {}) or {}
        ratios = item.get("ratios", {}) or {}
        ratio_text = "/".join(
            "无数据" if ratios.get(str(window)) is None else f"{float(ratios[str(window)]):.2f}"
            for window in TURNOVER_WINDOWS
        )
        weighted = item.get("weighted_heat_ratio")
        weighted_text = "无数据" if weighted is None else f"{float(weighted):.2f}"
        lines.append(
            f"- {name}({code})：当前成交额{_format_amount(item.get('current_turnover'))}；"
            f"可比成交额{_format_amount(item.get('comparable_turnover'))}；"
            f"5/30/90/180日比值={ratio_text}；"
            f"加权热度={weighted_text}（{item.get('heat_level', '数据不足')}）；"
            f"口径={item.get('comparison_mode', 'UNAVAILABLE')}；置信度={item.get('confidence', 'INSUFFICIENT')}"
        )
    lines.extend(
        [
            f"- 跨指数状态：{profile.get('cross_index_state', '数据不完整')}",
            f"- 市场结论：{profile.get('summary', '数据不足')}",
            "- LLM解读约束：加权值只是成交活跃度，不直接等于看多；必须结合指数涨跌、个股位置和资金方向，区分放量上涨、放量下跌及结构性分化。",
        ]
    )
    return "\n".join(lines)
