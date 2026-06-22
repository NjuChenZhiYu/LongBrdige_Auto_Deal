import argparse
import asyncio
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
from src.api.longport.client import longport_client
from src.analysis.futu_math_indicator import (
    build_hk_fundamental_data,
    build_mid_term_trend,
    build_short_term_memory,
)
from src.services.llm_analyst import LLMAnalyst


def generate_prompt_file(
    symbol_input: str,
    output_dir: str,
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
    prompt_template: Optional[str] = None,
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

    raw_capital_data = futu_client.get_capital_flow(standard_symbol)
    capital_data = raw_capital_data if isinstance(raw_capital_data, pd.DataFrame) else None

    max_trend_window = max(30, lookback_days_mid, 180)
    kline_days = max(max_trend_window + 60, 240)
    raw_klines_df = futu_client.get_hk_historical_klines(
        standard_symbol,
        kline_days,
    )
    if not isinstance(raw_klines_df, pd.DataFrame) or raw_klines_df.empty:
        raise RuntimeError(f"未获取到 {standard_symbol} 历史K线数据，无法生成 prompt。")
    klines_df = raw_klines_df

    short_memory = build_short_term_memory(klines_df, stock, capital_data, lookback_days_short)
    mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
    fundamental_data = build_hk_fundamental_data(
        standard_symbol,
        stock,
        (5, 10, 90),
        klines_df,
    )
    #print(f"[INFO] 机构持仓趋势: {fundamental_data.get('institutional_holding_profile', '无数据')}")
    #print(f"[INFO] 股东持仓变动: {fundamental_data.get('shareholder_holding_change_profile', '无数据')}")
    try:
        fundamental_data["revenue_disclosure_profile"] = asyncio.run(
            longport_client.get_revenue_disclosure_profile(standard_symbol)
        )
    except Exception as e:
        fundamental_data["revenue_disclosure_profile"] = f"长桥营收披露数据暂不可用（{e}）"

    prompt = analyst._build_single_stock_prompt(
        symbol_for_prompt,
        current_time,
        fundamental_data,
        short_memory,
        mid_trend,
        prompt_template=prompt_template,
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
        description="根据股票代码生成 _build_single_stock_prompt 的原始 prompt 并落盘，包含30/mid/180日窗口、机构持仓与股东持仓变动摘要。"
    )
    parser.add_argument("symbol", help="股票代码，例如 09880 / HK.09880")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "stock_promt_storage"),
        help="输出目录（默认: tmp/stock_promt_storage）",
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
        help="指定 config/prompt_templates.yaml 中 hk_single_stock.templates 的版本名；默认使用 active",
    )
    args = parser.parse_args()

    try:
        output_file = generate_prompt_file(
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
