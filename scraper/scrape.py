#!/usr/bin/env python3
"""Daily scraper for CommercialGuru (commercialguru.com.sg) Buy and Rent listings.

Reads only the public search-result pages (/property-for-sale/N and
/property-for-rent/N), which robots.txt allows. It does not open listing
detail pages, contact forms, PDFs or any path robots.txt disallows.

Output:
  * always: a JSON Lines file per listing type in --out-dir
  * when SUPABASE_URL and SUPABASE_SERVICE_KEY are set: upserts into Supabase

Usage:
  python scrape.py --types sale rent                 # full run
  python scrape.py --types sale --max-pages 2 --dump-html debug/   # smoke test
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://www.commercialguru.com.sg"
PATHS = {"sale": "/property-for-sale", "rent": "/property-for-rent"}
USER_AGENT = (
    "Mozilla/5.0 (compatible; personal-research-scraper/1.0; "
    "+https://github.com/griffleschan1314182026-ui)"
)

LISTING_HREF = re.compile(r"/listing/for-(sale|rent)-[^\"'?#]*?-(\d{6,})(?:[/?#]|$)")
PRICE_RE = re.compile(r"S\$\s?([\d,]+(?:\.\d+)?)\s*(/\s?mo)?", re.I)
SQFT_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*sq\s?ft", re.I)
PSF_RE = re.compile(r"S\$\s?([\d,]+(?:\.\d+)?)\s*psf", re.I)
TENURE_RE = re.compile(r"(Freehold|\d+-year Leasehold|Not Applicable)", re.I)
POSTED_RE = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4})")
TOTAL_RE = re.compile(r"([\d,]+)\s+unit\(s\)", re.I)

PROPERTY_TYPES = [
    "Office", "Shop / Shophouse", "Food & Beverage", "Mall Shop", "Other Retail",
    "Medical", "Light Industrial (B1)", "Factory / Workshop (B2)", "Warehouse",
    "Dormitory", "Hotel", "Land", "Land Only", "Land with Building",
    "Retail", "Industrial", "Others",
]


class Blocked(RuntimeError):
    """The site refused us (captcha / bot wall). Stop rather than hammer it."""


def num(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


# --------------------------------------------------------------------------- fetch
def fetch(session: requests.Session, url: str, retries: int = 4) -> str:
    for attempt in range(retries):
        r = session.get(url, timeout=30)
        if r.status_code == 200:
            low = r.text[:4000].lower()
            if "cf-challenge" in low or "captcha" in low or "just a moment" in low:
                raise Blocked(f"bot challenge at {url}")
            return r.text
        if r.status_code in (403, 401):
            raise Blocked(f"HTTP {r.status_code} at {url}")
        if r.status_code == 404:
            return ""
        # 429 / 5xx: back off politely
        time.sleep(min(120, 10 * 2 ** attempt))
    raise RuntimeError(f"giving up on {url}")


# --------------------------------------------------------------------------- parse
def _jsonld_listings(soup: BeautifulSoup, listing_type: str) -> list[dict]:
    """Some PropertyGuru-family pages embed an ItemList in JSON-LD; use it if present."""
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data.get("itemListElement", []) if isinstance(data, dict) else []
        for it in items:
            item = it.get("item", it) if isinstance(it, dict) else {}
            url = item.get("url", "")
            m = LISTING_HREF.search(url)
            if not m:
                continue
            offer = item.get("offers") or {}
            out.append({
                "listing_id": int(m.group(2)),
                "listing_type": listing_type,
                "url": url,
                "title": item.get("name"),
                "price_sgd": num(str(offer.get("price"))) if offer.get("price") else None,
            })
    return out


def _card_for(anchor, listing_id: str):
    """Walk up from a listing link to the largest ancestor that holds only this listing."""
    node, best = anchor, anchor
    for _ in range(12):
        node = node.parent
        if node is None or node.name in ("body", "html"):
            break
        ids = {m.group(2) for a in node.find_all("a", href=True)
               if (m := LISTING_HREF.search(a["href"]))}
        if ids - {listing_id}:
            break
        best = node
    return best


def _lines(card) -> list[str]:
    return [t.strip() for t in card.get_text("\n").split("\n") if t.strip()]


def parse_card(card, listing_id: str, href: str, listing_type: str) -> dict:
    text = " ".join(_lines(card))
    lines = _lines(card)

    title = None
    for a in card.find_all("a", href=True):
        if listing_id in a["href"]:
            t = a.get("title") or a.get_text(" ", strip=True)
            if t and (title is None or len(t) > len(title)):
                title = t

    # Titles often contain numbers ("3,875 sqft", "$6800"); match on the rest.
    if title:
        text = text.replace(title, " ")
        lines = [l for l in lines if l != title]

    price = psf = None
    psf_m = PSF_RE.search(text)
    if psf_m:
        psf = num(psf_m.group(1))
    for m in PRICE_RE.finditer(text):
        if psf_m and m.start() == psf_m.start():
            continue
        price = num(m.group(1))
        break
    sqft_m = SQFT_RE.search(text)
    area = num(sqft_m.group(1)) if sqft_m else None
    if psf is None and price and area:
        psf = round(price / area, 2)

    ptype = next((l for l in lines if l in PROPERTY_TYPES), None)
    location = next(
        (l for l in lines if " / " in l and l not in PROPERTY_TYPES and "S$" not in l and len(l) < 60),
        None,
    )
    tenure_m = TENURE_RE.search(text)
    posted_m = POSTED_RE.search(text)

    agency = next((l for l in lines if re.search(r"\b(PTE\.?\s*LTD|LIMITED|REALTY)\b", l)), None)

    return {
        "listing_id": int(listing_id),
        "listing_type": listing_type,
        "url": href if href.startswith("http") else BASE + href,
        "title": title,
        "price_sgd": price,
        "floor_area_sqft": area,
        "psf_sgd": psf,
        "property_type": ptype,
        "location": location,
        "tenure": tenure_m.group(1) if tenure_m else None,
        "agency": agency,
        "posted_on": (dt.datetime.strptime(posted_m.group(1), "%b %d, %Y").date().isoformat()
                      if posted_m else None),
    }


def parse_page(html: str, listing_type: str) -> tuple[list[dict], int | None]:
    soup = BeautifulSoup(html, "lxml")
    total_m = TOTAL_RE.search(soup.get_text(" "))
    total = int(total_m.group(1).replace(",", "")) if total_m else None

    seen: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        m = LISTING_HREF.search(a["href"])
        if not m or m.group(1) != listing_type or m.group(2) in seen:
            continue
        lid = m.group(2)
        seen[lid] = parse_card(_card_for(a, lid), lid, a["href"].split("?")[0], listing_type)

    # Fill gaps (e.g. title/price) from JSON-LD when the page has it.
    for j in _jsonld_listings(soup, listing_type):
        row = seen.setdefault(str(j["listing_id"]), j)
        for k, v in j.items():
            if row.get(k) is None and v is not None:
                row[k] = v
    return list(seen.values()), total


# --------------------------------------------------------------------------- store
class Supabase:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/") + "/rest/v1"
        self.h = {"apikey": key, "Content-Type": "application/json"}
        # Legacy service_role keys are JWTs and also go in Authorization.
        # New sb_secret_ keys must not: Supabase rejects them there with 401.
        if key.startswith("eyJ"):
            self.h["Authorization"] = f"Bearer {key}"

    def upsert(self, table: str, rows: list[dict], conflict: str) -> None:
        for i in range(0, len(rows), 500):
            r = requests.post(
                f"{self.url}/{table}?on_conflict={conflict}",
                headers={**self.h, "Prefer": "resolution=merge-duplicates,return=minimal"},
                data=json.dumps(rows[i:i + 500]), timeout=60)
            r.raise_for_status()

    def insert(self, table: str, row: dict) -> dict:
        r = requests.post(f"{self.url}/{table}",
                          headers={**self.h, "Prefer": "return=representation"},
                          data=json.dumps(row), timeout=30)
        r.raise_for_status()
        return r.json()[0]

    def patch(self, table: str, match: str, row: dict) -> None:
        r = requests.patch(f"{self.url}/{table}?{match}", headers=self.h,
                           data=json.dumps(row), timeout=30)
        r.raise_for_status()


# --------------------------------------------------------------------------- main
# Set when the site blocks us, so the other listing type stops too.
STOP = threading.Event()


def scrape_type(session, listing_type, max_pages, delay, dump_dir):
    rows: dict[int, dict] = {}
    page, last_page = 1, None
    while True:
        if STOP.is_set():
            raise Blocked("stopped: the other listing type was blocked")
        url = f"{BASE}{PATHS[listing_type]}" + (f"/{page}" if page > 1 else "")
        html = fetch(session, url)
        if dump_dir and page <= 3:
            Path(dump_dir, f"{listing_type}-{page}.html").write_text(html, encoding="utf-8")
        found, total = parse_page(html, listing_type) if html else ([], None)
        if total and last_page is None:
            last_page = -(-total // 20)
            print(f"[{listing_type}] site reports {total} listings (~{last_page} pages)", flush=True)
        new = [r for r in found if r["listing_id"] not in rows]
        for r in found:
            rows[r["listing_id"]] = r
        print(f"[{listing_type}] page {page}: {len(found)} cards, {len(new)} new", flush=True)
        if not new:
            break  # past the last page (site repeats or returns empty)
        if max_pages and page >= max_pages:
            break
        if last_page and page >= last_page + 2:
            break
        page += 1
        time.sleep(delay + random.uniform(0, delay / 2))
    return list(rows.values()), page


def load_env_file() -> None:
    """Read KEY=value lines from a .env file at the repo root (for local runs)."""
    env = Path(__file__).resolve().parents[1] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--types", nargs="+", default=["sale", "rent"], choices=list(PATHS))
    ap.add_argument("--max-pages", type=int, default=0, help="0 = all pages")
    ap.add_argument("--delay", type=float, default=0.6, help="seconds between page requests")
    ap.add_argument("--out-dir", default="output")
    ap.add_argument("--dump-html", default=None, help="save first 3 raw pages here for debugging")
    args = ap.parse_args()

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    if args.dump_html:
        Path(args.dump_html).mkdir(parents=True, exist_ok=True)

    load_env_file()
    sb = None
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"):
        sb = Supabase(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    today = dt.date.today().isoformat()

    def run_type(t: str) -> int:
        # Each type gets its own connection; Buy and Rent run side by side.
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-SG,en;q=0.9"})
        run = None
        try:
            run = sb.insert("scrape_runs", {"listing_type": t, "status": "running"}) if sb else None
            rows, pages = scrape_type(session, t, args.max_pages, args.delay, args.dump_html)
            out = Path(args.out_dir, f"{t}-{today}.jsonl")
            out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
            print(f"[{t}] {len(rows)} listings -> {out}", flush=True)
            if sb:
                keys = ["listing_id", "listing_type", "url", "title", "price_sgd",
                        "floor_area_sqft", "psf_sgd", "property_type", "location",
                        "tenure", "agency", "posted_on"]
                # PostgREST bulk upserts need every row to carry the same keys.
                rows = [{**{k: r.get(k) for k in keys}, "last_seen": today} for r in rows]
                sb.upsert("listings", rows, "listing_id")
                # Partial (--max-pages) runs must not make unseen listings look delisted.
                complete = not args.max_pages
                sb.patch("scrape_runs", f"id=eq.{run['id']}", {
                    "status": "complete" if complete else "partial",
                    "pages": pages, "listings": len(rows),
                    "finished_at": dt.datetime.now(dt.timezone.utc).isoformat()})
            return 0
        except Exception as e:  # record the failure; the other type carries on unless blocked
            print(f"[{t}] FAILED: {e}", file=sys.stderr, flush=True)
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 401:
                print("    Supabase refused the key. Check SUPABASE_SERVICE_KEY in .env is the "
                      "secret (sb_secret_...) or service_role key, not the publishable one.",
                      file=sys.stderr, flush=True)
            if isinstance(e, Blocked):
                STOP.set()
            if sb and run:
                try:
                    sb.patch("scrape_runs", f"id=eq.{run['id']}",
                             {"status": "failed", "error": str(e)[:500],
                              "finished_at": dt.datetime.now(dt.timezone.utc).isoformat()})
                except requests.RequestException:
                    pass
            return 1

    with ThreadPoolExecutor(max_workers=len(args.types)) as pool:
        exit_code = max(pool.map(run_type, args.types))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
