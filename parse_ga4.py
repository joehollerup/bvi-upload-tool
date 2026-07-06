#!/usr/bin/env python3
"""Parse a single-month GA4 Traffic Acquisition CSV: Direct vs Organic sessions.

GA4 Traffic Acquisition exports have no built-in monthly dimension, so a raw
export can be one of two shapes:

  Shape A: full-range aggregate — one row per channel, no date column,
           covers many months summed together. Useless for MoM scoring.
           Detected via (End date - Start date) > 31 days. Rejected.

  Shape B: single-month export — one row per channel, date range in the
           CSV header comments ("# Start date: YYYYMMDD"). One file per
           month. This is the supported format.
"""

import sys
from datetime import datetime

FILES = [
    "KEEN - GA4 Traffic Acquisition.csv",
    "Traffic_acquisition_Session_primary_channel_group_(Default_Channel_Group).csv",
]

MAX_SPAN_DAYS = 31


def _log(msg):
    print(f"[parse_ga4] {msg}", file=sys.stderr)


class GA4ParseError(Exception):
    """Raised when a GA4 CSV is rejected or malformed. Message is user-facing."""


def read(path):
    with open(path) as f:
        return [line.rstrip("\n") for line in f]


def meta_date(lines, label):
    for line in lines:
        if line.startswith("#") and label in line:
            digits = line.split(":", 1)[1].strip()
            return datetime.strptime(digits, "%Y%m%d")
    raise ValueError(f"{label} not found")


def cell(row):
    return [c.strip().strip('"') for c in row.split(",")]


def _parse_file(path, verbose=True):
    """Parse one GA4 CSV. Returns (month_str, {direct, organic, total, direct_pct}).

    Raises GA4ParseError with a user-facing reason on rejection/malformed input.
    """
    log = _log if verbose else (lambda msg: None)
    log(f"── Parsing: {path}")

    try:
        lines = read(path)
    except Exception as e:
        log(f"REJECTED: could not read file ({e})")
        raise GA4ParseError(f"Could not read file: {e}")

    log(f"  {len(lines)} lines read")

    comment_lines = [l for l in lines if l.startswith("#")]
    log(f"  {len(comment_lines)} comment line(s) found:")
    for c in comment_lines:
        log(f"    {c!r}")

    try:
        start = meta_date(lines, "Start date")
    except ValueError:
        log("REJECTED: no '# Start date: YYYYMMDD' comment line found")
        raise GA4ParseError(
            "Missing 'Start date' header comment — this doesn't look like a "
            "standard GA4 Traffic Acquisition export."
        )

    try:
        end = meta_date(lines, "End date")
    except ValueError:
        log("REJECTED: no '# End date: YYYYMMDD' comment line found")
        raise GA4ParseError(
            "Missing 'End date' header comment — this doesn't look like a "
            "standard GA4 Traffic Acquisition export."
        )

    span_days = (end - start).days
    log(f"  Start date: {start:%Y-%m-%d}   End date: {end:%Y-%m-%d}   span: {span_days} days")

    if span_days > MAX_SPAN_DAYS:
        log(f"REJECTED: Shape A (aggregate) — spans {span_days} days, max is {MAX_SPAN_DAYS}")
        raise GA4ParseError(
            f"spans {span_days} days ({start:%b %Y}–{end:%b %Y}) — that's a "
            f"multi-month aggregate export, not a single month. Re-export from "
            f"GA4 with the date range set to exactly one calendar month."
        )

    log(f"  Shape B (single-month) — target month {start:%Y-%m}")

    data = [l for l in lines if l.strip() and not l.startswith("#")]
    if not data:
        log("REJECTED: no data rows found after stripping comments")
        raise GA4ParseError("No data rows found in file after the header comments.")

    header = cell(data[0])
    log(f"  header: {header}")

    if "Sessions" not in header:
        log("REJECTED: no 'Sessions' column in header")
        raise GA4ParseError(
            f"No 'Sessions' column found in header ({header[:3]}...). "
            f"Make sure the export includes the Sessions metric."
        )
    si = header.index("Sessions")

    direct = organic = total = 0
    found_direct = found_organic = False
    channel_rows = []
    for row in data[1:]:
        cols = cell(row)
        name = cols[0].lower()
        try:
            val = int(cols[si])
        except (ValueError, IndexError):
            continue
        channel_rows.append((cols[0], val))
        total += val
        if name == "direct":
            direct = val
            found_direct = True
        elif name.startswith("organic"):
            organic = val
            found_organic = True

    log(f"  channel rows found: {channel_rows}")
    log(f"  direct={'FOUND' if found_direct else 'not found (0)'} ({direct}), "
        f"organic={'FOUND' if found_organic else 'not found (0)'} ({organic}), total={total}")

    if not channel_rows:
        log("REJECTED: no channel rows found under the header")
        raise GA4ParseError("No channel rows found under the header row.")

    direct_pct = direct / total * 100 if total else 0.0
    log(f"  ACCEPTED: {start:%Y-%m} → direct={direct} organic={organic} "
        f"total={total} direct_pct={direct_pct:.1f}%")

    return f"{start:%Y-%m}", {
        "direct": direct, "organic": organic, "total": total,
        "direct_pct": direct_pct,
    }


def parse(path):
    """CLI debug helper — prints a human-readable summary for one file."""
    print(f"\n=== {path} ===")
    try:
        month, d = _parse_file(path, verbose=True)
    except GA4ParseError as e:
        print(f"REJECTED: {e}")
        return
    print(f"Month:           {month}")
    print(f"Direct sessions: {d['direct']:,}")
    print(f"Organic sessions:{d['organic']:,}")
    print(f"Total sessions:  {d['total']:,}")
    print(f"Direct %:        {d['direct_pct']:.1f}%")


def load_from_with_diagnostics(paths, verbose=True):
    """Parse each GA4 file, never raising — collects a diagnostic per file.

    Returns (data_dict, diagnostics) where data_dict is {YYYY-MM: {...}} for
    every accepted file, and diagnostics is a list of dicts:
        {"path": str, "status": "accepted"|"rejected", "reason": str|None, "month": str|None}
    """
    out = {}
    diagnostics = []
    for path in paths:
        try:
            month, data = _parse_file(path, verbose=verbose)
            out[month] = data
            diagnostics.append({
                "path": path, "status": "accepted", "reason": None, "month": month,
            })
        except GA4ParseError as e:
            diagnostics.append({
                "path": path, "status": "rejected", "reason": str(e), "month": None,
            })
        except Exception as e:
            if verbose:
                _log(f"REJECTED: unexpected error parsing {path}: {e}")
            diagnostics.append({
                "path": path, "status": "rejected",
                "reason": f"Unexpected error while parsing: {e}", "month": None,
            })
    return out, diagnostics


def load():
    """Return {YYYY-MM: {direct, organic, total, direct_pct}} for valid single-month files.

    Aggregate exports (span > 31 days) are rejected and omitted.
    """
    out, _ = load_from_with_diagnostics(FILES, verbose=False)
    return out


def load_from(paths):
    """Like load() but accepts an explicit list of file paths instead of hardcoded FILES.

    Silently omits rejected/malformed files, matching the historical behavior.
    Use load_from_with_diagnostics() to see why a file was rejected.
    """
    out, _ = load_from_with_diagnostics(paths, verbose=False)
    return out


def main():
    for path in FILES:
        parse(path)

if __name__ == "__main__":
    main()
