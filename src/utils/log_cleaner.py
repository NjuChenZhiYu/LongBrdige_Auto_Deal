import os
import glob
import time
import logging

logger = logging.getLogger(__name__)

LOG_RETENTION_DAYS = 7
LOG_PATTERNS = ("*.log", "*.log.*", "*.out.log", "*.err.log")


def _cleanup_files(log_dir, patterns, days_to_keep):
    """
    清理指定目录中超过保留期的日志文件。
    默认只保留最近 `days_to_keep` 天的日志。
    """
    try:
        if not os.path.exists(log_dir):
            logger.info(f"Log directory does not exist: {log_dir}. Skipping cleanup.")
            return 0, 0

        current_time = time.time()
        cutoff_time = current_time - (days_to_keep * 24 * 3600)
        deleted_count = 0
        freed_space = 0

        for pattern in patterns:
            search_path = os.path.join(log_dir, "**", pattern)
            for file_path in glob.glob(search_path, recursive=True):
                if os.path.isfile(file_path):
                    file_mtime = os.path.getmtime(file_path)
                    if file_mtime < cutoff_time:
                        try:
                            file_size = os.path.getsize(file_path)
                            os.remove(file_path)
                            deleted_count += 1
                            freed_space += file_size
                            logger.debug(f"Deleted old log: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to delete log {file_path}: {e}")

        return deleted_count, freed_space
    except Exception as e:
        logger.error(f"Error during log cleanup: {e}")
        return 0, 0


def clean_project_logs(days_to_keep=LOG_RETENTION_DAYS):
    """清理项目 logs/ 目录，仅保留最近 `days_to_keep` 天的日志。"""
    log_dir = os.path.join(os.getcwd(), "logs")
    deleted_count, freed_space = _cleanup_files(log_dir, LOG_PATTERNS, days_to_keep)

    if deleted_count > 0:
        logger.info(
            f"Cleaned up {deleted_count} old project logs. "
            f"Freed {freed_space / (1024 * 1024):.2f} MB."
        )
    else:
        logger.info("No old project logs found to clean.")


def clean_futu_logs(days_to_keep=LOG_RETENTION_DAYS):
    """
    清理 FutuOpenD 产生的底层 C++ / Python SDK 日志文件。
    保留该函数名以兼容现有调用。
    """
    log_dir = os.path.join(os.getcwd(), "logs", "futu_appdata", "com.futunn.FutuOpenD", "Log")
    deleted_count, freed_space = _cleanup_files(log_dir, ("py_*.log*", "*.log"), days_to_keep)

    if deleted_count > 0:
        logger.info(
            f"Cleaned up {deleted_count} old Futu logs. "
            f"Freed {freed_space / (1024 * 1024):.2f} MB."
        )
    else:
        logger.info("No old Futu logs found to clean.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    clean_project_logs(LOG_RETENTION_DAYS)