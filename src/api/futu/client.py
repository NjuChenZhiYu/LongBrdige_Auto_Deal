
import logging
import pandas as pd
from futu import OpenQuoteContext, SysConfig
from config.settings import Settings

logger = logging.getLogger(__name__)

class FutuClient:
    _instance = None
    _quote_ctx = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FutuClient, cls).__new__(cls)
        return cls._instance

    def get_quote_context(self, host=None, port=None):
        """Get or create OpenQuoteContext singleton"""
        if host is None:
            host = Settings.FUTU_HOST
        if port is None:
            port = Settings.FUTU_PORT
            
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
        # Ensure context is initialized
        try:
            self.get_quote_context()
        except Exception:
            return []

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

    def get_threshold_quotes(self, threshold: float = 0.0) -> list:
        """
        Get real-time quotes for HK stocks from watchlist that exceed the threshold.
        This method is synchronous (blocking) because Futu API is blocking.
        Callers should use asyncio.to_thread if calling from an async loop.
        
        Args:
            threshold (float): Price change percentage threshold. Default 0.0.
            
        Returns:
            list: List of dicts with stock data [{'symbol':..., 'last_price':..., 'change_rate':...}]
        """
        try:
            # Get HK watchlist from Futu
            hk_securities = self.get_hk_user_securities("全部")
            if not hk_securities:
                logger.warning(f"No HK symbols in watchlist")
                return []

            # Parse symbols (format is "HK.00700 Name")
            symbols = [s.split(' ')[0] for s in hk_securities]
            
            if not symbols:
                logger.warning(f"No valid HK symbols found")
                return []

            # Define blocking function to fetch snapshots (internal helper)
            def fetch_snapshots(codes):
                ctx = self.get_quote_context()
                chunk_size = 200
                all_frames = []
                
                for i in range(0, len(codes), chunk_size):
                    chunk = codes[i:i+chunk_size]
                    ret, data = ctx.get_market_snapshot(chunk)
                    if ret == 0:
                        all_frames.append(data)
                    else:
                        logger.error(f"Futu snapshot error for chunk {i}: {data}")
                
                if all_frames:
                    return pd.concat(all_frames)
                return None

            # Fetch quotes
            quotes_df = fetch_snapshots(symbols)
            
            threshold_stocks = []
            
            if quotes_df is not None and not quotes_df.empty:
                for _, row in quotes_df.iterrows():
                    try:
                        last_price = float(row['last_price'])
                        prev_close = float(row['prev_close_price'])
                        symbol = row['code']
                        
                        if prev_close > 0:
                            change_rate = ((last_price - prev_close) / prev_close) * 100
                            
                            # Debug log for significant changes or all symbols
                            logger.info(f"Futu Quote: {symbol} Last: {last_price}, Prev: {prev_close}, Change: {change_rate:.2f}% (Threshold: {threshold}%)")
                            
                            # If threshold is 0, return all; otherwise filter by absolute change
                            if threshold == 0 or abs(change_rate) >= threshold:
                                # Get stock name from the row
                                name = row.get('name', '')
                                display_symbol = f"{symbol} {name}" if name and name != symbol else symbol
                                threshold_stocks.append({
                                    'symbol': display_symbol,
                                    'code': symbol,
                                    'name': name,
                                    'last_price': last_price,
                                    'change_rate': change_rate,
                                    'prev_close': prev_close
                                })
                        else:
                            logger.warning(f"Futu Quote: {symbol} has invalid prev_close: {prev_close}")
                            
                    except Exception as e:
                        logger.error(f"Error processing Futu quote for {row.get('code', 'unknown')}: {e}")
                        continue
                        
            return threshold_stocks

        except Exception as e:
            logger.error(f"Error fetching Futu threshold quotes: {e}")
            return []

    def get_capital_flow(self, symbol):
        """
        Get capital flow distribution for a stock.
        """
        if not self._quote_ctx:
            return None
            
        try:
            # get_capital_distribution returns (ret, data)
            ret, data = self._quote_ctx.get_capital_distribution(symbol)
            if ret == 0:
                return data
            else:
                logger.error(f"Failed to get capital distribution for {symbol}: {data}")
                return None
        except Exception as e:
            logger.error(f"Error getting capital distribution for {symbol}: {e}")
            return None

    def get_hk_historical_klines(self, code, num_days=60):
        """
        Get historical daily k-lines for EMA/Bias calculation.
        """
        from futu import KLType, AuType
        from datetime import datetime, timedelta
        
        if not self._quote_ctx:
            return None
            
        try:
            start_date = (datetime.now() - timedelta(days=num_days + 30)).strftime('%Y-%m-%d') # Get extra days for EMA to warm up
            end_date = datetime.now().strftime('%Y-%m-%d')
            
            ret, data, page_req_key = self._quote_ctx.request_history_kline(
                code, 
                start=start_date, 
                end=end_date, 
                ktype=KLType.K_DAY, 
                autype=AuType.QFQ, 
                max_count=num_days + 30
            )
            
            if ret == 0 and not data.empty:
                return data
            else:
                logger.warning(f"Failed to get historical klines for {code}: {data}")
                return None
        except Exception as e:
            logger.error(f"Error getting historical klines for {code}: {e}")
            return None

    def analyze_capital_flow(self, capital_data, current_price_change):
        """
        Analyze capital flow to determine market state.
        Returns: (flow_label, smart_money_net, retail_money_net)
        """
        if capital_data is None or capital_data.empty:
             return "数据缺失", 0, 0
             
        try:
            # Assuming data is a DataFrame with one row
            row = capital_data.iloc[0]
            
            in_super = float(row.get('capital_in_super', 0))
            in_large = float(row.get('capital_in_large', 0))
            out_super = float(row.get('capital_out_super', 0))
            out_large = float(row.get('capital_out_large', 0))
            
            in_mid = float(row.get('capital_in_mid', 0))
            in_small = float(row.get('capital_in_small', 0))
            out_mid = float(row.get('capital_out_mid', 0))
            out_small = float(row.get('capital_out_small', 0))
            
            # Smart Money Net = (Super In + Large In) - (Super Out + Large Out)
            smart_net = (in_super + in_large) - (out_super + out_large)
            
            # Retail Money Net = (Mid In + Small In) - (Mid Out + Small Out)
            retail_net = (in_mid + in_small) - (out_mid + out_small)
            
            # Convert to Wan (Ten Thousand) for display
            smart_net_wan = smart_net / 10000
            retail_net_wan = retail_net / 10000
            
            label = "资金博弈不明"
            
            # Logic from strategy doc
            # 1. 【主力洗盘 / 机构吸筹】
            # Price drop, Smart Net > 0, Retail Net < 0
            if current_price_change < 0 and smart_net > 0 and retail_net < 0:
                label = "【主力洗盘 / 机构吸筹】"
                
            # 2. 【机构出逃 / 踩踏砸盘】
            # Price drop, Smart Net < 0
            elif current_price_change < 0 and smart_net < 0:
                 label = "【机构出逃 / 踩踏砸盘】"
                 
            # 3. 【主力抢筹 / 主升浪】
            # Price rise, Smart Net > 0
            elif current_price_change > 0 and smart_net > 0:
                label = "【主力抢筹 / 主升浪】"
                
            # 4. 【散户诱多 / 诱多出货】
            # Price rise, Smart Net < 0, Retail Net > 0
            elif current_price_change > 0 and smart_net < 0 and retail_net > 0:
                label = "【散户诱多 / 诱多出货】"
            
            return label, round(smart_net_wan, 2), round(retail_net_wan, 2)
            
        except Exception as e:
            logger.error(f"Error analyzing capital flow: {e}")
            return "分析错误", 0, 0

    def close(self):
        if self._quote_ctx:
            logger.info("Closing Futu OpenQuoteContext...")
            self._quote_ctx.close()
            self._quote_ctx = None

futu_client = FutuClient()
