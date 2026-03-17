import requests
import sys
import time

def check_endpoint(url, description):
    print(f"Checking {description} ({url})...")
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print("SUCCESS")
            return True
        else:
            print(f"FAILED: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

base_url = "http://127.0.0.1:5001"

print("Waiting for server to be ready...")
time.sleep(2)

results = []
results.append(check_endpoint(f"{base_url}/", "US Market Dashboard"))
results.append(check_endpoint(f"{base_url}/hk_market", "HK Market Dashboard"))
results.append(check_endpoint(f"{base_url}/reports", "Daily Reports Center"))
results.append(check_endpoint(f"{base_url}/api/reports", "Reports API"))

if all(results):
    print("\nAll endpoints verified successfully!")
    sys.exit(0)
else:
    print("\nSome endpoints failed verification.")
    sys.exit(1)
