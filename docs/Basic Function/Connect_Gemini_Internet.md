# Gemini 联网能力接入说明

本文说明如何在本项目中给 Gemini 开启“联网搜索（Google Search Grounding）”能力，并解释为什么 OpenAI 兼容接口下通常无法直接开启该能力。

## 1. 背景结论

当前项目大量调用的是 OpenAI 兼容协议（如 `/v1beta/openai/`）+ `openai` SDK。  
这种方式适合统一模型调用接口，但有一个关键限制：

- `openai` SDK 协议中没有 Gemini 原生 `google_search` 工具开关。
- 因此，即使底层模型是 Gemini，也未必能直接用“官方 Google Search Grounding”。

要稳定使用 Gemini 联网能力，推荐使用 **Google 官方原生 SDK（`google-genai`）**。

---

## 2. 方案对比

### 方案 A（推荐）：官方 Gemini SDK + Google Search 工具

优点：

- 原生支持 `tools=[types.Tool(google_search=types.GoogleSearch())]`
- 代码清晰、能力可控、文档对应准确
- 无需额外第三方搜索服务即可启用 Google 搜索增强

适用场景：

- 对“行业对标、实时估值、最新事件”有强实时性要求
- 允许在项目中引入一条 Gemini 原生调用链

### 方案 B：继续用 OpenAI 兼容接口

优点：

- 保持现有统一 SDK 架构，不改动大

限制：

- 通常无法直接开启 Gemini 原生 Google Search 工具
- 需要额外接第三方搜索或自行 RAG，工程复杂度更高

---

## 3. 最小可运行示例（官方推荐）

### 3.1 安装依赖

```bash
pip install google-genai
```

### 3.2 Python 示例

```python
from google import genai
from google.genai import types

client = genai.Client(api_key="你的_GEMINI_API_KEY")

prompt_text = """
【行业对标与相对估值指令】
请利用你的联网搜索功能，寻找美股市场中与极智嘉(AMR机器人)商业模式最接近的对标公司（如 Symbotic / AutoStore），
获取其最新市销率（PS），并与当前标的 PS(TTM) 进行对比分析。
"""

response = client.models.generate_content(
    model="gemini-2.5-pro",
    contents=prompt_text,
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.2,
    ),
)

print(response.text)
```

---

## 4. 接入建议（结合本项目）

建议不要一次性替换全项目 LLM 客户端，而是先做“局部接入”：

1. 在单股深度分析链路中，新增一个“联网对标”步骤。
2. 该步骤单独走 `google-genai` 客户端。
3. 返回结构化文本（或 JSON）后，再拼回主 Prompt。
4. 其他报告链路继续沿用现有 OpenAI 兼容方式。

这样改造成本低、风险可控。

---

## 5. 常见注意事项

1. API Key 权限：确认当前 Key 对应模型可用且支持工具调用。
2. 成本控制：联网查询会增加 token 与调用成本，建议只在“需要实时对标”的段落启用。
3. 结果可追溯：建议在输出中附带“对标公司名称 + 检索时间 + 关键估值数值”。
4. 失败降级：联网失败时，回退到“仅基于本地结构化数据”继续生成，避免全链路失败。

---

## 6. 一句话总结

如果你要在 Gemini 上稳定使用“联网搜索”，最佳实践是：  
**关键链路改用 `google-genai` 原生 SDK，并显式注入 `GoogleSearch` 工具。**
