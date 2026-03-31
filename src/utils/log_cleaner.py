import os
import glob
import time
import logging

logger = logging.getLogger(__name__)

def clean_futu_logs(days_to_keep=5):
    """
    清理 FutuOpenD 产生的底层 C++ / Python SDK 日志文件。
    默认只保留最近 `days_to_keep` 天的日志。
    """
    try:
        # Futu logs directory setup in the project
        log_dir = os.path.join(os.getcwd(), "logs", "futu_appdata", "com.futunn.FutuOpenD", "Log")
        
        if not os.path.exists(log_dir):
            logger.info(f"Futu log directory does not exist: {log_dir}. Skipping cleanup.")
            return

        # Calculate the cutoff time
        current_time = time.time()
        cutoff_time = current_time - (days_to_keep * 24 * 3600)
        
        # Patterns for Futu logs (e.g., py_*.log*)
        patterns = ["py_*.log*", "*.log"]
        
        deleted_count = 0
        freed_space = 0
        
        for pattern in patterns:
            search_path = os.path.join(log_dir, pattern)
            for file_path in glob.glob(search_path):
                if os.path.isfile(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_time:
                        try:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            deleted_count += 1
                            freed_space += file_size
                            logger.debug(f"Deleted old Futu log: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete Futu log {file_path}: {e}")
                            
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old Futu logs. Freed {freed_space / (1024*1024):.2f} MB.")
        else:
            logger.info("No old Futu logs found to clean.")
            
    except Exception as e:
        logger.error(f"Error during Futu log cleanup: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    clean_futu_logs(5)