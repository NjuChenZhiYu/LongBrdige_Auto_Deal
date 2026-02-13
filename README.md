# 美股期权实时监控分析系统 (LongBridge Auto Deal)

基于长桥证券 OpenAPI (LongPort SDK) 搭建的工业级美股+期权实时监控分析系统。本项目采用模块化架构设计，支持实时行情订阅、策略分析、多渠道告警及自动交易。

## 核心功能

*   **实时监控**：毫秒级订阅美股/期权实时行情 (WebSocket)。
*   **智能分析**：内置价格波动、买卖盘价差分析算法。
*   **多维告警**：支持飞书、钉钉机器人实时推送策略信号。
*   **自动交易**：可选开启自动下单功能，支持限价/市价单。
*   **工程化设计**：模块解耦、日志规范、异常处理完善。

## 目录结构

```
LongBridge_Auto_Deal/
├── src/
│   ├── api/            # 外部接口封装 (Feishu, DingTalk, LongPort Trade)
│   ├── analysis/       # 策略分析核心逻辑
│   ├── monitor/        # 监控主循环与事件分发
│   ├── utils/          # 通用工具 (日志, 配置)
│   └── config.py       # 配置管理
├── tests/              # 单元测试
├── docs/               # 详细文档
├── main.py             # 程序入口
├── requirements.txt    # 依赖管理
└── .env.example        # 环境变量模板
```

## 快速开始

### 1. 环境准备
确保 Python 3.8+ 环境，并安装依赖：
```bash
pip install -r requirements.txt
```

### 2. 配置 (安全重要)
本项目严格遵循安全规范，敏感信息不直接提交到 Git。请按以下步骤配置：

1.  复制配置模板：
    ```bash
    # 推荐方式：在 config 目录下创建 .env
    cp config/.env.example config/.env
    ```

2.  编辑 `config/.env` 填入您的 LongBridge Token 和 Webhook 地址。

    > **安全提示**：
    > *   `config/.env` 文件已被 `.gitignore` 忽略，**绝不会**被提交到远程仓库。
    > *   请确保服务器上的 `config/.env` 文件权限设置为 600 (仅所有者可读写)：
    >     ```bash
    >     chmod 600 config/.env
    >     ```

### 3. 运行
```bash
python main.py
```

更多部署细节请参考 [docs/deploy.md](docs/deploy.md)。

## 测试
运行单元测试确保功能正常：
```bash
python -m unittest discover tests
```
