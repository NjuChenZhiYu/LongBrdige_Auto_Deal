# API 参考文档

## 第三方平台接口

### 1. 长桥 OpenAPI (LongPort)
*   **文档地址**: [https://open.longportapp.cn/zh-CN/docs/index](https://open.longportapp.cn/zh-CN/docs/index)
*   **核心模块**:
    *   `QuoteContext`: 行情订阅上下文。
    *   `TradeContext`: 交易上下文。
    *   `Config`: SDK 配置类。

### 2. 飞书自定义机器人 (Feishu Webhook)
*   **文档地址**: [https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)
*   **核心参数**:
    *   `msg_type`: 消息类型 (text, post, interactive)。
    *   `content`: 消息内容。

### 3. 钉钉自定义机器人 (DingTalk Webhook)
*   **文档地址**: [https://open.dingtalk.com/document/robots/custom-robot-access](https://open.dingtalk.com/document/robots/custom-robot-access)
*   **核心参数**:
    *   `msgtype`: 消息类型 (text, markdown)。
    *   `text`: 文本内容。

## 项目内部核心类

### 1. `src.analysis.strategy.StrategyAnalyzer`
策略分析器，用于处理行情数据并生成信号。
*   `analyze(quote: Quote) -> list[StrategySignal]`: 输入行情，返回触发的信号列表。

### 2. `src.api.notification.AlertManager`
告警管理器，封装多渠道推送逻辑。
*   `send_alert(title, content)`: 同时推送到飞书和钉钉。

### 3. `src.api.trade.TradeManager`
交易管理器，封装下单逻辑。
*   `submit_order(symbol, side, price, quantity)`: 提交限价单。
