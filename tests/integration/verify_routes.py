import requests
import sys

base_url = "http://127.0.0.1:5001"

routes = [
    "/",
    "/hk_market",
    "/reports",
    "/api/reports"
]

print("Checking routes...")
for route in routes:
    try:
        url = base_url + route
        response = requests.get(url, timeout=5, proxies={"http": None, "https": None})
        print(f"GET {route}: {response.status_code}")
        if response.status_code == 500:
            print(f"ERROR BODY: {response.text[:500]}") # Print first 500 chars of error
    except Exception as e:
        print(f"GET {route}: FAILED ({e})")
