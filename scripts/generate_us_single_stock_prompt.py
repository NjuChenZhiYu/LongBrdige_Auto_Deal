"""
US single-stock prompt generator (Futu API).

Usage:
    python scripts/generate_us_single_stock_prompt.py AUR        # 裸 ticker（最简）
    python scripts/generate_us_single_stock_prompt.py AUR.US     # 标准格式
    python scripts/generate_us_single_stock_prompt.py US.AUR     # Futu 原生格式
    python scripts/generate_us_single_stock_prompt.py NVDA --short 10 --mid 90
    python scripts/generate_us_single_stock_prompt.py AAPL --output-dir tmp/my_dir

Symbol format: AUR / AUR.US / US.AUR 均可，脚本内部统一转为 US.TICKER。
"""

import argparse
import os
import sys
from datetime import datetime

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.api.futu.client import futu_client
from src.analysis.us_single_stock_indicator import (
    build_mid_term_trend,
    build_short_term_memory,
    build_us_fundamental_data,
)
from src.services.llm_analyst import LLMAnalyst


# ---------------------------------------------------------------------------
# Symbol helpers
# ---------------------------------------------------------------------------

def standard_to_futu(standard_code: str) -> str:
    """AAPL.US → US.AAPL"""
    if "." in standard_code:
        ticker, market = standard_code.rsplit(".", 1)
        return f"{market.upper()}.{ticker.upper()}"
    return standard_code.upper()


def futu_to_standard(futu_code: str) -> str:
    """US.AAPL → AAPL.US"""
    if "." in futu_code:
        market, ticker = futu_code.split(".", 1)
        return f"{ticker}.{market}"
    return futu_code


def parse_us_symbol(symbol_input: str) -> str:
    """
    Flexible US symbol parser — accepts any of:
      AUR         → US.AUR  (bare ticker, most convenient)
      AUR.US      → US.AUR  (standard format)
      US.AUR      → US.AUR  (Futu native, pass-through)
    Always returns Futu-native US.TICKER form.
    """
    raw = symbol_input.strip().upper()
    if raw.startswith("US."):
        return raw                     # already US.AUR
    if raw.endswith(".US"):
        return standard_to_futu(raw)  # AUR.US → US.AUR
    # bare ticker: AUR → US.AUR (assume US market)
    if raw.isalpha() or raw.replace("-", "").replace(".", "").isalnum():
        return f"US.{raw}"
    raise ValueError(
        f"无法识别美股代码格式: {symbol_input!r}。"
        "支持格式：AUR / AUR.US / US.AUR"
    )


# ---------------------------------------------------------------------------
# Core generation logic
# ---------------------------------------------------------------------------

def generate_us_prompt_file(
    symbol_input: str,
    output_dir: str,
    lookback_days_short: int = 10,
    lookback_days_mid: int = 90,
) -> str:
    analyst = LLMAnalyst()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_tag = datetime.now().strftime("%m%d")

    futu_symbol = parse_us_symbol(symbol_input)          # e.g. US.AUR
    standard_symbol = futu_to_standard(futu_symbol)      # e.g. AUR.US

    print(f"[INFO] Futu symbol: {futu_symbol}  (standard: {standard_symbol})")

    # --- 1. Snapshot ---
    snapshot_list = futu_client.get_special_quotes([futu_symbol])
    if not snapshot_list:
        raise RuntimeError(
            f"未获取到 {futu_symbol} 快照数据，请确认 FutuOpenD 已启动且行情权限包含美股。"
        )
    stock = snapshot_list[0]
    price = float(stock.get("last_price", 0.0))
    stock_name = str(stock.get("name", "") or "").strip()
    symbol_for_prompt = f"{standard_symbol} {stock_name}" if stock_name else standard_symbol
    print(f"[INFO] Snapshot OK — price={price}  name={stock_name!r}")

    # --- 2. Historical K-lines ---
    klines_df = futu_client.get_historical_klines(
        futu_symbol,
        max(lookback_days_mid + 30, 120),
    )
    if klines_df is None or klines_df.empty:
        raise RuntimeError(f"未获取到 {futu_symbol} 历史K线数据，无法生成 prompt。")
    print(f"[INFO] K-lines OK — rows={len(klines_df)}")

    # --- 3. Historical capital-flow (10-day window used for smart/retail net) ---
    capital_data = futu_client.get_capital_flow_history(futu_symbol, window_days=90)
    if capital_data is None or capital_data.empty:
        print("[WARN] 未获取到历史资金流数据，smart_net/retail_net 将为 0。")
    else:
        print(f"[INFO] Capital-flow history OK — rows={len(capital_data)}")

    # --- 4. Build three modules ---
    short_memory = build_short_term_memory(
        klines_df, stock, capital_data, lookback_days_short
    )
    mid_trend = build_mid_term_trend(klines_df, price, lookback_days_mid)
    fundamental_data = build_us_fundamental_data(
        futu_symbol,
        base_snapshot=stock,
        flow_windows=(5, 10, 90),
    )
    print("[INFO] All three modules built successfully.")

    # --- 5. Build prompt ---
    prompt = analyst._build_us_single_stock_prompt(
        symbol_for_prompt,
        current_time,
        fundamental_data,
        short_memory,
        mid_trend,
    )

    # --- 6. Write to file ---
    os.makedirs(output_dir, exist_ok=True)
    ticker_clean = standard_symbol.replace(".US", "")
    output_file = os.path.join(
        output_dir,
        f"us_stock_prompt_{date_tag}_{ticker_clean}.txt",
    )
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return output_file


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="根据美股代码生成 us_single_stock_prompt 并落盘。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n  python scripts/generate_us_single_stock_prompt.py AUR\n  python scripts/generate_us_single_stock_prompt.py NVDA --short 10 --mid 90",
    )
    parser.add_argument("symbol", help="美股代码，例如 AUR.US 或 US.AUR")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "stock_promt_storage"),
        help="输出目录（默认: tmp/stock_promt_storage）",
    )
    parser.add_argument("--short", type=int, default=10, help="短期窗口天数，默认 10")
    parser.add_argument("--mid", type=int, default=90, help="中期窗口天数，默认 90")
    args = parser.parse_args()

    try:
        output_file = generate_us_prompt_file(
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
