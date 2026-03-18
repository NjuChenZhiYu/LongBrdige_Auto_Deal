# 异动数据与研报持久化及前端管理规范 (Data Storage & UI Specs - v2)

## 1. 核心持久化策略 (Persistence Strategy)

系统需将底层的“异动快照”与顶层的“分析研报”采取两种不同的持久化策略：

* **异动股票快照 (`anomaly_stocks`) -> 状态覆盖 (Upsert)**：
  * 策略：同一交易日内，同一只股票（如 `HK.00700`）只保留一条最新的异动数据。
  * 目的：防止数据库充斥着同一天内某只股票同一价位的冗余快照，保持当日数据的最新鲜状态。
* **大模型研报 (`daily_reports`) -> 追加流水 (Append)**：
  * 策略：无论是定时任务（如 10:00、15:20）触发，还是用户通过前端 API **手动触发**，生成的研报都作为一条**全新**的记录追加写入数据库。
  * 目的：保留一天内不同时间点的投研分析轨迹（例如，保留早盘的分析与尾盘的分析进行对比）。

## 2. 数据库设计与操作规范 (Database Schema & SQL Logic)

### 2.1 表 A：`anomaly_stocks` (异动标的明细表)
采用 `UNIQUE(report_date, symbol)` 联合唯一索引实现同日更新。

| 字段名 | 数据类型 | 说明 / 示例 |
| :--- | :--- | :--- |
| `id` | INTEGER | 主键，自增 |
| `report_date` | DATE | 报告归属日期 (YYYY-MM-DD) |
| `market` | VARCHAR(10) | `HK` 或 `US` |
| `symbol` | VARCHAR(20) | 股票代码  |
| `name` | VARCHAR(20) | 股票名称 |
| `price` | REAL | 触发时的现价 |
| `change_pct` | REAL | 涨跌幅数值 |
| `flow_label` | VARCHAR(50) | 量化研判标签 (如 `【主力抢筹 / 主升浪】`) |
| `smart_net` | REAL | 主力净流入金额 (万) |
| `retail_net` | REAL | 散户净流入金额 (万) |
| `updated_at` | DATETIME | 最后一次更新此条记录的精确时间 |

* **写入语法 (Trae 必须使用)**：
  ```sql
  INSERT OR REPLACE INTO anomaly_stocks 
  (report_date, market, symbol, name, price, change_pct, flow_label, smart_net, retail_net, updated_at) 
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  ```

### 2.2 表 B：`daily_reports` (大模型研报流水表)
取消同日唯一限制，允许同一天存在多份研报。

| 字段名 | 数据类型 | 说明 / 示例 |
| :--- | :--- | :--- |
| `id` | INTEGER | 主键，自增 |
| `report_date` | DATE | 报告归属日期 (YYYY-MM-DD) |
| `market` | VARCHAR(10) | `HK` 或 `US` |
| `trigger_type` | VARCHAR(20) | 触发方式：CRON (定时) 或 MANUAL (手动) |
| `report_content`| TEXT | 大模型生成的完整 Markdown 研报正文 |
| `created_at` | DATETIME | 记录写入的精确时间 |

* **写入语法 (Trae 必须使用)**：
```sql
INSERT INTO daily_reports 
(report_date, market, trigger_type, report_content, created_at) 
VALUES (?, ?, ?, ?, ?)
```

### 3.1 研报展示 API
* **`GET /api/reports`**：分页获取历史研报列表。
  * **返回结构**：`[{ "id": 1, "date": "2026-03-10", "market": "HK", "content": "...", "created_at": "..." }]`
  * 前端据此渲染研报列表（显示时间和内容）。

### 3.2 研报删除 API
* **`DELETE /api/reports/{id}`**：根据 ID 删除指定的研报。
  * 需在数据库中执行 `DELETE FROM daily_reports WHERE id = ?`，并返回成功状态码 `200`。


##  4. **改造定时任务 (`scheduler.add_job`)**： 在#app.py 中
   * 在调用的任务函数中增加一个布尔参数 `save_to_db=False`。
   * 对于 `hour=10, minute=0` (HK) 和 `hour=22, minute=50` (US) 的任务，保持 `save_to_db=False`（仅推送）。
   * 对于 `hour=15, minute=20` (HK) 和 `hour=7, minute=50` (US) 的任务，传入 `save_to_db=True`（推送并落库）。