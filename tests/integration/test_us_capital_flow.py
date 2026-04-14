import asyncio
from src.api.longport.client import longport_client
from config.settings import Settings

async def main():
    symbol = "AAPL.US"
    print(f"Testing {symbol}...")
    res = await longport_client.get_capital_flow(symbol)
    if res:
        print("Capital flow data fetched:")
        print(f"Capital In - Large: {res.capital_in.large}, Medium: {res.capital_in.medium}, Small: {res.capital_in.small}")
        print(f"Capital Out - Large: {res.capital_out.large}, Medium: {res.capital_out.medium}, Small: {res.capital_out.small}")
        
        # Test analyze
        label, smart, retail = longport_client.analyze_us_capital_flow(res, -2.5) # Simulate drop
        print(f"\nAnalysis with -2.5% change:")
        print(f"Label: {label}")
        print(f"Smart Net: {smart}万")
        print(f"Retail Net: {retail}万")
        
        label, smart, retail = longport_client.analyze_us_capital_flow(res, 2.5) # Simulate rise
        print(f"\nAnalysis with 2.5% change:")
        print(f"Label: {label}")
        print(f"Smart Net: {smart}万")
        print(f"Retail Net: {retail}万")
    else:
        print("Failed to fetch data")

if __name__ == "__main__":
    asyncio.run(main())