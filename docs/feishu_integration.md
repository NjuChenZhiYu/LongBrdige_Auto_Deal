# 飞书通知接入指南

本文档介绍如何将美股期权监控系统的告警消息推送到飞书（Feishu）。

## 功能概述

系统支持通过飞书机器人 webhook 发送实时告警，包括：
- 📈 价格异动提醒（涨跌幅超过阈值）
- 📊 买卖盘价差异常提醒
- ⚠️ 系统错误/断线通知
- 🔔 交易信号通知（如开启自动交易）

## 快速配置（3分钟搞定）

### 第一步：创建飞书机器人

1. 打开飞书，进入需要接收告警的**群组**
2. 点击群设置 → **群机器人** → **添加机器人**
3. 选择 **"自定义机器人"**
4. 给机器人起名（如"美股监控"），选择头像
5. **复制 Webhook 地址**（格式如下）：
   ```
   https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

> 💡 **安全提示**：Webhook 地址是机器人密钥，**不要泄露给他人**！

### 第二步：配置项目

1. 编辑配置文件：
   ```bash
   cd LongBrdige_Auto_Deal
   vim config/.env
   ```

2. 填入飞书 Webhook：
   ```bash
   # 飞书机器人 webhook
   FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```

3. 保存并重启服务：
   ```bash
   ./scripts/stop_all.sh
   ./scripts/start_all.sh
   ```

### 第三步：测试验证

发送测试消息：
```bash
# 进入项目目录
cd LongBrdige_Auto_Deal
source venv/bin/activate

# 运行测试脚本
python -c "
from src.api.notification import AlertManager
AlertManager.send_alert('测试消息', '飞书通知配置成功！🎉')
"
```

如果配置正确，你的飞书群会立即收到测试消息。

---

## 高级配置

### 自定义消息格式

当前系统发送纯文本消息，如需富文本（如带颜色、链接），可修改 `src/api/notification.py`：

```python
# 富文本消息示例（支持颜色、链接）
data = {
    "msg_type": "interactive",
    "card": {
        "config": {
            "wide_screen_mode": True
        },
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "🚨 价格异动提醒"
            },
            "template": "red"  # 红色标题
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**AAPL.US** 价格上涨 **5.2%**"
                }
            }
        ]
    }
}
```

更多卡片格式请参考：[飞书消息卡片指南](https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/send-feishu-cards)

### 多群组通知

如需发送到多个飞书群，可配置多个 webhook：

```python
# 在 notification.py 中添加
FEISHU_WEBHOOKS = [
    "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx1",
    "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx2",
]

@staticmethod
def send_feishu_to_all(message: str):
    for webhook in FEISHU_WEBHOOKS:
        # 发送逻辑...
```

### 消息签名验证（高级安全）

如需防止 webhook 被伪造，可启用飞书签名验证：

1. 创建机器人时勾选 **"签名校验"**
2. 获取 **Secret** 密钥
3. 修改代码添加签名：

```python
import hashlib
import base64
import hmac
import time

def gen_sign(timestamp, secret):
    """生成飞书签名"""
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    sign = base64.b64encode(hmac_code).decode('utf-8')
    return sign

# 使用
timestamp = int(time.time())
sign = gen_sign(timestamp, Settings.FEISHU_SECRET)

headers = {'Content-Type': 'application/json'}
data = {
    "timestamp": timestamp,
    "sign": sign,
    "msg_type": "text",
    "content": {"text": message}
}
```

---

## 故障排查

### ❌ 收不到消息

| 检查项 | 排查方法 |
|-------|---------|
| Webhook 是否正确 | 对比飞书后台复制的地址 |
| 服务是否重启 | `ps aux \| grep watchlist` 查看进程 |
| 环境变量是否加载 | 检查 `config/.env` 文件路径 |
| 网络是否通畅 | 服务器能否访问 `open.feishu.cn` |

### 🔍 查看日志

```bash
# 查看告警发送日志
tail -f logs/monitor.log | grep -i feishu

# 测试网络连通性
curl -I https://open.feishu.cn
```

### 🚨 常见错误

**错误 1**: `Failed to send Feishu alert: 404`
- 原因：Webhook 地址错误或机器人被删除
- 解决：重新创建机器人并更新 Webhook

**错误 2**: `Failed to send Feishu alert: 403`
- 原因：IP 白名单限制或机器人被封
- 解决：检查飞书机器人安全设置

**错误 3**: 消息延迟
- 原因：服务器网络问题或飞书限流
- 解决：检查服务器网络，或增加重试机制

---

## 相关文件

- 告警代码：`src/api/notification.py`
- 配置加载：`config/settings.py`
- 配置文件：`config/.env`

## 参考链接

- [飞书自定义机器人指南](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)
- [飞书消息格式文档](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create)
