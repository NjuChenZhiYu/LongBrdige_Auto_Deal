
import logging
from futu import OpenQuoteContext, SysConfig

logger = logging.getLogger(__name__)

class FutuClient:
    _instance = None
    _quote_ctx = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FutuClient, cls).__new__(cls)
        return cls._instance

    def get_quote_context(self, host="127.0.0.1", port=11111):
        """Get or create OpenQuoteContext singleton"""
        if self._quote_ctx is None or not self._quote_ctx.status: # Check if connected
            try:
                logger.info(f"Initializing Futu OpenQuoteContext at {host}:{port}...")
                # SysConfig.set_all_thread_daemon(True) # Optional: set daemon threads
                self._quote_ctx = OpenQuoteContext(host=host, port=port)
                self._quote_ctx.start() # Ensure it's started if needed, though init usually starts it
                logger.info("Futu OpenQuoteContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Futu OpenQuoteContext: {e}")
                raise
        return self._quote_ctx

    def subscribe(self, symbols, sub_types, is_first_push=True):
        """
        Subscribe with market routing and permission isolation.
        Only allows HK symbols (starting with 'HK.').
        """
        if not self._quote_ctx:
            logger.error("Futu OpenQuoteContext not initialized")
            return -1, "Context not initialized"

        # 1. Market Routing / Permission Isolation
        valid_symbols = []
        for s in symbols:
            # Handle "Code Name" format from yaml
            code = s.split(' ')[0] if ' ' in s else s
            
            if code.startswith("HK."):
                valid_symbols.append(code)
            else:
                logger.warning(f"Market Routing: Symbol {s} excluded from Futu subscription (Non-HK market)")
        
        if not valid_symbols:
            logger.warning("No valid HK symbols to subscribe")
            return 0, "No valid symbols"

        # 2. Subscribe with Exception Handling
        try:
            ret, data = self._quote_ctx.subscribe(valid_symbols, sub_types, is_first_push=is_first_push)
            
            # Check for specific error codes if ret != RET_OK
            # However, Futu SDK returns ret code. 
            # 104: No Permission, 105: Quota Limit
            # But usually ret is RET_ERROR (-1) and data is error msg.
            # We rely on ret code here.
            return ret, data
        except Exception as e:
            logger.error(f"Futu subscribe error: {e}")
            # Don't crash the process
            return -1, str(e)

    def get_hk_user_securities(self, group_name="全部"):
        """
        Get user's self-selected stocks (User Security) for HK market.
        Returns a list of HK stock codes.
        """
        if not self._quote_ctx:
            logger.error("Futu OpenQuoteContext not initialized")
            return []

        try:
            # Get user security list
            ret, data = self._quote_ctx.get_user_security(group_name)
            if ret != 0:
                logger.error(f"Failed to get user security: {data}")
                return []
            
            # data is a DataFrame with 'code', 'name', 'stock_type' columns
            # Filter for HK stocks
            hk_symbols = []
            for _, row in data.iterrows():
                code = row['code']
                name = row['name']
                if code.startswith("HK."):
                    hk_symbols.append(f"{code} {name}")
            
            logger.info(f"Retrieved {len(hk_symbols)} HK symbols from user security group '{group_name}'")
            return hk_symbols
            
        except Exception as e:
            logger.error(f"Error getting user security: {e}")
            return []

    def close(self):
        if self._quote_ctx:
            logger.info("Closing Futu OpenQuoteContext...")
            self._quote_ctx.close()
            self._quote_ctx = None

futu_client = FutuClient()
