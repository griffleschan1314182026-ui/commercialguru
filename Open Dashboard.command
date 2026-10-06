#!/bin/sh
# Double-click to open the listings dashboard in your browser.
cd "$(dirname "$0")"
if [ ! -f dashboard/config.json ]; then
  osascript -e 'display alert "Dashboard not set up" message "Run \"Install Daily Scrape\" first."'
  exit 1
fi
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python dashboard/build.py >/dev/null && open dashboard/index.html
# Close this Terminal window.
osascript -e 'tell application "Terminal" to close (every window whose name contains "Open Dashboard")' >/dev/null 2>&1 &
