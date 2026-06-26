"""A-share single-stock prompt generator (Futu API).

Usage:
    python scripts/generate_a_market_single_stock_prompt.py 000001
    python scripts/generate_a_market_single_stock_prompt.py SZ.000001
    python scripts/generate_a_market_single_stock_prompt.py 600519.SH
    python scripts/generate_a_market_single_stock_prompt.py 300750 --short 10 --mid 90
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

import pandas as pd

# Futu 在部分 Python/Protobuf 组合下会触发 pb2 描述符兼容错误。
# 仅对本脚本启用 pure-python protobuf 解析，避免全局环境改动。
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.api.futu.client import futu_client
from src.analysis.a_market_single_stock_indicator import (
    build_a_market_fundamental_data,
    build_mid_term_trend,
    build_short_term_memory,
)
from src.services.llm_analyst import LLMAnalyst


def generate_a_market_prompt_file(
    symbol_input: str,
    output_dir: str,
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
    prompt_template: Optional[str] = None,
) -> str:
    analyst = LLMAnalyst()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_tag = datetime.now().strftime("%m%d")

    standard_symbol = analyst._parse_a_market_symbol(symbol_input)
    if not standard_symbol:
        raise ValueError("未匹配到有效A股代码（示例：000001 / SZ.000001 / 600519.SH）")

    print(f"[INFO] A-share symbol: {standard_symbol}")

    snapshot_list = futu_client.get_special_quotes([standard_symbol])
    if not snapshot_list:
        raise RuntimeError(f"未获取到 {standard_symbol} 快照数据，请确认 FutuOpenD 已启动且行情权限包含A股。")

    stock = snapshot_list[0]
    price = float(stock.get("last_price", 0.0))
    stock_name = str(stock.get("name", "") or "").strip()
    symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol
    print(f"[INFO] Snapshot OK — price={price}  name={stock_name!r}")

    raw_capital_data = futu_client.get_capital_flow(standard_symbol)
    capital_data = raw_capital_data if isinstance(raw_capital_data, pd.DataFrame) else None
    if capital_data is None or capital_data.empty:
        print("[WARN] 未获取到当日资金分布，短期资金博弈字段将降级。")
    else:
        print(f"[INFO] Intraday capital distribution OK — rows={len(capital_data)}")

    max_trend_window = max(30, lookback_days_mid, 180)
    kline_days = max(max_trend_window + 60, 240)
    klines_df = futu_client.get_historical_klines(standard_symbol, kline_days)
    if not isinstance(klines_df, pd.DataFrame) or klines_df.empty:
        raise RuntimeError(f"未获取到 {standard_symbol} 历史K线数据，无法生成 prompt。")
    print(f"[INFO] K-lines OK — rows={len(klines_df)}")

    short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
    mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
    fundamental_data = build_a_market_fundamental_data(
        standard_symbol,
        base_snapshot=stock,
        flow_windows=(5, 10, 90),
        klines_df=klines_df,
    )
    print("[INFO] A-share modules built successfully.")

    prompt = analyst._build_a_market_single_stock_prompt(
        symbol_for_prompt,
        current_time,
        fundamental_data,
        short_memory,
        mid_trend,
        prompt_template=prompt_template,
    )

    os.makedirs(output_dir, exist_ok=True)
    symbol_key = standard_symbol.replace(".", "")
    output_file = os.path.join(
        output_dir,
        f"a_market_stock_prompt_{date_tag}_{symbol_key}.txt",
    )
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="根据A股代码生成 a_market_single_stock_prompt 并落盘。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/generate_a_market_single_stock_prompt.py 000001\n"
            "  python scripts/generate_a_market_single_stock_prompt.py SZ.000001\n"
            "  python scripts/generate_a_market_single_stock_prompt.py 600519.SH --short 10 --mid 90"
        ),
    )
    parser.add_argument("symbol", help="A股代码，例如 000001 / SZ.000001 / 600519.SH")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "a_market_stock_prompt_storage"),
        help="输出目录（默认: tmp/a_market_stock_prompt_storage）",
    )
    parser.add_argument("--short", type=int, default=10, help="短期窗口天数，默认 10")
    parser.add_argument(
        "--mid",
        type=int,
        default=90,
        help="多周期核心窗口天数，默认 90；脚本固定同时生成 30/mid/180 日窗口",
    )
    parser.add_argument(
        "--prompt-template",
        default=None,
        help="指定 config/single_stock_prompt_templates.yaml 中 a_market_single_stock.templates 的版本名；默认使用 active",
    )
    args = parser.parse_args()

    try:
        output_file = generate_a_market_prompt_file(
            symbol_input=args.symbol,
            output_dir=args.output_dir,
            lookback_days_short=args.short,
            lookback_days_mid=args.mid,
            prompt_template=args.prompt_template,
        )
        print(f"[OK] Prompt 已写入: {output_file}")
    finally:
        futu_client.close()


if __name__ == "__main__":
    main()
