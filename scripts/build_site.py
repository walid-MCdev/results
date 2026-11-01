#!/usr/bin/env python3
"""Build the GitHub Pages site: one search page per PDF in pdfs/, plus an index."""
import html
import json
import shutil
import sys
from pathlib import Path

from hsc_parser import extract_text, load_names, parse

ROOT = Path(__file__).resolve().parent.parent
PDFS = sorted((ROOT / "pdfs").glob("*.pdf"))
SITE = ROOT / "site"
DATA = ROOT / "data"
TEMPLATE = (Path(__file__).parent / "search_template.html").read_text(encoding="utf-8")
NAMES_CSV = ROOT / "names.csv"
DETAILS_FILE = ROOT / "data" / "details.json"


def main():
    if not PDFS:
        sys.exit("No PDFs found in pdfs/")
    names = load_names(NAMES_CSV) if NAMES_CSV.exists() else {}
    print(f"Loaded {len(names)} names" if names else "No names in names.csv (roll search only)")

    scraped = json.loads(DETAILS_FILE.read_text(encoding="utf-8")) if DETAILS_FILE.exists() else {}
    print(f"Loaded scraped details for {len(scraped)} rolls")

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    DATA.mkdir(exist_ok=True)
    for old in DATA.glob("*.json"):
        if old.name != "details.json":
            old.unlink()
    (SITE / ".nojekyll").touch()

    entries = []
    for pdf in PDFS:
        data = parse(extract_text(pdf))
        for r in data["records"]:
            d = scraped.get(r["roll"])
            r["name"] = names.get(r["roll"]) or (d or {}).get("name", "")   # names.csv overrides scraped
            if d:
                r["father"], r["mother"] = d.get("father", ""), d.get("mother", "")
                r["total_marks"] = d.get("total_marks")
                r["details"] = {"fields": d.get("fields", {}), "subjects": d.get("subjects", [])}
        data["records"].sort(key=lambda r: r["roll"])

        meta = data["meta"]
        passed = sum(r["result"] == "PASS" for r in data["records"])
        if passed != int(meta.get("passed", passed)):
            sys.exit(f"{pdf.name}: parsed {passed} passes but PDF header says {meta['passed']}")

        out = SITE / pdf.stem
        out.mkdir()
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        (out / "results.json").write_text(payload, encoding="utf-8")   # served on the website
        (DATA / f"{pdf.stem}.json").write_text(payload, encoding="utf-8")  # committed to the repo
        (out / "index.html").write_text(
            TEMPLATE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
        entries.append((pdf.stem, meta.get("institute_name", pdf.stem), len(data["records"])))
        print(f"{pdf.name}: {len(data['records'])} records -> data/{pdf.stem}.json + site/{pdf.stem}/")

    if len(entries) == 1:
        slug = entries[0][0]
        index = f'<!DOCTYPE html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={slug}/"><a href="{slug}/">Open results</a>'
    else:
        items = "".join(
            f'<li><a href="{html.escape(s)}/">{html.escape(n)}</a> ({c} records)</li>' for s, n, c in entries)
        index = f'<!DOCTYPE html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HSC Results</title><body style="font-family:system-ui;max-width:700px;margin:40px auto;padding:0 16px"><h1>HSC Results</h1><ul>{items}</ul></body>'
    (SITE / "index.html").write_text(index, encoding="utf-8")


if __name__ == "__main__":
    main()
