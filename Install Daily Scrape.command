#!/bin/sh
# Double-click once. Saves your Supabase keys, sets up Python, and schedules
# a scrape every morning at 7:00. If the Mac is asleep at 7:00, it runs
# as soon as the Mac wakes. Double-click again any time to change the keys.
cd "$(dirname "$0")"
DIR="$(pwd)"
ask() { osascript -e "text returned of (display dialog \"$1\" default answer \"$2\" with title \"CommercialGuru setup\")" 2>/dev/null; }
cur() { grep "^$1=" .env 2>/dev/null | cut -d= -f2-; }

URL=$(ask "Supabase Project URL (Project Settings > Data API):" "$(cur SUPABASE_URL)") || exit 1
KEY=$(ask "Supabase service_role or secret key (Project Settings > API Keys). Keep this private." "$(cur SUPABASE_SERVICE_KEY)") || exit 1
PUB=$(ask "Supabase publishable or anon key (read-only, for the dashboard):" "$(sed -n 's/.*"anonKey": *"\([^"]*\)".*/\1/p' dashboard/config.json 2>/dev/null)") || exit 1
URL=$(printf %s "$URL" | tr -d '[:space:]'); KEY=$(printf %s "$KEY" | tr -d '[:space:]'); PUB=$(printf %s "$PUB" | tr -d '[:space:]')
printf 'SUPABASE_URL=%s\nSUPABASE_SERVICE_KEY=%s\n' "$URL" "$KEY" > .env
printf '{"supabaseUrl": "%s", "anonKey": "%s"}\n' "$URL" "$PUB" > dashboard/config.json

echo "Setting up Python..."
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r scraper/requirements.txt
chmod +x run_daily.sh *.command

PLIST="$HOME/Library/LaunchAgents/sg.commercialguru.scrape.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>sg.commercialguru.scrape</string>
  <key>ProgramArguments</key><array><string>/bin/sh</string><string>$DIR/run_daily.sh</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardErrorPath</key><string>$DIR/logs/launchd.log</string>
</dict></plist>
PL
mkdir -p logs
launchctl bootout "gui/$(id -u)/sg.commercialguru.scrape" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST"
.venv/bin/python dashboard/build.py >/dev/null
osascript -e 'display alert "All set" message "Listings will be scraped every morning at 7:00. Double-click \"Open Dashboard\" to view them, or \"Run Scrape Now\" to update right away."'
