import asyncio
import os
import sys

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from src.services.llm_analyst import LLMAnalyst


async def main() -> None:
    analyst = LLMAnalyst()
    result = await analyst.generate_single_stock_futu_report(
        "02598",
        enable_grounded_search=True,
    )
    print("OK=", result.get("ok"))
    print("ERR=", result.get("error"))
    report = result.get("report") or ""
    print("REPORT_LEN=", len(report))
    print("REPORT_HEAD_START")
    print(report[:2000])
    print("REPORT_HEAD_END")


if __name__ == "__main__":
    asyncio.run(main())
