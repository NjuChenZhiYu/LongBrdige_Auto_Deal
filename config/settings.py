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
        load_dotenv(config_env_path)
    else:
        # 2. Fallback to default .env in root
        root_env_path = os.path.join(os.path.dirname(config_dir), ".env")
        load_dotenv(root_env_path)
except ImportError:
    # If python-dotenv is not installed, assume environment variables are set manually
    pass

class Settings:
    # LongBridge API
    LONGPORT_APP_KEY = os.getenv("LONGPORT_APP_KEY") or os.getenv("LB_APP_KEY")
    LONGPORT_APP_SECRET = os.getenv("LONGPORT_APP_SECRET") or os.getenv("LB_APP_SECRET")
    LONGPORT_ACCESS_TOKEN = os.getenv("LONGPORT_ACCESS_TOKEN") or os.getenv("LB_ACCESS_TOKEN")
    LONGPORT_WS_URL = os.getenv("LONGPORT_WS_URL", "wss://openapi.longportapp.com/v1/quote/ws")

    # Alert Webhooks
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
    DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK")

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

    # Strategy Thresholds
    try:
        PRICE_CHANGE_THRESHOLD = float(os.getenv("PRICE_CHANGE_THRESHOLD", "2.0"))
    except ValueError:
        PRICE_CHANGE_THRESHOLD = 2.0

    try:
        SPREAD_THRESHOLD = float(os.getenv("SPREAD_THRESHOLD", "0.05"))
    except ValueError:
        SPREAD_THRESHOLD = 0.05

    # Trading
    ENABLE_TRADING = os.getenv("ENABLE_TRADING", "false").lower() == "true"

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
