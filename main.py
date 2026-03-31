import multiprocessing
import time
import os
import sys
import logging

# Ensure project root is in path
sys.path.append(os.getcwd())

# setup_logger function has been migrated to src/utils/logger.py

def start_longport_process():
    try:
        # Re-configure logging for this process
        from src.utils.logger import setup_logger
        logger = setup_logger("LongPort", "logs/longport_monitor.log")
        logger.info(f"Initializing LongPort Monitor... Executable: {sys.executable}")
        logger.info(f"Sys Path: {sys.path}")
        
        from src.monitor.longport_task import run_monitor
        run_monitor()
    except Exception as e:
        if 'logger' in locals():
            logger.error(f"LongPort Process Error: {e}", exc_info=True)
        else:
            print(f"LongPort Process Error: {e}")
            import traceback
            traceback.print_exc()

def start_futu_process():
    try:
        # Re-configure logging for this process
        from src.utils.logger import setup_logger
        logger = setup_logger("Futu", "logs/futu_monitor.log")
        logger.info(f"Initializing Futu Monitor... Executable: {sys.executable}")
        logger.info(f"Sys Path: {sys.path}")
        
        from src.monitor.futu_task import run_futu_monitor
        run_futu_monitor()
    except Exception as e:
        if 'logger' in locals():
            logger.error(f"Futu Process Error: {e}", exc_info=True)
        else:
            print(f"Futu Process Error: {e}")
            import traceback
            traceback.print_exc()

def start_web_server():
    try:
        # Re-configure logging for this process
        logger = setup_logger("Web", "logs/web_server.log")
        logger.info(f"Initializing Web Server... Executable: {sys.executable}")
        
        from src.web.app import app
        # Disable reloader to prevent multiple processes issues
        app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
    except Exception as e:
        if 'logger' in locals():
            logger.error(f"Web Server Error: {e}", exc_info=True)
        else:
            print(f"Web Server Error: {e}")
            import traceback
            traceback.print_exc()

def main():
    # Setup Main logger
    if not os.path.exists("logs"):
        os.makedirs("logs")
        
    logger = setup_logger("Main", "logs/main_process.log")
    logger.info(f"Starting Multi-Market Quantitative System (PID: {os.getpid()})")
    
    processes = {}

    def spawn_process(name, target):
        p = multiprocessing.Process(target=target, name=name)
        p.start()
        processes[name] = p
        logger.info(f"Started process: {name} (PID: {p.pid})")
        return p

    # Start processes
    processes["LongPortMonitor"] = spawn_process("LongPortMonitor", start_longport_process)
    processes["FutuMonitor"] = spawn_process("FutuMonitor", start_futu_process)
    processes["WebDashboard"] = spawn_process("WebDashboard", start_web_server)
    
    try:
        while True:
            time.sleep(5)
            # Check if processes are alive
            for name, p in list(processes.items()):
                if not p.is_alive():
                    logger.warning(f"Process {name} died (Exit Code: {p.exitcode})! Restarting...")
                    # Re-spawn
                    if name == "LongPortMonitor":
                        processes[name] = spawn_process(name, start_longport_process)
                    elif name == "FutuMonitor":
                        processes[name] = spawn_process(name, start_futu_process)
                    elif name == "WebDashboard":
                        processes[name] = spawn_process(name, start_web_server)
                        
    except KeyboardInterrupt:
        logger.info("Stopping all processes...")
        for name, p in processes.items():
            if p.is_alive():
                logger.info(f"Terminating {name}...")
                p.terminate()
                p.join()
        logger.info("All processes stopped.")
        sys.exit(0)

if __name__ == "__main__":
    # Windows support for multiprocessing
    multiprocessing.freeze_support()
    main()
