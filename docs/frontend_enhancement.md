# 前端增强任务：港股独立监控看板与动态管理

## 1. 核心目标
在现有 `Global_Quant_System` 基础上，增强前端展示能力，实现港股 (Futu) 与美股 (LongPort) 的界面解耦，并支持动态阈值与排序。

## 2. 功能需求 (Functional Requirements)
1. **独立标签页 (UI Routing)**:
   - 前端增加 "Hong Kong Market" 专属看板。
   - 数据源严格锁定为 `futu_symbols.yaml` 中的标的。
2. **实时排序功能 (Real-time Sorting)**:
   - 看板需显示：代码、名称、现价、涨跌额、涨跌幅、成交量。
   - 点击“涨跌幅”表头，支持在【升序 / 降序 / 默认】三种状态间切换。
3. **动态阈值管理 (Threshold Management)**:
   - 为港股看板增加“阈值设置”入口。
   - 允许用户为不同港股单独设置 `price_change_threshold` (涨跌幅预警线)。
   - 修改需同步至配置文件并即时生效。

## 3. 技术实现建议
- **数据后端**: `futu_task.py` 需将最新的快照存入内存数据库 (如 TinyDB 或 Redis)，方便前端高频读取排序结果。
- **状态同步**: 确保排序逻辑在前端完成（JS），以减轻 Python 后端进程的计算压力。