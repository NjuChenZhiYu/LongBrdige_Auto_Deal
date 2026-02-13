import asyncio
import signal
from src.monitor.core import Monitor
from src.utils.logger import logger
from config.settings import Settings

async def main():
    logger.info("Starting LongBridge Auto Deal System...")
    
    # Validate configuration
    try:
        Settings.validate()
    except ValueError as e:
        logger.error(f"Configuration Error: {e}")
        return

    # Initialize Monitor
    monitor = Monitor()
    
    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def signal_handler():
        logger.info("Shutdown signal received")
        stop_event.set()
        
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGINT/SIGTERM in some cases
            pass

    # Start monitoring
    try:
        await monitor.start()
        # Keep running until stop signal
        # Note: In a real asyncio app, monitor.start() might be a long-running task 
        # or we wait on the stop_event while the monitor runs in background tasks.
        # Here assuming monitor.start() enters the main loop or sets up callbacks.
        # If monitor.start() returns immediately after setup:
        logger.info("Monitor started. Press Ctrl+C to stop.")
        
        # On Windows, we might need a loop to check for interrupts if signal handlers fail
        while not stop_event.is_set():
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"Runtime error: {e}")
    finally:
        logger.info("Shutting down...")
        # Add cleanup logic here if needed

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
