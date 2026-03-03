# 多市场量化交易系统中台化重构与富途 (Futu) 接入指南

## 1. 架构目标 (Architecture Goals)
当前系统 (`LongBridge_Auto_Deal`) 已成功实现长桥 (LongPort) 美股与期权的异步监控。
本次迭代的目标是：采用**适配器模式 (Adapter Pattern)** 进行架构重构，在不破坏现有长桥异步数据流的前提下，接入富途 (`futu-api`) 实现港股行情监控。最终演进为一个支持多券商、跨市场的统一量化监控中台。

## 2. 目标目录树结构 (Target Directory Structure)
请严格按照以下结构对现有代码进行重构和扩建：

```text
Global_Quant_System/
├── config/ 
│   ├── settings.py           # 需更新：支持多数据源配置加载
│   ├── longport_symbols.yaml # 原 symbols.yaml 重命名
│   └── futu_symbols.yaml     # 【新增】富途港股标的配置
├── src/
│   ├── api/
│   │   ├── longport/         # 【保持原样】长桥原生 asyncio 逻辑
│   │   ├── futu/             # 【新增】富途 API 适配层
│   │   │   ├── client.py     # 初始化 OpenD 上下文 (SysQuoteContext)
│   │   │   └── callback.py   # 富途行情回调处理 (继承 StockQuoteTest 并在 on_recv_rsp 中处理)
│   │   └── notification.py   # 【共享】钉钉/飞书消息网关
│   ├── analysis/             # 【共享】策略与大模型分析层
│   │   ├── llm_engine.py     # 大模型 (Kimi/Gemini) 研报生成
│   │   └── strategy.py       # 异动信号计算逻辑
│   ├── monitor/ 
│   │   ├── longport_task.py  # 【重构】封装长桥的主监控任务
│   │   └── futu_task.py      # 【新增】封装富途的主监控任务
│   └── utils/ 
└── main.py                   # 【重构】多进程入口文件
```

## 3. 核心重构任务 (Core Tasks)
### 任务 3.1：配置文件分离
- 将原有的`symbols.yaml`重命名为 `longport_symbols.yaml`。
- 新增 `futu_symbols.yaml`，用于配置富途港股标的。
- 修改 `config/settings.py`，使其能够分别解析这两个文件，并为上下游提供配置字典。

### 任务 3.2：富途适配器实现 (src/api/futu/)
- 使用富途官方 Python SDK (futu-api)。
- 编写行情订阅回调逻辑。当富途触发 PushQuote (如异动、放量) 时，提取关键字段（如代码、最新价、成交量）。

### 任务 3.3：数据标准化 (Data Normalization)
- 核心要求：长桥和富途的底层数据结构不同。在调用 src/analysis/ (策略与 LLM) 和 src/notification.py (推送) 之前，必须在各自的 task 层将数据清洗为统一的 Python 字典格式。
- 目的：让大模型分析引擎和钉钉推送模块“无感”于数据来源，实现完全解耦的复用。

### 任务 3.4：入口文件重写 (Process Isolation - 绝对红线)
- 技术背景：长桥 SDK 深度依赖原生 asyncio，而富途 SDK 底层依赖多线程和同步阻塞机制。
- 重构要求：在 main.py 中，严禁将长桥和富途的任务放入同一个异步事件循环 (Event Loop) 中。
- 解决方案：必须使用 Python 的 multiprocessing.Process。
- 进程 A：运行 monitor.longport_task.run()
- 进程 B：运行 monitor.futu_task.run()

### 任务 3.5：测试与调试
在本地环境下，分别启动进程 A 和 B。
验证：
- 长桥标的是否能正常触发异动信号。
- 富途标的是否能正常触发异动信号。
- 大模型分析是否能正常处理来自不同市场的数据。
- 钉钉推送是否能正常工作。
确保两个网关在操作系统层面物理隔离，互不阻塞。

## 4. 异常处理规范
- 富途重连机制：处理富途 OpenD 意外断开的异常，需实现自动重连逻辑。
- 进程守护：main.py 作为主进程，需监控子进程 (长桥/富途) 的健康状态，若子进程崩溃需自动重启。

## 5. 市场路由与权限隔离规范 (Market Routing & Permission Isolation)

**关键背景**：当前系统拥有两套 API 的不同市场权限。
* **Futu API (富途)**：仅具备港股 (HK)、港股期权、港股期货的 LV2 实时行情权限。美股无权限。
* **LongPort API (长桥)**：具备美股 (US) 及美股期权的实时行情权限。

**开发要求 (For Trae)**：
为了避免 API 权限报错和订阅配额浪费，系统必须在最外层配置和底层订阅时实现严格的“市场路由”。

1. **配置文件强隔离**：
   * `config/futu_symbols.yaml` 中的所有标的，必须严格以港股前缀开头（如富途格式的 `HK.00700` 或 `HK.800000` 等指数/正股/期权）。
   * `config/longport_symbols.yaml` 中的所有标的，必须严格限制为美股及其期权（如 `AAPL`, `RXRX261120C3500`）。
   
2. **适配器级的鉴权过滤 (Adapter Level Filtering)**：
   * 在 `src/api/futu/client.py` 执行 `subscribe` 动作前，增加一个断言或过滤逻辑：遍历传入的 symbols 列表，如果发现非 `HK.` 开头的标的，记录 Warning 日志并剔除，**绝对禁止**向 Futu 发起美股订阅请求。
   * 同样，在 `src/api/longport/client.py` 中，排除掉任何可能误入的港股代码。

3. **异常处理**：
   * 捕获富途 `104` (无权限) 或 `105` (配额不足) 的底层报错，不要让单个错误代码引发整个适配器进程的 Crash。


