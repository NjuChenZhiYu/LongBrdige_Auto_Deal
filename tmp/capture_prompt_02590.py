import asyncio
import json
import os
import sys
from datetime import datetime

os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from src.services.llm_analyst import LLMAnalyst
from src.api.feishu import FeishuAlert


async def _noop_send_alert(*args, **kwargs):
    return None


async def main() -> None:
    symbol = "02590"
    out_dir = os.path.join(ROOT_DIR, "tmp")
    os.makedirs(out_dir, exist_ok=True)
    prompt_path = os.path.join(out_dir, "single_stock_prompt_02590.txt")
    meta_path = os.path.join(out_dir, "single_stock_prompt_02590_meta.json")

    analyst = LLMAnalyst()
    captured = {"prompt": ""}
    original_build_prompt = analyst._build_single_stock_prompt

    def wrapped_build_prompt(symbol, current_time, short_memory, mid_trend):
        prompt = original_build_prompt(symbol, current_time, short_memory, mid_trend)
        captured["prompt"] = prompt
        return prompt

    async def fake_call_llm_with_retry(prompt: str, max_tokens: int = 4000, temperature: float = 0.9):
        captured["prompt"] = prompt
        return "mock report for prompt capture"

    analyst._build_single_stock_prompt = wrapped_build_prompt
    analyst._call_llm_with_retry = fake_call_llm_with_retry
    FeishuAlert.send_alert = _noop_send_alert

    result = await analyst.generate_single_stock_futu_report(symbol)

    if captured["prompt"]:
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(captured["prompt"])

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "symbol_input": symbol,
        "ok": result.get("ok"),
        "error": result.get("error"),
        "title": result.get("title"),
        "prompt_saved": bool(captured["prompt"]),
        "prompt_path": prompt_path,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
