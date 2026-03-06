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

## 2. Deduplication Logic (Updated)

As of the latest update, the **1-hour deduplication cache has been disabled** to ensure real-time alerting.

- **Previous Logic**: Same symbol + same reason within 1 hour (3600s) would be deduplicated (suppressed).
- **Current Logic**: 
  - `DEDUP_WINDOW_SECONDS` is set to `0`.
  - **All alerts are sent immediately** regardless of frequency, provided they meet the threshold conditions.
  - This applies to both DingTalk and Feishu.

## 3. Alert Triggering Conditions

### 3.1. Real-time Price Monitoring (Watchlist Monitor)

- **Source**: `src/monitor/watchlist_monitor.py` (US/LongPort) & `src/monitor/futu_monitor.py` (HK/Futu).
- **Triggers**:
  - **Price Change**: Triggers when price change percentage absolute value `>= PRICE_CHANGE_THRESHOLD` (default 5.0%).
  - **Spread**: Triggers when bid/ask spread exceeds `SPREAD_THRESHOLD` (if configured).
- **Process**:
  1. Market data push received.
  2. Check against thresholds.
  3. If threshold exceeded -> Send Alert (DingTalk for US, Feishu for HK).

### 3.2. Scheduled LLM Reports

- **Source**: `src/services/llm_analyst.py`.
- **US Market Report (Gemini)**:
  - **Schedule**: 22:50 CST (Pre-market), 07:50 CST (Post-market).
  - **Channel**: DingTalk.
  - **Content**: Analysis of watchlist stocks exceeding thresholds.
- **HK Market Report (Kimi)**:
  - **Schedule**: 10:00 CST (Morning), 15:20 CST (Afternoon).
  - **Channel**: Feishu.
  - **Content**: Analysis of HK stocks exceeding thresholds using Kimi LLM.

### 3.3. Options Monitoring

- **Source**: `src/monitor/option_monitor.py`.
- **Triggers**: Large option trades, unusual IV, volume spikes.
- **Channel**: DingTalk.

## 4. Troubleshooting

- **No Alerts?**
  - Check `.env` for valid Webhook URLs.
  - Verify `PRICE_CHANGE_THRESHOLD` is not too high.
  - Check logs (`logs/web.log`, `logs/monitor.log`) for API errors.
- **Too Many Alerts?**
  - Increase `PRICE_CHANGE_THRESHOLD`.
  - Re-enable deduplication by setting `DEDUP_WINDOW_SECONDS > 0` in `src/api/dingtalk.py` and `src/api/feishu.py`.
