#!/usr/bin/env python3
"""Parse Instagram & TikTok manual-number CSVs into monthly social metrics."""

import csv
from datetime import datetime

# (label, path, engagement cols, denominator cols, reach cols) — matched by header name.
PLATFORMS = [
    ("Instagram", "KEEN - Instagram Manual Numbers.csv",
     ["Engagements", "Organic Engagements"], ["Views", "Impressions"], ["Reach", "Video Views"]),
    ("TikTok", "KEEN - TikTok Manual Numbers.csv",
     ["Engagements", "Organic Engagements"], ["Views", "Impressions"], ["Reach", "Video Views"]),
]

def num(s):
    s = s.strip().strip('"').replace(",", "")
    return int(s) if s and s.lstrip("-").isdigit() else 0

def find(header, candidates):
    for c in candidates:
        if c in header:
            return header.index(c)
    raise ValueError(f"none of {candidates} in header")

def parse(path, eng_names, den_names, reach_names):
    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    h = rows[0]
    di, fi, ni = h.index("Date"), h.index("Followers"), h.index("Net Follower Growth")
    ei, vi, ri = find(h, eng_names), find(h, den_names), find(h, reach_names)

    months = {}
    for r in rows[1:]:
        if not r or not r[di].strip():
            continue
        d = datetime.strptime(r[di].strip().strip('"'), "%m-%d-%Y")
        key = f"{d.year:04d}-{d.month:02d}"
        m = months.setdefault(key, {"date": None, "foll": 0, "net": 0, "eng": 0, "den": 0, "reach": 0})
        if m["date"] is None or d >= m["date"]:          # last day of month
            m["date"], m["foll"] = d, num(r[fi])
        m["net"] += num(r[ni])
        m["eng"] += num(r[ei])
        m["den"] += num(r[vi])
        m["reach"] += num(r[ri])

    out, prev = {}, None
    for k in sorted(months):
        m = months[k]
        out[k] = {
            "foll": m["foll"],
            "net": m["net"],
            "er": (m["eng"] / m["den"] * 100) if m["den"] else 0.0,
            "reach": m["reach"],
            "gr": (m["net"] / prev * 100) if prev else None,
        }
        prev = m["foll"]
    return out

def show(label, data):
    print(f"\n=== {label} ===")
    print(f"{'Month':<9}{'Followers':>12}{'NetGrowth':>11}{'Growth%':>9}{'EngRate%':>10}{'OrgReach':>13}")
    for k in sorted(data):
        d = data[k]
        gr = f"{d['gr']:.2f}" if d["gr"] is not None else "-"
        print(f"{k:<9}{d['foll']:>12,}{d['net']:>11,}{gr:>9}{d['er']:>9.2f}%{d['reach']:>13,}")

def show_combined(results):
    print("\n=== Combined (avg eng rate, avg growth rate, summed reach) ===")
    print(f"{'Month':<9}{'AvgEngRate%':>13}{'AvgGrowth%':>12}{'TotalReach':>14}")
    keys = sorted(set().union(*[r.keys() for r in results.values()]))
    for k in keys:
        present = [r[k] for r in results.values() if k in r]
        ers = [p["er"] for p in present]
        grs = [p["gr"] for p in present if p["gr"] is not None]
        reach = sum(p["reach"] for p in present)
        gr = f"{sum(grs) / len(grs):.2f}" if grs else "-"
        print(f"{k:<9}{sum(ers) / len(ers):>12.2f}%{gr:>12}{reach:>14,}")

def load():
    """Return combined monthly social metrics: {YYYY-MM: {er, gr, reach}}.

    er = avg engagement rate across platforms, gr = avg follower growth rate
    (None until each platform has a prior month), reach = summed organic reach.
    """
    res = {label: parse(path, eng, den, reach)
           for label, path, eng, den, reach in PLATFORMS}
    keys = sorted(set().union(*[r.keys() for r in res.values()]))
    out = {}
    for k in keys:
        present = [r[k] for r in res.values() if k in r]
        ers = [p["er"] for p in present]
        grs = [p["gr"] for p in present if p["gr"] is not None]
        out[k] = {
            "er": sum(ers) / len(ers) if ers else 0.0,
            "gr": sum(grs) / len(grs) if grs else None,
            "reach": sum(p["reach"] for p in present),
        }
    return out


def load_from(ig_path=None, tt_path=None):
    """Like load() but accepts explicit paths. Combined output includes net follower growth."""
    platforms = []
    eng = ["Engagements", "Organic Engagements"]
    den = ["Views", "Impressions"]
    reach = ["Reach", "Video Views"]
    if ig_path:
        platforms.append(("Instagram", ig_path, eng, den, reach))
    if tt_path:
        platforms.append(("TikTok", tt_path, eng, den, reach))
    if not platforms:
        return {}
    res = {lbl: parse(path, e, d, r) for lbl, path, e, d, r in platforms}
    keys = sorted(set().union(*[r.keys() for r in res.values()]))
    out = {}
    for k in keys:
        present = [r[k] for r in res.values() if k in r]
        ers = [p["er"] for p in present]
        grs = [p["gr"] for p in present if p["gr"] is not None]
        out[k] = {
            "er": sum(ers) / len(ers) if ers else 0.0,
            "gr": sum(grs) / len(grs) if grs else None,
            "reach": sum(p["reach"] for p in present),
            "net": sum(p["net"] for p in present),
        }
    return out


def main():
    results = {}
    for label, path, eng, den, reach in PLATFORMS:
        results[label] = parse(path, eng, den, reach)
        show(label, results[label])
    show_combined(results)

if __name__ == "__main__":
    main()
