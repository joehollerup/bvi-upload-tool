#!/usr/bin/env python3
"""Compute monthly Bronze-tier BVI scores from the four KEEN data parsers.

Implements BVI_Scoring_Spec_v1.1 Sections 3-5 for the Bronze tier:
  - MoM signal scoring via the 3.1 (% change) and 3.2 (percentage-point) scales
  - First-month baseline = 55 (3.4); large-swing cap at +/-40% (3.5)
  - Dimension score = average of its active signal scores (per task brief)
  - Composite = weighted avg of ACTIVE dimensions, weights normalized (2.4)
  - Momentum badge, and BASELINE_MONTH / DATA_GAP / INSUFFICIENT_TIER flags

`compute()` returns the full structured result (dimension scores + per-signal
raw values, MoM changes, and signal scores) for downstream consumers such as
export_dashboard.py. `main()` prints a human-readable summary table.

Scope notes (conscious simplifications vs. the full spec, kept faithful to the
task brief's per-dimension signal lists):
  * Dimensions are equal-weighted averages of the listed signals (the spec's
    intra-dimension weights in 4.x are not applied).
  * The rising-tide 0.90 cross-modifier on Search/Category (4.1, 4.5) is not
    applied; rising tide is instead scored directly as a Category signal.
  * A dimension is ACTIVE in a month only when it has data in BOTH that month
    and the prior month (MoM computable); otherwise it is a DATA_GAP.
"""

import parse_trends
import parse_gsc
import parse_ga4
import parse_social

# Bronze weights (spec 2.1); normalized over active dims each month (2.4).
WEIGHTS = {"Search": 0.22, "Digital": 0.22, "Social": 0.14,
           "Competitive": 0.14, "Category": 0.08}
DIMS = ["Search", "Digital", "Social", "Competitive", "Category"]
BASELINE_SCORE = 55.0


# ── Scales (spec Section 3) ────────────────────────────────────────────────
def _interp(x, pts, below, above):
    """Piecewise-linear interpolation across (threshold, score) anchors."""
    if x < pts[0][0]:
        return below
    if x > pts[-1][0]:
        return above
    for (x0, s0), (x1, s1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return s0 + (x - x0) / (x1 - x0) * (s1 - s0)
    return above


# 3.1 Standard MoM % change scale (v1.2 — compressed)
# Neutral (0% MoM) = 50. Middle band ±4% stays inside 44-56.
# Extreme scores (<20, >80) require genuine ±20% moves.
_PCT = [(-20, 20), (-10, 34), (-4, 44), (0, 50), (4, 56), (10, 68), (20, 82)]
def scale_pct(x):
    return None if x is None else _interp(x, _PCT, 12, 90)


# 3.2 Percentage-point change scale (v1.2 — compressed)
# Neutral (0pp MoM) ≈ 50. Middle band ±0.5pp stays inside 44-56.
# Extreme scores (<20, >80) require ±3pp moves.
_PTS = [(-3, 20), (-1.5, 34), (-0.5, 44), (0.5, 56), (1.5, 68), (3, 82)]
def scale_pts(x):
    return None if x is None else _interp(x, _PTS, 12, 90)


def mom_pct(cur, prev):
    """MoM % change, capped at +/-40% per large-swing rule (3.5). None if no base."""
    if cur is None or prev in (None, 0):
        return None
    return max(-40.0, min(40.0, (cur - prev) / prev * 100))


def _avg(scores):
    scores = [s for s in scores if s is not None]
    return sum(scores) / len(scores) if scores else None


def sig(value, mom, scale, score):
    """One signal detail entry for the dashboard's detail cards."""
    return {
        "value": value,
        "mom": round(mom, 2) if mom is not None else None,
        "scale": scale,
        "score": round(score) if score is not None else None,
    }


# ── Dimension scorers ──────────────────────────────────────────────────────
# Each returns {"score": float|None, "signals": {...}, "has_data": bool}.
# score is None unless a MoM comparison is possible (current + prior month).
def score_search(m, pm, gsc, comp, brand_key="KEEN"):
    has = m in gsc and m in comp
    if not has:
        return {"score": None, "signals": {}, "has_data": False}
    prior = pm is not None and pm in gsc and pm in comp
    ii = mom_pct(gsc[m]["br_impr"], gsc[pm]["br_impr"]) if prior else None
    ci = mom_pct(gsc[m]["br_clicks"], gsc[pm]["br_clicks"]) if prior else None
    ti = mom_pct(comp[m][brand_key], comp[pm][brand_key]) if prior else None
    s_ii, s_ci, s_ti = scale_pct(ii), scale_pct(ci), scale_pct(ti)
    signals = {
        "branded_impressions": sig(round(gsc[m]["br_impr"] / 1000, 1), ii, "pct", s_ii),
        "branded_clicks": sig(round(gsc[m]["br_clicks"] / 1000, 1), ci, "pct", s_ci),
        "brand_trends_index": sig(comp[m][brand_key], ti, "pct", s_ti),
    }
    return {"score": _avg([s_ii, s_ci, s_ti]), "signals": signals, "has_data": True}


def score_digital(m, pm, ga4):
    has = m in ga4
    if not has:
        return {"score": None, "signals": {}, "has_data": False}
    prior = pm is not None and pm in ga4
    ds = mom_pct(ga4[m]["direct"], ga4[pm]["direct"]) if prior else None
    osm = mom_pct(ga4[m]["organic"], ga4[pm]["organic"]) if prior else None
    dp = (ga4[m]["direct_pct"] - ga4[pm]["direct_pct"]) if prior else None
    s_ds, s_os, s_dp = scale_pct(ds), scale_pct(osm), scale_pts(dp)
    signals = {
        "direct_sessions": sig(round(ga4[m]["direct"] / 1000, 1), ds, "pct", s_ds),
        "direct_pct": sig(round(ga4[m]["direct_pct"], 1), dp, "pts", s_dp),
        "organic_sessions": sig(round(ga4[m]["organic"] / 1000, 1), osm, "pct", s_os),
    }
    return {"score": _avg([s_ds, s_os, s_dp]), "signals": signals, "has_data": True}


def score_social(m, pm, soc):
    has = m in soc
    if not has:
        return {"score": None, "signals": {}, "has_data": False}
    prior = pm is not None and pm in soc
    er = (soc[m]["er"] - soc[pm]["er"]) if prior else None
    rr = mom_pct(soc[m]["reach"], soc[pm]["reach"]) if prior else None
    gr = None
    if prior and soc[m]["gr"] is not None and soc[pm]["gr"] is not None:
        gr = mom_pct(soc[m]["gr"], soc[pm]["gr"])
    s_er, s_rr, s_gr = scale_pts(er), scale_pct(rr), scale_pct(gr)
    signals = {
        "engagement_rate": sig(round(soc[m]["er"], 2), er, "pts", s_er),
        "follower_growth_rate": sig(
            round(soc[m]["gr"], 2) if soc[m]["gr"] is not None else None, gr, "pct", s_gr),
        "organic_reach": sig(round(soc[m]["reach"] / 1000, 1), rr, "pct", s_rr),
    }
    return {"score": _avg([s_er, s_gr, s_rr]), "signals": signals, "has_data": True}


def score_competitive(m, pm, comp, rivals, brand_key="KEEN"):
    has = m in comp
    if not has:
        return {"score": None, "signals": {}, "has_data": False}
    prior = pm is not None and pm in comp

    def share(row):
        return row[brand_key] / sum(row.values()) * 100

    def nearest(row):
        nm = max(rivals, key=lambda r: row[r])
        return nm, row[nm]

    nm_now, ni_now = nearest(comp[m])
    gap_now = comp[m]["KEEN"] - ni_now
    sh_now = share(comp[m])
    sh_mom = gap_mom = None
    if prior:
        sh_mom = sh_now - share(comp[pm])
        _, ni_prev = nearest(comp[pm])
        gap_mom = gap_now - (comp[pm]["KEEN"] - ni_prev)
    s_sh, s_gap = scale_pts(sh_mom), scale_pts(gap_mom)
    signals = {
        "brand_share": sig(round(sh_now, 1), sh_mom, "pts", s_sh),
        "gap_to_nearest": {**sig(gap_now, gap_mom, "pts", s_gap),
                           "nearest": nm_now, "nearest_index": ni_now},
    }
    return {"score": _avg([s_sh, s_gap]), "signals": signals, "has_data": True}


def score_category(m, pm, cat, primary, brand_key="KEEN"):
    has = m in cat
    if not has:
        return {"score": None, "signals": {}, "has_data": False}
    prior = pm is not None and pm in cat
    gap_now = cat[m][brand_key] - cat[m][primary]
    gap_mom = None
    rising = False
    if prior:
        gap_mom = gap_now - (cat[pm][brand_key] - cat[pm][primary])
        bd = cat[m][brand_key] - cat[pm][brand_key]
        cd = cat[m][primary] - cat[pm][primary]
        rising = (bd > 0 and cd > 0 and cd >= 0.5 * bd)
    s_gap = scale_pts(gap_mom)
    s_rt = (46 if rising else 57) if prior else None
    signals = {
        "category_gap": {**sig(gap_now, gap_mom, "pts", s_gap),
                         "primary_category": primary,
                         "category_index": cat[m][primary], "brand_index": cat[m][brand_key]},
        "rising_tide": {"value": rising if prior else None, "mom": None,
                        "scale": "flag", "score": s_rt},
    }
    return {"score": _avg([s_gap, s_rt]), "signals": signals, "has_data": True}


# ── Composite, momentum ────────────────────────────────────────────────────
def composite(scores):
    active = {d: v for d, v in scores.items() if v is not None}
    if not active:
        return None, []
    wsum = sum(WEIGHTS[d] for d in active)
    bvi = sum(v * WEIGHTS[d] / wsum for d, v in active.items())
    return bvi, sorted(active)


def momentum(bvi, prev_bvi=None):
    if bvi is None:
        return "-"
    if prev_bvi is None:
        # Baseline month — no prior to compare; use absolute score for initial badge
        if bvi > 55:
            return "Rising"
        if bvi >= 50:
            return "Stable"
        return "Declining"
    delta = bvi - prev_bvi
    if delta > 2:
        return "Rising"
    if delta >= -2:
        return "Stable"
    return "Declining"


# ── Full structured computation ────────────────────────────────────────────
def compute(brand_key="KEEN", T=None, G=None, A=None, S=None):
    """Return a list of per-month result dicts (chronological).

    Accepts pre-loaded data dicts to avoid re-reading files when called from
    generate_dashboard. Falls back to hardcoded file paths when not provided.
    """
    if T is None:
        T = parse_trends.load()
    if G is None:
        G = parse_gsc.load()
    if A is None:
        A = parse_ga4.load()
    if S is None:
        S = parse_social.load()
    comp, cat, gsc = T["comp"], T["cat"], G["months"]

    rivals = [k for k in next(iter(comp.values())) if k != brand_key]
    cat_terms = [k for k in next(iter(cat.values())) if k != brand_key]
    means = {t: sum(cat[mo][t] for mo in cat) / len(cat) for t in cat_terms}
    primary = max(means, key=means.get)

    months = sorted(set(comp) | set(cat) | set(gsc) | set(S) | set(A))
    results = []
    for i, m in enumerate(months):
        pm = months[i - 1] if i > 0 else None
        baseline = i == 0
        raw = {
            "Search": score_search(m, pm, gsc, comp, brand_key),
            "Digital": score_digital(m, pm, A),
            "Social": score_social(m, pm, S),
            "Competitive": score_competitive(m, pm, comp, rivals, brand_key),
            "Category": score_category(m, pm, cat, primary, brand_key),
        }

        scores, dims = {}, {}
        for d in DIMS:
            r = raw[d]
            if baseline:
                sc = BASELINE_SCORE if r["has_data"] else None
                status = "baseline" if r["has_data"] else "data_gap"
            else:
                sc = r["score"]
                status = "live" if sc is not None else "data_gap"
            scores[d] = sc
            dims[d] = {"score": sc, "weight": WEIGHTS[d],
                       "status": status, "signals": r["signals"]}

        bvi, active = composite(scores)
        wsum = sum(WEIGHTS[d] for d in active)
        normw = {d: WEIGHTS[d] / wsum for d in active}
        for d in DIMS:
            dims[d]["normalized_weight"] = normw.get(d)

        flags = []
        if baseline:
            flags.append("BASELINE_MONTH")
        gaps = [d for d in DIMS if scores[d] is None]
        if gaps:
            flags.append("DATA_GAP(" + ",".join(gaps) + ")")
        if len(active) < 2:
            flags.append("INSUFFICIENT_TIER")

        prev_bvi = results[-1]["bvi_score"] if results else None
        results.append({
            "month": m,
            "status": "baseline" if baseline else "live",
            "bvi_score": bvi,
            "momentum": momentum(bvi, None if baseline else prev_bvi),
            "active": active,
            "normalized_weights": normw,
            "flags": flags,
            "dimensions": dims,
            "primary_category": primary,
        })
    return results


def main():
    results = compute()
    first = results[0]
    print(f"Primary category term: {first['primary_category']}   |   "
          f"Nearest competitor: dynamic (max index)")
    print(f"Months scored: {len(results)} "
          f"({results[0]['month']} -> {results[-1]['month']})\n")
    head = (f"{'Month':<9}{'BVI':>6}{'Momentum':>11}"
            f"{'Search':>8}{'Digital':>8}{'Social':>8}{'Comp':>7}{'Categ':>7}   Flags")
    print(head)
    print("-" * len(head))

    def cell(v):
        return f"{v:.0f}" if v is not None else "—"

    for r in results:
        d = r["dimensions"]
        bvi = r["bvi_score"]
        print(f"{r['month']:<9}{(f'{bvi:.1f}' if bvi is not None else '—'):>6}"
              f"{r['momentum']:>11}"
              f"{cell(d['Search']['score']):>8}{cell(d['Digital']['score']):>8}"
              f"{cell(d['Social']['score']):>8}{cell(d['Competitive']['score']):>7}"
              f"{cell(d['Category']['score']):>7}   {' '.join(r['flags']) or '—'}")


if __name__ == "__main__":
    main()
