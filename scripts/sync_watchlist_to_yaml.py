import asyncio
import yaml
import os
import sys
from typing import List
from longport.openapi import Config, AsyncQuoteContext

from config.settings import Settings
from src.utils.logger import logger

async def fetch_and_update_symbols():
    """Fetch all watchlist symbols and update config/symbols.yaml"""
    print("Connecting to LongPort API to fetch watchlist...")
    
    # Check config
    if not Settings.LONGPORT_APP_KEY or not Settings.LONGPORT_ACCESS_TOKEN:
        print("Error: LongPort API configuration missing in .env")
        return

    config = Config(
        app_key=Settings.LONGPORT_APP_KEY,
        app_secret=Settings.LONGPORT_APP_SECRET,
        access_token=Settings.LONGPORT_ACCESS_TOKEN
    )
    
    try:
        ctx = await AsyncQuoteContext.create(config)

        # Fetch all watchlists
        groups = await ctx.watchlist()
        all_symbols = set()
        
        print(f"Found {len(groups)} watchlist groups.")
        
        for group in groups:
            print(f"Fetching group: {group.name} (ID: {group.id})")
            for sec in group.securities:
                all_symbols.add(sec.symbol)
                
        sorted_symbols = sorted(list(all_symbols))
        print(f"Total unique symbols found: {len(sorted_symbols)}")
        print(f"Symbols: {sorted_symbols}")
        
        # Update symbols.yaml
        yaml_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "symbols.yaml")
        
        current_data = {}
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r', encoding='utf-8') as f:
                current_data = yaml.safe_load(f) or {}
        
        # Update symbols list
        current_data['symbols'] = sorted_symbols
        
        # Ensure thresholds exist
        if 'thresholds' not in current_data:
            current_data['thresholds'] = {'price_change': 5.0}
            
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_data, f, default_flow_style=False, allow_unicode=True)
            
        print(f"Successfully updated {yaml_path} with {len(sorted_symbols)} symbols.")
        
    except Exception as e:
        print(f"Error fetching watchlist: {e}")
    finally:
        # ctx.close() # QuoteContext doesn't need close in some versions, but let's be safe if supported
        pass

if __name__ == "__main__":
    asyncio.run(fetch_and_update_symbols())
