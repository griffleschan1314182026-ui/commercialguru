@echo off
rem Daily CommercialGuru scrape for Windows. Schedule with Task Scheduler (see README).
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -q -r scraper\requirements.txt
if not exist logs mkdir logs
.venv\Scripts\python scraper\scrape.py --types sale rent --out-dir output >> logs\scrape.log 2>&1
