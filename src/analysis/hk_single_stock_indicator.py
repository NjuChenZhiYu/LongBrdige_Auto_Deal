import pandas as pd
from typing import Optional, Dict, List, Any
import logging
from src.analysis.single_stock_math_calculate import (
    _build_short_window_price_distribute as common_build_short_window_price_distribute,
    _calculate_max_contiguous_drop_pct as common_calculate_max_contiguous_drop_pct,
    _calculate_max_contiguous_up_pct as common_calculate_max_contiguous_up_pct,
    _calculate_risk_metrics as common_calculate_risk_metrics,
    _format_rt_time_label as common_format_rt_time_label,
    _safe_float as common_safe_float,
    calc_poc as common_calc_poc,
    calculate_ema_derivatives as common_calculate_ema_derivatives,
    classify_mid_shape as common_classify_mid_shape,
    extract_pivots as common_extract_pivots,
)
from src.analysis.single_stock_feature_builder import (
    calculate_tag_today_by_derivatives as common_calculate_tag_today_by_derivatives,
    build_current_day_indicator as common_build_current_day_indicator,
    empty_short_term_payload as common_empty_short_term_payload,
    build_multi_window_trends as common_build_multi_window_trends,
    build_mid_trade_features as common_build_mid_trade_features,
    prepare_short_term_dataset as common_prepare_short_term_dataset,
    build_short_window_indicator as common_build_short_window_indicator,
)

logger = logging.getLogger(__name__)

# Backward-compatible re-exports for callers that still import from this module.
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



def build_short_term_memory(
    klines_df: Optional[pd.DataFrame],
    stock_snapshot: Dict[str, Any],
    capital_data: Optional[pd.DataFrame],
    lookback_days_short: int = 10
) -> Dict[str, Any]:
    """Build short-term memory by composing current-day and short-window indicators."""
    from src.api.futu.client import futu_client

    if klines_df is None or klines_df.empty:
        _, smart_net, retail_net = futu_client.analyze_capital_flow(
            capital_data, float(stock_snapshot.get("change_rate", 0.0))
        )
        return common_empty_short_term_payload(lookback_days_short, smart_net, retail_net)

    try:
        prepared = common_prepare_short_term_dataset(
            klines_df,
            stock_snapshot,
            lookback_days_short,
            realtime_session_checker=futu_client.is_realtime_trading_session,
        )
    except ValueError:
        return common_empty_short_term_payload(lookback_days_short, 0.0, 0.0)

    date_col = prepared["date_col"]
    current_price = prepared["current_price"]
    d_current = prepared["d_current"]
    last_n = prepared["last_n"]
    use_realtime_price = prepared.get("use_realtime_price", True)
    current_volume = prepared.get("current_volume")
    current_turnover = prepared.get("current_turnover")

    _, smart_net, retail_net = futu_client.analyze_capital_flow(
        capital_data, float(stock_snapshot.get("change_rate", 0.0))
    )

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

def _aggregate_hk_capital_flow_from_df(flow_df: Optional[pd.DataFrame], window_days: int) -> Dict[str, Any]:
    """Aggregate HK capital flow for a specific window from preloaded historical data."""
    window_days = max(1, int(window_days))
    if flow_df is None or flow_df.empty:
        return {
            "window_days": window_days,
            "main_in_flow_hkd": 0.0,
            "total_in_flow_hkd": 0.0,
            "flow_status_tag": "资金流数据缺失",
        }

    d = flow_df.copy()
    for col in ("main_in_flow", "in_flow"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
        else:
            d[col] = 0.0
    d = d.dropna(subset=["in_flow"])
    if d.empty:
        return {
            "window_days": window_days,
            "main_in_flow_hkd": 0.0,
            "total_in_flow_hkd": 0.0,
            "flow_status_tag": "资金流数据缺失",
        }

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
        "main_in_flow_hkd": round(main_in, 2),
        "total_in_flow_hkd": round(total_in, 2),
        "flow_status_tag": tag,
    }


def calculate_hk_capital_flow_profiles(
    symbol: str,
    windows: Optional[tuple] = (5, 10, 90),
) -> Dict[int, Dict[str, Any]]:
    """
    一次拉取资金流历史，然后复用计算多个窗口（默认 5/10/90），减少重复远端请求。
    """
    from src.api.futu.client import futu_client

    windows = tuple(sorted({max(1, int(w)) for w in (windows or (5, 10, 90))}))
    max_window = max(windows) if windows else 90
    flow_df = futu_client.get_capital_flow_history(symbol, window_days=max(max_window, 90))
    return {w: _aggregate_hk_capital_flow_from_df(flow_df, window_days=w) for w in windows}

def hk_basic_finance_data(
    stock_snapshot: Dict[str, Any],
    capital_flow_profiles: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
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

    def _fmt_ratio(val: float, raw: Any, digits: int = 2) -> str:
        if _is_missing(raw):
            return "无数据"
        return f"{round(val, digits)}"

    def _fmt_percent(val: float, raw: Any, digits: int = 2) -> str:
        if _is_missing(raw):
            return "无数据"
        return f"{round(val, digits)}%"

    def _fmt_shares(val: float, raw: Any) -> str:
        if _is_missing(raw):
            return "无数据"
        if abs(val) > 1_0000_0000:
            return f"{round(val / 1_0000_0000.0, 2)}亿股"
        if abs(val) > 1_0000:
            return f"{round(val / 1_0000.0, 2)}万股"
        return f"{round(val, 0)}股"

    capital_flow_profiles = capital_flow_profiles or {}

    total_market_val_raw = stock_snapshot.get("total_market_val")
    circular_market_val_raw = stock_snapshot.get("circular_market_val")
    net_asset_raw = stock_snapshot.get("net_asset")
    earning_per_share_raw = stock_snapshot.get("earning_per_share")
    net_asset_per_share_raw = stock_snapshot.get("net_asset_per_share")
    pb_ratio_raw = stock_snapshot.get("pb_ratio")
    # 富途 get_market_snapshot：pe_ratio=市盈率（静），pe_ttm_ratio=市盈率 TTM（见 docs/Futu-API-Doc-zh-Python.md）
    pe_ratio_raw = stock_snapshot.get("pe_ratio")
    pe_ttm_ratio_raw = stock_snapshot.get("pe_ttm_ratio")
    issued_shares_raw = stock_snapshot.get("issued_shares")
    outstanding_shares_raw = stock_snapshot.get("outstanding_shares")

    ps_ttm_raw = stock_snapshot.get("ps_ttm")

    total_market_val = common_safe_float(total_market_val_raw, 0.0)
    circular_market_val = common_safe_float(circular_market_val_raw, 0.0)
    net_asset = common_safe_float(net_asset_raw, 0.0)
    earning_per_share = common_safe_float(earning_per_share_raw, 0.0)
    net_asset_per_share = common_safe_float(net_asset_per_share_raw, 0.0)
    pb_ratio = common_safe_float(pb_ratio_raw, 0.0)
    pe_ratio_static = common_safe_float(pe_ratio_raw, 0.0)
    pe_ttm_ratio = common_safe_float(pe_ttm_ratio_raw, 0.0)
    issued_shares = common_safe_float(issued_shares_raw, 0.0)
    outstanding_shares = common_safe_float(outstanding_shares_raw, 0.0)
    ps_ttm = common_safe_float(ps_ttm_raw, 0.0)

    flow_5d = capital_flow_profiles.get(5, {})
    flow_10d = capital_flow_profiles.get(10, {})
    flow_90d = capital_flow_profiles.get(90, {})
    return {
        "total_market_val": _fmt_amount(total_market_val, total_market_val_raw),
        "circular_market_val": _fmt_amount(circular_market_val, circular_market_val_raw),
        "issued_shares": _fmt_shares(issued_shares, issued_shares_raw),
        "outstanding_shares": _fmt_shares(outstanding_shares, outstanding_shares_raw),
        "net_asset": _fmt_amount(net_asset, net_asset_raw),
        "earning_per_share": _fmt_ratio(earning_per_share, earning_per_share_raw, digits=3),
        "net_asset_per_share": _fmt_ratio(net_asset_per_share, net_asset_per_share_raw, digits=3),
        "pb_ratio": _fmt_ratio(pb_ratio, pb_ratio_raw),
        "pe_ttm": _fmt_ratio(pe_ttm_ratio, pe_ttm_ratio_raw),
        "pe_static": _fmt_ratio(pe_ratio_static, pe_ratio_raw),
        "ps_ttm": _fmt_ratio(ps_ttm, ps_ttm_raw),
        "main_in_flow_5d": _fmt_amount(common_safe_float(flow_5d.get("main_in_flow_hkd"), 0.0), flow_5d.get("main_in_flow_hkd")),
        "total_in_flow_5d": _fmt_amount(common_safe_float(flow_5d.get("total_in_flow_hkd"), 0.0), flow_5d.get("total_in_flow_hkd")),
        "main_in_flow_10d": _fmt_amount(common_safe_float(flow_10d.get("main_in_flow_hkd"), 0.0), flow_10d.get("main_in_flow_hkd")),
        "total_in_flow_10d": _fmt_amount(common_safe_float(flow_10d.get("total_in_flow_hkd"), 0.0), flow_10d.get("total_in_flow_hkd")),
        "main_in_flow_90d": _fmt_amount(common_safe_float(flow_90d.get("main_in_flow_hkd"), 0.0), flow_90d.get("main_in_flow_hkd")),
        "total_in_flow_90d": _fmt_amount(common_safe_float(flow_90d.get("total_in_flow_hkd"), 0.0), flow_90d.get("total_in_flow_hkd")),
    }


def get_today_capital_flow(symbol: str) -> Dict[str, str]:
    """
    调用 get_capital_distribution 拉取今日盘中实时资金分布，
    返回格式化后的主力净流和整体净流（单位：万/亿）。

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
        if dist_df is None or dist_df.empty:
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
        retail_net = (_g("capital_in_mid") + _g("capital_in_small")) - (_g("capital_out_mid") + _g("capital_out_small"))
        total_net = main_net + retail_net

        return {
            "main_in_flow_today": _fmt_flow(main_net),
            "total_in_flow_today": _fmt_flow(total_net),
        }
    except Exception as e:
        logger.warning(f"[SingleStock/TodayFlow] Failed to fetch capital distribution for {symbol}: {e}")
        return {"main_in_flow_today": "无数据", "total_in_flow_today": "无数据"}


def build_hk_fundamental_data(
    symbol: str,
    base_snapshot: Optional[Dict[str, Any]] = None,
    flow_windows: Optional[tuple] = (5, 10, 90),
) -> Dict[str, Any]:
    """
    单股基本面构建统一入口：
    1) 获取板块信息（plate_info）
    2) 拉取完整快照（补全 get_special_quotes 的裁剪字段）
    3) 聚合多窗口资金流（5/10/90 日，T-1 历史锚）
    4) 拼接今日盘中实时资金（get_today_capital_flow）
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
        logger.warning(f"[SingleStock/Fundamental] Failed to fetch plate/snapshot for {symbol}: {e}")

    try:
        capital_flow_profiles = calculate_hk_capital_flow_profiles(symbol, windows=flow_windows)
    except Exception as e:
        logger.warning(f"[SingleStock/Fundamental] Failed to fetch capital flow profiles for {symbol}: {e}")
        capital_flow_profiles = {}

    fundamental_data = hk_basic_finance_data(
        finance_snapshot,
        capital_flow_profiles=capital_flow_profiles,
    )
    fundamental_data["plate_info"] = plate_info
    fundamental_data.update(get_today_capital_flow(symbol))
    return fundamental_data


def build_mid_term_trend(
    klines_df: Optional[pd.DataFrame],
    current_price: float,
    lookback_days_mid: int = 90
) -> Dict[str, Any]:
    """Build multi-window trend summary while preserving the legacy 90-day keys."""
    windows = (30, lookback_days_mid, 180)
    window_trends = common_build_multi_window_trends(klines_df, current_price, windows=windows)
    primary = next(
        (item for item in window_trends if item.get("window_days") == int(lookback_days_mid)),
        window_trends[0] if window_trends else {},
    )
    return {
        "mode": primary.get("mode", "INSUFFICIENT"),
        "window_used": primary.get("window_used", 0),
        "summary": primary.get("summary", "趋势样本不足，仅可参考实时快照。"),
        "shape": primary.get("shape", "数据不足"),
        "position_pct": primary.get("position_pct", 0.0),
        "peaks": primary.get("peaks", []),
        "troughs": primary.get("troughs", []),
        "poc_range": primary.get("poc_range", [0.0, 0.0]),
        "poc_ratio_pct": primary.get("poc_ratio_pct", 0.0),
        "volatility_pct": primary.get("volatility_pct", 0.0),
        "window_trends": window_trends,
    }
