"""Parser test against a fixture shaped like CommercialGuru search-result cards.

The fixture is synthetic (built from real page-1 listings captured 2026-10-06),
so it checks the parsing logic, not the live markup. Run the workflow with
max_pages=2 to check against the real site; raw pages are saved for debugging.
"""
import html, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scraper"))
from scrape import parse_page  # noqa: E402

def card(r):
    e = html.escape
    price = f"S$ {r['price_sgd']:,.0f}" + (" /mo" if r["listing_type"] == "rent" else "")
    href = r["url"].replace("https://www.commercialguru.com.sg", "")
    return f"""
<div class="listing-card"><a href="{href}"><img alt=""></a>
 <div class="card-body">
  <h3><a href="{href}?ref=search" title="{e(r['title'])}">{e(r['title'])}</a></h3>
  <div class="price">{price}</div>
  <ul><li>{r['floor_area_sqft']:,.0f} sqft</li><li>S$ {r['psf_sgd']:,.2f} psf</li></ul>
  <span class="type">{e(r['property_type'])}</span>
  <span class="loc">{e(r['location'])}</span>
  {f"<span>{r['tenure']}</span>" if r['tenure'] else ""}
  <div class="agent"><span>Agent</span>{f"<span>{e(r['agency'])}</span>" if r['agency'] else ""}</div>
  <time>Listed on Oct 05, 2026 (8h ago)</time>
 </div></div>"""

def test_parse_fixture():
    rows = json.loads((ROOT / "data" / "sample_listings.json").read_text())
    for typ in ("sale", "rent"):
        want = [r for r in rows if r["listing_type"] == typ]
        page = ("<html><body><h1>9,469 unit(s) of Commercial Properties</h1>"
                + "".join(card(r) for r in want)
                + '<nav><a href="/property-for-sale/2">2</a></nav></body></html>')
        got, total = parse_page(page, typ)
        assert total == 9469
        assert len(got) == len(want), (typ, len(got))
        by_id = {g["listing_id"]: g for g in got}
        for w in want:
            g = by_id[w["listing_id"]]
            assert g["title"] == w["title"], (g["title"], w["title"])
            assert g["price_sgd"] == w["price_sgd"]
            assert g["floor_area_sqft"] == w["floor_area_sqft"]
            assert abs(g["psf_sgd"] - w["psf_sgd"]) < 0.01
            assert g["property_type"] == w["property_type"]
            assert g["location"] == w["location"]
            assert g["tenure"] == w["tenure"]
            assert g["agency"] == w["agency"]
            assert g["url"].endswith(str(w["listing_id"]))
            assert g["posted_on"] == "2026-10-05"

if __name__ == "__main__":
    test_parse_fixture(); print("parser test passed")
