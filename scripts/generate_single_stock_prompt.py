import argparse
import os
import sys
from datetime import datetime

# Futu 在部分 Python/Protobuf 组合下会触发 pb2 描述符兼容错误。
# 仅对本脚本启用 pure-python protobuf 解析，避免全局环境改动。
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.api.futu.client import futu_client
from src.analysis.futu_math_indicator import (
    build_mid_term_trend,
    build_short_term_memory,
    calculate_hk_capital_flow,
    hk_basic_finance_data,
)
from src.services.llm_analyst import LLMAnalyst


def generate_prompt_file(
    symbol_input: str,
    output_dir: str,
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
) -> str:
    analyst = LLMAnalyst()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_tag = datetime.now().strftime("%m%d")

    standard_symbol = futu_client.parse_symbol_input(symbol_input)
    if not standard_symbol:
        raise ValueError("未匹配到有效港股代码（示例：09880 / HK.09880 / 9880）")

    snapshot_list = futu_client.get_special_quotes([standard_symbol])
    if not snapshot_list:
        raise RuntimeError("未获取到股票快照数据，请确认代码或行情权限。")

    stock = snapshot_list[0]
    price = float(stock.get("last_price", 0.0))
    stock_name = str(stock.get("name", "") or "").strip()
    symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol

    capital_data = futu_client.get_capital_flow(standard_symbol)

    plate_info = "无数据"
    full_snapshot = {}
    try:
        quote_ctx = futu_client.get_quote_context()
        ret_plate, plate_data = quote_ctx.get_owner_plate([standard_symbol])
        if ret_plate == 0 and plate_data is not None and not plate_data.empty:
            valid_plates = plate_data[plate_data["plate_type"].isin(["INDUSTRY", "CONCEPT"])]
            if not valid_plates.empty:
                plate_info = "、".join(valid_plates["plate_name"].tolist())
        # get_special_quotes 返回字段较少，这里补拉完整快照以获取基本面估值字段。
        ret_snap, snap_df = quote_ctx.get_market_snapshot([standard_symbol])
        if ret_snap == 0 and snap_df is not None and not snap_df.empty:
            full_snapshot = snap_df.iloc[0].to_dict()
    except Exception:
        plate_info = "获取失败"

    klines_df = futu_client.get_hk_historical_klines(
        standard_symbol,
        max(lookback_days_mid + 30, 120),
    )
    if klines_df is None or klines_df.empty:
        raise RuntimeError(f"未获取到 {standard_symbol} 历史K线数据，无法生成 prompt。")

    short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
    mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
    finance_snapshot = {**stock, **full_snapshot}
    capital_flow_profiles = {
        5: calculate_hk_capital_flow(standard_symbol, 5),
        10: calculate_hk_capital_flow(standard_symbol, 10),
        90: calculate_hk_capital_flow(standard_symbol, 90),
    }
    fundamental_data = hk_basic_finance_data(
        finance_snapshot,
        capital_flow_profiles=capital_flow_profiles,
    )
    fundamental_data["plate_info"] = plate_info

    prompt = analyst._build_single_stock_prompt(
        symbol_for_prompt,
        current_time,
        fundamental_data,
        short_memory,
        mid_trend,
    )

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(
        output_dir,
        f"single_stock_prompt_{date_tag}_{standard_symbol.replace('HK.', '')}.txt",
    )
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="根据股票代码生成 _build_single_stock_prompt 的原始 prompt 并落盘。"
    )
    parser.add_argument("symbol", help="股票代码，例如 09880 / HK.09880")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "stock_promt_storage"),
        help="输出目录（默认: tmp/stock_promt_storage）",
    )
    parser.add_argument("--short", type=int, default=10, help="短期窗口天数，默认 10")
    parser.add_argument("--mid", type=int, default=90, help="中期窗口天数，默认 90")
    args = parser.parse_args()

    try:
        output_file = generate_prompt_file(
            symbol_input=args.symbol,
            output_dir=args.output_dir,
            lookback_days_short=args.short,
            lookback_days_mid=args.mid,
        )
        print(f"[OK] Prompt 已写入: {output_file}")
    finally:
        futu_client.close()


if __name__ == "__main__":
    main()
