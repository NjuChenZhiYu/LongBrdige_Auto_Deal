[English](README.md) | [中文](README_zh.md)

# LongBridge Auto Deal: US & HK Stock & Options Real-time Monitoring System

An industrial-grade real-time monitoring and analysis system for US and HK stocks & options, built on the LongPort SDK and Futu OpenD. This project adopts a modular architecture and supports real-time market data subscription, strategy analysis, multi-channel alerts, and LLM-powered smart market reports.

## Table of Contents

*   [Core Features](#core-features)
    *   [1. Dual Market Real-time Monitoring System](#1-dual-market-real-time-monitoring-system)
    *   [2. LLM Smart Reports (AI Analyst)](#2-llm-smart-reports-ai-analyst)
    *   [3. Refined Alert Strategy](#3-refined-alert-strategy)
    *   [4. Industrial-grade Engineering Design](#4-industrial-grade-engineering-design)
*   [Directory Structure](#directory-structure)
*   [Quick Start](#quick-start)
    *   [1. Environment Preparation](#1-environment-preparation)
    *   [2. Configuration (Security Warning)](#2-configuration-security-warning)
    *   [3. Run](#3-run)
*   [Testing](#testing)

## Core Features

### 1. Dual Market Real-time Monitoring System
*   **US Market**: Based on **LongPort SDK**, providing millisecond-level WebSocket market data subscriptions and options anomaly monitoring.
*   **HK Market**: Based on **Futu OpenD**, supporting automatic watchlist synchronization, real-time snapshot polling, and state caching.
*   **Independent Frontend Dashboards**: Offers separate monitoring pages for US and HK markets, supporting **real-time sorting** (price change/volume), **dynamic threshold management**, and **manual trigger checks**.

### 2. LLM Smart Reports (AI Analyst)
*   **Dual-Engine Architecture**: Integrates **Google Gemini** (for US market/options) and **Kimi/Moonshot** (for HK market) large language models.
*   **Automated Daily Reports**: System automatically aggregates daily anomaly data to generate pre-market, mid-day, and post-market analysis reports.
*   **Interactive Generation**: The Web interface supports one-click manual triggering for report generation to analyze current market sentiment in real-time.
*   **Report Center**: Built-in historical report management with Markdown rich text rendering and persistent storage.

### 3. Refined Alert Strategy
*   **Channel Routing**:
    *   **DingTalk**: Receives US market anomalies, options signals, and system-level notifications.
    *   **Feishu**: Receives HK market anomalies and LLM market report pushes.
*   **Smart Deduplication**: Built-in signal recorder (`SignalRecorder`) to deduplicate the same type of signals for the same ticker within a trading day, preventing message spam.

### 4. Industrial-grade Engineering Design
*   **Hot Configuration Updates**: Supports dynamically adjusting monitoring thresholds via the Web interface or configuration files without restarting the service.
*   **High Availability**: Multi-process architecture isolates different market tasks, supporting automatic reconnection on disconnection and exponential backoff strategies.
*   **Security & Compliance**: Sensitive credentials (`.env`) are separated from business configurations, strictly adhering to security standards.

## Directory Structure

```
LongBridge_Auto_Deal/
├── config/             # Configuration management (sensitive & app configs)
│   ├── .env.example
│   ├── settings.py 
│   ├── longport_symbols.yaml # LongPort US/Options configs
│   └── futu_symbols.yaml     # Futu HK targets & threshold configs
├── src/
│   ├── api/            # External API wrappers
│   │   ├── longport/   # LongPort API core (pull, sub, push, etc.)
│   │   ├── futu/       # Futu API core (OpenD client, callbacks)
│   │   └── notification.py # Feishu/DingTalk alert modules
│   ├── services/       # Application service layer
│   │   ├── llm_analyst.py  # LLM report generation service
│   │   └── signal_recorder.py # Signal deduplication recorder
│   ├── monitor/        # Main monitoring loop & event dispatch
│   │   ├── base_monitor.py
│   │   ├── us_watchlist_monitor.py # US market monitor
│   │   ├── hk_watchlist_monitor.py # HK market monitor
│   │   ├── longport_task.py        # LongPort monitoring task
│   │   └── futu_task.py            # Futu monitoring task
│   └── utils/          # General utilities (logging, price calculation, etc.)
├── tests/              # Testing & validation scripts
├── docs/               # Detailed documentation
├── main.py             # Program entry point (multi-process start)
├── requirements.txt    # Dependency management
└── scripts/            # Startup & deployment scripts
```

## Quick Start

### 1. Environment Preparation
Ensure Python 3.8+ environment. A virtual environment is recommended:
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment (Linux/macOS)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration (Security Warning)
This project strictly follows security guidelines; sensitive information is not submitted to Git. Please follow these steps to configure:

1.  Copy the configuration template:
    ```bash
    # Recommended: create .env in the config directory
    cp config/.env.example config/.env
    ```

2.  Edit `config/.env` and fill in your LongBridge Token, Futu config, and Webhook addresses.

    > **Security Warning**:
    > *   The `config/.env` file is ignored by `.gitignore` and **will never** be committed to the remote repository.
    > *   Please ensure the `config/.env` file permissions on your server are set to 600 (read/write by owner only):
    >     ```bash
    >     chmod 600 config/.env
    >     ```

3.  **Futu OpenD Configuration** (Required for HK Market only):
    *   Install and start [Futu OpenD](https://www.futunn.com/download/OpenD).
    *   Configure `FUTU_HOST` and `FUTU_PORT` (default 11111) in `config/.env`.
    *   Ensure OpenD is logged in and the API listening port matches your configuration.

4.  **LLM Key Configuration** (Required for Smart Reports):
    *   Fill in `LLM_API_KEY` (Gemini) and `KIMI_API_KEY` (Moonshot) in `config/.env`.

### 3. Run

#### Windows (Recommended)
Use the PowerShell script to start all services with one click (no need to manually activate the virtual environment):
```powershell
# Start services (Monitor + Web)
./scripts/start_all.ps1

# Stop services
./scripts/stop_all.ps1
```

#### Linux/macOS
```bash
# Start services
./scripts/start_all.sh

# Stop services
./scripts/stop_all.sh
```

#### Run Manually (Development & Debugging)
If you want to manually run a single Python file, you need to activate the virtual environment first:
```bash
# Windows
venv\Scripts\activate
python main.py

# Linux/macOS
source venv/bin/activate
python main.py
```

For more deployment details, please refer to [docs/deploy.md](docs/deploy.md).

## Testing
Run unit tests to ensure everything is working correctly:
```bash
python -m unittest discover tests
```