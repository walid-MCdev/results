#!/usr/bin/env python3
"""
Fetch each student's individual result from the BISE Chattogram portal and
store it in data/details.json (incremental: already-fetched rolls are skipped).

Only the roll numbers that appear in your PDFs are requested (never a blind range).

Usage:
    python scripts/scrape_board.py                 # fetch missing rolls
    python scripts/scrape_board.py --refresh       # re-fetch everything
    python scripts/scrape_board.py --limit 5 --dump-html   # test: 5 rolls, save raw pages to debug_html/
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from hsc_parser import extract_text, parse

ROOT = Path(__file__).resolve().parent.parent
DETAILS_FILE = ROOT / "data" / "details.json"
BASE = "https://hscresult.bise-ctg.gov.bd/h22_31_x1_26/individual/"
POST_URL = BASE + "result_mark_details.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; hsc-result-search/1.0; personal project)",
    "Referer": BASE,
}
NAME_EXCLUDE = re.compile(r"father|mother|institute|college|school|centre|center|board|subject|group", re.I)


def clean(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip(" :\u00a0\t\r\n")


TITLE_CASE_KEYS = {"name", "board", "father's name", "mother's name", "group", "type", "institute"}
GRADE_MARKS = re.compile(r"^\s*([A-Z][+\-]?)\s*\(\s*(\d+)\s*\)\s*$")


def parse_result_html(html: str) -> dict | None:
    """Parse the board's individual result page. Returns None if it has no result sheet.

    Layout (as of HSC 2026): <div class="info"> holds label/value <div> pairs, and
    <table class="marks"> has rows like  "BANGLA (101) | B (106)".
    """
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one("div.info")
    if not info:
        return None

    cells = [clean(d.get_text(" ")) for d in info.find_all("div", recursive=False)]
    fields = {}
    for i in range(0, len(cells) - 1, 2):
        label, value = cells[i], cells[i + 1]
        if label.lower() in TITLE_CASE_KEYS:
            value = value.title()
        fields[label] = value
    if not fields:
        return None

    subjects = []
    for tr in soup.select("table.marks tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        code_el = tds[0].find(class_="code")
        code = clean(code_el.get_text()).strip("()") if code_el else ""
        if code_el:
            code_el.extract()
        raw = clean(tds[1].get_text(" "))
        m = GRADE_MARKS.match(raw)
        subjects.append({
            "subject": clean(tds[0].get_text(" ")).title(),
            "code": code,
            "grade": m.group(1) if m else raw,
            "marks": int(m.group(2)) if m else None,
        })

    return {
        "name": fields.get("Name", ""),
        "father": fields.get("Father's Name", ""),
        "mother": fields.get("Mother's Name", ""),
        "reg_no": fields.get("Reg. NO", ""),
        "session": fields.get("Session", ""),
        "fields": fields,
        "subjects": subjects,
        "total_marks": sum(x["marks"] or 0 for x in subjects),
    }


def fetch_roll(session: requests.Session, roll: str, retries: int = 3) -> tuple[str, str]:
    """Returns (status, html). status: ok | http_error | network_error"""
    last = "network_error"
    for attempt in range(retries):
        try:
            r = session.post(POST_URL, data={"roll": roll, "button2": ""}, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                r.encoding = "utf-8"
                return "ok", r.text
            last = "http_error"
            if r.status_code in (403, 429):
                return last, str(r.status_code)
        except requests.RequestException:
            last = "network_error"
        time.sleep(2 * (attempt + 1))
    return last, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", type=Path, default=ROOT / "pdfs")
    ap.add_argument("--refresh", action="store_true", help="re-fetch rolls already stored")
    ap.add_argument("--limit", type=int, help="only fetch this many rolls (for testing)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--dump-html", action="store_true", help="save raw responses to debug_html/")
    args = ap.parse_args()

    rolls = []
    for pdf in sorted(args.pdf_dir.glob("*.pdf")):
        rolls += [r["roll"] for r in parse(extract_text(pdf))["records"] if r["result"] != "ABSENT"]
    rolls = sorted(set(rolls))

    DETAILS_FILE.parent.mkdir(exist_ok=True)
    details = json.loads(DETAILS_FILE.read_text(encoding="utf-8")) if DETAILS_FILE.exists() else {}
    todo = [r for r in rolls if args.refresh or r not in details]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(rolls)} rolls in PDFs | {len(details)} already stored | fetching {len(todo)}")

    session = requests.Session()
    try:
        session.get(BASE, headers=HEADERS, timeout=25)  # pick up any cookies
    except requests.RequestException as e:
        print(f"Could not reach the portal: {e}", file=sys.stderr)
        sys.exit(1)

    dump_dir = ROOT / "debug_html"
    if args.dump_html:
        dump_dir.mkdir(exist_ok=True)

    fails_in_row = 0
    ok = missing = 0
    for i, roll in enumerate(todo, 1):
        status, html = fetch_roll(session, roll)
        if status != "ok":
            fails_in_row += 1
            print(f"[{i}/{len(todo)}] {roll}: {status} {html}")
            if fails_in_row >= 8 or html in ("403", "429"):
                print("Portal is refusing or blocking requests - stopping. Progress is saved.", file=sys.stderr)
                break
        else:
            fails_in_row = 0
            if args.dump_html:
                (dump_dir / f"{roll}.html").write_text(html, encoding="utf-8")
            parsed = parse_result_html(html)
            if parsed:
                details[roll] = parsed
                ok += 1
                print(f"[{i}/{len(todo)}] {roll}: {parsed['name'] or '(no name field found)'}")
            else:
                missing += 1
                print(f"[{i}/{len(todo)}] {roll}: no result data in response")

        if i % 25 == 0:
            DETAILS_FILE.write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(args.delay + random.uniform(0, 0.4))

    DETAILS_FILE.write_text(json.dumps(details, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Done. fetched={ok} no-data={missing} total stored={len(details)}")


if __name__ == "__main__":
    main()
