# Notification Rules and Configuration

This document outlines the notification rules for DingTalk (US Market) and Feishu (HK Market) alerts, including deduplication logic and triggering conditions.

## 1. Alert Channels

- **DingTalk (钉钉)**: Used for **US Market (美股)** alerts and **System** notifications.
  - **Webhook**: Configured in `.env` as `DINGTALK_WEBHOOK`.
  - **Security**: Uses HMAC-SHA256 signature with `DINGTALK_SECRET`.
  - **Keyword**: Alerts must contain the keyword (default: "告警") or be whitelisted.

- **Feishu (飞书)**: Used for **HK Market (港股)** alerts and **LLM Reports**.
  - **Webhook**: Configured in `.env` as `FEISHU_WEBHOOK`.
  - **Format**: Uses Feishu's interactive card/post format.
  - **Keyword**: Alerts usually contain "告警" or specific report titles.


## 3. Alert Triggering Conditions

### 3.1. Real-time Price Monitoring (Watchlist Monitor)

- **Source**: 
  - US Market: `src/monitor/watchlist_monitor.py`
  - HK Market: `src/monitor/futu_task.py` (via `callback.py`)
- **Behavior**:
  - **Monitoring**: Continuously checks price changes and spreads against thresholds.
  - **Action**: 
    - **HK Market**: Updates TinyDB cache (`data/futu_quotes.json`) for frontend display. Real-time data is **NOT** stored in the persistent database (queried from Futu API). Only daily anomalies from the scheduled report are saved to the persistent database. **Alert sending is DISABLED** (`send_alert=False` in `callback.py`).
    - **US Market**: Logs trigger conditions. **Alert sending is DISABLED** (default `send_alert=False` in `handle_watchlist_quote`).
  - **Reason**: Real-time alerts are disabled by default to prevent excessive notification spam during volatile market conditions.

### 3.2. Scheduled LLM Reports (Auto-Triggered)

- **Source**: `src/services/llm_analyst.py` (triggered by `src/web/app.py` scheduler).
- **US Market Report (Gemini)**:
  - **Schedule**: 
    - **22:50 CST** (Pre-market analysis, no DB save)
    - **07:50 CST** (Post-market analysis, saves to DB)
  - **Channel**: DingTalk (钉钉).
  - **Content**: AI analysis of US watchlist stocks exceeding thresholds.
- **HK Market Report (Kimi)**:
  - **Schedule**: 
    - **10:00 CST** (Morning analysis, no DB save)
    - **15:20 CST** (After-market analysis, saves to DB)
  - **Channel**: Feishu (飞书).
  - **Content**: AI analysis of HK stocks exceeding thresholds.

### 3.3. Manual Triggers (User Action)

Alerts can be manually triggered via the Web Dashboard buttons:

- **HK Market Page (`/hk_market`)**:
  - **"立即检查 (飞书推送)"**: Calls `/trigger_futu_check`. Checks current prices against thresholds and **SENDS** Feishu alerts for all matches.
  - **"生成港股研报"**: Calls `/api/reports/trigger/hk`. Generates and **SENDS** a full AI report to Feishu.

- **US Market Page (`/`)**:
  - **"立即检查"**: Calls `/trigger_check`. Checks current prices against thresholds and **SENDS** DingTalk alerts for all matches.
  - **"生成美股研报"**: Calls `/api/reports/trigger/us`. Generates and **SENDS** a full AI report to DingTalk.

### 3.4. Options Monitoring

- **Source**: `src/monitor/option_monitor.py`.
- **Triggers**: Large option trades, unusual IV, volume spikes.
- **Channel**: DingTalk.


