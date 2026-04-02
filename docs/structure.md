# 长桥美股期权监控系统 - 目录结构设计文档
## 文档说明
本文件定义了项目的标准化目录结构，需严格遵循长桥OpenAPI官方模块分类（拉取、订阅、推送、个性化、标的），同时保留工程化的核心目录（analysis/monitor/utils等），确保代码结构清晰、可维护。

## 一、整体项目目录结构
Global_Quant_System/          # (建议改个更宏大的名字，比如这个)
├── config/ 
│   ├── .env.example
│   ├── settings.py 
│   ├── longport_symbols.yaml # 明确为长桥美股/期权配置
│   └── futu_symbols.yaml     # 【新增】富途港股标的与阈值配置
├── src/
│   ├── analysis/             # 【新增】量化数学指标与技术分析引擎
│   │   ├── futu_math_indicator.py # 港股均线衍生指标与多周期共振量化模块
│   │   └── ...
│   ├── api/
│   │   ├── longport/         # (保持原样，完全不影响现有稳定运行的功能)
│   │   │   ├── client.py 
│   │   │   ├── push/ 
│   │   │   └── ...
│   │   ├── futu/             # 【新增】富途 API 核心 (适配器)
│   │   │   ├── client.py     # 富途 OpenD 客户端单例初始化
│   │   │   ├── callback/     # 富途底层是回调机制，对应长桥的 push
│   │   │   └── ...
│   │   └── notification.py   # 共享：钉钉/飞书告警模块 (长桥和富途共用它)
│   ├── services/             # 【调整】应用服务层
│   │   ├── llm_analyst.py    # 大模型研报生成服务 (原 analysis/llm_engine)
│   │   └── signal_recorder.py# 信号记录器
│   ├── monitor/ 
│   │   ├── base_monitor.py         # 【新增】监控器抽象基类
│   │   ├── us_watchlist_monitor.py # 【重命名】美股行情监控器 (原 watchlist_monitor.py)
│   │   ├── hk_watchlist_monitor.py # 【新增】港股行情监控器 (原 utils.py)
│   │   ├── longport_task.py        # 【重构】原有的长桥监控主控
│   │   └── futu_task.py            # 【新增】富途的监控主控
│   └── utils/ 
├── tests/            # 核心测试目录，所有测试/验证/调试脚本均应放置于此
│   ├── check_*.py    # 环境/端口/配置检查脚本
│   ├── debug_*.py    # 调试脚本
│   ├── inspect_*.py  # 数据/对象检查脚本
│   ├── test_*.py     # 单元测试与功能测试
│   └── verify_*.py   # 集成验证脚本
└── main.py           # 【重构】使用多进程启动长桥和富途两个 Task，每个进程负责一个监控循环

## 二、目录/文件职责说明
### 1. config/ 目录
| 文件/目录       | 核心职责                                                                 | 安全要求                                  |
|-----------------|--------------------------------------------------------------------------|-------------------------------------------|
| .env.example    | 配置模板，包含长桥Token/飞书Webhook等占位符，注释说明用途，允许提交Git    | 禁止包含真实敏感值                        |
| settings.py     | 加载.env文件、定义全局常量（阈值/URL）、配置校验，对外提供统一调用接口    | 禁止打印/日志输出敏感配置值                |
| symbols.yaml    | YAML格式配置监控标的，支持不同标的自定义阈值                             | 允许提交Git（无敏感信息）                 |

### 2. src/api/longport/ 目录（长桥API核心）
| 模块/文件         | 核心职责                                                                 |
|-------------------|--------------------------------------------------------------------------|
| client.py         | 初始化长桥Config、创建WebSocket/HTTP连接、统一异常处理/重试逻辑          |
| pull/             | 封装长桥“拉取类”接口，与官方GetQuote/GetDepth等接口一一对应               |
| subscribe/        | 封装长桥“订阅类”接口，提供订阅/取消订阅方法，转发推送事件到push模块       |
| push/             | 处理长桥推送数据，handler.py统一分发，子文件解析不同类型推送（行情/成交） |
| personalized/     | 封装自选股管理、个性化行情设置等官方接口                                 |
| symbol/           | 封装标的搜索、基本信息、期权链查询等接口                                 |

### 3. 其他核心目录
| 目录             | 核心职责                                                                 |
|------------------|--------------------------------------------------------------------------|
| src/analysis/    | 量化数学指标与技术分析引擎，包含EMA、乖离率等多周期共振计算模块             |
| src/services/    | 应用服务层，包含大模型研报生成 (`llm_analyst`) 和信号记录 (`signal_recorder`) |
| src/monitor/     | 监控核心，包含长桥/富途的监控器实现 (`base_monitor`及其子类) 和任务主控     |
| src/utils/       | 通用工具（日志初始化、价格计算、异常处理），避免代码重复                 |
| tests/           | 每个核心模块对应测试用例，覆盖正常/异常/边界场景                        |
| docs/            | 项目文档，包含部署步骤、API参考、使用说明                                |

## 三、代码规范要求
### 1. 文件命名与编码
- 所有文件命名使用**蛇形命名法**（如`quote_monitor.py`），禁止大写/特殊字符；
- 代码编码统一为UTF-8，所有`.py`文件包含文件头注释（模块说明/作者/日期）。

### 2. 模块调用规则
- `src/monitor/` 仅依赖`src/api/longport/`的订阅/推送模块，不直接调用底层接口；
- 所有长桥API调用必须通过`client.py`初始化的客户端，禁止重复创建Config；
- `src/api/longport/__init__.py`导出核心类/函数，上层模块通过`from src.api.longport import XXX`调用。

### 3. 敏感信息处理
- 真实Token/密钥仅存于本地`config/.env`文件，该文件被`.gitignore`屏蔽，禁止提交Git；
- `config/.env`文件权限在本地/服务器必须设为600（仅所有者可读写）；
- 配置校验仅提示“字段缺失”，不暴露具体配置值。

## 四、Git提交规则
### 1. .gitignore 核心规则
1. 敏感配置（绝对禁止提交）
- config/.env
- config/.env.local
- config/*.secret
2. 允许提交模板（清空敏感值）
- !config/.env.example
3. 系统 / 缓存文件
pycache/*.pyclogs/.DS_Store
### 2. 提交要求
- 仅提交代码/文档/配置模板，禁止提交任何包含真实敏感值的文件；
- 测试提交时需验证`config/.env`不会被纳入Git追踪范围。

## 五、交付验证标准
1. 目录结构严格匹配本文档，无缺失/多余目录；
2. 每个`.py`文件包含基础注释（模块说明/核心函数说明）；
3. `tests/test_longport_api.py`覆盖长桥5大模块核心接口测试；
4. `docs/api_reference.md`明确长桥API模块与文件的对应关系；
5. 执行`python main.py`可正常启动监控，无配置/导入错误。