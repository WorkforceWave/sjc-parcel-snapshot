#!/usr/bin/env python3
"""
Refresh the San Joaquin County parcel snapshot.

Downloads the county's public parcel file, reduces it to the columns the voice
agent lookup actually uses, and writes a gzipped CSV plus a meta.json.

The county exports at 23:30 UTC daily. Their export has failed before, producing
a header-only file, so every guard below exists to stop a bad export from
overwriting good data. The script exits non-zero and writes nothing rather than
publish a file it does not trust.

Output columns (no header, matching the Scout lookup block's parser):
    0 assessment         12-digit, no punctuation
    1 parcel_dashes      fee parcel id, dashed
    2 roll_category      CS = secured (real property), CU = unsecured
    3 address            street address as the county stores it
    4 city_state_zip
    5 bill_url           the county's own bill URL, verbatim
    6 assessment_dashes
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

SOURCE_URL = "https://app.sjgov.org/ttc/parceladdress.txt"
OUT_CSV_GZ = "sjc_parcels.csv.gz"
OUT_META = "meta.json"

# The county file has carried ~263k rows since we started tracking it. Anything
# far below that is an export failure, not a real drop in parcels.
MIN_ROWS = 200_000
# Even above the floor, refuse a file that lost more than 5% against the last
# good snapshot. Catches a partial export that still clears MIN_ROWS.
MAX_SHRINK = 0.05

# Column positions in the county's 13-column export.
C_ASSESSMENT, C_ROLL_CATEGORY = 0, 2
C_TAX_YEAR, C_ADDRESS, C_CITY, C_BILL_URL = 4, 5, 6, 7
C_ASSESSMENT_DASHES, C_PARCEL_DASHES = 8, 9
MIN_FIELDS = 10


def die(msg: str) -> None:
    print(f"REFUSING TO PUBLISH: {msg}", file=sys.stderr)
    sys.exit(1)


def fetch_source() -> tuple[str, str | None]:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "wfw-sjc-snapshot/1.0"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        if resp.status != 200:
            die(f"county returned HTTP {resp.status}")
        last_modified = resp.headers.get("Last-Modified")
        return resp.read().decode("utf-8", errors="replace"), last_modified


def previous_row_count() -> int:
    if not os.path.exists(OUT_META):
        return 0
    try:
        with open(OUT_META, encoding="utf-8") as fh:
            return int(json.load(fh).get("rows", 0))
    except (ValueError, OSError):
        return 0


def reduce_rows(text: str) -> tuple[list[list[str]], set[str]]:
    reader = csv.reader(io.StringIO(text))
    try:
        next(reader)  # discard the county's header
    except StopIteration:
        die("county file was empty")

    rows: list[list[str]] = []
    tax_years: set[str] = set()
    for field in reader:
        if len(field) < MIN_FIELDS:
            continue
        assessment = field[C_ASSESSMENT].strip()
        if not assessment:
            continue
        if field[C_TAX_YEAR].strip():
            tax_years.add(field[C_TAX_YEAR].strip())
        rows.append([
            assessment,
            field[C_PARCEL_DASHES].strip(),
            field[C_ROLL_CATEGORY].strip(),
            field[C_ADDRESS].strip(),
            field[C_CITY].strip(),
            field[C_BILL_URL].strip(),
            field[C_ASSESSMENT_DASHES].strip(),
        ])
    return rows, tax_years


def encode(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    # mtime=0 so an unchanged file produces identical bytes and no commit.
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))
    return out.getvalue()


def main() -> None:
    print(f"fetching {SOURCE_URL}")
    text, last_modified = fetch_source()
    print(f"  {len(text):,} chars, county Last-Modified: {last_modified}")

    rows, tax_years = reduce_rows(text)
    print(f"  parsed {len(rows):,} rows, tax year(s): {sorted(tax_years) or 'unknown'}")

    if len(rows) < MIN_ROWS:
        die(f"only {len(rows):,} rows (floor is {MIN_ROWS:,}) — county export looks broken")

    previous = previous_row_count()
    if previous and len(rows) < previous * (1 - MAX_SHRINK):
        die(f"{len(rows):,} rows is more than {MAX_SHRINK:.0%} below the last good {previous:,}")

    with_url = sum(1 for r in rows if r[5].startswith("http"))
    if with_url < len(rows) * 0.95:
        die(f"only {with_url:,} of {len(rows):,} rows carry a bill URL")

    payload = encode(rows)

    if os.path.exists(OUT_CSV_GZ):
        with open(OUT_CSV_GZ, "rb") as fh:
            if fh.read() == payload:
                print("no change since last snapshot — nothing to commit")
                return

    with open(OUT_CSV_GZ, "wb") as fh:
        fh.write(payload)

    meta = {
        "rows": len(rows),
        "tax_years": sorted(tax_years),
        "bytes_gz": len(payload),
        "source_url": SOURCE_URL,
        "source_last_modified": last_modified,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "columns": [
            "assessment", "parcel_dashes", "roll_category",
            "address", "city_state_zip", "bill_url", "assessment_dashes",
        ],
    }
    with open(OUT_META, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
        fh.write("\n")

    print(f"wrote {OUT_CSV_GZ} ({len(payload):,} bytes) and {OUT_META}")


if __name__ == "__main__":
    main()
