"""
HK daily market prompt generator (Futu API).

Usage:
    python scripts/generate_hk_stock_promt.py
    python scripts/generate_hk_stock_promt.py --threshold 5 --max-stocks 10
    python scripts/generate_hk_stock_promt.py --output-dir tmp/stock_promt_storage

Default output:
    tmp/stock_promt_storage/hk_stock_MMDD.txt
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config.settings import Settings
from src.analysis.futu_math_indicator import calculate_ema_derivatives
from src.api.futu.client import futu_client
from src.services.llm_analyst import LLMAnalyst


Stock = Dict[str, Any]


def _load_threshold(threshold: Optional[float]) -> float:
    if threshold is not None:
        return float(threshold)

    default_threshold = getattr(Settings, "PRICE_CHANGE_THRESHOLD", 5.0)
    config = getattr(Settings, "FUTU_SYMBOLS_CONFIG", {})
    return float(config.get("thresholds", {}).get("price_change", default_threshold))


def _load_special_stock_codes() -> List[str]:
    config = getattr(Settings, "FUTU_SYMBOLS_CONFIG", {})
    special_symbols = config.get("special_symbols", [])
    return [s.split(" ")[0] for s in special_symbols] if special_symbols else []


def _select_hk_stocks(
    threshold_stocks: List[Stock],
    special_stocks: List[Stock],
    max_stocks: int,
) -> List[Stock]:
    """Special symbols are pinned first, then threshold hits are added by abs(change_rate)."""
    merged_stocks: List[Stock] = []
    seen_codes = set()

    for stock in special_stocks:
        if len(merged_stocks) >= max_stocks:
            break
        code = stock.get("code", stock.get("symbol"))
        if code and code not in seen_codes:
            merged_stocks.append(stock)
            seen_codes.add(code)

    threshold_stocks.sort(key=lambda x: abs(x["change_rate"]), reverse=True)
    for stock in threshold_stocks:
        if len(merged_stocks) >= max_stocks:
            break
        code = stock.get("code", stock.get("symbol"))
        if code and code not in seen_codes:
            merged_stocks.append(stock)
            seen_codes.add(code)

    return merged_stocks


async def _fetch_stock_detail(stock: Stock, index: int, semaphore: asyncio.Semaphore) -> str:
    async with semaphore:
        symbol = stock.get("symbol", stock.get("code", "Unknown"))
        code = stock.get("code")
        price = float(stock["last_price"])
        change = float(stock["change_rate"])
        direction = "📈" if change > 0 else "📉"

        capital_task = asyncio.to_thread(futu_client.get_capital_flow, code)
        klines_task = asyncio.to_thread(futu_client.get_hk_historical_klines, code, 60)

        try:
            capital_data, klines_df = await asyncio.gather(capital_task, klines_task)
        except Exception as e:
            print(f"[WARN] {code} 数据拉取失败: {e}")
            capital_data, klines_df = None, None

        try:
            flow_label, smart_net, retail_net = futu_client.analyze_capital_flow(
                capital_data,
                change,
            )
        except Exception as e:
            print(f"[WARN] {code} 资金流分析失败: {e}")
            flow_label, smart_net, retail_net = "分析不可用", 0, 0

        try:
            if klines_df is not None and not klines_df.empty:
                ema_data = calculate_ema_derivatives(klines_df, price)
                ema_tag = ema_data.get("tag_combined", ema_data["tag"])
                v5 = ema_data["v5"]
                v20 = ema_data.get("v20", 0.0)
                a5 = ema_data["a5"]
                bias20 = ema_data.get("bias20", 0.0)
                ema_text = (
                    f"   - 【量化技术面】：{ema_tag} "
                    f"(V5: {v5}%, V20: {v20}%, A5: {a5}%, Bias20: {bias20}%)"
                )
            else:
                ema_text = "   - 【量化技术面】：数据缺失"
        except Exception as e:
            print(f"[WARN] {code} EMA 计算失败: {e}")
            ema_text = "   - 【量化技术面】：计算错误"

        return (
            f"{index}. {symbol} 现价${price:.2f} ({change:+.2f}%) {direction}\n"
            f"   - 【内部量化系统研判】：{flow_label}\n"
            f"   - (资金支撑：主力净流 {smart_net}万, 散户净流 {retail_net}万)\n"
            f"{ema_text}"
        )


def _build_hk_market_prompt(
    current_time: str,
    threshold: float,
    threshold_stocks: List[Stock],
    stocks_text: str,
    output_rules: str,
) -> str:
    up_count = sum(1 for s in threshold_stocks if s["change_rate"] > 0)
    down_count = len(threshold_stocks) - up_count
    avg_change = (
        sum(float(s["change_rate"]) for s in threshold_stocks) / len(threshold_stocks)
        if threshold_stocks
        else 0
    )

    return f"""你是一个顶级的量化分析师。以下是触发监控阈值的异动香港股票列表及【底层资金流向数据】与【量化技术面数据】：

【报告时间】{current_time}

【市场整体概况】
- 异动标的总数：{len(threshold_stocks)} 只
- 上涨家数：{up_count} 只 | 下跌家数：{down_count} 只
- 平均涨跌幅：{avg_change:+.2f}%
- 监控阈值：涨跌幅绝对值 ≥ {threshold}%

【异动标的详情】
{stocks_text}

{output_rules}"""


async def generate_hk_prompt_file(
    output_dir: str,
    threshold: Optional[float] = None,
    max_stocks: int = LLMAnalyst.MAX_WATCH_STOCKS,
    concurrency: int = 4,
    prompt_template: Optional[str] = None,
) -> str:
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_tag = datetime.now().strftime("%m%d")
    threshold_value = _load_threshold(threshold)
    special_stock_codes = _load_special_stock_codes()

    print(f"[INFO] Fetch threshold stocks: abs(change_rate) >= {threshold_value}%")
    threshold_task = asyncio.to_thread(futu_client.get_threshold_quotes, threshold_value)
    special_task = asyncio.to_thread(futu_client.get_special_quotes, special_stock_codes)
    threshold_stocks, special_stocks = await asyncio.gather(threshold_task, special_task)

    selected_stocks = _select_hk_stocks(
        threshold_stocks,
        special_stocks,
        max_stocks=max(1, int(max_stocks)),
    )
    if not selected_stocks:
        raise RuntimeError("当前无阈值异动股票，且未获取到特殊关注股票。")

    print(
        f"[INFO] Selected {len(selected_stocks)} stocks "
        f"(special={len(special_stocks)}, threshold_hits={len(threshold_stocks)})"
    )

    semaphore = asyncio.Semaphore(max(1, int(concurrency)))
    tasks = [
        _fetch_stock_detail(stock, i, semaphore)
        for i, stock in enumerate(selected_stocks, 1)
    ]
    stock_details = await asyncio.gather(*tasks)
    stocks_text = "\n".join(stock_details)
    analyst = LLMAnalyst()
    output_rules = analyst._get_stocks_prompt_output_rules(
        "hk_market_report",
        prompt_template,
    )

    prompt = _build_hk_market_prompt(
        current_time=current_time,
        threshold=threshold_value,
        threshold_stocks=selected_stocks,
        stocks_text=stocks_text,
        output_rules=output_rules,
    )

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"hk_stock_{date_tag}.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(prompt)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(
        description="生成每日港股市场分析 prompt 并落盘，不调用 LLM、不发送通知。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python scripts/generate_hk_stock_promt.py\n"
            "  python scripts/generate_hk_stock_promt.py --threshold 5 --max-stocks 10\n"
            "  python scripts/generate_hk_stock_promt.py --concurrency 2"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "stock_promt_storage"),
        help="输出目录（默认: tmp/stock_promt_storage）",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="涨跌幅阈值；默认读取 config/futu_symbols.yaml",
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=LLMAnalyst.MAX_WATCH_STOCKS,
        help="最多拼入 prompt 的股票数量，默认 10",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="并发拉取资金流和K线的股票数量，默认 4",
    )
    parser.add_argument(
        "--prompt-template",
        default=None,
        help="指定 config/stocks_prompt_templates.yaml 中 hk_market_report.templates 的版本名；默认使用 active",
    )
    args = parser.parse_args()

    try:
        output_file = asyncio.run(
            generate_hk_prompt_file(
                output_dir=args.output_dir,
                threshold=args.threshold,
                max_stocks=args.max_stocks,
                concurrency=args.concurrency,
                prompt_template=args.prompt_template,
            )
        )
        print(f"[OK] Prompt 已写入: {output_file}")
    finally:
        futu_client.close()


if __name__ == "__main__":
    main()
