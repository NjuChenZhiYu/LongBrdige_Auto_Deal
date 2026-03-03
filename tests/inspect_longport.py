
import inspect
from longport.openapi import QuoteContext, TradeContext

print("\nInspecting QuoteContext methods:")
for name in dir(QuoteContext):
    if name.startswith('_'): continue
    attr = getattr(QuoteContext, name)
    # Check if it's a function (unbound method in Python 3) or method
    if inspect.isfunction(attr) or inspect.ismethod(attr):
        print(f"Method: {name}, Async: {inspect.iscoroutinefunction(attr)}")
    # Also check if it is wrapped in some way
    elif hasattr(attr, '__call__'):
        print(f"Callable: {name}, Async: {inspect.iscoroutinefunction(attr)}")

print("\nInspecting TradeContext methods:")
for name in dir(TradeContext):
    if name.startswith('_'): continue
    attr = getattr(TradeContext, name)
    if inspect.isfunction(attr) or inspect.ismethod(attr):
        print(f"Method: {name}, Async: {inspect.iscoroutinefunction(attr)}")
