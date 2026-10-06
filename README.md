# CommercialGuru listings scraper

Daily scrape of Buy and Rent listings on commercialguru.com.sg into Supabase, with a web dashboard.

## Stack
| Piece | Choice | Cost |
|---|---|---|
| Scheduler | GitHub Actions cron, 03:00 SGT daily (`.github/workflows/daily-scrape.yml`) | Free (private repo: 2,000 min/month; a full run is ~75–90 min, so ~45 h/month. **Use a public repo, or self-host the runner, to stay within free minutes.**) |
| Storage | Supabase Postgres (`supabase/schema.sql`) | Free tier: 500 MB, ample for ~30k listings + price changes |
| Dashboard | `dashboard/index.html`, static page reading Supabase with the read-only anon key | Free on GitHub Pages |

## Scope and etiquette
* Only the public search-result pages `/property-for-sale/N` and `/property-for-rent/N` are read. robots.txt allows these. Listing detail pages are not fetched.
* About 20 listings per page: ~475 sale pages + ~915 rent pages ≈ 1,400 requests/day, spaced 3–4.5 s apart.
* The site's Terms of Service (s3.3, s10.1) limit use of its content to personal, non-commercial use and forbid republishing. Keep the dashboard private.
* If the site answers with a bot challenge or 403 the run stops instead of retrying.

## Setup
1. Supabase: done 2026-10-06 in project `wzeflmzbxhaljzzzpqte` (Singapore). Tables `listings`, `price_history`, `scrape_runs`, views `listings_current`, `daily_stats`; 40 sample listings loaded. Public key can read, cannot write.
2. GitHub repo: push this folder; add secrets `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (service-role key).
3. Actions → "Daily CommercialGuru scrape" → Run workflow with `max_pages = 2` as a smoke test. Check the log and the `output/debug/*.html` artifact.
4. Dashboard: `dashboard/config.json` holds the Supabase URL and public key; `python dashboard/build.py` writes `dashboard/index.html` (live data) for GitHub Pages.

## Local run
```
pip install -r scraper/requirements.txt
python scraper/scrape.py --types sale --max-pages 2 --dump-html debug/
python tests/test_parser.py
```

## Status
The parser was built against a fixture shaped like the site's cards (from 40 real page-1 listings captured 2026-10-06); the build container could not reach the site directly. The first smoke-test run against the live site is the real check of the selectors.
