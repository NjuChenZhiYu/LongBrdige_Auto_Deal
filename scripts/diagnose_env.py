
import sys
import os
import pkg_resources

print("="*50)
print("DIAGNOSTIC START")
print("="*50)

print(f"Python Executable: {sys.executable}")
print(f"Python Version: {sys.version}")
print(f"CWD: {os.getcwd()}")
print(f"sys.path: {sys.path}")

print("-" * 30)
print("Checking installed packages:")
installed_packages = {d.project_name: d.version for d in pkg_resources.working_set}
if 'longport' in installed_packages:
    print(f"longport version: {installed_packages['longport']}")
else:
    print("longport NOT installed via pip")

if 'openapi' in installed_packages:
    print(f"WARNING: 'openapi' package found! Version: {installed_packages['openapi']}")
    print("This package likely conflicts with 'longport'. Please uninstall it: pip uninstall openapi")

print("-" * 30)
print("Attempting imports:")

try:
    import longport
    print(f"Successfully imported longport from: {longport.__file__ if hasattr(longport, '__file__') else 'unknown'}")
    print(f"longport dir: {dir(longport)}")
except ImportError as e:
    print(f"Failed to import longport: {e}")

try:
    import longport.openapi as openapi_mod
    print(f"Successfully imported longport.openapi from: {openapi_mod.__file__ if hasattr(openapi_mod, '__file__') else 'unknown'}")
    if hasattr(openapi_mod, "AsyncQuoteContext"):
        print("AsyncQuoteContext FOUND in longport.openapi")
    else:
        print("AsyncQuoteContext NOT found in longport.openapi")
        print(f"Available attributes: {dir(openapi_mod)}")
except ImportError as e:
    print(f"Failed to import longport.openapi: {e}")

try:
    from longport.openapi import AsyncQuoteContext
    print("Successfully imported AsyncQuoteContext directly")
except ImportError as e:
    print(f"Failed to import AsyncQuoteContext directly: {e}")

# Check for rogue openapi module
try:
    import openapi
    print(f"WARNING: Top-level 'openapi' module found at: {openapi.__file__ if hasattr(openapi, '__file__') else 'unknown'}")
    print("This is likely the cause of the conflict.")
except ImportError:
    print("Top-level 'openapi' module not found (good)")

print("="*50)
print("DIAGNOSTIC END")
print("="*50)
