# Feature: Kimi Integration for HK/Futu Reports

## Branch: `feature/kimi_integration_hk`

## 主要修改

### 1. 修复股票代码显示问题 ✅
**文件**: `src/api/futu/callback.py` 和 `src/api/futu/client.py`

- 修改 `get_threshold_quotes()` 方法，返回的股票数据现在包含股票名称
- 显示格式从 `"HK.00700"` 改为 `"HK.00700 腾讯控股"`
- 数据字段新增 `name` 和 `code`，`symbol` 字段现在包含完整显示名称

### 2. 集成 Kimi 大模型用于富途研报 ✅
**文件**: `src/services/llm_analyst.py`

- **新增方法**: `generate_futu_hk_report()` - 专用于富途港股研报生成
  - 使用 Kimi k2.5 模型
  - 针对港股市场优化的系统提示词
  - 分析维度：市场综述、板块热点、重点个股、策略建议
  - 自动推送到飞书

- **重构**: `generate_stock_report()` 拆分为独立的市场研报方法
  - `generate_longport_us_report()`: 使用 Gemini 模型 (LLM_*) 生成美股研报
  - `generate_futu_hk_report()`: 使用 Kimi 模型 (KIMI_*) 生成港股研报
  - 消除模型冲突，实现市场隔离

### 3. 默认配置更新 ✅
**文件**: `config/settings.py`

```python
# 美股分析 (Gemini)
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-1.5-pro")

# 港股分析 (Kimi)
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_LLM_BASE_URL = os.getenv("KIMI_LLM_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_LLM_MODEL = os.getenv("KIMI_LLM_MODEL", "kimi-k2.5")
```

### 4. Web 界面支持 ✅
**文件**: `src/web/app.py`

- 新增路由: `/generate_futu_kimi_report`
- 支持手动触发富途Kimi研报生成

## 使用方法

### 环境变量配置
确保 `.env` 文件中有：
```bash
LLM_API_KEY=sk-your-moonshot-api-key
# LLM_BASE_URL 和 LLM_MODEL 现在有默认值，可选配置
```

### 手动生成研报
1. **通过Web界面**: 访问 `/generate_futu_kimi_report`
2. **通过代码调用**:
   ```python
   from src.services.llm_analyst import llm_analyst
   await llm_analyst.generate_futu_hk_report()
   ```

### 定时任务
系统会自动在以下时间生成研报：
- 美股日报：22:50
- 港股日报：07:50

港股研报默认使用Kimi模型生成。

## 推送目标

| 市场 | 推送渠道 | AI模型 |
|------|---------|--------|
| 美股 | 钉钉 | Kimi (默认) |
| 港股(富途) | 飞书 | Kimi k2.5 |

## Git 操作

```bash
# 切换到新分支
git checkout feature/kimi_integration_hk

# 查看修改
git log --oneline -5

# 推送到远程
git push origin feature/kimi_integration_hk
```

## 测试建议

1. 确保 `LLM_API_KEY` 配置正确
2. 检查富途自选股配置 `config/futu_symbols.yaml`
3. 手动触发 `/generate_futu_kimi_report` 测试研报生成
4. 检查飞书是否收到带股票名称的研报推送
