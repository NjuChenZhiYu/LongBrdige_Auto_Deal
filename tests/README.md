# Tests Directory Structure

This directory contains all the tests and testing scripts for the project, organized by their purpose and scope.

## 📁 `tests/unit/`
Contains standard unit tests that test individual modules in isolation. They use Python's built-in `unittest` framework and typically mock external dependencies.
- **`api/`**: Tests for API integrations (`longport`, `notification`).
- **`monitor/`**: Tests for the monitoring logic (`market_routing`, `watchlist_monitor_logic`).
- **`analysis/`**: Tests for trading and analysis strategies (`strategy`).
- **`utils/`**: Tests for utility functions.

To run all unit tests:
```bash
python -m unittest discover tests/unit
```

## 📁 `tests/integration/`
Contains tests that verify the integration between different components or interact with live APIs (e.g., LongPort, Futu, Adanos, Feishu, DingTalk, LLM).
These tests usually don't mock the APIs and are used to verify the actual flow.
*Examples: `test_adanos.py`, `test_llm_us_report.py`, `verify_strategy_flow.py`*

## 📁 `tests/scripts/`
Contains utility and debugging scripts meant to be run manually. These scripts help inspect the environment, query real-time quotes, check system status, or start individual components for debugging.
*Examples: `check_futu_port.py`, `inspect_longport.py`, `debug_watchlist.py`*
