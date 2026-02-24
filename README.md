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
确保 Python 3.8+ 环境。建议使用虚拟环境：
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境 (Linux/macOS)
source venv/bin/activate

# 安装依赖
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

#### Windows (推荐)
使用 PowerShell 脚本一键启动所有服务（无需手动激活虚拟环境）：
```powershell
# 启动服务 (监控 + Web)
./scripts/start_all.ps1

# 停止服务
./scripts/stop_all.ps1
```

#### Linux/macOS
```bash
# 启动服务
./scripts/start_all.sh

# 停止服务
./scripts/stop_all.sh
```

#### 手动运行 (开发调试)
如果您想手动运行单个 Python 文件，需要先激活虚拟环境：
```bash
# Windows
venv\Scripts\activate
python main.py

# Linux/macOS
source venv/bin/activate
python main.py
```

更多部署细节请参考 [docs/deploy.md](docs/deploy.md)。

## 实时监控服务 (Watchlist Monitor)

本项目包含一个基于自选股的 7x24 小时实时监控服务，支持配置热更新、断线重连和多渠道告警。

### 启动服务
```bash
python -m src.monitor.watchlist_monitor
```

### 功能特性
- **自选股自动同步**：自动拉取长桥 App 自选股列表并订阅行情。
- **配置热更新**：修改 `config/symbols.yaml` 或自选股列表后，服务自动刷新，无需重启。
- **智能告警**：支持价格涨跌幅和买卖价差阈值告警，并在交易日内自动去重。
- **高可用**：支持断线自动重连（指数退避策略）。

### 部署为系统服务
请参考 [docs/deploy.md](docs/deploy.md) 配置 systemd 服务。

## 测试
运行单元测试确保功能正常：
```bash
python -m unittest discover tests
```
