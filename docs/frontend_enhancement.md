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

## 4. 每日研报中心 (Daily Reports Center)

基于后端 `daily_reports` 存储的研报数据，为用户提供历史研报的查看与管理功能。

### 4.1 功能需求 (Functional Requirements)

1.  **研报列表 (Reports List)**:
    -   增加 **"Market Reports"** 专属导航入口。
    -   列表展示字段：
        -   **日期 (Date)**: `report_date` (YYYY-MM-DD)
        -   **时间 (Time)**: `created_at` (具体生成时间)
        -   **市场 (Market)**: 标签显示 `HK` (港股) 或 `US` (美股)
        -   **触发类型 (Type)**: `CRON` (定时) 或 `MANUAL` (手动)
        -   **摘要 (Summary)**: 截取研报正文前 50-100 字用于预览。
    -   **筛选与排序**:
        -   默认按生成时间倒序排列 (最新的在前)。
        -   提供按 **市场** (`All/HK/US`) 和 **日期** 的筛选器。

2.  **研报详情与渲染 (Detail View & Rendering)**:
    -   点击列表项，展开或弹窗显示完整研报内容。
    -   **Markdown 渲染**: 研报内容为 Markdown 格式，前端必须使用 Markdown 解析库（如 `marked.js`, `react-markdown` 等）进行富文本渲染，确保标题、加粗、列表、分割线等格式正确显示。

3.  **研报管理 (Management)**:
    -   **删除功能**: 每条研报提供“删除”按钮。
    -   **操作流程**: 点击删除 -> 弹出二次确认框 -> 确认后调用 API 删除 -> 刷新列表。

### 4.2 接口对接 (API Integration)

*   **获取列表**: `GET /api/reports?page=1&per_page=20&market=HK` (参数可选)
*   **删除研报**: `DELETE /api/reports/{id}`
