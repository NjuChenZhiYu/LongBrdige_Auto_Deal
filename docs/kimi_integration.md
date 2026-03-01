# Kimi 期权分析配置指南

## 环境变量配置

在 `config/.env` 文件中添加以下配置：

```bash
# ===========================================
# Kimi (Moonshot) LLM 配置
# ===========================================

# Moonshot API Key
# 获取地址：https://platform.moonshot.cn/
LLM_API_KEY=sk-your-moonshot-api-key

# Moonshot API 地址（使用 OpenAI 兼容模式）
LLM_BASE_URL=https://api.moonshot.cn/v1

# 模型名称
LLM_MODEL=kimi-k2.5

# ===========================================
# 飞书 webhook 配置
# ===========================================

# 飞书机器人 webhook 地址
# 创建方式：飞书群 -> 设置 -> 机器人 -> 添加自定义机器人
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx

# ===========================================
# 期权监控配置
# ===========================================

# 监控的期权代码（逗号分隔）
# 格式：标的.交易所.期权类型.行权价
MONITOR_OPTIONS=LEGN.US.C.200,LEGN.US.P.200,KYMR.US.C.50

# 监控的正股代码（用于计算 Greeks）
MONITOR_SYMBOLS=LEGN,KYMR,NTLA

# ===========================================
# 长桥 API 配置（如未配置）
# ===========================================
LONGPORT_APP_KEY=your-app-key
LONGPORT_APP_SECRET=your-app-secret
LONGPORT_ACCESS_TOKEN=your-access-token
```

## 快速启动

```bash
# 1. 确保在虚拟环境中
source venv/bin/activate

# 2. 安装依赖（如未安装）
pip install -r requirements.txt

# 3. 启动增强版监控器
python start_enhanced_monitor.py
```

## 功能特性

### 1. 实时信号检测
- **IV 飙升**：IV > HV * 1.5 或 IV > 100%
- **量能异常**：成交量 > 持仓量 * 50%（Smart Money）
- **Delta ITM 转化**：Delta 突破 0.5（深度实值）
- **价差异常**：买卖价差 > 5%（流动性风险）

### 2. Kimi AI 实时分析
信号触发后，自动调用 Kimi 进行实时分析：
- 信号含义解读
- 可能的催化事件推测
- 风险提示
- 操作建议

### 3. 飞书富文本推送
- 美观的格式化消息
- 包含信号详情和 AI 分析
- 支持多维度数据展示

### 4. 日终汇总报告
- 美股收盘后（北京时间 4:30 AM）自动推送
- 当日所有信号汇总分析
- 明日交易策略建议

### 5. 信号去重
- 同一标的 5 分钟内不重复触发
- 避免消息轰炸

## 监控标的配置

编辑 `config/symbols.yaml`：

```yaml
symbols:
  - LEGN.US
  - KYMR.US
  - NTLA.US

# 期权监控列表
options:
  - LEGN270115C20000
  - LEGN270115P20000
  - KYMR250620C50000

# 阈值配置
thresholds:
  iv_spike_multiplier: 1.5      # IV 超过 HV 的倍数
  volume_oi_ratio: 0.5          # 成交量/OI 比率
  delta_threshold: 0.5          # Delta 突破阈值
  spread_threshold: 0.05        # 买卖价差阈值
```

## 测试 Kimi 分析

```bash
# 测试实时分析
python -c "
import asyncio
from src.services.kimi_option_analyzer import kimi_analyzer

test_signal = {
    'symbol': 'LEGN270115C20000',
    'type': 'IV_SPIKE',
    'value': 85.5,
    'threshold': 50.0,
    'timestamp': '14:30:25',
    'details': 'IV: 85.5%, HV: 45%'
}

asyncio.run(kimi_analyzer.push_realtime_alert(test_signal))
"
```

## 日志查看

```bash
# 实时监控日志
tail -f logs/monitor.log | grep -E "(Kimi|信号|分析)"

# 查看完整日志
cat logs/monitor.log
```

## 故障排查

### Kimi API 调用失败
1. 检查 `LLM_API_KEY` 是否正确
2. 确认 API 余额充足
3. 查看日志中的错误信息

### 飞书消息未收到
1. 检查 `FEISHU_WEBHOOK` 是否正确
2. 确认 webhook 地址未过期
3. 检查飞书机器人是否被移出群聊

### 期权数据未更新
1. 检查长桥 API 连接状态
2. 确认 `MONITOR_OPTIONS` 格式正确
3. 查看 `logs/monitor.log` 中的订阅信息
