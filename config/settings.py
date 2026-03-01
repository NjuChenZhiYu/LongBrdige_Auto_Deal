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
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
    DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK")
    DINGTALK_SECRET = os.getenv("DINGTALK_SECRET")
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
    SYMBOLS_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "symbols.yaml")
    SYMBOLS_CONFIG = {}
    if os.path.exists(SYMBOLS_CONFIG_PATH):
        try:
            with open(SYMBOLS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                SYMBOLS_CONFIG = yaml.safe_load(f) or {}
                # Merge yaml symbols if env MONITOR_SYMBOLS is empty
                if not MONITOR_SYMBOLS and 'symbols' in SYMBOLS_CONFIG:
                    MONITOR_SYMBOLS = SYMBOLS_CONFIG['symbols']
        except Exception as e:
            print(f"Warning: Failed to load symbols.yaml: {e}")

    # Strategy Thresholds - Priority: symbols.yaml > .env > default
    # Load from symbols.yaml if available
    _yaml_thresholds = SYMBOLS_CONFIG.get('thresholds', {})
    
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

    # Trading
    ENABLE_TRADING = os.getenv("ENABLE_TRADING", "false").lower() == "true"

    # Option Monitoring
    _options_str = os.getenv("MONITOR_OPTIONS", "")
    MONITORED_OPTIONS = [s.strip() for s in _options_str.split(",") if s.strip()]

    # LLM Configuration
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4-turbo")

    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        missing = []
        if not cls.LONGPORT_APP_KEY: missing.append("LONGPORT_APP_KEY")
        if not cls.LONGPORT_APP_SECRET: missing.append("LONGPORT_APP_SECRET")
        if not cls.LONGPORT_ACCESS_TOKEN: missing.append("LONGPORT_ACCESS_TOKEN")
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
        if not cls.MONITOR_SYMBOLS:
            print("Warning: No symbols configured for monitoring (MONITOR_SYMBOLS is empty)")

# Alias for backward compatibility if needed, but prefer Settings
Config = Settings

# Debug: Print loaded configuration (masked)
print("-" * 30)
print("Configuration Loaded:")
print(f"LONGPORT_APP_KEY: {'*' * 8 if Settings.LONGPORT_APP_KEY else 'None'}")
print(f"LONGPORT_ACCESS_TOKEN: {'*' * 10 if Settings.LONGPORT_ACCESS_TOKEN else 'None'} (Length: {len(Settings.LONGPORT_ACCESS_TOKEN) if Settings.LONGPORT_ACCESS_TOKEN else 0})")
print(f"DINGTALK_WEBHOOK: {'*' * 20 if Settings.DINGTALK_WEBHOOK else 'None'}")
print(f"MONITOR_SYMBOLS: {Settings.MONITOR_SYMBOLS}")
print("-" * 30)
