import asyncio
from longport.openapi import Config, AsyncQuoteContext
from config.settings import Settings

async def main():
    config = Config(
        app_key=Settings.LONGPORT_APP_KEY,
        app_secret=Settings.LONGPORT_APP_SECRET,
        access_token=Settings.LONGPORT_ACCESS_TOKEN
    )
    ctx = await AsyncQuoteContext.create(config)
    res = await ctx.capital_flow("AAPL.US")
    print(dir(res))
    print(res)

if __name__ == "__main__":
    asyncio.run(main())