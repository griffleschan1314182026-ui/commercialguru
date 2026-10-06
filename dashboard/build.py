"""Embed data/sample_listings.json into the dashboard and write index.html for static hosting."""
import json, re, sys
from pathlib import Path
d = Path(__file__).parent
page = (d / "dashboard.html").read_text(encoding="utf-8")
sample = json.dumps(json.loads((d.parent / "data" / "sample_listings.json").read_text()), ensure_ascii=False)
page = re.sub(r"/\*SAMPLE_DATA\*/.*?/\*END_SAMPLE_DATA\*/", lambda m: f"/*SAMPLE_DATA*/{sample}/*END_SAMPLE_DATA*/", page, flags=re.S)
# The hosted copy (index.html) reads live data; the sample copy stays offline.
cfg = d / "config.json"
live = page.replace('const CONFIG = { supabaseUrl: "", anonKey: "" };',
                    "const CONFIG = " + cfg.read_text().strip() + ";") if cfg.exists() else page
out = Path(sys.argv[1]) if len(sys.argv) > 1 else d / "with-sample.html"
out.write_text(page, encoding="utf-8")
(d / "index.html").write_text('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    '<style>body{margin:0}[hidden]{display:none!important}</style>\n</head><body>\n' + live + "\n</body></html>\n", encoding="utf-8")
print("wrote", out, "and", d / "index.html")
