#!/usr/bin/env python3
"""
启动增强版期权监控 + Kimi 实时分析
Start Enhanced Option Monitor with Kimi Real-time Analysis
"""

import asyncio
import signal
import sys
from datetime import datetime
from src.monitor.enhanced_option_monitor import enhanced_option_monitor
from src.services.kimi_option_analyzer import kimi_analyzer
from src.utils.logger import logger


async def daily_summary_task():
    """
    每日收盘后推送汇总报告
    美股收盘时间：北京时间 次日 4:00 AM（夏令时）/ 5:00 AM（冬令时）
    """
    while True:
        now = datetime.now()
        
        # 美股收盘时间（北京时间）
        # 夏令时 4:00, 冬令时 5:00
        # 这里使用 4:30 作为报告时间（留 30 分钟缓冲）
        target_hour, target_minute = 4, 30
        
        # 计算下次报告时间
        if now.hour < target_hour or (now.hour == target_hour and now.minute < target_minute):
            # 今天还没推送
            next_run = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
        else:
            # 明天推送
            from datetime import timedelta
            next_run = (now + timedelta(days=1)).replace(
                hour=target_hour, minute=target_minute, second=0, microsecond=0
            )
        
        wait_seconds = (next_run - now).total_seconds()
        logger.info(f"📅 Next daily summary scheduled at {next_run} (in {wait_seconds/3600:.1f} hours)")
        
        await asyncio.sleep(wait_seconds)
        
        # 推送日终报告
        try:
            logger.info("📊 Generating daily summary report...")
            await kimi_analyzer.push_daily_summary()
        except Exception as e:
            logger.error(f"Daily summary failed: {e}")


async def main():
    """主函数"""
    logger.info("🚀 Starting LongBridge Enhanced Option Monitor with Kimi AI...")
    
    # 启动监控
    await enhanced_option_monitor.start()
    
    # 启动日终报告任务
    summary_task = asyncio.create_task(daily_summary_task())
    
    # 设置信号处理
    stop_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        stop_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 保持运行
    try:
        while not stop_event.is_set():
            # 每 60 秒打印一次状态
            await asyncio.sleep(60)
            stats = enhanced_option_monitor.get_stats()
            logger.info(f"📈 Monitor Stats: {stats}")
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("🛑 Shutting down...")
        await enhanced_option_monitor.stop()
        summary_task.cancel()
        try:
            await summary_task
        except asyncio.CancelledError:
            pass
        logger.info("✅ Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bye!")
        sys.exit(0)
