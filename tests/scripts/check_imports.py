import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print(f"Python Executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")
print(f"Path: {sys.path}")

try:
    import futu
    print("Futu imported successfully")
except ImportError as e:
    print(f"Futu import failed: {e}")

try:
    import scipy
    print("Scipy imported successfully")
except ImportError as e:
    print(f"Scipy import failed: {e}")
