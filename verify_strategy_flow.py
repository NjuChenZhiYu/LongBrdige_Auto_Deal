
import asyncio
import logging
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from src.monitor.option_monitor import OptionMonitor
from src.services.signal_recorder import signal_recorder
from src.services.llm_analyst import LLMAnalyst

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock OptionQuote object
class MockQuote:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

async def test_option_monitor_logic():
    logger.info("Testing OptionMonitor logic...")
    
    # Reset signals
    signal_recorder.clear_signals()
    
    monitor = OptionMonitor()
    # Mock underlying prices for Delta calculation
    monitor.underlying_prices = {"AAPL.US": 230.0} 
    monitor.risk_free_rate = 0.045
    
    # Case 1: IV Spike
    # HV = 0.2, Threshold = 0.26. IV = 0.3 -> Should Trigger
    quote_iv = MockQuote(
        symbol="AAPL.US.C.250",
        last_done=10.0,
        volume=100,
        open_interest=1000,
        implied_volatility=0.30,
        historical_volatility=0.20,
        strike_price=250.0,
        expiry_date="2025-06-20",
        underlying_symbol="AAPL.US",
        delta=0.4
    )
    monitor._process_quote("AAPL.US.C.250", quote_iv)
    
    # Case 2: Smart Money (Volume > OI * 0.2)
    # OI = 100, Volume = 30. 30 > 20 -> Should Trigger
    quote_sm = MockQuote(
        symbol="AAPL.US.C.260",
        last_done=5.0,
        volume=30,
        open_interest=100,
        implied_volatility=0.20,
        historical_volatility=0.20,
        strike_price=260.0,
        expiry_date="2025-06-20",
        underlying_symbol="AAPL.US",
        delta=0.3
    )
    monitor._process_quote("AAPL.US.C.260", quote_sm)
    
    # Case 3: Delta Crossing (Delta > 0.5)
    # Delta = 0.6 -> Should Trigger
    quote_delta = MockQuote(
        symbol="AAPL.US.C.240",
        last_done=15.0,
        volume=10,
        open_interest=1000,
        implied_volatility=0.20,
        historical_volatility=0.20,
        strike_price=240.0,
        expiry_date="2025-06-20",
        underlying_symbol="AAPL.US",
        delta=0.6
    )
    monitor._process_quote("AAPL.US.C.240", quote_delta)
    
    # Case 4: Delta Calculation (Delta is N/A, calculate manually)
    # S=230, K=200, T=0.5, r=0.045, sigma=0.2 -> Call Delta should be high (> 0.5)
    quote_calc_delta = MockQuote(
        symbol="AAPL.US.C.200",
        last_done=35.0,
        volume=10,
        open_interest=1000,
        implied_volatility=0.20,
        historical_volatility=0.20,
        strike_price=200.0,
        expiry_date="2027-12-19", # Future date relative to 2026
        underlying_symbol="AAPL.US",
        delta='nan' # Force calculation
    )
    monitor._process_quote("AAPL.US.C.200", quote_calc_delta)

    signals = signal_recorder.get_daily_signals()
    logger.info(f"Recorded {len(signals)} signals.")
    
    expected_types = ["IV_SPIKE", "SMART_MONEY_VOLUME", "DELTA_CROSS_0.5", "DELTA_CROSS_0.5"]
    recorded_types = [s['type'] for s in signals]
    
    logger.info(f"Recorded types: {recorded_types}")
    
    assert len(signals) == 4, f"Expected 4 signals, got {len(signals)}"
    assert "IV_SPIKE" in recorded_types
    assert "SMART_MONEY_VOLUME" in recorded_types
    assert "DELTA_CROSS_0.5" in recorded_types
    
    logger.info("OptionMonitor logic test passed!")

async def test_llm_analyst_flow():
    logger.info("Testing LLMAnalyst flow...")
    
    # Ensure we have signals
    if not signal_recorder.get_daily_signals():
        logger.warning("No signals to report, adding dummy signal.")
        signal_recorder.add_signal({
             "symbol": "TEST.US",
             "type": "TEST_SIGNAL",
             "value": 100,
             "threshold": 50,
             "timestamp": "12:00:00",
             "details": "Test details"
         })

    with patch('src.services.llm_analyst.AsyncOpenAI') as MockAI, \
         patch('src.api.dingtalk.DingTalkAlert.send_alert', new_callable=AsyncMock) as mock_send_alert:
        
        # Setup Mock LLM response
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Mock Report Content"))]
        mock_client.chat.completions.create.return_value = mock_response
        
        analyst = LLMAnalyst()
        analyst.client = mock_client
        
        await analyst.generate_report()
        
        # Verify LLM called
        mock_client.chat.completions.create.assert_called_once()
        logger.info("LLM client called successfully.")
        
        # Verify DingTalk called
        mock_send_alert.assert_called_once()
        args, kwargs = mock_send_alert.call_args
        assert kwargs['title'] == "[AI Analyst] 期权异动复盘报告"
        assert kwargs['content'] == "Mock Report Content"
        logger.info("DingTalk alert triggered successfully.")
        
        # Verify signals cleared
        assert len(signal_recorder.get_daily_signals()) == 0
        logger.info("Signals cleared after report.")

    logger.info("LLMAnalyst flow test passed!")

async def main():
    try:
        await test_option_monitor_logic()
        await test_llm_analyst_flow()
        logger.info("All integration tests passed!")
    except AssertionError as e:
        logger.error(f"Test failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())
