# CommercialGuru listings scraper

Daily scrape of Buy and Rent listings on commercialguru.com.sg into Supabase, with a web dashboard.

## Stack
| Piece | Choice | Cost |
|---|---|---|
| Scheduler | Your own computer, once a day (`run_daily.sh` / `run_daily.bat`). CommercialGuru blocks GitHub's servers (HTTP 403, 2026-10-06), so the GitHub workflow is manual-only. | Free |
| Storage | Supabase Postgres (`supabase/schema.sql`) | Free tier: 500 MB, ample for ~30k listings + price changes |
| Dashboard | `dashboard/index.html`, static page reading Supabase with the read-only anon key | Free on GitHub Pages |

## Scope and etiquette
* Only the public search-result pages `/property-for-sale/N` and `/property-for-rent/N` are read. robots.txt allows these. Listing detail pages are not fetched.
* About 20 listings per page: ~475 sale pages + ~915 rent pages ≈ 1,400 requests/day, spaced 0.6–0.9 s apart, one at a time; the run backs off on HTTP 429 and stops on 403.
* The site's Terms of Service (s3.3, s10.1) limit use of its content to personal, non-commercial use and forbid republishing. Keep the dashboard private.
* If the site answers with a bot challenge or 403 the run stops instead of retrying.

## Setup
1. Supabase: done 2026-10-06 in project `wzeflmzbxhaljzzzpqte` (Singapore). Tables `listings`, `price_history`, `scrape_runs`, views `listings_current`, `daily_stats`; 40 sample listings loaded. Public key can read, cannot write.
2. GitHub repo: push this folder; add secrets `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (service-role key).
3. Actions → "Daily CommercialGuru scrape" → Run workflow with `max_pages = 2` as a smoke test. Check the log and the `output/debug/*.html` artifact.
4. Dashboard: `dashboard/config.json` holds the Supabase URL and public key; `python dashboard/build.py` writes `dashboard/index.html` (live data) for GitHub Pages.

## Run it daily on your computer
A full run takes about 30–40 minutes; the computer must be on and awake.

1. Install Python 3.10+ and download this repo (Code → Download ZIP, or `git clone`).
2. Copy `.env.example` to `.env` and paste your Supabase secret key (Supabase → Project Settings → API Keys). Never commit `.env`.
3. Test once with 2 pages: `python scraper/scrape.py --types sale rent --max-pages 2`
4. Schedule it:
   * **Windows:** Task Scheduler → Create Basic Task → Daily, 3:00 AM → Start a program → browse to `run_daily.bat`. Tick "Wake the computer to run this task" under Conditions.
   * **macOS / Linux:** `crontab -e` and add `0 3 * * * /full/path/to/commercialguru/run_daily.sh`
5. Logs go to `logs/`; each run is also recorded in the `scrape_runs` table in Supabase.

## Local run
```
pip install -r scraper/requirements.txt
python scraper/scrape.py --types sale --max-pages 2 --dump-html debug/
python tests/test_parser.py
```

## Status
The parser was built against a fixture shaped like the site's cards (from 40 real page-1 listings captured 2026-10-06); the build container could not reach the site directly. The first smoke-test run against the live site is the real check of the selectors.
