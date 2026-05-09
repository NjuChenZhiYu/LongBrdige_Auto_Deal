import asyncio
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.services.llm_analyst import LLMAnalyst
from src.api.feishu import FeishuAlert
from src.api.futu.client import futu_client
import src.analysis.futu_math_indicator as fmi


class _DummyQuoteCtx:
    def get_owner_plate(self, symbols):
        df = pd.DataFrame(
            [
                {"plate_type": "INDUSTRY", "plate_name": "智能物流"},
                {"plate_type": "CONCEPT", "plate_name": "机器人"},
            ]
        )
        return 0, df

    def get_market_snapshot(self, symbols):
        df = pd.DataFrame(
            [
                {
                    "total_market_val": 6.3e9,
                    "circular_market_val": 2.5e9,
                    "net_asset": 3.4e9,
                    "earning_per_share": 1.675,
                    "net_asset_per_share": 3.095,
                    "pb_ratio": 1.86,
                    "issued_shares": 1.1e9,
                    "outstanding_shares": 4.4e8,
                    "ps_ttm": 6.8,
                }
            ]
        )
        return 0, df


def _build_dummy_klines(n: int = 120) -> pd.DataFrame:
    base = datetime.now() - timedelta(days=n)
    rows = []
    price = 6.2
    for i in range(n):
        price = max(4.0, price * (1 + (0.002 if i % 7 else -0.01)))
        open_p = price * 0.995
        high_p = price * 1.02
        low_p = price * 0.98
        close_p = price
        rows.append(
            {
                "time_key": (base + timedelta(days=i)).strftime("%Y-%m-%d"),
                "open": round(open_p, 3),
                "high": round(high_p, 3),
                "low": round(low_p, 3),
                "close": round(close_p, 3),
                "volume": 1_000_000 + i * 1000,
            }
        )
    return pd.DataFrame(rows)


async def _noop_send_alert(title, content):
    return {"ok": True}


async def main() -> None:
    # monkeypatch futu dependency to keep test stable and fast
    futu_client.parse_symbol_input = lambda s: "HK.02598"
    futu_client.get_special_quotes = lambda symbols: [
        {"code": "HK.02598", "name": "连连数字", "last_price": 5.76}
    ]
    futu_client.get_capital_flow = lambda symbol: {"main_net_inflow": 0.0, "retail_net_inflow": 0.0}
    futu_client.get_hk_historical_klines = lambda symbol, num: _build_dummy_klines(max(120, int(num)))
    futu_client.get_quote_context = lambda: _DummyQuoteCtx()
    fmi.calculate_hk_capital_flow = lambda symbol, window: {
        "window_days": window,
        "main_in_flow_hkd": 1000000.0 * (1 if window != 90 else 3),
        "total_in_flow_hkd": 600000.0 * (1 if window != 90 else 2),
        "flow_status_tag": "主力持续净流入",
    }
    FeishuAlert.send_alert = _noop_send_alert

    analyst = LLMAnalyst()
    result = await analyst.generate_single_stock_futu_report(
        symbol_input="02598",
        enable_grounded_search=True,
    )

    print("OK=", result.get("ok"))
    print("ERR=", result.get("error"))
    report = result.get("report") or ""
    print("REPORT_LEN=", len(report))
    print("HAS_SYMBOL=", "HK.02598" in report)
    print("HAS_BENCHMARK_HINT=", ("对标" in report) or ("PS" in report))
    print("REPORT_HEAD_START")
    print(report[:1800])
    print("REPORT_HEAD_END")


if __name__ == "__main__":
    asyncio.run(main())
