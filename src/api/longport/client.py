import asyncio
import importlib
import inspect
from typing import Any, Dict
from longport.openapi import Config, AsyncQuoteContext, AsyncTradeContext
from config.settings import Settings
from src.utils.logger import logger

from src.api.longport.personalized.watchlist import get_watchlist

class LongPortClient:
    _instance = None
    _quote_ctx = None
    _trade_ctx = None
    _fundamental_ctx = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LongPortClient, cls).__new__(cls)
        return cls._instance

    @property
    def config(self):
        return Config(
            app_key=Settings.LONGPORT_APP_KEY or "",
            app_secret=Settings.LONGPORT_APP_SECRET or "",
            access_token=Settings.LONGPORT_ACCESS_TOKEN or ""
        )

    @staticmethod
    def _create_config(config_cls: Any) -> Any:
        app_key = Settings.LONGPORT_APP_KEY or ""
        app_secret = Settings.LONGPORT_APP_SECRET or ""
        access_token = Settings.LONGPORT_ACCESS_TOKEN or ""

        if hasattr(config_cls, "from_apikey"):
            return config_cls.from_apikey(app_key, app_secret, access_token)
        if hasattr(config_cls, "from_env") and not all((app_key, app_secret, access_token)):
            return config_cls.from_env()
        if hasattr(config_cls, "from_apikey_env") and not all((app_key, app_secret, access_token)):
            return config_cls.from_apikey_env()

        return config_cls(
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
        )

    async def get_quote_context(self):
        """Get or create AsyncQuoteContext singleton"""
        if self._quote_ctx is None:
            try:
                logger.info("Initializing LongPort AsyncQuoteContext...")
                # Native async context creation
                self._quote_ctx = await AsyncQuoteContext.create(self.config)
                logger.info("LongPort AsyncQuoteContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncQuoteContext: {e}")
                raise
        return self._quote_ctx

    async def get_trade_context(self):
        """Get or create AsyncTradeContext singleton"""
        if not Settings.ENABLE_TRADING:
            logger.warning("Trading is disabled in settings")
            return None
            
        if self._trade_ctx is None:
            try:
                logger.info("Initializing LongPort AsyncTradeContext...")
                self._trade_ctx = await AsyncTradeContext.create(self.config)
                logger.info("LongPort AsyncTradeContext initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize AsyncTradeContext: {e}")
                raise
        return self._trade_ctx

    async def get_fundamental_context(self):
        """Get or create FundamentalContext when supported by the installed SDK."""
        if self._fundamental_ctx is None:
            try:
                try:
                    openapi = importlib.import_module("longbridge.openapi")
                except ImportError:
                    openapi = importlib.import_module("longport.openapi")

                ctx_cls = getattr(openapi, "AsyncFundamentalContext", None) or getattr(openapi, "FundamentalContext", None)
                if ctx_cls is None:
                    raise RuntimeError("installed Longbridge SDK does not expose FundamentalContext")

                config_cls = getattr(openapi, "Config", None)
                if config_cls is None:
                    raise RuntimeError("installed Longbridge SDK does not expose Config")

                fundamental_config = self._create_config(config_cls)
                if hasattr(ctx_cls, "create"):
                    created = ctx_cls.create(fundamental_config)
                else:
                    created = ctx_cls(fundamental_config)
                self._fundamental_ctx = await created if inspect.isawaitable(created) else created
                logger.info("LongPort FundamentalContext initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize FundamentalContext: {e}")
                raise
        return self._fundamental_ctx

    async def reset_context(self):
        """Reset contexts (e.g. for reconnection)"""
        if self._quote_ctx:
            # Async context usually doesn't need explicit close if not running,
            # but ideally we should check if there's a close method.
            # LongPort SDK usually manages connection.
            self._quote_ctx = None
        if self._trade_ctx:
            self._trade_ctx = None
        if self._fundamental_ctx:
            self._fundamental_ctx = None
        logger.info("LongPort contexts reset")

    @staticmethod
    def normalize_to_longbridge_symbol(symbol: str) -> str:
        """Convert Futu HK.02513 style to Longbridge ticker.region style: 2513.HK."""
        raw = str(symbol or "").strip().upper().split(" ")[0]
        if raw.startswith("HK."):
            return f"{raw.split('.', 1)[1].lstrip('0') or '0'}.HK"
        if raw.endswith(".HK"):
            ticker = raw.rsplit(".", 1)[0].lstrip("0") or "0"
            return f"{ticker}.HK"
        return raw

    @staticmethod
    def _get_value(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _format_yoy(value: Any) -> str:
        if value in (None, ""):
            return "无数据"
        text = str(value).strip()
        if not text:
            return "无数据"
        if text.endswith("%"):
            return text
        try:
            num = float(text)
        except Exception:
            return text
        pct = num * 100 if abs(num) <= 3 else num
        sign = "+" if pct > 0 else ""
        return f"{sign}{round(pct, 2)}%"

    @classmethod
    def _extract_operating_revenue_rows(cls, payload: Any) -> Dict[str, str]:
        rows = {}
        items = cls._get_value(payload, "list", []) or []
        report_labels = {
            "af": "年报",
            "saf": "半年报",
            "qf": "最近季报",
            "q1": "最近季报",
            "q2": "最近季报",
            "q3": "最近季报",
            "q4": "最近季报",
            "3q": "最近季报",
        }

        for item in items:
            report = str(cls._get_value(item, "report", "") or "").lower()
            label = report_labels.get(report)
            if not label or label in rows:
                continue

            financial = cls._get_value(item, "financial")
            currency = str(cls._get_value(financial, "currency", "") or "").strip()
            indicators = cls._get_value(financial, "indicators", []) or []
            for indicator in indicators:
                field = str(cls._get_value(indicator, "field_name", "") or "").lower()
                name = str(cls._get_value(indicator, "indicator_name", "") or "").lower()
                if "revenue" not in field and "revenue" not in name and "收入" not in name:
                    continue

                period = cls._get_value(item, "title", "") or cls._get_value(item, "report", "") or "最新披露"
                value = cls._get_value(indicator, "indicator_value", "无数据")
                value_with_currency = f"{value} {currency}" if currency and value != "无数据" else value
                yoy = cls._format_yoy(cls._get_value(indicator, "yoy"))
                rows[label] = f"{label}：{period}，营业收入 {value_with_currency}，同比 {yoy}"
                break
        return rows

    @staticmethod
    def _format_sdk_error(error: Exception) -> str:
        message = str(error).strip()
        if "429002" in message or "request is limited" in message.lower():
            return "rate limited"
        if "token expired" in message.lower():
            return "token expired"
        if "permission" in message.lower() or "unauthorized" in message.lower():
            return "permission denied"
        return message or error.__class__.__name__

    async def _operating_call(self, ctx: Any, symbol: str) -> Any:
        call = getattr(ctx, "operating")
        if ctx.__class__.__name__.startswith("Async"):
            result = call(symbol)
        else:
            result = await asyncio.to_thread(call, symbol)
        return await result if inspect.isawaitable(result) else result

    async def get_revenue_disclosure_profile(self, symbol: str) -> str:
        """
        Return three compact revenue disclosure lines from Longbridge fundamentals.

        The installed SDK may not expose FundamentalContext yet; in that case this
        degrades to an explicit data-unavailable string without blocking reports.
        """
        lb_symbol = self.normalize_to_longbridge_symbol(symbol)
        try:
            ctx = await self.get_fundamental_context()
        except Exception as e:
            return f"长桥基本面不可用（{e}）"

        labels = ("年报", "半年报", "最近季报")
        rows: Dict[str, str] = {}
        try:
            operating_payload = await self._operating_call(ctx, lb_symbol)
            rows.update(self._extract_operating_revenue_rows(operating_payload))
        except Exception as e:
            logger.warning(f"[Longbridge/Fundamental] operating revenue fetch failed for {lb_symbol}: {e}")
            return "\n      ".join(f"{label}：获取失败（{self._format_sdk_error(e)}）" for label in labels)

        return "\n      ".join(rows.get(label, f"{label}：无数据") for label in labels)

    async def subscribe(self, ctx, symbols, sub_types):
        """
        Subscribe with market routing and permission isolation.
        Excludes HK symbols (starting with 'HK.').
        """
        # 1. Market Routing / Permission Isolation
        valid_symbols = []
        for s in symbols:
            # Check if it looks like a HK symbol (HK.xxxxx)
            if s.startswith("HK."):
                logger.warning(f"Market Routing: Symbol {s} excluded from LongPort subscription (HK market not supported)")
            else:
                valid_symbols.append(s)
        
        if not valid_symbols:
            logger.warning("No valid non-HK symbols to subscribe")
            return []

        # 2. Subscribe
        try:
            # ctx.subscribe is async
            return await ctx.subscribe(valid_symbols, sub_types)
        except Exception as e:
            logger.error(f"LongPort subscribe error: {e}")
            # Don't crash, return empty or re-raise if critical
            # Re-raising might be better for LongPort as it handles its own reconnections mostly,
            # but we want to avoid crashing the whole monitor task if one sub fails?
            # Actually, LongPort subscribe usually doesn't fail unless network is down.
            raise e

    async def get_threshold_quotes(self, threshold: float = 0.0) -> list:
        """
        Get real-time quotes for US stocks from watchlist that exceed the threshold.
        
        Args:
            threshold (float): Price change percentage threshold. Default 0.0 (return all valid quotes).
            
        Returns:
            list: List of dicts with stock data [{'symbol':..., 'last_price':..., 'change_rate':...}]
        """
        try:
            # Get watchlist symbols (with deduplication)
            watchlist_items = await get_watchlist()
            symbols = list(set([item['symbol'] for item in watchlist_items if item['symbol'].endswith(".US")]))
            
            if not symbols:
                logger.warning(f"No US symbols in watchlist")
                return []
            
            # Fetch real-time quotes from LongPort
            ctx = await self.get_quote_context()
            quotes = await ctx.quote(symbols)
            
            if not quotes:
                logger.warning(f"No quotes returned for US market")
                return []
            
            # Filter stocks
            threshold_stocks = []
            seen_symbols = set()
            for q in quotes:
                if q is None: continue
                symbol = getattr(q, 'symbol', None)
                if not symbol or symbol in seen_symbols: continue
                
                prev_close = float(getattr(q, 'prev_close', 0) or 0)
                last_done = float(getattr(q, 'last_done', 0) or 0)
                
                if prev_close > 0:
                    change_rate = ((last_done - prev_close) / prev_close) * 100
                    
                    # If threshold is 0, return all; otherwise filter by absolute change
                    if threshold == 0 or abs(change_rate) >= threshold:
                        threshold_stocks.append({
                            'symbol': symbol,
                            'last_price': last_done,
                            'change_rate': change_rate,
                            'prev_close': prev_close
                        })
                        seen_symbols.add(symbol)
            
            return threshold_stocks
            
        except Exception as e:
            logger.error(f"Error fetching LongPort threshold quotes: {e}")
            return []

    async def get_capital_flow(self, symbol: str):
        """
        Get capital flow distribution for a US stock.
        """
        try:
            ctx = await self.get_quote_context()
            res = await ctx.capital_distribution(symbol)
            return res
        except Exception as e:
            logger.error(f"Error getting capital distribution for {symbol}: {e}")
            return None

    def analyze_us_capital_flow(self, capital_data, current_price_change: float):
        """
        Analyze capital flow to determine market state for US stocks.
        Returns: (flow_label, smart_money_net, retail_money_net)
        """
        if capital_data is None:
             return "数据缺失", 0, 0
             
        try:
            cap_in = capital_data.capital_in
            cap_out = capital_data.capital_out
            
            in_large = getattr(cap_in, "large", 0) or 0
            out_large = getattr(cap_out, "large", 0) or 0
            
            in_mid = getattr(cap_in, "medium", 0) or 0
            in_small = getattr(cap_in, "small", 0) or 0
            out_mid = getattr(cap_out, "medium", 0) or 0
            out_small = getattr(cap_out, "small", 0) or 0
            
            # LongPort API does not have "super" (特大单), so we use "large" (大单) as Smart Money
            # Smart Money Net = Large In - Large Out
            smart_net = in_large - out_large
            
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
                
            # 4. 【庄家诱多 / 诱多出货】
            # Price rise, Smart Net < 0, Retail Net > 0
            elif current_price_change > 0 and smart_net < 0 and retail_net > 0:
                label = "【庄户诱多 / 诱多出货】"
            
            return label, round(smart_net_wan, 2), round(retail_net_wan, 2)
            
        except Exception as e:
            logger.error(f"Error analyzing US capital flow: {e}")
            return "分析错误", 0, 0

# Global client instance
longport_client = LongPortClient()
