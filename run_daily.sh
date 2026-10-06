#!/bin/sh
# Daily CommercialGuru scrape for macOS / Linux. Schedule with cron (see README).
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r scraper/requirements.txt
mkdir -p logs
.venv/bin/python scraper/scrape.py --types sale rent --out-dir output >> "logs/scrape-$(date +%F).log" 2>&1
