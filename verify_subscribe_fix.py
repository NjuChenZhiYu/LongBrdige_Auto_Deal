
import asyncio
from unittest.mock import MagicMock
from src.api.longport.client import AsyncContextAdapter

async def test_subscribe_signature():
    print("Testing AsyncContextAdapter.subscribe signature handling...")
    
    # Mock context
    mock_ctx = MagicMock()
    
    # Define subscribe method that strictly does NOT accept is_first_push
    def mock_subscribe(symbols, sub_types):
        print(f"Called mock_subscribe with symbols={symbols}, sub_types={sub_types}")
        return ["SUCCESS"]
        
    mock_ctx.subscribe = mock_subscribe
    
    adapter = AsyncContextAdapter(mock_ctx)
    
    try:
        # Call with is_first_push=True, which caused the error before
        print("Calling adapter.subscribe(..., is_first_push=True)")
        result = await adapter.subscribe(["AAPL"], [1], is_first_push=True)
        print(f"Result: {result}")
        print("SUCCESS: Adapter successfully ignored is_first_push")
    except Exception as e:
        print(f"FAILURE: Adapter raised exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_subscribe_signature())
