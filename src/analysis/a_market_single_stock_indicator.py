"""A-share single-stock indicator builder (Futu API).

First version keeps the HK report data shape so the service/prompt layer can
reuse the same short-term and multi-window trend builders.
"""
import logging
from typing import Any, Dict, Optional

import pandas as pd

from src.analysis.hk_single_stock_indicator import (
    build_mid_term_trend,
    build_short_term_memory,
    get_today_capital_flow,
)
from src.analysis.single_stock_feature_builder import (
    build_liquidity_profiles as common_build_liquidity_profiles,
)
from src.analysis.single_stock_math_calculate import (
    _safe_float as common_safe_float,
    build_revenue_breakdown_profile as common_build_revenue_breakdown_profile,
)

logger = logging.getLogger(__name__)


def _format_amount(val: float, raw: Any) -> str:
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


def _format_shares(val: float, raw: Any) -> str:
    if raw is None:
        return "无数据"
    try:
        if pd.isna(raw):
            return "无数据"
    except Exception:
        pass
    if abs(val) > 1_0000_0000:
        return f"{round(val / 1_0000_0000.0, 2)}亿股"
    if abs(val) > 1_0000:
        return f"{round(val / 1_0000.0, 2)}万股"
    return f"{round(val, 0)}股"


def _aggregate_a_market_capital_flow_from_df(
    flow_df: Optional[pd.DataFrame],
    window_days: int,
) -> Dict[str, Any]:
    """Aggregate A-share daily capital flow for a rolling window."""
    window_days = max(1, int(window_days))
    empty = {
        "window_days": window_days,
        "main_in_flow_cny": 0.0,
        "total_in_flow_cny": 0.0,
        "flow_status_tag": "资金流数据缺失",
    }
    if flow_df is None or flow_df.empty:
        return empty

    d = flow_df.copy()
    for col in ("main_in_flow", "in_flow"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
        else:
            d[col] = 0.0
    d = d.dropna(subset=["in_flow"])
    if d.empty:
        return empty

    d = d.tail(min(window_days, len(d)))
    records = d.to_dict("records")
    main_in = sum(common_safe_float(row.get("main_in_flow"), 0.0) for row in records if isinstance(row, dict))
    total_in = sum(common_safe_float(row.get("in_flow"), 0.0) for row in records if isinstance(row, dict))
    if main_in > 0 and total_in < 0:
        tag = "主力逆势吸筹"
    elif main_in > 0 and total_in >= 0:
        tag = "主力持续净流入"
    elif main_in < 0 and total_in < 0:
        tag = "资金共振流出"
    elif main_in < 0 <= total_in:
        tag = "大单撤退/小单承接"
    else:
        tag = "资金博弈不明"

    return {
        "window_days": window_days,
        "main_in_flow_cny": round(main_in, 2),
        "total_in_flow_cny": round(total_in, 2),
        "flow_status_tag": tag,
    }


def calculate_a_market_capital_flow_profiles(
    symbol: str,
    windows: Optional[tuple] = (5, 10, 90),
) -> Dict[int, Dict[str, Any]]:
    """Pull A-share capital-flow history once and compute multiple windows."""
    from src.api.futu.client import futu_client

    windows = tuple(sorted({max(1, int(w)) for w in (windows or (5, 10, 90))}))
    max_window = max(windows) if windows else 90
    flow_df = futu_client.get_capital_flow_history(symbol, window_days=max(max_window, 90))
    return {w: _aggregate_a_market_capital_flow_from_df(flow_df, window_days=w) for w in windows}


def a_market_basic_finance_data(
    stock_snapshot: Dict[str, Any],
    capital_flow_profiles: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Format A-share fundamental fields from a Futu get_market_snapshot row."""
    stock_snapshot = stock_snapshot or {}
    capital_flow_profiles = capital_flow_profiles or {}

    total_market_val_raw = stock_snapshot.get("total_market_val")
    circular_market_val_raw = stock_snapshot.get("circular_market_val")
    net_asset_raw = stock_snapshot.get("net_asset")
    issued_shares_raw = stock_snapshot.get("issued_shares")
    outstanding_shares_raw = stock_snapshot.get("outstanding_shares")

    flow_5d = capital_flow_profiles.get(5, {})
    flow_10d = capital_flow_profiles.get(10, {})
    flow_90d = capital_flow_profiles.get(90, {})

    return {
        "total_market_val": _format_amount(common_safe_float(total_market_val_raw, 0.0), total_market_val_raw),
        "circular_market_val": _format_amount(common_safe_float(circular_market_val_raw, 0.0), circular_market_val_raw),
        "issued_shares": _format_shares(common_safe_float(issued_shares_raw, 0.0), issued_shares_raw),
        "outstanding_shares": _format_shares(common_safe_float(outstanding_shares_raw, 0.0), outstanding_shares_raw),
        "net_asset": _format_amount(common_safe_float(net_asset_raw, 0.0), net_asset_raw),
        "main_in_flow_5d": _format_amount(
            common_safe_float(flow_5d.get("main_in_flow_cny"), 0.0),
            flow_5d.get("main_in_flow_cny"),
        ),
        "total_in_flow_5d": _format_amount(
            common_safe_float(flow_5d.get("total_in_flow_cny"), 0.0),
            flow_5d.get("total_in_flow_cny"),
        ),
        "main_in_flow_10d": _format_amount(
            common_safe_float(flow_10d.get("main_in_flow_cny"), 0.0),
            flow_10d.get("main_in_flow_cny"),
        ),
        "total_in_flow_10d": _format_amount(
            common_safe_float(flow_10d.get("total_in_flow_cny"), 0.0),
            flow_10d.get("total_in_flow_cny"),
        ),
        "main_in_flow_90d": _format_amount(
            common_safe_float(flow_90d.get("main_in_flow_cny"), 0.0),
            flow_90d.get("main_in_flow_cny"),
        ),
        "total_in_flow_90d": _format_amount(
            common_safe_float(flow_90d.get("total_in_flow_cny"), 0.0),
            flow_90d.get("total_in_flow_cny"),
        ),
    }


def build_a_market_fundamental_data(
    symbol: str,
    base_snapshot: Optional[Dict[str, Any]] = None,
    flow_windows: Optional[tuple] = (5, 10, 90),
    klines_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Build A-share fundamental, capital-flow, and liquidity profile data."""
    from src.api.futu.client import futu_client

    finance_snapshot: Dict[str, Any] = dict(base_snapshot or {})
    plate_info = "无数据"

    try:
        quote_ctx = futu_client.get_quote_context()
        ret_plate, plate_data = quote_ctx.get_owner_plate([symbol])
        if ret_plate == 0 and isinstance(plate_data, pd.DataFrame) and not plate_data.empty:
            valid_plates = plate_data[plate_data["plate_type"].isin(["INDUSTRY", "CONCEPT"])]
            if not valid_plates.empty:
                plate_info = "、".join(valid_plates["plate_name"].astype(str).tolist())

        ret_snap, snap_df = quote_ctx.get_market_snapshot([symbol])
        if ret_snap == 0 and isinstance(snap_df, pd.DataFrame) and not snap_df.empty:
            finance_snapshot.update(snap_df.iloc[0].to_dict())
    except Exception as e:
        logger.warning(f"[AMarket/Fundamental] Failed to fetch plate/snapshot for {symbol}: {e}")

    try:
        capital_flow_profiles = calculate_a_market_capital_flow_profiles(symbol, windows=flow_windows)
    except Exception as e:
        logger.warning(f"[AMarket/Fundamental] Failed to fetch capital flow profiles for {symbol}: {e}")
        capital_flow_profiles = {}

    fundamental_data = a_market_basic_finance_data(
        finance_snapshot,
        capital_flow_profiles=capital_flow_profiles,
    )
    fundamental_data["plate_info"] = plate_info
    fundamental_data.update(get_today_capital_flow(symbol))
    fundamental_data.update(common_build_liquidity_profiles(klines_df, finance_snapshot))
    fundamental_data["revenue_breakdown_profile"] = common_build_revenue_breakdown_profile(symbol, log_prefix="AMarket")
    return fundamental_data
