import signal
import sys
from src.utils.logger import setup_logger
from src.monitor.core import MonitorSystem

def main():
    # Initialize Logger
    setup_logger("root", log_file="monitor.log")
    
    # Initialize and start monitor
    monitor = MonitorSystem()
    
    # Handle signals for graceful shutdown
    signal.signal(signal.SIGINT, monitor.stop)
    signal.signal(signal.SIGTERM, monitor.stop)
    
    monitor.start()

if __name__ == "__main__":
    main()
