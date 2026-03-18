# 美股期权实时监控分析系统 (LongBridge Auto Deal)

基于长桥证券 OpenAPI (LongPort SDK) 搭建的工业级美股+期权实时监控分析系统。本项目采用模块化架构设计，支持实时行情订阅、策略分析、多渠道告警及自动交易。

## 目录

*   [核心功能](#核心功能)
    *   [1. 双市场实时监控体系](#1-双市场实时监控体系)
    *   [2. LLM 智能研报 (AI Analyst)](#2-llm-智能研报-ai-analyst)
    *   [3. 精细化告警策略](#3-精细化告警策略)
    *   [4. 工业级工程设计](#4-工业级工程设计)
*   [目录结构](#目录结构)
*   [快速开始](#快速开始)
    *   [1. 环境准备](#1-环境准备)
    *   [2. 配置 (安全重要)](#2-配置-安全重要)
    *   [3. 运行](#3-运行)
*   [测试](#测试)

## 核心功能

### 1. 双市场实时监控体系
*   **美股 (US)**：基于 **LongPort SDK**，实现毫秒级 WebSocket 行情订阅与期权异动监控。
*   **港股 (HK)**：基于 **Futu OpenD**，支持自选股自动同步、实时快照轮询与状态缓存。
*   **独立前端看板**：提供美股/港股独立监控页，支持**实时排序**（涨跌幅/成交量）、**动态阈值管理**及**手动触发检查**。

### 2. LLM 智能研报 (AI Analyst)
*   **双引擎架构**：集成 **Google Gemini** (负责美股/期权) 与 **Kimi/Moonshot** (负责港股) 大模型。
*   **自动化日报**：系统定时聚合全天异动数据，生成盘前/盘中/盘后市场分析报告。
*   **交互式生成**：Web 界面支持一键手动触发研报生成，实时分析当前市场情绪。
*   **研报中心**：内置历史研报管理功能，支持 Markdown 富文本渲染与持久化存储。

### 3. 精细化告警策略
*   **渠道分流**：
    *   **钉钉 (DingTalk)**：接收美股异动、期权信号及系统级通知。
    *   **飞书 (Feishu)**：接收港股异动及 LLM 市场研报推送。
*   **智能去重**：内置信号记录器 (`SignalRecorder`)，在交易日内对同一标的同一类型信号进行去重，防止消息轰炸。

### 4. 工业级工程设计
*   **配置热更新**：支持通过 Web 界面或配置文件动态调整监控阈值，无需重启服务。
*   **高可用性**：多进程架构隔离不同市场任务，支持断线自动重连与指数退避策略。
*   **安全合规**：敏感凭据 (`.env`) 与业务配置分离，严格遵循安全规范。
### 1. 双市场实时监控体系
*   **美股 (US)**：基于 **LongPort SDK**，实现毫秒级 WebSocket 行情订阅与期权异动监控。
*   **港股 (HK)**：基于 **Futu OpenD**，支持自选股自动同步、实时快照轮询与状态缓存。
*   **独立前端看板**：提供美股/港股独立监控页，支持**实时排序**（涨跌幅/成交量）、**动态阈值管理**及**手动触发检查**。

### 2. LLM 智能研报 (AI Analyst)
*   **双引擎架构**：集成 **Google Gemini** (负责美股/期权) 与 **Kimi/Moonshot** (负责港股) 大模型。
*   **自动化日报**：系统定时聚合全天异动数据，生成盘前/盘中/盘后市场分析报告。
*   **交互式生成**：Web 界面支持一键手动触发研报生成，实时分析当前市场情绪。
*   **研报中心**：内置历史研报管理功能，支持 Markdown 富文本渲染与持久化存储。

### 3. 精细化告警策略
*   **渠道分流**：
    *   **钉钉 (DingTalk)**：接收美股异动、期权信号及系统级通知。
    *   **飞书 (Feishu)**：接收港股异动及 LLM 市场研报推送。
*   **智能去重**：内置信号记录器 (`SignalRecorder`)，在交易日内对同一标的同一类型信号进行去重，防止消息轰炸。

### 4. 工业级工程设计
*   **配置热更新**：支持通过 Web 界面或配置文件动态调整监控阈值，无需重启服务。
*   **高可用性**：多进程架构隔离不同市场任务，支持断线自动重连与指数退避策略。
*   **安全合规**：敏感凭据 (`.env`) 与业务配置分离，严格遵循安全规范。

## 目录结构

```
LongBridge_Auto_Deal/
├── config/             # 配置管理 (敏感配置与应用配置)
│   ├── .env.example
│   ├── settings.py 
│   ├── longport_symbols.yaml # 长桥美股/期权配置
│   └── futu_symbols.yaml     # 富途港股标的与阈值配置
├── src/
│   ├── api/            # 外部接口封装
│   │   ├── longport/   # 长桥 API 核心 (拉取、订阅、推送等)
│   │   ├── futu/       # 富途 API 核心 (OpenD 客户端、回调)
│   │   └── notification.py # 飞书/钉钉告警模块
│   ├── services/       # 应用服务层
│   │   ├── llm_analyst.py  # 大模型研报生成服务
│   │   └── signal_recorder.py # 信号记录器
│   ├── monitor/        # 监控主循环与事件分发
│   │   ├── base_monitor.py
│   │   ├── us_watchlist_monitor.py # 美股行情监控器
│   │   ├── hk_watchlist_monitor.py # 港股行情监控器
│   │   ├── longport_task.py        # 长桥监控主控
│   │   └── futu_task.py            # 富途监控主控
│   └── utils/          # 通用工具 (日志, 价格计算等)
├── tests/              # 测试与验证脚本
├── docs/               # 详细文档
├── main.py             # 程序入口 (多进程启动)
├── requirements.txt    # 依赖管理
└── scripts/            # 启动与部署脚本
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
    >     ```
    >     chmod 600 config/.env
    >     ```

3.  **Futu OpenD 配置** (仅港股需要)：
    *   安装并启动 [Futu OpenD](https://www.futunn.com/download/OpenD)。
    *   在 `config/.env` 中配置 `FUTU_HOST` 和 `FUTU_PORT` (默认 11111)。
    *   确保 OpenD 已登录且 API 监听端口与配置一致。

4.  **LLM 密钥配置** (智能研报需要)：
    *   在 `config/.env` 中填入 `LLM_API_KEY` (Gemini) 和 `KIMI_API_KEY` (Moonshot)。

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

## 测试
运行单元测试确保功能正常：
```bash
python -m unittest discover tests
```
