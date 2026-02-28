# Volume Breakout Strategy Architecture
# 放量突破监控策略架构文档

**项目名称**: LongBridge_Auto_Deal  
**策略名称**: Volume Breakout Monitor (放量突破监控)  
**版本**: v1.0.0  
**文档日期**: 2026-02-27  
**编写者**: AI Architect  

---

## 1. 策略概述 (Overview)

### 1.1 定义

Volume Breakout Strategy 是一种**基于7日均量基准的实时放量突破监控策略**。通过在美股盘中持续监控个股的成交量异动，结合AI新闻归因，快速捕捉市场热点和潜在交易机会。

### 1.2 核心目标

| 目标 | 描述 | 优先级 |
|------|------|--------|
| **异动捕捉** | 实时监控美股个股成交量突破7日均量150%阈值 | P0 |
| **智能归因** | 结合大模型AI分析放量背后的新闻/事件驱动 | P0 |
| **即时推送** | 通过飞书机器人推送结构化告警消息 | P0 |
| **风险控制** | 内置冷却机制防止重复报警 | P1 |
| **高可用性** | WebSocket断线自动重连，API限流优雅降级 | P1 |

### 1.3 监控范围

- **市场**: 美股主要交易所 (NYSE, NASDAQ, AMEX)
- **标的**: 用户自定义Watchlist (建议不超过100只)
- **监控时段**: 美东时间 09:30 - 16:00 (盘中)
- **数据粒度**: Level 1 行情 (实时推送)

---

## 2. 系统架构 (Architecture)

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           LongBridge_Auto_Deal                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐ │
│  │   Watchlist     │    │   LongPort SDK  │    │   Volume Analyzer   │ │
│  │   Manager       │───▶│   QuoteContext  │───▶│   Engine            │ │
│  │                 │    │   (WebSocket)   │    │                     │ │
│  │ - Load symbols  │    │                 │    │ - 7-day avg calc    │ │
│  │ - Validate      │    │ - Subscribe     │    │ - Threshold check   │ │
│  │   symbols       │    │ - PushQuote     │    │ - Cooldown manage   │ │
│  └─────────────────┘    └────────┬────────┘    └──────────┬──────────┘ │
│                                  │                        │            │
│                                  ▼                        ▼            │
│                         ┌─────────────────┐    ┌─────────────────────┐ │
│                         │   Connection    │    │   AI Attribution    │ │
│                         │   Manager       │◀───│   Layer             │ │
│                         │                 │    │                     │ │
│                         │ - Reconnect     │    │ - Kimi API Client   │ │
│                         │ - Heartbeat     │    │ - News search       │ │
│                         │ - Error retry   │    │ - Summary gen       │ │
│                         └─────────────────┘    └──────────┬──────────┘ │
│                                                           │            │
│                                                           ▼            │
│                                                  ┌─────────────────────┐│
│                                                  │   Lark Pusher       ││
│                                                  │                     ││
│                                                  │ - Message format    ││
│                                                  │ - Rate limiting     ││
│                                                  │ - Retry logic       ││
│                                                  └─────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈选型

| 模块 | 技术选型 | 版本要求 | 选型理由 |
|------|----------|----------|----------|
| **行情数据** | LongPort Python SDK | >=2.0.0 | 官方支持，WebSocket稳定 |
| **异步框架** | asyncio + aiohttp | Python 3.9+ | 高并发订阅处理 |
| **AI引擎** | Kimi k2.5 (moonshot) | moonshot-v1-32k | 联网搜索+长上下文 |
| **消息推送** | Lark Webhook API | OpenAPI v3 | 实时可靠，格式丰富 |
| **数据缓存** | Redis (可选) | >=6.0 | 冷却状态持久化 |
| **日志记录** | loguru | >=0.7.0 | 结构化日志，自动轮转 |

### 2.3 模块职责

#### 2.3.1 Data Layer (数据层)
```python
# longport_data_provider.py
class LongPortDataProvider:
    """
    职责:
    1. 管理LongPort SDK连接生命周期
    2. 处理WebSocket订阅/取消订阅
    3. 原始行情数据标准化输出
    4. 连接状态监控与自动重连
    """
    pass
```

#### 2.3.2 Strategy Layer (策略层)
```python
# volume_breakout_engine.py
class VolumeBreakoutEngine:
    """
    职责:
    1. 计算7日均量基准 V_avg
    2. 实时计算当前成交量 V_current
    3. 触发条件判断 (V_current > 1.5 * V_avg)
    4. 冷却时间管理 (Cooldown Manager)
    """
    pass
```

#### 2.3.3 AI Layer (AI归因层)
```python
# ai_attribution_client.py
class AIAttributionClient:
    """
    职责:
    1. 构造Kimi API请求 (Prompt Engineering)
    2. 联网搜索新闻资讯
    3. 生成异动原因总结 (50字内)
    4. 情绪倾向判定 (偏多/偏空/中性)
    """
    pass
```

#### 2.3.4 Notification Layer (通知层)
```python
# lark_notifier.py
class LarkNotifier:
    """
    职责:
    1. 构造飞书卡片消息 (富文本/Markdown)
    2. 处理推送限流和重试
    3. 失败告警兜底机制
    """
    pass
```

---

## 3. 核心算法逻辑 (Core Logic)

### 3.1 数据流时序图

```
美东时间 09:25                    盘中 09:30-16:00
    │                                   │
    ▼                                   ▼
┌─────────┐                    ┌─────────────────┐
│ 盘前准备 │                    │   实时监控循环   │
│ 阶段    │                    │                 │
└────┬────┘                    └────────┬────────┘
     │                                  │
     │ 1. 获取历史K线                    │ 2. 接收PushQuote
     │    (过去7个交易日)                 │    
     │                                  │
     ▼                                  ▼
┌─────────────┐                ┌─────────────────┐
│ 计算 V_avg   │                │ 提取 V_current  │
│ (7日平均)   │                │ (当日累计成交)  │
└──────┬──────┘                └────────┬────────┘
       │                                │
       │ 存储基准值                      │ 3. 判断条件
       │                                │    V_current > 1.5 × V_avg ?
       │                                │
       ▼                                ▼
┌─────────────┐                ┌─────────────────┐
│ 内存缓存     │                │ 是 → 检查冷却    │
│ {symbol:    │                │ 否 → 继续监控    │
│  V_avg}    │                └─────────────────┘
└─────────────┘                         │
                                        │ 4. 冷却检查
                                        │    1小时内是否已报过?
                                        ▼
                               ┌─────────────────┐
                               │ 通过 → 触发归因  │
                               │ 拦截 → 静默丢弃  │
                               └─────────────────┘
```

### 3.2 盘前基准计算 (Pre-market Calculation)

#### 3.2.1 算法步骤

```python
async def calculate_baseline(symbol: str) -> float:
    """
    计算单只股票的7日平均成交量基准
    
    步骤:
    1. 调用 LongPort 历史K线 API
       - 周期: Day (日线)
       - 数量: 7 根 (过去7个交易日)
       - 字段: volume
    
    2. 数据清洗:
       - 过滤停牌日 (volume = 0)
       - 排除当日 (未收盘)
    
    3. 计算均值:
       V_avg = Σ(volume_i) / n, where n ∈ [5, 7]
       (允许最多2天数据缺失，最少5天有效数据)
    
    4. 异常处理:
       - 新股上市不足7天: 使用实际天数计算
       - 数据缺失超过2天: 标记为"基准不可靠"
       
    返回:
        float: 7日平均成交量
        None: 数据不足无法计算
    """
    pass
```

#### 3.2.2 API调用示例

```python
from longport.openapi import QuoteContext, Period

ctx = QuoteContext.from_env()

# 获取日线数据
resp = await ctx.history_candles(
    symbol="AAPL.US",
    period=Period.Day,
    count=10  # 多取3天以防节假日
)

# 提取成交量并计算
volumes = [candle.volume for candle in resp[-7:]]  # 取最近7天
V_avg = sum(volumes) / len(volumes)
```

#### 3.2.3 缓存策略

```python
# 基准值缓存结构
BASELINE_CACHE = {
    "AAPL.US": {
        "v_avg": 45_230_000,        # 7日均量
        "calculated_at": "2026-02-27T09:25:00-05:00",
        "valid_days": 7,             # 有效天数
        "reliability": "high"        # high | medium | low
    },
    # ...
}

# 刷新策略:
# - 每日盘前 (09:25 ET) 统一刷新
# - 盘中不更新，避免基准值抖动
```

### 3.3 盘中实时监控 (Intraday Monitor)

#### 3.3.1 行情订阅处理

```python
async def on_quote_update(quote: PushQuote):
    """
    实时行情推送回调处理
    
    Args:
        quote: 推送的行情数据
        
    关键字段:
        - symbol: 股票代码
        - volume: 当日累计成交量
        - timestamp: 推送时间戳
    """
    symbol = quote.symbol
    v_current = quote.volume  # 当日累计成交量
    
    # 1. 获取基准值
    baseline = get_baseline(symbol)
    if not baseline:
        logger.warning(f"{symbol}: 无基准值，跳过")
        return
    
    v_avg = baseline["v_avg"]
    threshold = v_avg * CONFIG["volume_threshold"]  # 默认1.5倍
    
    # 2. 阈值判断
    if v_current < threshold:
        return  # 未触发，静默
    
    # 3. 冷却检查
    if is_in_cooldown(symbol):
        logger.debug(f"{symbol}: 冷却期内，跳过")
        return
    
    # 4. 触发告警流程
    await trigger_alert(symbol, v_current, v_avg)
```

#### 3.3.2 触发条件公式

```
触发条件 = V_current > (V_avg × Threshold_Multiplier) 
                         AND 
           NOT InCooldown(symbol)

其中:
- V_current: 当日累计成交量 (从行情推送获取)
- V_avg: 7日平均成交量 (盘前计算)
- Threshold_Multiplier: 阈值倍数 (默认1.5, 可配置1.2-3.0)
- InCooldown(symbol): 检查该股票是否在冷却期
```

#### 3.3.3 冷却机制 (Cooldown Manager)

```python
class CooldownManager:
    """
    冷却时间管理器
    
    规则:
    - 同一股票触发后，进入冷却期 (默认60分钟)
    - 冷却期内即使再次放量也不重复报警
    - 冷却期结束后可再次触发
    
    实现:
    - 内存存储: {symbol: last_alert_timestamp}
    - 持久化: 可选Redis (防止重启后重复报警)
    """
    
    COOLDOWN_MINUTES = 60
    
    def is_in_cooldown(self, symbol: str) -> bool:
        last_alert = self.get_last_alert_time(symbol)
        if not last_alert:
            return False
        
        elapsed = (now() - last_alert).total_seconds() / 60
        return elapsed < self.COOLDOWN_MINUTES
    
    def record_alert(self, symbol: str):
        """记录本次报警时间"""
        self.store[symbol] = now()
```

---

## 4. AI归因模块 (AI Attribution Layer)

### 4.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Attribution Layer                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Input: symbol="TSLA.US", volume_spike=180%                 │
│                          │                                  │
│                          ▼                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Prompt Constructor                        │   │
│  │                                                     │   │
│  │  系统提示词 + 上下文信息 + 格式约束                  │   │
│  │                                                     │   │
│  │  "股票 TSLA 今日放量180%，请联网搜索该股票过去12小时  │   │
│  │   的最新资讯，分析可能的异动原因..."                 │   │
│  └────────────────┬────────────────────────────────────┘   │
│                   │                                         │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Kimi API Client                           │   │
│  │                                                     │   │
│  │  - Model: moonshot-v1-32k                          │   │
│  │  - Temperature: 0.3 (低随机性)                      │   │
│  │  - Enable Web Search: True                          │   │
│  │  - Max Tokens: 200                                  │   │
│  └────────────────┬────────────────────────────────────┘   │
│                   │                                         │
│                   ▼                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           Response Parser                           │   │
│  │                                                     │   │
│  │  解析输出格式:                                       │   │
│  │  {"reason": "xx", "sentiment": "偏多", "confidence": 0.8}│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Prompt模板 (System Prompt)

```python
SYSTEM_PROMPT = """你是一位专业的股票分析师，擅长分析美股异动原因。

任务：分析股票 {symbol} 的成交量异动原因。

背景信息：
- 该股票今日成交量较7日均量增长 {volume_spike}%
- 当前时间: {current_time} ET
- 交易市场: 美股

要求：
1. 联网搜索该股票过去12小时的最新资讯
2. 分析可能导致成交量放大的原因（新闻、事件、财报等）
3. 输出格式必须是JSON：
{{
    "reason": "50字以内的异动原因总结",
    "sentiment": "偏多|偏空|中性",
    "confidence": 0.0-1.0,
    "key_events": ["关键事件1", "关键事件2"]
}}

约束：
- reason 字段必须在50字以内
- sentiment 只能是：偏多、偏空、中性
- confidence 表示你对此分析的置信度
- 如果没有找到明确原因，reason填"暂未发现明确驱动因素"
"""
```

### 4.3 API调用实现

```python
import openai
from typing import Optional

class KimiAttributionClient:
    """Kimi AI归因客户端"""
    
    MODEL = "moonshot-v1-32k"
    MAX_TOKENS = 200
    TEMPERATURE = 0.3
    TIMEOUT_SECONDS = 30
    
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1"
        )
    
    async def analyze(
        self, 
        symbol: str, 
        volume_spike_pct: float
    ) -> Optional[dict]:
        """
        分析股票异动原因
        
        Args:
            symbol: 股票代码 (如 "TSLA.US")
            volume_spike_pct: 成交量增长率 (如 180.0)
            
        Returns:
            dict: {"reason": str, "sentiment": str, "confidence": float}
            None: 调用失败
        """
        prompt = SYSTEM_PROMPT.format(
            symbol=symbol,
            volume_spike=round(volume_spike_pct, 1),
            current_time=self.get_current_time_et()
        )
        
        try:
            response = await asyncio.wait_for(
                self._call_api(prompt),
                timeout=self.TIMEOUT_SECONDS
            )
            return self._parse_response(response)
            
        except asyncio.TimeoutError:
            logger.error(f"Kimi API 调用超时: {symbol}")
            return None
        except Exception as e:
            logger.error(f"Kimi API 调用失败: {e}")
            return None
    
    async def _call_api(self, prompt: str) -> str:
        """调用Kimi API"""
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {"role": "system", "content": "You are a professional stock analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=self.TEMPERATURE,
            max_tokens=self.MAX_TOKENS,
            tools=[{
                "type": "builtin_function",
                "function": {"name": "web_search"}
            }]
        )
        return response.choices[0].message.content
    
    def _parse_response(self, text: str) -> dict:
        """解析JSON响应"""
        import json
        try:
            # 提取JSON部分
            json_str = text[text.find('{'):text.rfind('}')+1]
            return json.loads(json_str)
        except Exception:
            # 降级处理: 返回原始文本
            return {
                "reason": text[:50],
                "sentiment": "中性",
                "confidence": 0.5
            }
```

### 4.4 情绪图标映射

```python
SENTIMENT_ICONS = {
    "偏多": "🟢📈",  # 上涨/利好
    "偏空": "🔴📉",  # 下跌/利空
    "中性": "⚪➡️",  # 中性/观望
}

SENTIMENT_COLORS = {
    "偏多": "green",
    "偏空": "red", 
    "中性": "gray"
}
```

---

## 5. 异常处理规范 (Error Handling)

### 5.1 异常分类体系

```
LongBridgeAutoDealException
├── DataProviderException
│   ├── WebSocketDisconnectedError    # WebSocket断线
│   ├── SubscriptionFailedError       # 订阅失败
│   ├── RateLimitError                # 限流
│   └── DataValidationError           # 数据异常
│
├── AIAttributionException
│   ├── APITimeoutError               # AI调用超时
│   ├── RateLimitError                # 配额超限
│   ├── ContentFilterError            # 内容过滤
│   └── ParseError                    # 解析失败
│
└── NotificationException
    ├── WebhookFailedError            # 推送失败
    └── RateLimitError                # 推送限流
```

### 5.2 WebSocket断线重连逻辑

```python
class WebSocketConnectionManager:
    """
    WebSocket连接管理器
    
    重连策略:
    1. 指数退避: 1s, 2s, 4s, 8s, 16s, 30s (max)
    2. 最大重试: 无限 (盘中保持尝试)
    3. 全量重连: 断线后重新订阅所有股票
    """
    
    INITIAL_BACKOFF = 1.0      # 初始退避1秒
    MAX_BACKOFF = 30.0         # 最大退避30秒
    BACKOFF_MULTIPLIER = 2.0   # 指数倍数
    
    async def connect_with_retry(self):
        """带重连的连接"""
        backoff = self.INITIAL_BACKOFF
        attempt = 0
        
        while True:
            try:
                attempt += 1
                logger.info(f"尝试连接 WebSocket... (第{attempt}次)")
                
                await self._connect()
                await self._resubscribe_all()  # 重新订阅
                
                logger.info("WebSocket 连接成功")
                backoff = self.INITIAL_BACKOFF  # 重置退避
                
                # 启动心跳检测
                await self._heartbeat_loop()
                
            except WebSocketDisconnectedError:
                logger.error(f"WebSocket 断开，{backoff}秒后重连...")
                await asyncio.sleep(backoff)
                
                # 指数退避
                backoff = min(
                    backoff * self.BACKOFF_MULTIPLIER,
                    self.MAX_BACKOFF
                )
                
            except Exception as e:
                logger.exception(f"WebSocket 异常: {e}")
                await asyncio.sleep(backoff)
    
    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while True:
            try:
                await asyncio.wait_for(
                    self._wait_for_message(),
                    timeout=60  # 60秒无消息认为断线
                )
            except asyncio.TimeoutError:
                raise WebSocketDisconnectedError("心跳超时")
```

### 5.3 Kimi API限流与降级

```python
class AIAttributionWithFallback:
    """
    带降级机制的AI归因客户端
    
    降级策略:
    1. 超时 (>30s): 仅发送基础放量告警，不带AI分析
    2. 限流 (429): 延迟5秒后重试，最多3次
    3. 故障: 跳过AI分析，不影响主监控流程
    """
    
    MAX_RETRIES = 3
    RETRY_DELAY = 5.0
    
    async def analyze_with_fallback(
        self, 
        symbol: str, 
        v_current: int,
        v_avg: float
    ) -> dict:
        """
        带降级的分析
        
        Returns:
            成功: AI分析结果
            降级: 基础信息 {"reason": "AI分析暂时不可用", "sentiment": "中性"}
        """
        spike_pct = (v_current / v_avg - 1) * 100
        
        for attempt in range(self.MAX_RETRIES):
            try:
                result = await self.kimi_client.analyze(symbol, spike_pct)
                if result:
                    return result
                    
            except RateLimitError:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"Kimi限流，{self.RETRY_DELAY}秒后重试...")
                    await asyncio.sleep(self.RETRY_DELAY)
                else:
                    logger.error("Kimi限流，已达最大重试次数")
                    
            except APITimeoutError:
                logger.error("Kimi调用超时，启用降级")
                break
                
            except Exception as e:
                logger.error(f"Kimi调用失败: {e}")
                break
        
        # 降级: 返回基础信息
        return self._fallback_response(symbol, spike_pct)
    
    def _fallback_response(self, symbol: str, spike_pct: float) -> dict:
        """降级响应"""
        return {
            "reason": f"放量{spike_pct:.0f}%，AI分析暂时不可用",
            "sentiment": "中性",
            "confidence": 0.0,
            "fallback": True  # 标记为降级响应
        }
```

### 5.4 飞书推送失败处理

```python
class LarkNotifierWithRetry:
    """
    带重试的飞书推送器
    
    策略:
    1. 失败重试3次，间隔2秒
    2. 网络错误降级为本地日志记录
    3. 批量推送使用熔断器模式
    """
    
    MAX_RETRIES = 3
    RETRY_INTERVAL = 2.0
    
    async def send_with_retry(self, message: dict) -> bool:
        """带重试的发送"""
        for attempt in range(self.MAX_RETRIES):
            try:
                await self._send(message)
                return True
                
            except WebhookFailedError as e:
                logger.warning(f"飞书推送失败 (尝试{attempt+1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_INTERVAL)
                    
            except Exception as e:
                logger.error(f"飞书推送异常: {e}")
                break
        
        # 最终失败: 记录到本地日志
        self._log_failed_message(message)
        return False
    
    def _log_failed_message(self, message: dict):
        """记录失败消息到本地"""
        logger.error(f"[FAILED_MESSAGE] {json.dumps(message)}")
        # 可扩展: 写入文件或数据库，后续人工补发
```

---

## 6. 配置参数汇总

### 6.1 策略配置 (config/strategy.yaml)

```yaml
volume_breakout:
  # 监控标的
  watchlist:
    - "AAPL.US"
    - "TSLA.US"
    - "NVDA.US"
    - "MSFT.US"
    
  # 触发阈值
  volume_threshold: 1.5        # 放量倍数 (1.2 - 3.0)
  
  # 冷却机制
  cooldown_minutes: 60         # 冷却时间 (分钟)
  
  # 监控时段 (美东时间)
  trading_hours:
    start: "09:30"
    end: "16:00"
  
  # 数据源
  data_provider:
    name: "longport"
    websocket_timeout: 60      # 心跳超时(秒)
    reconnect_max_backoff: 30  # 最大重连间隔(秒)
  
  # AI归因
  ai_attribution:
    provider: "kimi"
    model: "moonshot-v1-32k"
    timeout: 30                # API调用超时(秒)
    max_retries: 3
    temperature: 0.3
    
  # 消息推送
  notification:
    lark_webhook: "${LARK_WEBHOOK_URL}"
    lark_secret: "${LARK_SECRET}"  # 可选
    rate_limit_per_minute: 20
```

---

## 7. 接口定义速查

### 7.1 核心类接口

```python
# 数据提供者接口
class IDataProvider(ABC):
    @abstractmethod
    async def connect(self): pass
    
    @abstractmethod
    async def subscribe(self, symbols: List[str]): pass
    
    @abstractmethod
    async def get_history_volume(self, symbol: str, days: int) -> List[int]: pass
    
    @abstractmethod
    def on_quote(self, callback: Callable[[PushQuote], None]): pass

# 策略引擎接口
class IStrategyEngine(ABC):
    @abstractmethod
    async def calculate_baseline(self, symbol: str) -> float: pass
    
    @abstractmethod
    def check_trigger(self, symbol: str, v_current: int) -> bool: pass
    
    @abstractmethod
    def is_in_cooldown(self, symbol: str) -> bool: pass

# AI归因接口
class IAIAttribution(ABC):
    @abstractmethod
    async def analyze(self, symbol: str, volume_spike: float) -> dict: pass

# 通知接口
class INotifier(ABC):
    @abstractmethod
    async def send_alert(self, alert_data: dict): pass
```

---

## 8. 开发检查清单

在提交代码前，请确认以下检查项：

### 8.1 功能完整性
- [ ] 盘前7日平均成交量计算正确
- [ ] 实时行情订阅和处理正常
- [ ] 放量阈值判断逻辑正确
- [ ] 冷却机制生效
- [ ] Kimi API调用和解析正常
- [ ] 飞书消息推送正常

### 8.2 异常处理
- [ ] WebSocket断线自动重连
- [ ] Kimi API超时降级处理
- [ ] 飞书推送失败重试
- [ ] 日志记录完整

### 8.3 代码质量
- [ ] 类型注解完整
- [ ] 异常分类清晰
- [ ] 配置外置化
- [ ] 单元测试覆盖核心逻辑

---

**文档版本**: v1.0.0  
**适用项目**: LongBridge_Auto_Deal  
**编写目的**: 为AI编程助手(Trae)提供清晰的实现蓝图

---

*"量化交易的本质是将不确定性转化为可计算的概率优势。"*
