
import sys
import os

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

try:
    import longport
    print(f"Successfully imported longport from: {longport.__file__ if hasattr(longport, '__file__') else 'unknown'}")
    print(f"longport dir: {dir(longport)}")
except ImportError:
    print("Failed to import longport")

try:
    import longport.openapi as openapi
    print(f"Successfully imported longport.openapi from: {openapi.__file__ if hasattr(openapi, '__file__') else 'unknown'}")
    if hasattr(openapi, "AsyncQuoteContext"):
        print("AsyncQuoteContext is available in longport.openapi")
    else:
        print("AsyncQuoteContext NOT found in longport.openapi")
        print(f"Available attributes in longport.openapi: {dir(openapi)}")
except ImportError as e:
    print(f"Failed to import longport.openapi: {e}")

# Check for rogue openapi module
try:
    import openapi
    print(f"WARNING: Found top-level 'openapi' module at: {openapi.__file__}")
except ImportError:
    print("Top-level 'openapi' module not found (good)")
