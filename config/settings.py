import os
import yaml

try:
    from dotenv import load_dotenv
    # Load environment variables from config/.env file
    # Priority: config/.env > .env > system env
    
    # 1. Try loading from config/.env
    # This file is located at config/settings.py, so .env is in the same directory
    config_dir = os.path.dirname(os.path.abspath(__file__))
    config_env_path = os.path.join(config_dir, ".env")
    
    if os.path.exists(config_env_path):
        print(f"Loading configuration from: {config_env_path}")
        load_dotenv(config_env_path, override=True)
    else:
        # 2. Fallback to default .env in root
        root_env_path = os.path.join(os.path.dirname(config_dir), ".env")
        if os.path.exists(root_env_path):
            print(f"Loading configuration from: {root_env_path}")
            load_dotenv(root_env_path, override=True)
        else:
            print("Warning: No .env file found in config/ or root directory.")

except ImportError:
    print("Warning: python-dotenv not installed. Relying on system environment variables.")


class Settings:
    # LongBridge API
    LONGPORT_APP_KEY = os.getenv("LONGPORT_APP_KEY") or os.getenv("LB_APP_KEY")
    LONGPORT_APP_SECRET = os.getenv("LONGPORT_APP_SECRET") or os.getenv("LB_APP_SECRET")
    LONGPORT_ACCESS_TOKEN = os.getenv("LONGPORT_ACCESS_TOKEN") or os.getenv("LB_ACCESS_TOKEN")
    LONGPORT_WS_URL = os.getenv("LONGPORT_WS_URL", "wss://openapi.longportapp.com/v1/quote/ws")

    # Alert Webhooks
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "").strip()
    FEISHU_KEYWORD = os.getenv("FEISHU_KEYWORD", "告警").strip()
    FEISHU_ALERT_ENABLE = os.getenv("FEISHU_ALERT_ENABLE", "true").lower() == "true"
    DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK", "").strip()
    DINGTALK_KEYWORD = os.getenv("DINGTALK_KEYWORD", "告警").strip()
    DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "").strip()
    DINGTALK_ALERT_ENABLE = os.getenv("DINGTALK_ALERT_ENABLE", "true").lower() == "true"
    try:
        DINGTALK_RETRY_TIMES = int(os.getenv("DINGTALK_RETRY_TIMES", "3"))
    except ValueError:
        DINGTALK_RETRY_TIMES = 3
    try:
        DINGTALK_RETRY_INTERVAL = int(os.getenv("DINGTALK_RETRY_INTERVAL", "1"))
    except ValueError:
        DINGTALK_RETRY_INTERVAL = 1

    # Monitoring
    _symbols_str = os.getenv("MONITOR_SYMBOLS", "")
    MONITOR_SYMBOLS = [s.strip() for s in _symbols_str.split(",") if s.strip()]

    # Load symbols from yaml if available
    LONGPORT_SYMBOLS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "longport_symbols.yaml")
    FUTU_SYMBOLS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "futu_symbols.yaml")
    
    LONGPORT_SYMBOLS_CONFIG = {}
    FUTU_SYMBOLS_CONFIG = {}

    # Load LongPort Symbols
    if os.path.exists(LONGPORT_SYMBOLS_CONFIG_PATH):
        try:
            with open(LONGPORT_SYMBOLS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                LONGPORT_SYMBOLS_CONFIG = yaml.safe_load(f) or {}
                # Merge yaml symbols if env MONITOR_SYMBOLS is empty
                if not MONITOR_SYMBOLS and 'symbols' in LONGPORT_SYMBOLS_CONFIG:
                    MONITOR_SYMBOLS = LONGPORT_SYMBOLS_CONFIG['symbols']
        except Exception as e:
            print(f"Warning: Failed to load longport_symbols.yaml: {e}")

    # Load Futu Symbols
    if os.path.exists(FUTU_SYMBOLS_CONFIG_PATH):
        try:
            with open(FUTU_SYMBOLS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                FUTU_SYMBOLS_CONFIG = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to load futu_symbols.yaml: {e}")

    # Strategy Thresholds - Priority: longport_symbols.yaml > .env > default
    # Load from LONGPORT_SYMBOLS_CONFIG if available (Primary source for now)
    _yaml_thresholds = LONGPORT_SYMBOLS_CONFIG.get('thresholds', {})
    
    try:
        PRICE_CHANGE_THRESHOLD = float(_yaml_thresholds.get('price_change', 
            os.getenv("PRICE_CHANGE_THRESHOLD", "5.0")))
    except ValueError:
        PRICE_CHANGE_THRESHOLD = 5.0

    try:
        SPREAD_THRESHOLD = float(_yaml_thresholds.get('spread', 
            os.getenv("SPREAD_THRESHOLD", "0.05")))
    except ValueError:
        SPREAD_THRESHOLD = 0.05

    # Futu Configuration
    FUTU_HOST = os.getenv("FUTU_HOST", "127.0.0.1")
    FUTU_PORT = int(os.getenv("FUTU_PORT", "45575"))
    FUTU_PWD_UNLOCK = os.getenv("FUTU_PWD_UNLOCK")

    # Trading
    ENABLE_TRADING = os.getenv("ENABLE_TRADING", "false").lower() == "true"

    # Option Monitoring
    _options_str = os.getenv("MONITOR_OPTIONS", "")
    MONITORED_OPTIONS = [s.strip() for s in _options_str.split(",") if s.strip()]

    # LLM Configuration (Gemini for US)
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-pro")

    # Kimi Configuration (Moonshot for HK)
    KIMI_API_KEY = os.getenv("KIMI_API_KEY")
    KIMI_LLM_BASE_URL = os.getenv("KIMI_LLM_BASE_URL", "https://api.moonshot.cn/v1")
    KIMI_LLM_MODEL = os.getenv("KIMI_LLM_MODEL", "kimi-k2.5")

    # Adanos Sentiment API
    ADANOS_API_KEY = os.getenv("ADANOS_API_KEY")
