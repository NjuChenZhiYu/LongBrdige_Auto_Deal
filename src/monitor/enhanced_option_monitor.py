"""
Enhanced Option Monitor with Kimi Real-time Analysis
增强版期权监控器 - 集成 Kimi 实时分析
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from config.settings import Settings
from src.api.longport.client import longport_client
from src.services.signal_recorder import signal_recorder
from src.services.kimi_option_analyzer import kimi_analyzer
from src.utils.greeks import calculate_black_scholes
from longport.openapi import SubType

logger = logging.getLogger(__name__)


class EnhancedOptionMonitor:
    """
    增强版期权监控器
    
    新增功能：
    1. 信号触发时即时 Kimi 分析
    2. 飞书富文本推送
    3. 信号去重（同一标的5分钟内不重复触发）
    4. 信号强度分级（重要信号优先分析）
    5. 多维度数据缓存
    """
    
    def __init__(self):
        self.monitored_options = Settings.MONITORED_OPTIONS or []
        self.monitored_stocks = Settings.MONITOR_SYMBOLS or []
        self.underlying_prices = {}
        self.option_cache = {}  # 期权数据缓存
        self.risk_free_rate = 0.045
        
        self.ctx = None
        self.loop = None
        self._is_running = False
        
        # 信号去重：记录上次触发时间
        self.last_signal_time: Dict[str, datetime] = {}
        self.signal_cooldown = timedelta(minutes=5)  # 5分钟冷却期
        
        # 统计
        self.signals_today = 0
        self.analyses_today = 0
        
    async def start(self):
        """启动监控"""
        self.loop = asyncio.get_running_loop()
        
        if not self.monitored_options:
            logger.warning("No option symbols configured for monitoring.")
            return
        
        try:
            self.ctx = await longport_client.get_quote_context()
            self.ctx.set_on_quote(self._on_quote_update)
            
            # 订阅期权+正股行情
            subscribe_list = list(set(self.monitored_options + self.monitored_stocks))
            await self.ctx.subscribe(subscribe_list, [SubType.Quote])
            
            logger.info(f"✅ EnhancedOptionMonitor started. Monitoring {len(self.monitored_options)} options.")
            self._is_running = True
            
        except Exception as e:
            logger.error(f"Failed to start EnhancedOptionMonitor: {e}")
    
    def _on_quote_update(self, symbol: str, event: Any):
        """处理行情推送"""
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._process_quote_async(symbol, event), 
                self.loop
            )
    
    async def _process_quote_async(self, symbol: str, event: Any):
        """异步处理行情更新"""
        try:
            # 更新正股价格
            if symbol in self.monitored_stocks:
                price = getattr(event, 'last_done', None)
                if price:
                    self.underlying_prices[symbol] = float(price)
                return
            
            # 处理期权数据
            if symbol not in self.monitored_options:
                return
            
            # 获取完整期权行情
            quotes = await self.ctx.option_quote([symbol])
            if not quotes:
                return
            
            quote = quotes[0]
            await self._analyze_and_signal(symbol, quote)
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")
    
    async def _analyze_and_signal(self, symbol: str, quote: Any):
        """
        分析期权数据并生成信号
        """
        timestamp = datetime.now()
        time_str = timestamp.strftime("%H:%M:%S")
        
        # 提取基础数据
        data = self._extract_quote_data(quote)
        data['symbol'] = symbol
        data['timestamp'] = time_str
        
        # 缓存数据
        self.option_cache[symbol] = data
        
        # 检测策略信号
        signals = self._detect_signals(symbol, data, timestamp)
        
        if not signals:
            return
        
        # 处理每个信号
        for signal in signals:
            # 1. 记录信号
            signal_recorder.add_signal(signal)
            self.signals_today += 1
            
            # 2. 检查是否需要实时分析（重要信号 + 冷却期已过）
            if self._should_analyze_realtime(symbol, signal, timestamp):
                # 3. 触发 Kimi 实时分析
                asyncio.create_task(
                    kimi_analyzer.push_realtime_alert(signal, data)
                )
                self.analyses_today += 1
                self.last_signal_time[symbol] = timestamp
                
                logger.info(f"🚨 Realtime analysis triggered for {symbol} - {signal['type']}")
    
    def _extract_quote_data(self, quote: Any) -> Dict[str, Any]:
        """提取行情数据"""
        return {
            'last_price': float(getattr(quote, 'last_done', 0)),
            'volume': int(getattr(quote, 'volume', 0)),
            'open_interest': int(getattr(quote, 'open_interest', 0)),
            'implied_volatility': float(getattr(quote, 'implied_volatility', 0)),
            'historical_volatility': float(getattr(quote, 'historical_volatility', 0) or 0),
            'strike_price': float(getattr(quote, 'strike_price', 0)),
            'expiry_date': getattr(quote, 'expiry_date', None),
            'underlying_symbol': getattr(quote, 'underlying_symbol', None),
            'delta': getattr(quote, 'delta', None),
            'gamma': getattr(quote, 'gamma', None),
            'theta': getattr(quote, 'theta', None),
            'vega': getattr(quote, 'vega', None),
            'bid': float(getattr(quote, 'bid', 0)),
            'ask': float(getattr(quote, 'ask', 0)),
        }
    
    def _detect_signals(self, symbol: str, data: Dict, 
                        timestamp: datetime) -> list:
        """
        检测策略信号
        返回信号列表（可能同时触发多个信号）
        """
        signals = []
        time_str = data['timestamp']
        
        # ========== 策略1: IV 飙升 ==========
        iv = data['implied_volatility']
        hv = data['historical_volatility']
        
        if hv > 0 and iv > hv * 1.5:  # IV 超过 HV 50%
            signals.append({
                "symbol": symbol,
                "type": "IV_SPIKE",
                "value": round(iv, 2),
                "threshold": round(hv * 1.5, 2),
                "timestamp": time_str,
                "details": f"IV: {iv}%, HV: {hv}%",
                "priority": "high" if iv > hv * 2 else "medium"
            })
        elif iv > 100:  # 绝对阈值：IV > 100%
            signals.append({
                "symbol": symbol,
                "type": "IV_SPIKE",
                "value": round(iv, 2),
                "threshold": 100,
                "timestamp": time_str,
                "details": f"IV飙升至 {iv}%",
                "priority": "high"
            })
        
        # ========== 策略2: 量能异常 (Smart Money) ==========
        volume = data['volume']
        oi = data['open_interest']
        
        if oi > 10:
            volume_oi_ratio = volume / oi if oi > 0 else 0
            
            if volume > oi * 0.5:  # 成交量 > 50% 持仓量（非常异常）
                signals.append({
                    "symbol": symbol,
                    "type": "SMART_MONEY_VOLUME",
                    "value": volume,
                    "threshold": int(oi * 0.5),
                    "timestamp": time_str,
                    "details": f"成交量{volume} > OI*{volume_oi_ratio:.0%}",
                    "priority": "high"
                })
            elif volume > oi * 0.20:  # 原策略：> 20%
                signals.append({
                    "symbol": symbol,
                    "type": "VOLUME_SPIKE",
                    "value": volume,
                    "threshold": int(oi * 0.20),
                    "timestamp": time_str,
                    "details": f"Vol: {volume}, OI: {oi}",
                    "priority": "medium"
                })
        
        # ========== 策略3: Delta 突破 0.5 (ITM 转化) ==========
        delta = data['delta']
        underlying = data['underlying_symbol']
        
        # 如果 API 没有返回 Delta，尝试计算
        if (delta is None or str(delta) in ['nan', 'N/A']) and underlying:
            delta = self._calculate_delta(data)
        
        if delta and abs(float(delta)) > 0.5:
            # 判断方向
            direction = "看涨" if float(delta) > 0 else "看跌"
            signals.append({
                "symbol": symbol,
                "type": "DELTA_ITM_CROSS",
                "value": round(float(delta), 3),
                "threshold": 0.5,
                "timestamp": time_str,
                "details": f"深度{direction}ITM, Delta={delta}",
                "priority": "medium"
            })
        
        # ========== 策略4: 买卖价差异常 (流动性风险) ==========
        bid = data['bid']
        ask = data['ask']
        last = data['last_price']
        
        if bid > 0 and ask > 0 and last > 0:
            spread_pct = (ask - bid) / last
            if spread_pct > 0.05:  # 价差 > 5%
                signals.append({
                    "symbol": symbol,
                    "type": "WIDE_SPREAD",
                    "value": round(spread_pct * 100, 2),
                    "threshold": 5.0,
                    "timestamp": time_str,
                    "details": f"Bid={bid}, Ask={ask}, Spread={spread_pct:.1%}",
                    "priority": "low"
                })
        
        return signals
    
    def _calculate_delta(self, data: Dict) -> Optional[float]:
        """计算 Delta（当 API 未提供时）"""
        try:
            underlying_symbol = data['underlying_symbol']
            underlying_price = self.underlying_prices.get(underlying_symbol)
            
            if not underlying_price or not data['strike_price'] or not data['expiry_date']:
                return None
            
            expiry = datetime.strptime(str(data['expiry_date']), "%Y-%m-%d")
            time_to_expiry = (expiry - datetime.now()).days / 365.0
            
            if time_to_expiry <= 0:
                return None
            
            # 判断期权类型
            option_type = "call"  # 默认
            symbol = data['symbol']
            if ".P." in symbol or "PUT" in symbol.upper():
                option_type = "put"
            
            iv_decimal = data['implied_volatility'] / 100.0 if data['implied_volatility'] > 1 else data['implied_volatility']
            
            delta = calculate_black_scholes(
                S=underlying_price,
                K=data['strike_price'],
                T=time_to_expiry,
                r=self.risk_free_rate,
                sigma=iv_decimal,
                option_type=option_type
            )
            
            return delta
            
        except Exception as e:
            logger.warning(f"Delta calculation failed: {e}")
            return None
    
    def _should_analyze_realtime(self, symbol: str, signal: Dict, 
                                  timestamp: datetime) -> bool:
        """
        判断是否应该进行实时分析
        
        条件：
        1. 高优先级信号 或 IV 大幅飙升
        2. 冷却期已过
        """
        # 优先级判断
        priority = signal.get('priority', 'low')
        signal_type = signal['type']
        
        # 只有高/中优先级才实时分析
        if priority not in ['high', 'medium']:
            return False
        
        # IV 飙升超过 2 倍，强制分析
        if signal_type == 'IV_SPIKE':
            iv = signal['value']
            threshold = signal['threshold']
            if iv > threshold * 1.5:  # IV 远超阈值
                priority = 'high'
        
        # 检查冷却期
        last_time = self.last_signal_time.get(symbol)
        if last_time:
            elapsed = timestamp - last_time
            if elapsed < self.signal_cooldown:
                logger.debug(f"Signal cooldown active for {symbol}: {elapsed}")
                return False
        
        return True
    
    async def stop(self):
        """停止监控"""
        self._is_running = False
        logger.info(f"📊 Monitor stopped. Signals today: {self.signals_today}, Analyses: {self.analyses_today}")
    
    def get_stats(self) -> Dict:
        """获取监控统计"""
        return {
            'signals_today': self.signals_today,
            'analyses_today': self.analyses_today,
            'monitored_options': len(self.monitored_options),
            'cache_size': len(self.option_cache)
        }


# 全局实例
enhanced_option_monitor = EnhancedOptionMonitor()
