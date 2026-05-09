import asyncio
import os
import sys
import time

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.services.llm_analyst import LLMAnalyst


async def run_once(symbol: str, grounded: bool):
    analyst = LLMAnalyst()
    t0 = time.perf_counter()
    result = await analyst.generate_single_stock_futu_report(
        symbol_input=symbol,
        trigger_type="MANUAL_BENCH",
        enable_grounded_search=grounded,
    )
    dt = time.perf_counter() - t0
    return {
        "grounded": grounded,
        "seconds": round(dt, 2),
        "ok": bool(result.get("ok")),
        "error": result.get("error"),
        "report_len": len((result.get("report") or "")),
    }


async def main():
    symbol = "02590"
    plain = await run_once(symbol, grounded=False)
    grounded = await run_once(symbol, grounded=True)
    print("BENCH_RESULT_START")
    print(plain)
    print(grounded)
    if plain["seconds"] > 0:
        delta = grounded["seconds"] - plain["seconds"]
        ratio = grounded["seconds"] / plain["seconds"]
        print(
            {
                "delta_seconds": round(delta, 2),
                "speed_ratio": round(ratio, 2),
            }
        )
    print("BENCH_RESULT_END")


if __name__ == "__main__":
    asyncio.run(main())
