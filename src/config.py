import os

try:
    from dotenv import load_dotenv
    # Load environment variables from config/.env file
    # Priority: config/.env > .env > system env
    
    # 1. Try loading from config/.env
    config_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", ".env")
    if os.path.exists(config_env_path):
        load_dotenv(config_env_path)
    else:
        # 2. Fallback to default .env
        load_dotenv()
except ImportError:
    # If python-dotenv is not installed, assume environment variables are set manually
    pass

class Config:
    # LongBridge API
    # Support both new LONGPORT_ prefix (recommended) and old LB_ prefix
    LB_APP_KEY = os.getenv("LONGPORT_APP_KEY") or os.getenv("LB_APP_KEY")
    LB_APP_SECRET = os.getenv("LONGPORT_APP_SECRET") or os.getenv("LB_APP_SECRET")
    LB_ACCESS_TOKEN = os.getenv("LONGPORT_ACCESS_TOKEN") or os.getenv("LB_ACCESS_TOKEN")

    # Alert Webhooks
    FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK")
    DINGTALK_WEBHOOK = os.getenv("DINGTALK_WEBHOOK")

    # Monitoring
    _symbols_str = os.getenv("MONITOR_SYMBOLS", "")
    MONITOR_SYMBOLS = [s.strip() for s in _symbols_str.split(",") if s.strip()]

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
        if not cls.LB_APP_KEY: missing.append("LB_APP_KEY")
        if not cls.LB_APP_SECRET: missing.append("LB_APP_SECRET")
        if not cls.LB_ACCESS_TOKEN: missing.append("LB_ACCESS_TOKEN")
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
        if not cls.MONITOR_SYMBOLS:
            print("Warning: No symbols configured for monitoring (MONITOR_SYMBOLS is empty)")
