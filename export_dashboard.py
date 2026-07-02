#!/usr/bin/env python3
"""Export scored BVI data to keen_bvi_output.json for the dashboard (v3 spec Sec 3).

Imports score_bvi.compute() and reshapes each month into the structure the
dashboard consumes: per-month objects with bvi_score, momentum, tier,
dimensions (score / weight / normalized_weight / status / signals), flags, and
the active normalized weights. Each signal carries its raw value + MoM change
+ signal score so the UI can render detail cards. Nulls mean "not available"
(rendered as "—"), per the spec's null convention (3.2).
"""

import json
from datetime import datetime

import score_bvi

OUT_PATH = "keen_bvi_output.json"
TIER = "bronze"


def label(month):
    """'2025-05' -> \"May '25\" (dashboard month-label convention, spec 3.3)."""
    return datetime.strptime(month + "-01", "%Y-%m-%d").strftime("%b '%y")


def r1(x):
    return round(x, 1) if x is not None else None


def build(results):
    out = []
    for r in results:
        dims = {}
        for name, d in r["dimensions"].items():
            dims[name] = {
                "score": r1(d["score"]),
                "weight": d["weight"],
                "normalized_weight": r1(d["normalized_weight"] * 100)
                if d["normalized_weight"] is not None else None,
                "status": d["status"],
                "signals": d["signals"],
            }
        out.append({
            "month": r["month"],
            "label": label(r["month"]),
            "tier": TIER,
            "status": r["status"],
            "bvi_score": r1(r["bvi_score"]),
            "momentum": r["momentum"],
            "flags": r["flags"],
            "normalized_weights": {k: r1(v * 100) for k, v in r["normalized_weights"].items()},
            "dimensions": dims,
        })
    return out


def main():
    data = build(score_bvi.compute())
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {len(data)} monthly objects to {OUT_PATH}\n")
    print(f"--- Most recent scored month: {data[-1]['label']} ({data[-1]['month']}) ---")
    print(json.dumps(data[-1], indent=2))


if __name__ == "__main__":
    main()
