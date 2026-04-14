import requests
import sys

with open("status_output.txt", "w") as f:
    def check_url(url, name):
        try:
            response = requests.get(url, proxies={'http': None, 'https': None}, timeout=5)
            f.write(f"{name}: {response.status_code}\n")
            if response.status_code != 200:
                f.write(f"Error content: {response.text[:500]}\n")
        except Exception as e:
            f.write(f"{name}: Failed - {e}\n")

    check_url('http://127.0.0.1:5001/', 'ROOT')
    check_url('http://127.0.0.1:5001/hk_market', 'HK')
    check_url('http://127.0.0.1:5001/reports', 'REPORTS')
    check_url('http://127.0.0.1:5001/api/reports', 'API')
    check_url('http://127.0.0.1:5001/api/reports?date=2024-01-01', 'API_DATE')
