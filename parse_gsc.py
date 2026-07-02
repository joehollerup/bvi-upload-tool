#!/usr/bin/env python3
"""Parse a GSC ZIP export: monthly totals + branded share applied to clicks/impressions."""

import zipfile
import os

ZIP_PATH = "KEEN - GSC Zip File.zip"
EXTRACT_DIR = "gsc_extract"


def find_file(name):
    for root, _, files in os.walk(EXTRACT_DIR):
        if name in files:
            return os.path.join(root, name)
    raise FileNotFoundError(name)


def read_rows(path):
    with open(path) as f:
        lines = [line.strip() for line in f if line.strip()]
    return [[cell.strip().strip('"') for cell in line.split(",")] for line in lines]


def load():
    """Return {'share': float, 'months': {YYYY-MM: {clicks, impr, br_clicks, br_impr}}}."""
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(EXTRACT_DIR)

    # Branded share from Queries.csv
    q_rows = read_rows(find_file("Queries.csv"))[1:]  # skip header
    total_clicks = sum(int(r[1]) for r in q_rows)
    branded_clicks = sum(int(r[1]) for r in q_rows if "keen" in r[0].lower())
    share = branded_clicks / total_clicks

    # Monthly aggregation from Chart.csv
    chart = read_rows(find_file("Chart.csv"))[1:]  # skip header
    months = {}
    for date, clicks, impr, *_ in chart:
        m = months.setdefault(date[:7], {"clicks": 0, "impr": 0})
        m["clicks"] += int(clicks)
        m["impr"] += int(impr)
    for m in months.values():
        m["br_clicks"] = m["clicks"] * share
        m["br_impr"] = m["impr"] * share
    return {"share": share, "months": months}


def load_from(zip_path, extract_dir, brand_key):
    """Like load() but with explicit paths, brand key for branded share, plus position/ctr."""
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(extract_dir)

    def _find(name):
        for root, _, files in os.walk(extract_dir):
            if name in files:
                return os.path.join(root, name)
        raise FileNotFoundError(name)

    q_rows = read_rows(_find("Queries.csv"))[1:]
    total_clicks = sum(int(r[1]) for r in q_rows)
    brand_lower = brand_key.lower()
    branded_clicks = sum(int(r[1]) for r in q_rows if brand_lower in r[0].lower())
    share = branded_clicks / total_clicks if total_clicks else 0.0

    chart = read_rows(_find("Chart.csv"))[1:]
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
