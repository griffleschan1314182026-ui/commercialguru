#!/bin/sh
# Double-click to scrape all Buy and Rent listings now (about 20-25 minutes).
cd "$(dirname "$0")"
echo "Scraping CommercialGuru Buy and Rent listings. Leave this window open."
./run_daily.sh
echo
tail -4 "logs/scrape-$(date +%F).log"
osascript -e 'display notification "Scrape finished. Open the dashboard to see today'\''s listings." with title "CommercialGuru"'
echo
echo "Done. You can close this window."
