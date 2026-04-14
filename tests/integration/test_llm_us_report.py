import asyncio
from src.services.llm_analyst import llm_analyst

async def main():
    # Only test the US report function
    await llm_analyst.generate_longport_us_report()
    print("Done testing US report")

if __name__ == "__main__":
    asyncio.run(main())