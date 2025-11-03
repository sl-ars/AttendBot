#!/usr/bin/env sh
set -eu

# Wait for Selenium Grid to be ready
SEL_HOST="${SEL_HOST:-selenium}"
SEL_PORT="${SEL_PORT:-4444}"

echo "Waiting for Selenium at http://${SEL_HOST}:${SEL_PORT}/status ..."
python /wait_for_selenium.py "http://${SEL_HOST}:${SEL_PORT}/status"
echo "Selenium is ready."

exec python /bot/main.py
