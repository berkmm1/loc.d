import requests
import time
import os

URL = "http://localhost:8000/status"

def monitor():
    print("Starting monitoring...")
    while True:
        try:
            res = requests.get(URL)
            if res.status_code == 200:
                data = res.json()
                print(f"[{time.strftime('%H:%M:%S')}] Price: ${data['price']} | Engine: {'Running' if data['is_running'] else 'Stopped'}")
            else:
                print(f"Alert: HTTP {res.status_code}")
        except Exception as e:
            print(f"Alert: Bot offline ({e})")
        time.sleep(60)

if __name__ == "__main__":
    monitor()
