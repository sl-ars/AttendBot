import json, os, sys, time, urllib.request, urllib.error

status_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SEL_STATUS_URL", "http://selenium:4444/status")

def ready(payload: dict) -> bool:
    # Selenium 4 usually returns {"value": {"ready": true, ...}}
    if "ready" in payload:
        return bool(payload.get("ready"))
    return bool(payload.get("value", {}).get("ready"))

for i in range(600):  # up to ~10 minutes
    try:
        with urllib.request.urlopen(status_url, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")
            if ready(data):
                sys.exit(0)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        pass
    time.sleep(1)

print("Timed out waiting for Selenium status endpoint:", status_url, file=sys.stderr)
sys.exit(1)
