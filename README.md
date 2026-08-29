# SJC parcel snapshot

A daily mirror of San Joaquin County's public parcel file, used by the Treasurer–Tax
Collector voice agent to look up a caller's property and text them their tax bill link.

**Data only. Nothing deploys from this repo.**

## Why it exists

The county publishes the file openly at
[`app.sjgov.org/ttc/parceladdress.txt`](https://app.sjgov.org/ttc/parceladdress.txt) — 46.8 MB,
uncompressed, no compression support on their server. The lookup used to download and re-index
that entire file on *every single call*, which took 6.3 seconds on a good day and hung long
enough to fail the call on a bad one. Callers got "I cannot pull up that parcel on this line at
the moment."

This snapshot is the same data at roughly an eighth the size, so the lookup fetches it in about
0.6 seconds and the county's server is no longer in the call path.

## What's in it

`sjc_parcels.csv.gz` — gzipped CSV, no header, one row per assessment:

| # | Column | Notes |
|---|--------|-------|
| 0 | `assessment` | 12-digit, no punctuation |
| 1 | `parcel_dashes` | fee parcel id, dashed |
| 2 | `roll_category` | `CS` secured (real property), `CU` unsecured |
| 3 | `address` | as the county stores it — abbreviations are theirs |
| 4 | `city_state_zip` | |
| 5 | `bill_url` | the county's own bill URL, verbatim — never reconstructed |
| 6 | `assessment_dashes` | |

`meta.json` carries the row count, tax year, and the county's `Last-Modified` for the source
file the snapshot was built from.

**No owner names.** The county does not publish them and the agent is not permitted to disclose
them. This snapshot also drops three columns the county does publish and we have no use for:
`BoatNumber`, `AircraftNumber`, and `DecalNum`.

## How it refreshes

`.github/workflows/refresh.yml` runs daily at 23:45 UTC — fifteen minutes after the county's own
23:30 UTC export — and commits only when the content actually changed.

The county's export has failed before, on 2026-07-03, producing a header-only file. Every guard
in `scripts/refresh.py` exists because of that: the script refuses to publish a file with fewer
than 200,000 rows, one that shrank more than 5% against the last good snapshot, or one where
fewer than 95% of rows carry a bill URL. When it refuses it writes nothing and exits non-zero, so
the last good snapshot stays in place and the run shows as failed.

Run it by hand from the Actions tab (`workflow_dispatch`) if you need an off-schedule refresh.

## Tax year

The county rolls the tax year each July, which changes every `bill_url`. The daily refresh picks
that up on its own — `meta.json` records which year the current snapshot holds.
