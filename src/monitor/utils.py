import logging
import datetime
from typing import Dict, Tuple, Optional
from src.api.dingtalk import DingTalkAlert
from src.api.feishu import FeishuAlert
from src.services.signal_recorder import signal_recorder

logger = logging.getLogger(__name__)

async def handle_quote_alert(
    symbol: str, 
    last_price: float, 
    prev_close: float, 
    threshold_config: Dict, 
    market_type: str = "US",
    send_alert: bool = False,
    volume: int = 0,
    turnover: float = 0.0
) -> Tuple[bool, Dict]:
    """
    Generic handler for quote alerts with LLM analysis. Checks thresholds and sends alerts if triggered.
    Records alert to SignalRecorder for daily report generation.
    
    :param symbol: Stock symbol (e.g., 'AAPL', 'HK.00700')
    :param last_price: Current price
    :param prev_close: Previous closing price
    :param threshold_config: Configuration for thresholds (e.g., {'price_change': 2.0})
    :param market_type: Market identifier for the alert message (e.g., 'US', 'HK')
    :param send_alert: Whether to actually send the alert
    :param volume: Trading volume
    :param turnover: Trading turnover
    :return: (triggered, alert_data)
    """
    triggered = False
    alert_data = {}
    current_time_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        if prev_close > 0:
            change_rate = ((last_price - prev_close) / prev_close) * 100
            
            # Get threshold from config or default (2.0% as a fallback default)
            price_change_threshold = threshold_config.get('price_change', 2.0)
            
            if abs(change_rate) >= price_change_threshold:
                direction = "涨" if change_rate > 0 else "跌"
                market_name = "美股" if market_type == "US" else "港股" if market_type == "HK" else market_type
                
                # Record alert to SignalRecorder for daily report
                signal_recorder.add_stock_alert({
                    "symbol": symbol,
                    "market_type": market_type,
                    "last_price": last_price,
                    "change_rate": change_rate,
                    "volume": volume,
                    "turnover": turnover,
                    "timestamp": current_time_str
                })
                
                # LLM analysis for individual stocks is DEPRECATED/REMOVED to prevent token burnout.
                # Only basic alerts are sent if send_alert is True.
                
                title = f"[{market_type} Alert] {symbol} {direction}幅≥{price_change_threshold}%"
                content = f"""### {market_name}价格异动告警
* **标的**：{symbol}
* **最新价**：{last_price}
* **涨跌幅**：{change_rate:.2f}% (昨收：{prev_close})
* **触发规则**：{direction}幅≥{price_change_threshold}%
* **更新时间**：{current_time_str}
* **Keywords**: {market_type}, Alert, {market_name}, 监控, 告警
"""
                
                # Asynchronous alert sending
                reason_suffix = "rise" if change_rate > 0 else "fall"
                
                if send_alert:
                    if market_type == "HK":
                        # Use Feishu for HK market
                        feishu_content = f"{content}\n\n[Feishu Alert Channel]"
                        await FeishuAlert.send_alert(title, feishu_content)
                        logger.info(f"Feishu alert sent for {symbol}: {change_rate:.2f}%")
                    else:
                        # Use DingTalk for other markets (US)
                        await DingTalkAlert.send_alert(title, content, symbol, f"price_change_{reason_suffix}")
                        logger.info(f"DingTalk alert sent for {symbol}: {change_rate:.2f}%")
                else:
                    logger.info(f"Alert condition met for {symbol} ({change_rate:.2f}%), but sending skipped (send_alert=False)")
                    
                triggered = True
                alert_data['price_change'] = change_rate
                # alert_data['llm_analysis'] = llm_analysis # Removed
                
    except Exception as e:
        logger.error(f"Error in handle_quote_alert for {symbol}: {e}")
        return False, {}

    return triggered, alert_data
