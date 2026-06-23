"""Backward-compatible re-export shim.

HK-specific indicators have moved to hk_single_stock_indicator.
US-specific indicators live in us_single_stock_indicator.
Common math utilities live in single_stock_math_calculate and single_stock_feature_builder.
"""
from src.analysis.single_stock_math_calculate import (
    _build_short_window_price_distribute,
    _calculate_max_contiguous_drop_pct,
    _calculate_max_contiguous_up_pct,
    _calculate_risk_metrics,
    _format_rt_time_label,
    _safe_float,
    calc_poc,
    calculate_bollinger_bands,
    calculate_ema_derivatives,
    classify_mid_shape,
    extract_pivots,
)
from src.analysis.single_stock_feature_builder import (
    build_current_day_indicator,
    build_multi_window_trends,
    build_mid_trade_features,
    build_window_trend,
    build_short_window_indicator,
    calculate_tag_today_by_derivatives,
    empty_short_term_payload,
    prepare_short_term_dataset,
)
from src.analysis.hk_single_stock_indicator import (
    _aggregate_hk_capital_flow_from_df,
    build_hk_fundamental_data,
    build_mid_term_trend,
    build_short_term_memory,
    calculate_hk_capital_flow_profiles,
    hk_basic_finance_data,
)
from src.analysis.us_single_stock_indicator import (
    _aggregate_us_capital_flow_from_df,
    build_us_fundamental_data,
    calculate_us_capital_flow_profiles,
    us_basic_finance_data,
    build_short_term_memory as build_us_short_term_memory,
    build_mid_term_trend as build_us_mid_term_trend,
)

__all__ = [
    # HK
    "_aggregate_hk_capital_flow_from_df",
    "build_hk_fundamental_data",
    "calculate_hk_capital_flow_profiles",
    "hk_basic_finance_data",
    # US
    "_aggregate_us_capital_flow_from_df",
    "build_us_fundamental_data",
    "build_us_mid_term_trend",
    "build_us_short_term_memory",
    "calculate_us_capital_flow_profiles",
    "us_basic_finance_data",
    # shared (HK default)
    "build_mid_term_trend",
    "build_short_term_memory",
    # common math
    "_build_short_window_price_distribute",
    "_calculate_max_contiguous_drop_pct",
    "_calculate_max_contiguous_up_pct",
    "_calculate_risk_metrics",
    "_format_rt_time_label",
    "_safe_float",
    "build_current_day_indicator",
    "build_multi_window_trends",
    "build_mid_trade_features",
    "build_window_trend",
    "build_short_window_indicator",
    "calc_poc",
    "calculate_bollinger_bands",
    "calculate_ema_derivatives",
    "calculate_tag_today_by_derivatives",
    "classify_mid_shape",
    "empty_short_term_payload",
    "extract_pivots",
    "prepare_short_term_dataset",
]
