#!/usr/bin/env python3
"""Download UCDP API data with filters and save as CSV. Stdlib only.

Examples:
  python ucdp_download.py                       # DRC (490), 2025-2026, GED events
  python ucdp_download.py --country 490,500 --start 2024-01-01 --end 2024-12-31
  python ucdp_download.py --resource ucdpprioconflict --country ""   # no filters
Token is read from api.txt (last whitespace-separated token) or $UCDP_TOKEN.
"""
import argparse, csv, json, os, sys, urllib.request
from pathlib import Path

BASE = "https://ucdpapi.pcr.uu.se/api"
HERE = Path(__file__).parent


def token():
    if os.environ.get("UCDP_TOKEN"):
        return os.environ["UCDP_TOKEN"]
    return (HERE / "api.txt").read_text().split()[-1]


def fetch(url, tok):
    req = urllib.request.Request(url, headers={"x-ucdp-access-token": tok})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def download(resource, version, params, tok, pagesize=1000):
    qs = "&".join(f"{k}={v}" for k, v in {**params, "pagesize": pagesize}.items() if v)
    url = f"{BASE}/{resource}/{version}?{qs}"
    rows = []
    while url:  # follow NextPageUrl until empty
        page = fetch(url, tok)
        rows += page["Result"]
        print(f"  {len(rows)}/{page['TotalCount']}", file=sys.stderr)
        url = page.get("NextPageUrl") or None
    return rows


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--resource", default="gedevents")
    a.add_argument("--version", default="26.1")
    a.add_argument("--country", default="490", help="Gleditsch-Ward codes, comma-separated (490 = DR Congo)")
    a.add_argument("--start", default="2025-01-01", help="StartDate YYYY-MM-DD")
    a.add_argument("--end", default="2026-12-31", help="EndDate YYYY-MM-DD")
    a.add_argument("--type-of-violence", default="", help="1,2,3 (GED only)")
    a.add_argument("--out", default="")
    a = a.parse_args()

    # Date filters only apply to GED events; other resources are filtered by Country/year server-side or after.
    params = {"Country": a.country, "TypeOfViolence": a.type_of_violence}
    if a.resource == "gedevents":
        params |= {"StartDate": a.start, "EndDate": a.end}

    rows = download(a.resource, a.version, params, token())
    if not rows:
        sys.exit("No rows returned.")
    out = Path(a.out or HERE / f"{a.resource}_{a.country or 'all'}_{a.start[:4]}-{a.end[:4]}.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
