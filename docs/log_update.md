# 日志系统优化设计文档 (Log Rotation Strategy)

## 1. 背景问题
当前系统的日志（如 `monitor.log` 和 `monitor_futu.log`）均采用标准的 `logging.FileHandler`。这种方式会将所有的日志内容无限追加到同一个文件中。由于监控系统是 7x24 小时持续运行的，随着时间的推移，日志文件体积会不断膨胀，最终可能导致服务器磁盘空间耗尽，并且在排查问题时打开超大日志文件也非常缓慢和困难。

## 2. 优化目标
*   **控制磁盘占用**：限制单一日志文件的最大体积，并且限制保留的历史日志总数。
*   **自动清理**：系统需自动清理过期或超出数量限制的旧日志，无需人工干预。
*   **便于排障**：最新的日志应保留在固定的文件名（如 `monitor.log`）中，旧日志按序号归档（如 `monitor.log.1`）。
*   **平滑迁移**：在现有代码架构下最小化修改，只调整 `logger.py` 中的 Handler 配置。

## 3. 技术方案

Python 的标准库 `logging.handlers` 提供了两种常用的日志滚动（Rotation）策略：
1.  **按时间滚动 (`TimedRotatingFileHandler`)**：每天/每小时生成一个新文件，保留最近 N 天。
2.  **按大小滚动 (`RotatingFileHandler`)**：当文件达到指定大小时，自动重命名归档，并创建新文件，保留最近 N 个文件。

**最终选择：按大小滚动 (`RotatingFileHandler`)**
理由：监控系统的日志产生速率在不同市场行情下差异巨大（例如开盘期间日志量极大，休盘期间几乎没有）。按时间滚动容易在异常情况下单日产生巨大的日志文件，而**按大小滚动**能够最严格地保证磁盘空间使用的上限，更适合对稳定性要求较高的交易监控系统。

### 3.1 核心参数设计
*   `maxBytes`: `10 * 1024 * 1024` (10 MB)。每个日志文件达到 10MB 后自动进行切分。
*   `backupCount`: `3`。系统最多保留 3 个旧的备份文件。
*   **容量估算**：单个日志系列（例如 `monitor.log`）的最大磁盘占用量将被严格限制在 `10MB * (1 + 3) = 40MB` 左右。

### 3.2 归档机制表现
当 `monitor.log` 达到 10MB 时：
1. 原有的 `monitor.log.3`（如果存在）将被删除。
2. 原有的 `monitor.log.2` 被重命名为 `monitor.log.3`。
3. ...以此类推...
4. 原有的 `monitor.log` 被重命名为 `monitor.log.1`。
5. 系统创建一个新的空 `monitor.log` 继续写入。

## 4. 实施步骤
1.  修改 `src/utils/logger.py` 文件。
2.  引入 `from logging.handlers import RotatingFileHandler`。
3.  将原有的 `logging.FileHandler` 替换为 `RotatingFileHandler`，并传入 `maxBytes` 和 `backupCount` 参数。
4.  确保日志统一输出到 `logs/` 目录下（如果尚未统一），以保持项目根目录的整洁。

## 5. 预期代码变更 (`src/utils/logger.py`)
```python
# 旧代码
# file_handler = logging.FileHandler(log_file, encoding='utf-8')

# 新代码
from logging.handlers import RotatingFileHandler

# maxBytes=10MB, backupCount=5
file_handler = RotatingFileHandler(
    log_file, 
    maxBytes=10 * 1024 * 1024, 
    backupCount=5, 
    encoding='utf-8'
)
```