"""
US single-stock indicator builder (Futu API).

Mirrors hk_single_stock_indicator.py for the US market.
Symbol format: US.AAPL (Futu) ↔ AAPL.US (standard).

Three public entry-points:
  build_us_fundamental_data  – Module A: snapshot + plate + capital-flow profiles
  build_short_term_memory    – Module B: 10-day klines + historical capital flow
  build_mid_term_trend       – Module C: 90-day klines (reused from HK layer)
"""

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.analysis.single_stock_math_calculate import (
    _safe_float as common_safe_float,
    _format_rt_time_label as common_format_rt_time_label,
    calc_poc as common_calc_poc,
    calculate_ema_derivatives as common_calculate_ema_derivatives,
    classify_mid_shape as common_classify_mid_shape,
    extract_pivots as common_extract_pivots,
    _calculate_risk_metrics as common_calculate_risk_metrics,
    _build_short_window_price_distribute as common_build_short_window_price_distribute,
    _calculate_max_contiguous_drop_pct as common_calculate_max_contiguous_drop_pct,
    _calculate_max_contiguous_up_pct as common_calculate_max_contiguous_up_pct,
)
from src.analysis.single_stock_feature_builder import (
    _should_use_current_volume as common_should_use_current_volume,
    build_current_day_indicator as common_build_current_day_indicator,
    build_mid_trade_features as common_build_mid_trade_features,
    build_short_window_indicator as common_build_short_window_indicator,
    calculate_tag_today_by_derivatives as common_calculate_tag_today_by_derivatives,
    empty_short_term_payload as common_empty_short_term_payload,
    prepare_short_term_dataset as common_prepare_short_term_dataset,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatible re-exports (common math utilities)
# ---------------------------------------------------------------------------
calculate_ema_derivatives = common_calculate_ema_derivatives
extract_pivots = common_extract_pivots
classify_mid_shape = common_classify_mid_shape
calc_poc = common_calc_poc
build_mid_trade_features = common_build_mid_trade_features
_safe_float = common_safe_float
_format_rt_time_label = common_format_rt_time_label
build_current_day_indicator = common_build_current_day_indicator
_calculate_max_contiguous_drop_pct = common_calculate_max_contiguous_drop_pct
_calculate_max_contiguous_up_pct = common_calculate_max_contiguous_up_pct
_calculate_risk_metrics = common_calculate_risk_metrics
_build_short_window_price_distribute = common_build_short_window_price_distribute
build_short_window_indicator = common_build_short_window_indicator
calculate_tag_today_by_derivatives = common_calculate_tag_today_by_derivatives
empty_short_term_payload = common_empty_short_term_payload
prepare_short_term_dataset = common_prepare_short_term_dataset
should_use_current_volume = common_should_use_current_volume


# ---------------------------------------------------------------------------
# Capital-flow helpers (US, symmetric with HK layer)
# ---------------------------------------------------------------------------

def _aggregate_us_capital_flow_from_df(
    flow_df: Optional[pd.DataFrame], window_days: int
) -> Dict[str, Any]:
    """
    Aggregate US daily capital flow for a rolling window.

    Expected columns in flow_df (from futu get_capital_flow PeriodType.DAY):
        main_in_flow, in_flow, super_in_flow, big_in_flow, mid_in_flow, sml_in_flow
    """
    window_days = max(1, int(window_days))
    empty = {
        "window_days": window_days,
        "main_in_flow_usd": 0.0,
        "total_in_flow_usd": 0.0,
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
    main_in = float(d["main_in_flow"].fillna(0.0).sum())
    total_in = float(d["in_flow"].fillna(0.0).sum())

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
        "main_in_flow_usd": round(main_in, 2),
        "total_in_flow_usd": round(total_in, 2),
        "flow_status_tag": tag,
    }


def _derive_us_smart_retail_net(
    flow_df: Optional[pd.DataFrame],
    window_days: int = 10,
) -> tuple[float, float]:
    """
    Derive 10-day smart-money and retail-money net flows from historical DataFrame.

    Returns (smart_net_wan, retail_net_wan) in 万-unit (10 000).
    - smart_net  = sum of main_in_flow   (大单+特大单主力净流合计)
    - retail_net = sum of sml_in_flow + mid_in_flow  (中小单净流合计)
    """
    if flow_df is None or flow_df.empty:
        return 0.0, 0.0

    d = flow_df.tail(min(window_days, len(flow_df))).copy()

    main = pd.to_numeric(d.get("main_in_flow", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    sml = pd.to_numeric(d.get("sml_in_flow", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    mid = pd.to_numeric(d.get("mid_in_flow", pd.Series(dtype=float)), errors="coerce").fillna(0.0)

    smart_net_wan = round(float(main.sum()) / 10_000, 2)
    retail_net_wan = round(float((sml + mid).sum()) / 10_000, 2)
    return smart_net_wan, retail_net_wan


def calculate_us_capital_flow_profiles(
    symbol: str,
    windows: Optional[tuple] = (5, 10, 90),
) -> Dict[int, Dict[str, Any]]:
    """
    Pull US capital-flow history once and compute multiple rolling windows.
    Symmetric with calculate_hk_capital_flow_profiles.
    """
    from src.api.futu.client import futu_client

    windows = tuple(sorted({max(1, int(w)) for w in (windows or (5, 10, 90))}))
    max_window = max(windows) if windows else 90
    flow_df = futu_client.get_capital_flow_history(symbol, window_days=max(max_window, 90))
    return {w: _aggregate_us_capital_flow_from_df(flow_df, window_days=w) for w in windows}


def get_today_capital_flow(symbol: str) -> Dict[str, str]:
    """
    Pull intraday US capital distribution and format today net flows.

    Returns:
        main_in_flow_today : 主力大单（超大单+大单）净流，正=净流入，负=净流出
        total_in_flow_today: 全市场净流（主力 + 中单 + 小单）
    """
    from src.api.futu.client import futu_client

    def _fmt_flow(val: float) -> str:
        wan = val / 10_000
        if abs(wan) >= 10_000:
            return f"{round(wan / 10_000, 2)}亿"
        return f"{round(wan, 2)}万"

    try:
        dist_df = futu_client.get_capital_flow(symbol)
        if not isinstance(dist_df, pd.DataFrame) or dist_df.empty:
            return {"main_in_flow_today": "无数据", "total_in_flow_today": "无数据"}

        row = dist_df.iloc[0]

        def _g(*cols: str) -> float:
            for col in cols:
                val = row.get(col)
                if val is not None and not pd.isna(val):
                    return float(val)
            return 0.0

        main_net = (
            _g("capital_in_super") + _g("capital_in_big", "capital_in_large")
        ) - (
            _g("capital_out_super") + _g("capital_out_big", "capital_out_large")
        )
        retail_net = (
            _g("capital_in_mid") + _g("capital_in_small")
        ) - (
            _g("capital_out_mid") + _g("capital_out_small")
        )
        total_net = main_net + retail_net

        return {
            "main_in_flow_today": _fmt_flow(main_net),
            "total_in_flow_today": _fmt_flow(total_net),
        }
    except Exception as e:
        logger.warning(f"[US/TodayFlow] Failed to fetch capital distribution for {symbol}: {e}")
        return {"main_in_flow_today": "无数据", "total_in_flow_today": "无数据"}


# ---------------------------------------------------------------------------
# Module A – fundamental data
# ---------------------------------------------------------------------------

def us_basic_finance_data(
    stock_snapshot: Dict[str, Any],
    capital_flow_profiles: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Format US fundamental fields from a Futu get_market_snapshot row.

    Extra fields vs. HK:
      net_profit, ey_ratio, 52-week high/low, history high/low,
      pre/after/overnight market data.
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

    def _fmt_ratio(val: float, raw: Any, digits: int = 2) -> str:
        if _is_missing(raw):
            return "无数据"
        return f"{round(val, digits)}"

    def _fmt_percent(val: float, raw: Any, digits: int = 2) -> str:
        if _is_missing(raw):
            return "无数据"
        return f"{round(val * 100, digits)}%"

    def _fmt_percent_raw(val: float, raw: Any, digits: int = 3) -> str:
        """For fields where Futu already returns a percentage value (not a decimal ratio)."""
        if _is_missing(raw):
            return "无数据"
        return f"{round(val, digits)}%"

    def _fmt_price(val: float, raw: Any, digits: int = 2) -> str:
        if _is_missing(raw):
            return "无数据"
        return f"{round(val, digits)}"

    def _fmt_shares(val: float, raw: Any) -> str:
        if _is_missing(raw):
            return "无数据"
        if abs(val) > 1_0000_0000:
            return f"{round(val / 1_0000_0000.0, 2)}亿股"
        if abs(val) > 1_0000:
            return f"{round(val / 1_0000.0, 2)}万股"
        return f"{round(val, 0)}股"

    capital_flow_profiles = capital_flow_profiles or {}

    # --- snapshot field extraction ---
    total_market_val_raw = stock_snapshot.get("total_market_val")
    circular_market_val_raw = stock_snapshot.get("circular_market_val")
    net_asset_raw = stock_snapshot.get("net_asset")
    net_profit_raw = stock_snapshot.get("net_profit")           # US-only: snapshot直出
    earning_per_share_raw = stock_snapshot.get("earning_per_share")
    net_asset_per_share_raw = stock_snapshot.get("net_asset_per_share")
    pb_ratio_raw = stock_snapshot.get("pb_ratio")
    pe_ratio_raw = stock_snapshot.get("pe_ratio")               # PE 静
    pe_ttm_ratio_raw = stock_snapshot.get("pe_ttm_ratio")
    ey_ratio_raw = stock_snapshot.get("ey_ratio")               # US-only: 收益率
    issued_shares_raw = stock_snapshot.get("issued_shares")
    outstanding_shares_raw = stock_snapshot.get("outstanding_shares")
    dividend_ratio_ttm_raw = stock_snapshot.get("dividend_ratio_ttm")
    ps_ttm_raw = stock_snapshot.get("ps_ttm")                   # 快照无此字段，保留占位

    # 52-week / history price (US-only)
    highest_52w_raw = stock_snapshot.get("highest_52weeks_price") or stock_snapshot.get("highest52weeks_price")
    lowest_52w_raw = stock_snapshot.get("lowest_52weeks_price") or stock_snapshot.get("lowest52weeks_price")
    highest_history_raw = stock_snapshot.get("highest_history_price")
    lowest_history_raw = stock_snapshot.get("lowest_history_price")

    # Extended-hours (US-only)
    pre_price_raw = stock_snapshot.get("pre_price")
    pre_change_rate_raw = stock_snapshot.get("pre_change_rate")
    after_price_raw = stock_snapshot.get("after_price")
    after_change_rate_raw = stock_snapshot.get("after_change_rate")
    overnight_price_raw = stock_snapshot.get("overnight_price")
    overnight_change_rate_raw = stock_snapshot.get("overnight_change_rate")

    # --- numeric conversions ---
    total_market_val = common_safe_float(total_market_val_raw)
    circular_market_val = common_safe_float(circular_market_val_raw)
    net_asset = common_safe_float(net_asset_raw)
    net_profit = common_safe_float(net_profit_raw)
    earning_per_share = common_safe_float(earning_per_share_raw)
    net_asset_per_share = common_safe_float(net_asset_per_share_raw)
    pb_ratio = common_safe_float(pb_ratio_raw)
    pe_ratio_static = common_safe_float(pe_ratio_raw)
    pe_ttm_ratio = common_safe_float(pe_ttm_ratio_raw)
    ey_ratio = common_safe_float(ey_ratio_raw)
    issued_shares = common_safe_float(issued_shares_raw)
    outstanding_shares = common_safe_float(outstanding_shares_raw)
    dividend_ratio_ttm = common_safe_float(dividend_ratio_ttm_raw)
    ps_ttm = common_safe_float(ps_ttm_raw)

    highest_52w = common_safe_float(highest_52w_raw)
    lowest_52w = common_safe_float(lowest_52w_raw)
    highest_history = common_safe_float(highest_history_raw)
    lowest_history = common_safe_float(lowest_history_raw)

    pre_price = common_safe_float(pre_price_raw)
    pre_change_rate = common_safe_float(pre_change_rate_raw)
    after_price = common_safe_float(after_price_raw)
    after_change_rate = common_safe_float(after_change_rate_raw)
    overnight_price = common_safe_float(overnight_price_raw)
    overnight_change_rate = common_safe_float(overnight_change_rate_raw)

    # --- capital-flow aggregation ---
    flow_5d = capital_flow_profiles.get(5, {})
    flow_10d = capital_flow_profiles.get(10, {})
    flow_90d = capital_flow_profiles.get(90, {})
    final_flow_tag = (
        flow_5d.get("flow_status_tag")
        or flow_10d.get("flow_status_tag")
        or flow_90d.get("flow_status_tag")
        or "资金博弈不明"
    )

    return {
        # --- valuation ---
        "total_market_val": _fmt_amount(total_market_val, total_market_val_raw),
        "circular_market_val": _fmt_amount(circular_market_val, circular_market_val_raw),
        "issued_shares": _fmt_shares(issued_shares, issued_shares_raw),
        "outstanding_shares": _fmt_shares(outstanding_shares, outstanding_shares_raw),
        "net_asset": _fmt_amount(net_asset, net_asset_raw),
        "net_profit": _fmt_amount(net_profit, net_profit_raw),          # US-only
        "earning_per_share": _fmt_ratio(earning_per_share, earning_per_share_raw, digits=3),
        "net_asset_per_share": _fmt_ratio(net_asset_per_share, net_asset_per_share_raw, digits=3),
        "pb_ratio": _fmt_ratio(pb_ratio, pb_ratio_raw),
        "pe_ttm": _fmt_ratio(pe_ttm_ratio, pe_ttm_ratio_raw),
        "pe_static": _fmt_ratio(pe_ratio_static, pe_ratio_raw),
        "ey_ratio": _fmt_ratio(ey_ratio, ey_ratio_raw, digits=3),       # US-only
        "dividend_ratio_ttm": _fmt_percent(dividend_ratio_ttm, dividend_ratio_ttm_raw),
        "ps_ttm": _fmt_ratio(ps_ttm, ps_ttm_raw),                       # 快照无此字段→"无数据"
        # --- price range (US-only) ---
        "highest_52w": _fmt_price(highest_52w, highest_52w_raw),
        "lowest_52w": _fmt_price(lowest_52w, lowest_52w_raw),
        "highest_history": _fmt_price(highest_history, highest_history_raw),
        "lowest_history": _fmt_price(lowest_history, lowest_history_raw),
        # --- extended-hours (US-only) ---
        "pre_price": _fmt_price(pre_price, pre_price_raw),
        "pre_change_rate": _fmt_percent_raw(pre_change_rate, pre_change_rate_raw),
        "after_price": _fmt_price(after_price, after_price_raw),
        "after_change_rate": _fmt_percent_raw(after_change_rate, after_change_rate_raw),
        "overnight_price": _fmt_price(overnight_price, overnight_price_raw),
        "overnight_change_rate": _fmt_percent_raw(overnight_change_rate, overnight_change_rate_raw),
        # --- capital flow ---
        "main_in_flow_5d": _fmt_amount(common_safe_float(flow_5d.get("main_in_flow_usd")), flow_5d.get("main_in_flow_usd")),
        "total_in_flow_5d": _fmt_amount(common_safe_float(flow_5d.get("total_in_flow_usd")), flow_5d.get("total_in_flow_usd")),
        "main_in_flow_10d": _fmt_amount(common_safe_float(flow_10d.get("main_in_flow_usd")), flow_10d.get("main_in_flow_usd")),
        "total_in_flow_10d": _fmt_amount(common_safe_float(flow_10d.get("total_in_flow_usd")), flow_10d.get("total_in_flow_usd")),
        "main_in_flow_90d": _fmt_amount(common_safe_float(flow_90d.get("main_in_flow_usd")), flow_90d.get("main_in_flow_usd")),
        "total_in_flow_90d": _fmt_amount(common_safe_float(flow_90d.get("total_in_flow_usd")), flow_90d.get("total_in_flow_usd")),
        "flow_status_tag": final_flow_tag,
    }


def build_us_fundamental_data(
    symbol: str,
    base_snapshot: Optional[Dict[str, Any]] = None,
    flow_windows: Optional[tuple] = (5, 10, 90),
) -> Dict[str, Any]:
    """
    US single-stock fundamental data entry-point (mirrors build_hk_fundamental_data).

    Steps:
      1. get_owner_plate  → plate_info
      2. get_market_snapshot → full snapshot (supplements base_snapshot)
      3. calculate_us_capital_flow_profiles → multi-window flow
      4. get_today_capital_flow → intraday flow
      5. us_basic_finance_data → formatted dict
    """
    from src.api.futu.client import futu_client

    finance_snapshot: Dict[str, Any] = dict(base_snapshot or {})
    plate_info = "无数据"

    try:
        quote_ctx = futu_client.get_quote_context()
        ret_plate, plate_data = quote_ctx.get_owner_plate([symbol])
        if ret_plate == 0 and plate_data is not None and not plate_data.empty:
            valid_plates = plate_data[plate_data["plate_type"].isin(["INDUSTRY", "CONCEPT"])]
            if not valid_plates.empty:
                plate_info = "、".join(valid_plates["plate_name"].tolist())

        ret_snap, snap_df = quote_ctx.get_market_snapshot([symbol])
        if ret_snap == 0 and snap_df is not None and not snap_df.empty:
            finance_snapshot.update(snap_df.iloc[0].to_dict())
    except Exception as e:
        logger.warning(f"[US/Fundamental] Failed to fetch plate/snapshot for {symbol}: {e}")

    try:
        capital_flow_profiles = calculate_us_capital_flow_profiles(symbol, windows=flow_windows)
    except Exception as e:
        logger.warning(f"[US/Fundamental] Failed to fetch capital flow profiles for {symbol}: {e}")
        capital_flow_profiles = {}

    fundamental_data = us_basic_finance_data(
        finance_snapshot,
        capital_flow_profiles=capital_flow_profiles,
    )
    fundamental_data["plate_info"] = plate_info
    fundamental_data.update(get_today_capital_flow(symbol))
    return fundamental_data


# ---------------------------------------------------------------------------
# Module B – short-term memory
# ---------------------------------------------------------------------------

def build_short_term_memory(
    klines_df: Optional[pd.DataFrame],
    stock_snapshot: Dict[str, Any],
    capital_data: Optional[pd.DataFrame],
    lookback_days_short: int = 10,
) -> Dict[str, Any]:
    """
    Build US short-term memory.

    capital_data: historical daily capital-flow DataFrame
        (from futu_client.get_capital_flow_history, PeriodType.DAY).
        smart_net_wan  = main_in_flow  10-day cumulative (万)
        retail_net_wan = (sml_in_flow + mid_in_flow) 10-day cumulative (万)

    If capital_data contains intraday-distribution columns instead
    (capital_in_big/capital_in_large, capital_in_mid, …), falls back to
    futu_client.analyze_capital_flow for backward compatibility.
    """
    from src.api.futu.client import futu_client

    # Determine whether capital_data is historical flow or intraday distribution
    is_historical_flow = (
        capital_data is not None
        and not capital_data.empty
        and any(col in capital_data.columns for col in ("main_in_flow", "in_flow", "sml_in_flow"))
    )

    if is_historical_flow:
        smart_net, retail_net = _derive_us_smart_retail_net(capital_data, window_days=lookback_days_short)
    else:
        # Fallback: intraday distribution via futu_client.analyze_capital_flow
        _, smart_net, retail_net = futu_client.analyze_capital_flow(
            capital_data, float(stock_snapshot.get("change_rate", 0.0))
        )

    if klines_df is None or klines_df.empty:
        return common_empty_short_term_payload(lookback_days_short, smart_net, retail_net)

    try:
        prepared = common_prepare_short_term_dataset(
            klines_df,
            stock_snapshot,
            lookback_days_short,
            realtime_session_checker=common_should_use_current_volume,
        )
    except ValueError:
        return common_empty_short_term_payload(lookback_days_short, smart_net, retail_net)

    date_col = prepared["date_col"]
    current_price = prepared["current_price"]
    d_current = prepared["d_current"]
    last_n = prepared["last_n"]
    use_realtime_price = prepared.get("use_realtime_price", True)
    current_volume = prepared.get("current_volume")
    current_turnover = prepared.get("current_turnover")

    _ema_history = d_current.iloc[:-1].copy().tail(max(20, lookback_days_short))
    _ema_result = common_calculate_ema_derivatives(
        _ema_history,
        current_price,
        current_volume=current_volume,
        current_turnover=current_turnover,
    )
    latest_tag = _ema_result.get("tag_combined", _ema_result.get("tag", "数据不足"))
    today = common_build_current_day_indicator(
        today_row=last_n.iloc[-1],
        stock_snapshot=stock_snapshot,
        date_col=date_col,
        latest_tag=latest_tag,
        technical_result=_ema_result,
        safe_float_fn=common_safe_float,
        use_realtime_price=use_realtime_price,
    )
    summary_10d = common_build_short_window_indicator(
        last_n=last_n,
        window_target=lookback_days_short,
    )

    return {
        "window_used": summary_10d["window_used"],
        "short_window_incomplete": summary_10d["short_window_incomplete"],
        "smart_net_wan": smart_net,
        "retail_net_wan": retail_net,
        "today": today,
        "summary_10d": summary_10d,
    }


# ---------------------------------------------------------------------------
# Module C – mid-term trend (fully reused from HK layer)
# ---------------------------------------------------------------------------

def build_mid_term_trend(
    klines_df: Optional[pd.DataFrame],
    current_price: float,
    lookback_days_mid: int = 90,
) -> Dict[str, Any]:
    """
    Build shape-first mid-term trend summary.

    Logic is market-agnostic; delegates to the HK implementation which itself
    uses only the common math layer (single_stock_math_calculate /
    single_stock_feature_builder).
    """
    from src.analysis.hk_single_stock_indicator import (
        build_mid_term_trend as _hk_build_mid_term_trend,
    )

    return _hk_build_mid_term_trend(klines_df, current_price, lookback_days_mid)
