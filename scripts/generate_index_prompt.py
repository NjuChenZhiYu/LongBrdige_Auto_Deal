import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Futu 在部分 Python/Protobuf 组合下会触发 pb2 描述符兼容错误。
# 仅对本脚本启用 pure-python protobuf 解析，避免全局环境改动。
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.api.futu.client import futu_client
from src.analysis.futu_math_indicator import (
    build_mid_trade_features,
    build_short_term_memory,
    calc_poc,
)


DEFAULT_WINDOWS = (10, 30, 90, 180)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except Exception:
        return default


def parse_hk_index_or_etf_symbol(symbol_input: str) -> Optional[str]:
    """Normalize HK index/ETF input, e.g. HSIDI -> HK.HSIDI, 2800 -> HK.02800."""
    if not symbol_input:
        return None

    raw = str(symbol_input).strip().upper()
    if not raw:
        return None

    suffix_match = re.match(r"^([A-Z0-9]{2,12})\.HK$", raw)
    if suffix_match:
        raw = f"HK.{suffix_match.group(1)}"

    if raw.startswith("HK."):
        code_body = raw[3:]
        if re.match(r"^[A-Z0-9]{2,12}$", code_body):
            return raw
        return None

    if re.match(r"^\d{1,6}$", raw):
        return f"HK.{raw.zfill(5) if len(raw) <= 5 else raw}"

    if re.match(r"^[A-Z][A-Z0-9]{1,11}$", raw):
        return f"HK.{raw}"

    return None


def parse_windows(value: str) -> List[int]:
    windows = []
    for part in str(value).split(","):
        part = part.strip()
        if not part:
            continue
        window = int(part)
        if window <= 0:
            raise ValueError("窗口天数必须为正整数")
        windows.append(window)
    return sorted(set(windows))


def get_full_snapshot(symbol: str) -> Dict[str, Any]:
    ctx = futu_client.get_quote_context()
    ret, data = ctx.get_market_snapshot([symbol])
    if ret != 0 or data is None or data.empty:
        raise RuntimeError(f"未获取到 {symbol} 快照数据：{data}")

    snapshot = data.iloc[0].to_dict()
    last_price = _safe_float(snapshot.get("last_price"))
    prev_close = _safe_float(snapshot.get("prev_close_price"))
    if prev_close > 0:
        snapshot["change_rate"] = round((last_price - prev_close) / prev_close * 100.0, 3)
    else:
        snapshot["change_rate"] = _safe_float(snapshot.get("change_rate"))
    return snapshot


def _normalize_lookup_query(symbol_input: str) -> str:
    raw = str(symbol_input or "").strip().upper()
    suffix_match = re.match(r"^([A-Z0-9]{2,12})\.HK$", raw)
    if suffix_match:
        raw = suffix_match.group(1)
    if raw.startswith("HK."):
        raw = raw[3:]
    return raw


def lookup_hk_index_or_etf_symbols(symbol_input: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Lookup HK index/ETF candidates from Futu static info by code or name."""
    from futu import Market, SecurityType

    query_code = _normalize_lookup_query(symbol_input)
    query_text = str(symbol_input or "").strip()
    if not query_code and not query_text:
        return []

    ctx = futu_client.get_quote_context()
    security_types = []
    for attr in ("IDX", "ETF"):
        sec_type = getattr(SecurityType, attr, None)
        if sec_type is not None:
            security_types.append(sec_type)

    candidates = []
    for sec_type in security_types:
        ret, data = ctx.get_stock_basicinfo(Market.HK, sec_type)
        if ret != 0 or data is None or data.empty:
            continue
        for _, row in data.iterrows():
            code = str(row.get("code", "") or "").upper()
            name = str(row.get("name", "") or row.get("stock_name", "") or "")
            code_body = code[3:] if code.startswith("HK.") else code
            code_hit = query_code and (query_code == code_body or query_code in code_body)
            name_hit = query_text and query_text in name
            if not code_hit and not name_hit:
                continue

            if query_code == code_body:
                score = 0
            elif code_hit:
                score = 1
            else:
                score = 2
            candidates.append(
                {
                    "code": code,
                    "name": name,
                    "stock_type": str(row.get("stock_type", sec_type)),
                    "score": score,
                }
            )

    candidates.sort(key=lambda item: (item["score"], item["code"]))
    return candidates[:limit]


def resolve_symbol_and_snapshot(symbol_input: str) -> Tuple[str, Dict[str, Any]]:
    direct_symbol = parse_hk_index_or_etf_symbol(symbol_input)
    direct_error = None
    if direct_symbol:
        try:
            return direct_symbol, get_full_snapshot(direct_symbol)
        except RuntimeError as exc:
            direct_error = str(exc)

    candidates = lookup_hk_index_or_etf_symbols(symbol_input, limit=10)
    for candidate in candidates:
        code = candidate["code"]
        if code == direct_symbol:
            continue
        try:
            return code, get_full_snapshot(code)
        except RuntimeError:
            continue

    if candidates:
        formatted = ", ".join(f"{item['code']} {item['name']}" for item in candidates)
        raise RuntimeError(f"未能获取快照；Futu 静态信息匹配到候选但快照不可用：{formatted}")
    if direct_error:
        raise RuntimeError(f"{direct_error}；且未在 Futu HK 指数/ETF静态信息中找到可用候选。")
    raise ValueError("未匹配到有效港股指数/ETF代码（示例：HSIDI / HK.HSIDI / 02800 / HK.800000 / 恒生科技）")


def get_hk_index_klines(symbol: str, num_days: int) -> Optional[pd.DataFrame]:
    from futu import AuType, KLType

    ctx = futu_client.get_quote_context()
    start_date = (datetime.now() - timedelta(days=num_days + 80)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")
    autype = getattr(AuType, "NONE", AuType.QFQ)

    ret, data, _ = ctx.request_history_kline(
        symbol,
        start=start_date,
        end=end_date,
        ktype=KLType.K_DAY,
        autype=autype,
        max_count=num_days + 80,
    )
    if ret == 0 and data is not None and not data.empty:
        return data
    return None


def _prepare_window_df(
    klines_df: pd.DataFrame,
    snapshot: Dict[str, Any],
    window_days: int,
) -> pd.DataFrame:
    d = klines_df.copy()
    date_col = "time_key" if "time_key" in d.columns else ("date" if "date" in d.columns else None)
    if date_col:
        d = d.sort_values(date_col)
    for col in ("open", "close", "high", "low", "volume", "turnover", "amount"):
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce")
    history_limit = max(window_days - 1, 1)
    d = d.dropna(subset=["close"]).tail(min(history_limit, len(d))).copy()
    if d.empty:
        return d

    current_price = _safe_float(snapshot.get("last_price"), _safe_float(d["close"].iloc[-1]))
    latest_row = d.iloc[-1].copy()
    latest_row["close"] = current_price
    latest_row["high"] = max(_safe_float(latest_row.get("high"), current_price), current_price)
    latest_row["low"] = min(_safe_float(latest_row.get("low"), current_price), current_price)
    if "volume" in d.columns and _safe_float(snapshot.get("volume")) > 0:
        latest_row["volume"] = _safe_float(snapshot.get("volume"))
    if "turnover" in d.columns and _safe_float(snapshot.get("turnover")) > 0:
        latest_row["turnover"] = _safe_float(snapshot.get("turnover"))
    if date_col:
        latest_row[date_col] = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} RT"
    d.loc[len(d)] = latest_row
    return d.reset_index(drop=True)


def _max_drawdown_pct(close: pd.Series) -> float:
    if close.empty:
        return 0.0
    running_high = close.cummax()
    drawdown = close / running_high - 1.0
    return round(float(drawdown.min() * 100.0), 2)


def build_window_trend(
    klines_df: pd.DataFrame,
    snapshot: Dict[str, Any],
    window_days: int,
) -> Dict[str, Any]:
    d = _prepare_window_df(klines_df, snapshot, window_days)
    default = {
        "window_days": window_days,
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
        "peaks": [],
        "troughs": [],
    }
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

    ma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
    ma_state = "均线样本不足"
    if ma20 is not None and not pd.isna(ma20):
        ma_state = "站上20日均线" if close.iloc[-1] >= ma20 else "跌破20日均线"
    if ma60 is not None and not pd.isna(ma60):
        ma_state += "，且在60日均线上方" if close.iloc[-1] >= ma60 else "，且在60日均线下方"

    summary = (
        f"近{window_days}日实际样本{len(close)}日，形态为{features.get('shape', '数据不足')}，"
        f"区间涨跌{round(return_pct, 2)}%，最大回撤{max_drawdown}%，"
        f"当前位置位于区间{features.get('position_pct', 0.0)}%，{ma_state}。"
    )

    return {
        "window_days": window_days,
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
        "peaks": features.get("peaks", []),
        "troughs": features.get("troughs", []),
    }


def _fmt_amount(value: Any) -> str:
    val = _safe_float(value)
    if val == 0:
        return "0"
    if abs(val) >= 100_000_000:
        return f"{round(val / 100_000_000, 2)}亿"
    if abs(val) >= 10_000:
        return f"{round(val / 10_000, 2)}万"
    return str(round(val, 2))


def build_index_prompt(
    symbol: str,
    snapshot: Dict[str, Any],
    short_memory: Dict[str, Any],
    window_trends: List[Dict[str, Any]],
) -> str:
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    name = str(snapshot.get("name", "") or "").strip()
    display_symbol = f"{symbol} {name}" if name else symbol
    today = short_memory.get("today", {}) or {}
    summary_10d = short_memory.get("summary_10d", {}) or {}
    index_valid = bool(snapshot.get("index_valid", False))
    breadth_text = "无数据"
    if index_valid:
        breadth_text = (
            f"上涨{_safe_int(snapshot.get('index_raise_count'))}，"
            f"下跌{_safe_int(snapshot.get('index_fall_count'))}，"
            f"平盘{_safe_int(snapshot.get('index_equal_count'))}"
        )

    trend_lines = "\n".join(
        (
            f"    - {item['window_days']}日：{item['summary']} "
            f"POC={item['poc_range']}，POC占比={item['poc_ratio_pct']}%，"
            f"年化波动={item['volatility_pct']}%，波峰={item['peaks']}，波谷={item['troughs']}"
        )
        for item in window_trends
    )

    return f"""你是港股指数与ETF量化择时分析师。请基于下面结构化数据生成指数/ETF交易分析，不要套用单股基本面、EPS、PB、PE、股本等公司财务框架。

    【报告时间】
    {current_time}

    【标的】
    {display_symbol}

    【指数/ETF行情快照】
    - 当前点位/价格：{_safe_float(snapshot.get('last_price'))}
    - 当日涨跌幅：{_safe_float(snapshot.get('change_rate'))}%
    - 开盘/最高/最低/昨收：{_safe_float(snapshot.get('open_price'))} / {_safe_float(snapshot.get('high_price'))} / {_safe_float(snapshot.get('low_price'))} / {_safe_float(snapshot.get('prev_close_price'))}
    - 成交量：{_fmt_amount(snapshot.get('volume'))}
    - 成交额：{_fmt_amount(snapshot.get('turnover'))}
    - 买一/买一量：{_safe_float(snapshot.get('bid_price'))} / {_fmt_amount(snapshot.get('bid_vol'))}
    - 卖一/卖一量：{_safe_float(snapshot.get('ask_price'))} / {_fmt_amount(snapshot.get('ask_vol'))}
    - 成分广度（若为指数且Futu返回）：{breadth_text}
    - 更新时间：{snapshot.get('update_time', '') or snapshot.get('data_time', '')}

    【短线技术记忆（近10日）】
    - window_used：{short_memory.get('window_used')}
    - short_window_incomplete：{short_memory.get('short_window_incomplete')}
    - 当日技术标签：{today.get('tag_today')}
    - 布林轨位置：{today.get('bb_summary')}
    - bias20：{today.get('bias20')}%
    - 10日累计最大涨幅：{summary_10d.get('max_cum_up_10d_pct')}%
    - 10日累计最大跌幅：{summary_10d.get('max_cum_drop_10d_pct')}%
    - 10日最大回撤：{summary_10d.get('max_drawdown_10d_pct')}%
    - 10日POC价格区间：{summary_10d.get('poc_range_10d')}，主峰占比：{summary_10d.get('poc_ratio_10d_pct')}%
    - 10日成交密集区前三名：{summary_10d.get('short_window_price_distribute')}

    【多周期趋势与位置】
{trend_lines}

    请按以下结构输出（Markdown）：
    1. 核心结论（40-80字，第一行固定格式：`【指数/ETF择时评分：评级(X/100) - 一句话方向总结】`）
    2. 多周期趋势共振（10/30/90/180日逐层判断，说明短线、中线、半年级别是否同向，180-240字）
    3. 量价与盘口证据（成交量、成交额、买一卖一量、POC、布林轨、bias20，判断是低位承接、趋势加速、分歧换手还是高位拥挤，160-220字）
    4. ETF交易计划（如果交易对应ETF，给出入场触发、加仓条件、止损位、失效条件、仓位建议，120-180字）
    5. 核心风险/证伪条件（给出1-2条会让指数趋势判断失效的条件，60-100字）

    约束：
    - 不要讨论公司基本面、EPS、PB、PE、股本。
    - 如果成分广度、资金流或盘口字段为0/无数据，必须明确说明该字段不可作为判断依据。
    - 交易建议必须以指数/ETF择时为核心，不能写成单股研报。
    """


def generate_prompt_file(
    symbol_input: str,
    output_dir: str,
    windows: Optional[List[int]] = None,
) -> str:
    windows = windows or list(DEFAULT_WINDOWS)
    if 10 not in windows:
        windows = sorted(set([10, *windows]))

    standard_symbol, snapshot = resolve_symbol_and_snapshot(symbol_input)
    price = _safe_float(snapshot.get("last_price"))
    if price <= 0:
        raise RuntimeError(f"未获取到 {standard_symbol} 有效最新价，无法生成 prompt。")

    max_window = max(windows)
    klines_df = get_hk_index_klines(standard_symbol, max(max_window, 180))
    if klines_df is None or klines_df.empty:
        raise RuntimeError(f"未获取到 {standard_symbol} 历史K线数据，无法生成 prompt。")

    short_memory = build_short_term_memory(klines_df, snapshot, None, 10)
    window_trends = [build_window_trend(klines_df, snapshot, window) for window in windows]
    prompt = build_index_prompt(standard_symbol, snapshot, short_memory, window_trends)

    os.makedirs(output_dir, exist_ok=True)
    date_tag = datetime.now().strftime("%m%d")
    safe_symbol = standard_symbol.replace("HK.", "").replace(".", "_")
    output_file = os.path.join(output_dir, f"index_prompt_{date_tag}_{safe_symbol}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="根据港股指数/ETF代码生成指数择时 prompt 并落盘。")
    parser.add_argument("symbol", help="指数/ETF代码，例如 HSIDI / HK.HSIDI / 02800 / HK.800000")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "stock_promt_storage"),
        help="输出目录（默认: tmp/stock_promt_storage）",
    )
    parser.add_argument(
        "--windows",
        default="10,30,90,180",
        help="多周期窗口，逗号分隔，默认 10,30,90,180",
    )
    parser.add_argument(
        "--lookup-only",
        action="store_true",
        help="只查找 Futu HK 指数/ETF候选代码，不生成 prompt",
    )
    args = parser.parse_args()

    try:
        if args.lookup_only:
            candidates = lookup_hk_index_or_etf_symbols(args.symbol, limit=20)
            if not candidates:
                print("[WARN] 未找到匹配的 HK 指数/ETF候选。")
                return
            for item in candidates:
                print(f"{item['code']}\t{item['name']}\t{item['stock_type']}")
            return

        output_file = generate_prompt_file(
            symbol_input=args.symbol,
            output_dir=args.output_dir,
            windows=parse_windows(args.windows),
        )
        print(f"[OK] 指数/ETF Prompt 已写入: {output_file}")
    finally:
        futu_client.close()


if __name__ == "__main__":
    main()
