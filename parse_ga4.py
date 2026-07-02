#!/usr/bin/env python3
"""Parse a single-month GA4 Traffic Acquisition CSV: Direct vs Organic sessions."""

import sys
from datetime import datetime

FILES = [
    "KEEN - GA4 Traffic Acquisition.csv",
    "Traffic_acquisition_Session_primary_channel_group_(Default_Channel_Group).csv",
]

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

def parse(path):
    print(f"\n=== {path} ===")
    lines = read(path)

    start = meta_date(lines, "Start date")
    end = meta_date(lines, "End date")
    if (end - start).days > 31:
        print("Aggregate export detected. Need single-month exports.")
        return

    data = [l for l in lines if l.strip() and not l.startswith("#")]
    header = cell(data[0])
    sessions_idx = header.index("Sessions")

    direct = organic = total = 0
    for row in data[1:]:
        cols = cell(row)
        name = cols[0].lower()
        val = int(cols[sessions_idx])
        total += val
        if name == "direct":
            direct = val
        elif name.startswith("organic"):
            organic = val

    print(f"Month:           {start:%Y-%m}")
    print(f"Direct sessions: {direct:,}")
    print(f"Organic sessions:{organic:,}")
    print(f"Total sessions:  {total:,}")
    print(f"Direct %:        {direct / total:.1%}")

def load():
    """Return {YYYY-MM: {direct, organic, total, direct_pct}} for valid single-month files.

    Aggregate exports (span > 31 days) are rejected and omitted.
    """
    out = {}
    for path in FILES:
        lines = read(path)
        start = meta_date(lines, "Start date")
        end = meta_date(lines, "End date")
        if (end - start).days > 31:
            continue  # aggregate export rejected
        data = [l for l in lines if l.strip() and not l.startswith("#")]
        header = cell(data[0])
        si = header.index("Sessions")
        direct = organic = total = 0
        for row in data[1:]:
            cols = cell(row)
            name = cols[0].lower()
            val = int(cols[si])
            total += val
            if name == "direct":
                direct = val
            elif name.startswith("organic"):
                organic = val
        out[f"{start:%Y-%m}"] = {
            "direct": direct, "organic": organic, "total": total,
            "direct_pct": direct / total * 100 if total else 0.0,
        }
    return out


def load_from(paths):
    """Like load() but accepts an explicit list of file paths instead of hardcoded FILES."""
    out = {}
    for path in paths:
        try:
            lines = read(path)
            start = meta_date(lines, "Start date")
            end = meta_date(lines, "End date")
            if (end - start).days > 31:
                continue
            data = [l for l in lines if l.strip() and not l.startswith("#")]
            header = cell(data[0])
            si = header.index("Sessions")
            direct = organic = total = 0
            for row in data[1:]:
                cols = cell(row)
                name = cols[0].lower()
                val = int(cols[si])
                total += val
                if name == "direct":
                    direct = val
                elif name.startswith("organic"):
                    organic = val
            out[f"{start:%Y-%m}"] = {
                "direct": direct, "organic": organic, "total": total,
                "direct_pct": direct / total * 100 if total else 0.0,
            }
        except Exception:
            continue
    return out


def main():
    for path in FILES:
        parse(path)

if __name__ == "__main__":
    main()
