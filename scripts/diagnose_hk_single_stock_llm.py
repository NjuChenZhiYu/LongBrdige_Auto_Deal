import argparse
import asyncio
import logging
import os
import sys
import traceback

# Keep behavior aligned with generate_single_stock_prompt.py.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config.settings import Settings
from scripts.generate_single_stock_prompt import generate_prompt_file
from src.api.futu.client import futu_client
from src.services.llm_analyst import LLMAnalyst


def _mask_secret(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def _call_openai_compatible(
    analyst: LLMAnalyst,
    prompt: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> str:
    if not analyst.us_client:
        raise RuntimeError("US LLM client (Gemini OpenAI-compatible) not initialized")

    stream = await analyst.us_client.chat.completions.create(
        model=analyst.us_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
        timeout=timeout,
    )

    chunks: list[str] = []
    async for chunk in stream:
        content = chunk.choices[0].delta.content
        if content:
            chunks.append(content)
    return "".join(chunks).strip()


async def diagnose(args: argparse.Namespace) -> int:
    analyst = LLMAnalyst()

    print("=== Gemini LLM Config ===")
    print(f"LLM_API_KEY: {_mask_secret(Settings.LLM_API_KEY)}")
    print(f"LLM_BASE_URL: {Settings.LLM_BASE_URL}")
    print(f"LLM_MODEL: {Settings.LLM_MODEL}")
    print(f"Grounded enabled: {analyst.grounded_client.enabled}")
    print()

    if not args.probe_only:
        print("=== Full generate_hk_single_stock_report ===")
        result = await analyst.generate_hk_single_stock_report(
            symbol_input=args.symbol,
            trigger_type="DIAGNOSE",
            lookback_days_short=args.short,
            lookback_days_mid=args.mid,
            enable_grounded_search=not args.skip_grounded,
        )
        print(f"ok: {result.get('ok')}")
        print(f"symbol: {result.get('symbol')}")
        print(f"title: {result.get('title')}")
        print(f"error: {result.get('error')}")
        report = (result.get("report") or "").strip()
        print(f"report chars: {len(report)}")
        if report:
            print("preview:")
            print(report[: args.preview_chars])
        futu_client.close()
        return 0 if result.get("ok") else 1

    if args.prompt_file:
        prompt_file = os.path.abspath(args.prompt_file)
    else:
        prompt_file = generate_prompt_file(
            symbol_input=args.symbol,
            output_dir=args.output_dir,
            lookback_days_short=args.short,
            lookback_days_mid=args.mid,
        )
    prompt = _read_text(prompt_file)

    print("=== Prompt ===")
    print(f"Prompt file: {prompt_file}")
    print(f"Prompt chars: {len(prompt)}")
    print()

    if not args.skip_grounded:
        print("=== Grounded generate_content ===")
        if not analyst.grounded_client.enabled:
            print("[SKIP] grounded client disabled")
        else:
            try:
                grounded_result = await asyncio.to_thread(
                    analyst.grounded_client.generate_grounded_content,
                    prompt,
                )
                grounded_text = (grounded_result.get("text") or "").strip()
                print(f"ok: {grounded_result.get('ok')}")
                print(f"text chars: {len(grounded_text)}")
                print(f"error: {grounded_result.get('error')}")
                if grounded_text:
                    print("preview:")
                    print(grounded_text[: args.preview_chars])
            except Exception:
                print("[ERROR] grounded call raised exception")
                traceback.print_exc()
        print()

    print("=== OpenAI-compatible chat.completions ===")
    try:
        content = await _call_openai_compatible(
            analyst=analyst,
            prompt=prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        print("[OK] OpenAI-compatible call succeeded")
        print(f"Response chars: {len(content)}")
        if content:
            print("preview:")
            print(content[: args.preview_chars])
        return 0 if len(content) > 120 else 2
    except Exception:
        print("[ERROR] OpenAI-compatible call failed")
        traceback.print_exc()
        return 1
    finally:
        futu_client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="诊断港股单股研报的 Gemini LLM 调用，复用 generate_single_stock_prompt.py 的 prompt 构建。"
    )
    parser.add_argument("symbol", nargs="?", default="03696", help="股票代码，例如 03696 / HK.03696")
    parser.add_argument(
        "--prompt-file",
        help="probe-only 模式使用已有 prompt 文件，跳过 Futu 数据采集与 prompt 生成。",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "tmp", "stock_promt_storage"),
        help="prompt 输出目录（默认: tmp/stock_promt_storage）",
    )
    parser.add_argument("--short", type=int, default=10, help="短期窗口天数，默认 10")
    parser.add_argument("--mid", type=int, default=90, help="中期窗口天数，默认 90")
    parser.add_argument("--skip-grounded", action="store_true", help="跳过 Gemini grounded generate_content 测试")
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="只诊断 prompt、grounded 与 OpenAI-compatible 调用，不触发完整研报和飞书通知。",
    )
    parser.add_argument("--max-tokens", type=int, default=5000, help="LLM 最大输出 tokens，默认 5000")
    parser.add_argument("--temperature", type=float, default=0.9, help="LLM temperature，默认 0.9")
    parser.add_argument("--timeout", type=float, default=90.0, help="LLM 单次请求超时秒数，默认 90")
    parser.add_argument("--preview-chars", type=int, default=800, help="输出预览字符数，默认 800")
    parser.add_argument("--debug", action="store_true", help="开启 debug 日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    raise SystemExit(asyncio.run(diagnose(args)))


if __name__ == "__main__":
    main()
