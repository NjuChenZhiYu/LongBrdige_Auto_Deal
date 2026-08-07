"""Diagnose the Gemini path used by single-stock reports.

This script does not connect to Futu, collect market data, or send alerts.
"""

import argparse
import asyncio
import logging
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from config.settings import Settings
from src.services.llm_analyst import LLMAnalyst

TEST_PROMPT = """这是一次 API 连通性测试，不需要查询实时资料。
请用简体中文回复一段至少 180 个汉字的文本，并且第一行必须是：
LLM_DIAGNOSIS_OK
随后简要说明：模型已经收到请求、能够生成内容，且该回复仅用于程序诊断。
不要输出投资建议。"""


def _mask_secret(value: str | None) -> str:
    value = (value or "").strip()
    if not value:
        return "<未配置>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]} (长度 {len(value)})"


def _print_config(analyst: LLMAnalyst) -> list[str]:
    errors: list[str] = []
    env_path = os.path.join(PROJECT_ROOT, "config", ".env")
    api_key = (Settings.LLM_API_KEY or "").strip()

    print("=== 配置检查 ===")
    print(f"配置文件: {env_path}")
    print(f"配置文件存在: {os.path.isfile(env_path)}")
    print(f"LLM_API_KEY: {_mask_secret(Settings.LLM_API_KEY)}")
    print(f"LLM_BASE_URL: {Settings.LLM_BASE_URL or '<未配置>'}")
    print(f"LLM_MODEL: {Settings.LLM_MODEL or '<未配置>'}")
    print(f"OpenAI 兼容客户端已初始化: {analyst.us_client is not None}")
    print(f"Gemini Grounded 客户端已初始化: {analyst.grounded_client.enabled}")

    if not api_key:
        errors.append("LLM_API_KEY 为空")
    elif api_key.lower().startswith("your_") or api_key.lower().endswith("_here"):
        errors.append("LLM_API_KEY 仍是示例占位符，请填写真实密钥并保存 config/.env")
    if not (Settings.LLM_BASE_URL or "").strip():
        errors.append("LLM_BASE_URL 为空")
    if not (Settings.LLM_MODEL or "").strip():
        errors.append("LLM_MODEL 为空")
    if analyst.us_client is None:
        errors.append("LLMAnalyst.us_client 未初始化")
    return errors


async def _run_probe(
    analyst: LLMAnalyst,
    *,
    name: str,
    enable_grounded_search: bool,
    preview_chars: int,
) -> bool:
    print(f"\n=== {name} ===")
    print(f"enable_grounded_search={enable_grounded_search}")
    try:
        response = await analyst._call_llm_with_retry(
            TEST_PROMPT,
            max_tokens=2000,
            temperature=0.1,
            enable_grounded_search=enable_grounded_search,
        )
    except Exception as exc:
        print(f"[失败] 调用抛出异常: {type(exc).__name__}: {exc}")
        return False

    if not response:
        print("[失败] 三次重试后未获得长度超过 120 字符的回复；请查看上方错误日志。")
        return False

    marker_ok = "LLM_DIAGNOSIS_OK" in response
    print(f"回复长度: {len(response)}")
    print(f"诊断标记存在: {marker_ok}")
    print("回复预览:")
    print(response[:preview_chars])
    if not marker_ok:
        print("[警告] API 有回复，但模型未遵循诊断标记指令。")
    print("[成功] LLM 调用链可用。")
    return True


async def diagnose(args: argparse.Namespace) -> int:
    try:
        analyst = LLMAnalyst()
    except Exception as exc:
        print(f"[失败] LLMAnalyst 初始化异常: {type(exc).__name__}: {exc}")
        return 2

    config_errors = _print_config(analyst)
    if config_errors:
        for error in config_errors:
            print(f"[配置错误] {error}")
        return 2

    probes: list[tuple[str, bool]] = []
    if args.mode in {"openai", "both"}:
        probes.append(("OpenAI 兼容接口（配置的 BASE_URL）", False))
    if args.mode in {"grounded", "both"}:
        if analyst.grounded_client.enabled:
            probes.append(("研报实际 Grounded 调用路径", True))
        else:
            print("\n[跳过] Grounded 客户端未初始化；将无法测试研报默认的搜索增强路径。")
            if args.mode == "grounded":
                return 2

    results = [
        await _run_probe(
            analyst,
            name=name,
            enable_grounded_search=grounded,
            preview_chars=args.preview_chars,
        )
        for name, grounded in probes
    ]
    return 0 if results and all(results) else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="测试单股研报所用 Gemini 配置和 LLM 调用链；不会访问 Futu 或发送飞书通知。"
    )
    parser.add_argument(
        "--mode",
        choices=("openai", "grounded", "both"),
        default="both",
        help="测试 OpenAI 兼容接口、Grounded 路径或两者（默认 both）。",
    )
    parser.add_argument("--preview-chars", type=int, default=500, help="回复预览字符数。")
    parser.add_argument("--debug", action="store_true", help="显示详细调用日志。")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    raise SystemExit(asyncio.run(diagnose(args)))


if __name__ == "__main__":
    main()
