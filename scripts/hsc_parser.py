#!/usr/bin/env python3
"""
HSC result PDF -> results.json + search.html

Usage:
    python hsc_parser.py HSC-Result-2026-104050.pdf
    python hsc_parser.py HSC-Result-2026-104050.pdf --names names.csv

Outputs (next to the PDF, or in --out):
    results.json   structured data you can query anywhere
    search.html    standalone search page (data embedded, works offline)

names.csv (optional) has two columns:  roll,name
The board PDF only lists roll numbers, so names must come from you.

Requires: pip install pdfplumber
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import pdfplumber

SECTION_RE = re.compile(r"^([A-Z][A-Z /&\-]+?)\s*\((\d+)\)\s*$")
ENTRY_RE = re.compile(r"(\d{5,7})\s*\[\s*([^\]]+?)\s*\]")
FAIL_TEXT = {
    "F": "Failed",
    "F1": "Failed (1 subject)",
    "F2": "Failed (2 subjects)",
    "ABS.": "Absent",
}


def grade_from_gpa(gpa: float) -> str:
    if gpa >= 5.0: return "A+"
    if gpa >= 4.0: return "A"
    if gpa >= 3.5: return "A-"
    if gpa >= 3.0: return "B"
    if gpa >= 2.0: return "C"
    if gpa >= 1.0: return "D"
    return "F"


def extract_text(pdf_path: Path) -> str:
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def parse(text: str) -> dict:
    meta, records = {}, {}
    group, passed_section = None, False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Header metadata
        m = re.match(r"^(INSTITUTE NAME|ZILLA|THANA|APPEARED|PASSED|PERCENT|GPA5)\s*:\s*(.+)$", line)
        if m:
            meta[m.group(1).lower().replace(" ", "_")] = m.group(2).strip()
            continue

        # Section header, e.g. "SCIENCE (40)"
        m = SECTION_RE.match(line)
        if m and "EXAMINEES" not in line:
            group = m.group(1).strip().title()
            passed_section = "UNSUCCESSFUL" not in m.group(1)
            continue

        if "EXAMINEES" in line:
            continue

        for roll, val in ENTRY_RE.findall(line):
            if roll in records:
                continue
            if val.upper() in FAIL_TEXT or not re.match(r"^\d+(\.\d+)?$", val):
                code = val.upper()
                records[roll] = {
                    "roll": roll,
                    "group": "Unsuccessful / Others",
                    "status": FAIL_TEXT.get(code, code),
                    "result": "ABSENT" if code.startswith("ABS") else "FAIL",
                    "code": code,
                    "gpa": None,
                    "grade": None,
                }
            else:
                gpa = float(val)
                records[roll] = {
                    "roll": roll,
                    "group": group,
                    "status": "Passed",
                    "result": "PASS",
                    "code": None,
                    "gpa": gpa,
                    "grade": grade_from_gpa(gpa),
                }
    return {"meta": meta, "records": list(records.values())}


def load_names(path: Path) -> dict:
    names = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) >= 2 and row[0].strip().isdigit():
                names[row[0].strip()] = row[1].strip()
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--names", type=Path, help="CSV with columns: roll,name")
    ap.add_argument("--out", type=Path, help="output directory (default: PDF's folder)")
    ap.add_argument("--template", type=Path, default=Path(__file__).with_name("search_template.html"))
    args = ap.parse_args()

    out = args.out or args.pdf.parent
    out.mkdir(parents=True, exist_ok=True)

    data = parse(extract_text(args.pdf))
    names = load_names(args.names) if args.names else {}
    for r in data["records"]:
        r["name"] = names.get(r["roll"], "")
    data["records"].sort(key=lambda r: r["roll"])

    # Sanity check against the totals printed in the PDF
    passed = sum(r["result"] == "PASS" for r in data["records"])
    expected = int(data["meta"].get("passed", passed))
    appeared = int(data["meta"].get("appeared", len(data["records"])))
    print(f"Parsed {len(data['records'])} rolls | passed {passed} (PDF says {expected}) | appeared (PDF says {appeared})")
    if passed != expected:
        print("WARNING: pass count does not match the PDF header", file=sys.stderr)

    payload = json.dumps(data, ensure_ascii=False, indent=2)
    (out / "results.json").write_text(payload, encoding="utf-8")
    print(f"Wrote {out / 'results.json'}")

    if args.template.exists():
        html = args.template.read_text(encoding="utf-8").replace(
            "/*__DATA__*/null", json.dumps(data, ensure_ascii=False)
        )
        (out / "search.html").write_text(html, encoding="utf-8")
        print(f"Wrote {out / 'search.html'}")
    else:
        print(f"Template not found: {args.template} (skipped search.html)", file=sys.stderr)


if __name__ == "__main__":
    main()
