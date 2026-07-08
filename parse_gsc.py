#!/usr/bin/env python3
"""Parse a GSC ZIP export: monthly totals + branded share applied to clicks/impressions."""

import os
import sys
import traceback
import zipfile

ZIP_PATH = "KEEN - GSC Zip File.zip"
EXTRACT_DIR = "gsc_extract"


def _log(msg):
    print(f"[parse_gsc] {msg}", file=sys.stderr)


def _log_zip_contents(zip_path):
    """Log every filename inside the ZIP (before extraction) — helps spot a
    renamed/relocated file in an export from a different GSC property/UI."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
        _log(f"ZIP {zip_path!r} contains {len(names)} entries:")
        for n in names:
            _log(f"  {n!r}")
    except Exception as e:
        _log(f"Could not list ZIP contents for {zip_path!r}: {e}")


def _log_file_head_bytes(path, n=5):
    """Log the first n lines of a file as raw bytes — catches encoding issues
    (BOM, UTF-16, CRLF vs LF) that a text-mode open() can mask or choke on."""
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
        lines = raw.split(b"\n")[:n]
        _log(f"First {len(lines)} raw line(s) of {path!r}:")
        for i, line in enumerate(lines):
            _log(f"  [{i}] {line!r}")
    except Exception as e:
        _log(f"Could not read raw bytes of {path!r}: {e}")


def find_file(name):
    for root, _, files in os.walk(EXTRACT_DIR):
        if name in files:
            return os.path.join(root, name)
    _log(f"'{name}' not found under {EXTRACT_DIR!r}. Files actually present:")
    for root, _, files in os.walk(EXTRACT_DIR):
        for fn in files:
            _log(f"  {os.path.join(root, fn)!r}")
    raise FileNotFoundError(name)


def read_rows(path):
    with open(path) as f:
        lines = [line.strip() for line in f if line.strip()]
    return [[cell.strip().strip('"') for cell in line.split(",")] for line in lines]


def load():
    """Return {'share': float, 'months': {YYYY-MM: {clicks, impr, br_clicks, br_impr}}}."""
    _log_zip_contents(ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(EXTRACT_DIR)

    try:
        queries_path = find_file("Queries.csv")
        _log_file_head_bytes(queries_path)
        q_rows = read_rows(queries_path)[1:]  # skip header
        total_clicks = sum(int(r[1]) for r in q_rows)
        branded_clicks = sum(int(r[1]) for r in q_rows if "keen" in r[0].lower())
        share = branded_clicks / total_clicks

        chart_path = find_file("Chart.csv")
        _log_file_head_bytes(chart_path)
        chart = read_rows(chart_path)[1:]  # skip header
        months = {}
        for date, clicks, impr, *_ in chart:
            m = months.setdefault(date[:7], {"clicks": 0, "impr": 0})
            m["clicks"] += int(clicks)
            m["impr"] += int(impr)
        for m in months.values():
            m["br_clicks"] = m["clicks"] * share
            m["br_impr"] = m["impr"] * share
    except Exception:
        _log("EXCEPTION while parsing GSC export:")
        _log(traceback.format_exc())
        raise

    return {"share": share, "months": months}


def load_from(zip_path, extract_dir, brand_key):
    """Like load() but with explicit paths, brand key for branded share, plus position/ctr."""
    _log_zip_contents(zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)

    def _find(name):
        for root, _, files in os.walk(extract_dir):
            if name in files:
                return os.path.join(root, name)
        _log(f"'{name}' not found under {extract_dir!r}. Files actually present:")
        for root, _, files in os.walk(extract_dir):
            for fn in files:
                _log(f"  {os.path.join(root, fn)!r}")
        raise FileNotFoundError(name)

    try:
        queries_path = _find("Queries.csv")
        _log_file_head_bytes(queries_path)
        q_rows = read_rows(queries_path)[1:]
        total_clicks = sum(int(r[1]) for r in q_rows)
        brand_lower = brand_key.lower()
        branded_clicks = sum(int(r[1]) for r in q_rows if brand_lower in r[0].lower())
        share = branded_clicks / total_clicks if total_clicks else 0.0

        chart_path = _find("Chart.csv")
        _log_file_head_bytes(chart_path)
        chart = read_rows(chart_path)[1:]
        months = {}
        pos_acc = {}
        for row in chart:
            date, clicks, impr, c_ctr, c_pos = row[0], row[1], row[2], row[3], row[4]
            mo = date[:7]
            m = months.setdefault(mo, {"clicks": 0, "impr": 0})
            m["clicks"] += int(clicks)
            m["impr"] += int(impr)
            a = pos_acc.setdefault(mo, [0.0, 0])
            a[0] += float(c_pos) * int(impr)
            a[1] += int(impr)

        for m in months.values():
            m["br_clicks"] = m["clicks"] * share
            m["br_impr"] = m["impr"] * share

        position = {mo: a[0] / a[1] for mo, a in pos_acc.items() if a[1] > 0}
        ctr = {mo: months[mo]["clicks"] / months[mo]["impr"] * 100
               for mo in months if months[mo]["impr"] > 0}
    except Exception:
        _log("EXCEPTION while parsing GSC export:")
        _log(traceback.format_exc())
        raise

    return {"share": share, "months": months, "position": position, "ctr": ctr}


def main():
    data = load()
    share, months = data["share"], data["months"]
    print(f"Branded share: {share:.2%}\n")
    print(f"{'Month':<9}{'Clicks':>10}{'Impressions':>14}{'CTR':>8}"
          f"{'Brand %':>9}{'Br.Clicks':>11}{'Br.Impr':>12}")
    for month in sorted(months):
        clicks, impr = months[month]["clicks"], months[month]["impr"]
        ctr = clicks / impr if impr else 0
        print(f"{month:<9}{clicks:>10,}{impr:>14,}{ctr:>7.2%}"
              f"{share:>8.1%}{round(clicks * share):>11,}{round(impr * share):>12,}")


if __name__ == "__main__":
    main()
