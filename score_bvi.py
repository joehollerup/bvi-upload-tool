#!/usr/bin/env python3
"""BVI scoring engine v2.2 - baseline-relative, per-metric baseline windows.

Implements BVI Scoring Spec v2.2. Replaces the month-over-month engine.

Change from v2.1 (per-metric baseline windows supersede SEASONAL_INDEX)
    v2.1 handled per-month seasonality with a SEASONAL-ADJUSTMENT LAYER
    (SEASONAL_INDEX) pending a pooled cross-client data pull. Clancy has
    approved a different, simpler fix: lengthen the baseline window itself
    for Trends/GA4/Social signals to 24 months (two full annual cycles), so
    every calendar month is represented twice in the baseline mean and each
    month's own seasonal component is absorbed directly, with no external
    coefficient table needed. GSC-derived signals stay at 12 months because
    Google caps Search Console at a rolling 16-month reporting window -- a
    24-month requirement would mean that baseline could never accumulate
    enough months to lock. SEASONAL_INDEX and its supporting code are left
    in place but are now permanently inert (see the block below); this is
    not "still pending," it is superseded.

Change from v2.0 (the seasonality fix, still true of the baseline itself)
    The baseline is the SEASON-NEUTRAL FULL-CYCLE MEAN: the mean of the
    client's first full window of backfill, locked once that window exists.
    A whole-year (or two) mean contains every season, so the reference
    cannot sit on an inflated (Q4) or deflated (Q1) month. Every month that
    has data is scored against that reference; nothing is excluded.

Two-layer design (Spec Section 10)
    ENGINE (this file) computes in log-growth and percentage-point space,
    deseasonalizes search interest against the category, subtracts the
    seasonal index from volume signals, assembles one composite, maps to
    0-100 once. SURFACE (dashboard, narrative) restates it in plain language.
    The SENSITIVITY block is the only bridge between the layers.

Determinism (Spec 1.2)
    Same inputs + same constants + same SEASONAL_INDEX -> identical output.
    The baseline for a metric with a full cycle is locked and immutable.
    A metric with less than a full cycle (typically social at onboarding)
    carries a PROVISIONAL_BASELINE flag and its baseline expands until it
    reaches a full cycle, then locks. The only estimated quantity is
    per-signal volatility, a deterministic standard deviation feeding ONLY
    the uncertainty band and the badge, never the headline number.

No dummy data (Spec 1.3)
    A metric is present in the parsed input or it is excluded and flagged.
    Nothing is filled, estimated, or fabricated. Fields not guaranteed by the
    existing parsers (e.g. GSC average position) are read with .get and
    treated as absent when missing.

CALIBRATION (Spec 3.6): the SENSITIVITY and SMALL-BASE blocks are committed
launch values from a coherence pass on the mapping. Retune trigger: real
fashion-client history (the Iris pull). Retuning shifts absolute levels only,
never logic, direction, or ordering.
"""

import math
import statistics
from datetime import datetime

import parse_trends
import parse_gsc
import parse_ga4
import parse_social


# ===========================================================================
# CONSTANTS
# ===========================================================================

# Per-source baseline windows (Spec 2.5). Approved by Clancy: replaces the
# single global BASELINE_CYCLE=12 with per-metric windows, and supersedes
# the SEASONAL_INDEX pending-data plan for the signals it covers (see the
# SEASONAL-ADJUSTMENT LAYER block below).
#
# GSC stays at 12 months. Google caps Search Console at a ROLLING 16-month
# reporting window: by the time a 17th month of history would exist, month 1
# has already aged out of what GSC will ever return again. A 24-month
# requirement would mean the GSC baseline could never accumulate 24 present
# values and would never lock. 12 months locks comfortably inside the
# 16-month cap, with margin for onboarding timing.
#
# Trends / GA4 / Social move to 24 months. A 24-month baseline mean spans
# two full annual cycles, so every calendar month is represented twice in
# the mean -- this absorbs each month's own seasonal component directly,
# which is what SEASONAL_INDEX was built to approximate from a pooled
# cross-client panel. The longer baseline supersedes that need.
BASELINE_CYCLE_GSC = 12        # branded impressions, branded clicks, avg position
BASELINE_CYCLE_TRENDS = 24     # brand Trends index, brand share, gaps, category share/gap
BASELINE_CYCLE_GA4 = 24        # direct sessions, organic sessions, direct % of sessions
BASELINE_CYCLE_SOCIAL = 24     # engagement rate, follower growth rate, organic reach

# Per-series baseline window, keyed the same as `ser`/`derived` in compute().
# Branded CTR is not listed: it is a display-only ratio of impressions/clicks
# computed in the dashboard, not an independently scored/baselined signal here.
BASELINE_CYCLES = {
    "search_impr": BASELINE_CYCLE_GSC,
    "search_clicks": BASELINE_CYCLE_GSC,
    "search_position": BASELINE_CYCLE_GSC,
    "search_trends": BASELINE_CYCLE_TRENDS,
    "dig_direct": BASELINE_CYCLE_GA4,
    "dig_organic": BASELINE_CYCLE_GA4,
    "dig_direct_pct": BASELINE_CYCLE_GA4,
    "soc_er": BASELINE_CYCLE_SOCIAL,
    "soc_gr": BASELINE_CYCLE_SOCIAL,
    "soc_reach": BASELINE_CYCLE_SOCIAL,
    "comp_share": BASELINE_CYCLE_TRENDS,
    "comp_gap": BASELINE_CYCLE_TRENDS,
    "comp_index": BASELINE_CYCLE_TRENDS,
    "cat_gap": BASELINE_CYCLE_TRENDS,
    "cat_share": BASELINE_CYCLE_TRENDS,
    "cat_brand": BASELINE_CYCLE_TRENDS,
    "cat_primary": BASELINE_CYCLE_TRENDS,
}

NEUTRAL = 50.0                # BVI at baseline (no movement)
SIGNAL_CAP = 40.0             # max +/- BVI points one signal may contribute (3.3)
DISPLAY_MIN, DISPLAY_MAX = 0.0, 100.0

# SENSITIVITY block - the surface<->engine contract (Spec 3.3).
# COMMITTED LAUNCH CALIBRATION (coherence pass, not a data fit): a brand
# growing a broad ~15% above baseline, net of category and season, lands near
# BVI 63; ~30% near the low 70s; exceptional growth reaches the low 80s;
# decline is symmetric. Retune trigger: Spec 3.6.
LOG_SENSITIVITY = 130.0       # BVI points per 1.0 natural-log unit of growth
PCT_POINT_SENSITIVITY = 8.0   # BVI points per 1 percentage-point change
POSITION_SENSITIVITY = 20.0   # BVI points per 1.0 position improved (lower=better)

# SMALL-BASE block (Spec 4.6). COMMITTED LAUNCH VALUES.
TRENDS_INDEX_FLOOR = 5.0
TRENDS_INDEX_HARD_MIN = 2.0
COUNT_FLOOR = 100.0
COUNT_HARD_MIN = 20.0

# Uncertainty / badge (Spec 6.3, 6.4). Secondary layer only.
VOL_FLOOR_LOG = 0.02
VOL_FLOOR_PCT = 0.15
BADGE_WINDOW = 3

# Dimension weights (Spec 2.1); normalized over active dims each month (2.4).
DIM_WEIGHTS = {"Search": 0.22, "Digital": 0.22, "Social": 0.14,
               "Competitive": 0.14, "Category": 0.08}
DIMS = ["Search", "Digital", "Social", "Competitive", "Category"]

# Intra-dimension signal weights (Spec Section 4).
SEARCH_W = {"branded_impressions": 0.35, "branded_clicks": 0.25,
            "brand_trends_index": 0.25, "avg_position": 0.15}
DIGITAL_W = {"direct_sessions": 0.30, "direct_pct": 0.40,
             "organic_sessions": 0.30}
SOCIAL_W = {"engagement_rate": 0.45, "follower_growth_rate": 0.30,
            "organic_reach": 0.25}
COMPETITIVE_W = {"brand_share": 0.50, "gap_to_nearest": 0.30,
                 "brand_trends_index": 0.20}
CATEGORY_W = {"category_gap": 0.60, "category_share": 0.40}

# ---------------------------------------------------------------------------
# GSC IMPRESSIONS LOGGING BUG (confirmed by Google) -- transparency flag only
# ---------------------------------------------------------------------------
# Google confirmed a logging error inflated Search Console impressions for
# ALL properties from 2025-05-13 through 2026-04-27. Clicks were unaffected;
# CTR and average position are DERIVED from impressions and are therefore
# also unreliable in this window. Google has stated the historical data will
# NOT be corrected retroactively.
#
# This does not change any scoring math, weight, or signal calculation -- it
# only adds a flag so the affected months (and any baseline built from them)
# are visibly caveated, per the spec's "all flags are displayed, never
# suppressed" rule (Section 3).
GSC_IMPRESSIONS_BUG_START = "2025-05"   # inclusive, YYYY-MM
GSC_IMPRESSIONS_BUG_END = "2026-04"     # inclusive, YYYY-MM

# Series whose season-neutral baseline (2.5) is built directly from GSC
# impressions or a metric derived from it.
GSC_IMPRESSIONS_BASELINE_KEYS = ("search_impr", "search_clicks", "search_position")

FLAG_TEXT = {
    "GSC_IMPRESSIONS_UNRELIABLE": (
        "GSC impressions, CTR, and average position are unreliable for this "
        "month due to a confirmed Google logging error (May 2025 - April "
        "2026). Branded clicks are unaffected."
    ),
}

DATASET_NOTE_TEXT = {
    "baseline_gsc_impressions_affected": (
        "This client's baseline includes months affected by the GSC "
        "impressions logging error. Interpret Search Demand movement with "
        "caution."
    ),
}


def _in_gsc_impressions_bug_window(month_key):
    """True if month_key (YYYY-MM) falls in the confirmed GSC logging-bug window."""
    return GSC_IMPRESSIONS_BUG_START <= month_key <= GSC_IMPRESSIONS_BUG_END


# ---------------------------------------------------------------------------
# SEASONAL-ADJUSTMENT LAYER (Spec v2.1 0.6, 3.2)  --  SUPERSEDED, PERMANENTLY INERT
# ---------------------------------------------------------------------------
# v2.1 built this layer to subtract a per-calendar-month seasonal coefficient
# from volume signals, pending a pooled cross-client data pull. v2.2
# supersedes that plan: BASELINE_CYCLE_TRENDS/GA4/SOCIAL above lengthen the
# baseline window for those same signal families to 24 months (two full
# annual cycles), which absorbs each month's own seasonal component directly
# in the baseline mean. There is no longer a pooled coefficient table to
# populate for these signals.
#
# The code below is INTENTIONALLY LEFT IN PLACE, unchanged, and PERMANENTLY
# INERT: SEASONAL_INDEX must stay empty. Do not populate it -- doing so would
# double-correct seasonality (once via the 24-month baseline, again via this
# layer) on top of signals it was never meant to touch. It is kept only so a
# future spec revision has the mechanism available if ever needed again.
#
# Structure (historical, for reference): SEASONAL_INDEX[sub_vertical]
# [calendar_month 1-12][family] = factor, where factor is the typical
# multiplicative level of that family in that calendar month relative to its
# annual mean. The engine subtracts ln(factor) from the log-movement of each
# volume signal. EMPTY = NO-OP: every offset is 0, so build_month_seasonals()
# always returns {} and every seas.get(...) call in the scorers below falls
# through to its 0.0 default.
SEASONAL_INDEX = {}   # PERMANENTLY EMPTY -- superseded by 24-month baselines (v2.2)

# signal name -> seasonal family bucket (only these signals are adjusted)
SEASONAL_SIGNALS = {
    "branded_impressions": "search_volume",
    "branded_clicks": "search_volume",
    "direct_sessions": "direct_traffic",
    "organic_sessions": "organic_traffic",
    "organic_reach": "social_reach",
    "follower_growth_rate": "social_growth",
}


# ===========================================================================
# LOW-LEVEL HELPERS
# ===========================================================================

def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def baseline_mean(series, months, cycle=BASELINE_CYCLE_GSC):
    """Season-neutral baseline (Spec 2.5).

    Baseline = mean of the earliest up-to-`cycle` present values. Locked once
    at least `cycle` present values exist; provisional (expanding) before that.
    `cycle` is now per-series (v2.2, BASELINE_CYCLES) -- callers in compute()
    always pass it explicitly; the default here is only a defensive fallback.
    Returns (baseline_value, used_month_set, locked_bool).
    """
    present = [m for m in months if series.get(m) is not None]
    if not present:
        return None, set(), False
    window = present[:cycle]
    return statistics.fmean(series[m] for m in window), set(window), \
        len(present) >= cycle


def parse_calendar_month(month_key):
    """Best-effort calendar-month (1-12) from a month label. None if unknown.

    NOTE FOR IMPLEMENTATION: confirm this against the real parser's month-key
    format before loading SEASONAL_INDEX. Add the actual format if missing.
    """
    if month_key is None:
        return None
    s = str(month_key).strip()
    for fmt in ("%Y-%m", "%Y-%m-%d", "%b '%y", "%b %Y", "%B %Y", "%b-%y", "%m/%Y"):
        try:
            return datetime.strptime(s, fmt).month
        except ValueError:
            continue
    return None


def seasonal_offset(sub_vertical, cal_month, family):
    """Log-space seasonal offset for a family; 0.0 when the table lacks it."""
    if not SEASONAL_INDEX or cal_month is None:
        return 0.0
    table = SEASONAL_INDEX.get(sub_vertical) or SEASONAL_INDEX.get("default")
    if not table:
        return 0.0
    factor = (table.get(cal_month) or {}).get(family)
    if not factor or factor <= 0:
        return 0.0
    return math.log(factor)


def build_month_seasonals(sub_vertical, cal_month):
    """Per-signal log offsets for the seasonal volume signals this month."""
    seas = {}
    for name, fam in SEASONAL_SIGNALS.items():
        off = seasonal_offset(sub_vertical, cal_month, fam)
        if off:
            seas[name] = off
    return seas


def _count_mode(baseline):
    if baseline is None:
        return "skip"
    if baseline >= COUNT_FLOOR:
        return "log"
    if baseline >= COUNT_HARD_MIN:
        return "point"
    return "skip"


def _index_mode(baseline):
    if baseline is None:
        return "skip"
    if baseline >= TRENDS_INDEX_FLOOR:
        return "log"
    if baseline >= TRENDS_INDEX_HARD_MIN:
        return "point"
    return "skip"


def log_move(value, baseline):
    if value is None or baseline is None or baseline <= 0 or value <= 0:
        return None
    return math.log(value / baseline)


def contrib_log(move, offset=0.0):
    """Log movement minus a deseason/seasonal offset -> capped contribution."""
    if move is None:
        return None, False
    raw = LOG_SENSITIVITY * (move - (offset or 0.0))
    capped = clamp(raw, -SIGNAL_CAP, SIGNAL_CAP)
    return capped, raw != capped


def contrib_point(move):
    if move is None:
        return None, False
    raw = PCT_POINT_SENSITIVITY * move
    capped = clamp(raw, -SIGNAL_CAP, SIGNAL_CAP)
    return capped, raw != capped


def contrib_position(move):
    if move is None:
        return None, False
    raw = POSITION_SENSITIVITY * move
    capped = clamp(raw, -SIGNAL_CAP, SIGNAL_CAP)
    return capped, raw != capped


def signal(value, move, mode, contribution, capped, note=""):
    return {
        "value": value,
        "move": round(move, 4) if move is not None else None,
        "mode": mode,
        "contribution": round(contribution, 2) if contribution is not None else None,
        "capped": capped,
        "note": note,
    }


def weighted_mean(pairs):
    live = [(w, v) for (w, v) in pairs if v is not None]
    if not live:
        return None
    wsum = sum(w for w, _ in live)
    return sum(w * v for w, v in live) / wsum if wsum else None


def month_to_month_vol(move_series, floor):
    vals = [v for v in move_series if v is not None]
    if len(vals) < 2:
        return floor
    diffs = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    if len(diffs) < 2:
        return max(abs(diffs[0]) if diffs else 0.0, floor)
    return max(statistics.pstdev(diffs), floor)


def _series(source, months, key):
    out = {}
    for m in months:
        row = source.get(m)
        if row is None:
            continue
        v = row.get(key)
        if v is not None:
            out[m] = v
    return out


# ===========================================================================
# DIMENSION SCORERS
# `seas` is the per-month dict of log seasonal offsets (empty until Iris data).
# ===========================================================================

def score_search(m, gsc, comp, brand_key, base, cat_deseason, seas):
    sig, moves, capped, small = {}, {}, [], []
    row = gsc.get(m, {}) if m in gsc else {}

    # A. branded impressions (count, log, seasonally adjusted)
    b = base["search_impr"]
    val = row.get("br_impr")
    mode = _count_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv, seas.get("branded_impressions", 0.0))
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("branded_impressions")
        sig["branded_impressions"] = signal(round(val / 1000, 1), mv, mode, c, cap)
        moves["branded_impressions"] = mv
        if cap:
            capped.append("branded_impressions")

    # B. branded clicks (count, log, seasonally adjusted)
    b = base["search_clicks"]
    val = row.get("br_clicks")
    mode = _count_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv, seas.get("branded_clicks", 0.0))
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("branded_clicks")
        sig["branded_clicks"] = signal(round(val / 1000, 1), mv, mode, c, cap)
        moves["branded_clicks"] = mv
        if cap:
            capped.append("branded_clicks")

    # C. brand Trends index (log, DESEASONALIZED vs CATEGORY - not seasonal idx)
    b = base["search_trends"]
    val = comp.get(m, {}).get(brand_key) if m in comp else None
    mode = _index_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv, cat_deseason or 0.0)
            note = "deseasonalized vs category"
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("brand_trends_index")
            note = "small-base point mode"
        sig["brand_trends_index"] = signal(val, mv, mode, c, cap, note)
        moves["brand_trends_index"] = mv
        if cap:
            capped.append("brand_trends_index")

    # D. average position (position scale; read defensively)
    b = base["search_position"]
    val = row.get("position")
    if val is not None and b is not None:
        mv = b - val
        c, cap = contrib_position(mv)
        sig["avg_position"] = signal(val, mv, "position", c, cap, "lower is better")
        moves["avg_position"] = mv
        if cap:
            capped.append("avg_position")

    contribution = weighted_mean(
        [(SEARCH_W[k], sig[k]["contribution"]) for k in sig])
    return {"contribution": contribution, "signals": sig, "active": bool(sig),
            "moves": moves, "capped": capped, "small_base": small}


def score_digital(m, ga4, base, seas):
    sig, moves, capped, small = {}, {}, [], []
    row = ga4.get(m) if m in ga4 else None

    # A. direct sessions (count, log, seasonally adjusted)
    b = base["dig_direct"]
    val = row.get("direct") if row else None
    mode = _count_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv, seas.get("direct_sessions", 0.0))
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("direct_sessions")
        sig["direct_sessions"] = signal(round(val / 1000, 1), mv, mode, c, cap)
        moves["direct_sessions"] = mv
        if cap:
            capped.append("direct_sessions")

    # B. direct % of total (percentage point; near season-neutral, not adjusted)
    b = base["dig_direct_pct"]
    val = row.get("direct_pct") if row else None
    if val is not None and b is not None:
        mv = val - b
        c, cap = contrib_point(mv)
        sig["direct_pct"] = signal(round(val, 1), mv, "point", c, cap,
                                   "Grand Total denominator")
        moves["direct_pct"] = mv
        if cap:
            capped.append("direct_pct")

    # C. organic sessions (count, log, seasonally adjusted)
    b = base["dig_organic"]
    val = row.get("organic") if row else None
    mode = _count_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv, seas.get("organic_sessions", 0.0))
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("organic_sessions")
        sig["organic_sessions"] = signal(round(val / 1000, 1), mv, mode, c, cap)
        moves["organic_sessions"] = mv
        if cap:
            capped.append("organic_sessions")

    contribution = weighted_mean(
        [(DIGITAL_W[k], sig[k]["contribution"]) for k in sig])
    return {"contribution": contribution, "signals": sig, "active": bool(sig),
            "moves": moves, "capped": capped, "small_base": small}


def score_social(m, soc, base, seas):
    sig, moves, capped, small = {}, {}, [], []
    row = soc.get(m) if m in soc else None

    # A. engagement rate (percentage point; not seasonally adjusted)
    b = base["soc_er"]
    val = row.get("er") if row else None
    if val is not None and b is not None:
        mv = val - b
        c, cap = contrib_point(mv)
        sig["engagement_rate"] = signal(round(val, 2), mv, "point", c, cap)
        moves["engagement_rate"] = mv
        if cap:
            capped.append("engagement_rate")

    # B. follower growth rate (log, seasonally adjusted)
    b = base["soc_gr"]
    val = row.get("gr") if row else None
    if val is not None and b is not None and b > 0 and val > 0:
        mv = log_move(val, b)
        c, cap = contrib_log(mv, seas.get("follower_growth_rate", 0.0))
        sig["follower_growth_rate"] = signal(round(val, 2), mv, "log", c, cap)
        moves["follower_growth_rate"] = mv
        if cap:
            capped.append("follower_growth_rate")

    # C. organic reach (count, log, seasonally adjusted)
    b = base["soc_reach"]
    val = row.get("reach") if row else None
    mode = _count_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv, seas.get("organic_reach", 0.0))
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("organic_reach")
        sig["organic_reach"] = signal(round(val / 1000, 1), mv, mode, c, cap)
        moves["organic_reach"] = mv
        if cap:
            capped.append("organic_reach")

    contribution = weighted_mean(
        [(SOCIAL_W[k], sig[k]["contribution"]) for k in sig])
    flags = []
    if row and row.get("single_platform"):
        flags.append("SINGLE_PLATFORM_SOCIAL")
    return {"contribution": contribution, "signals": sig, "active": bool(sig),
            "moves": moves, "capped": capped, "small_base": small, "flags": flags}


def score_competitive(m, comp, rivals, brand_key, base):
    sig, moves, capped, small = {}, {}, [], []
    row = comp.get(m) if m in comp else None
    if not row:
        return {"contribution": None, "signals": {}, "active": False,
                "moves": {}, "capped": [], "small_base": []}

    def share(r):
        tot = sum(r.values())
        return r[brand_key] / tot * 100 if tot else None

    def nearest(r):
        present = [x for x in rivals if r.get(x) is not None]
        if not present:
            return None, None
        nm = max(present, key=lambda x: r[x])
        return nm, r[nm]

    # A. brand Trends share vs baseline (percentage point)
    b = base["comp_share"]
    sh = share(row)
    if sh is not None and b is not None:
        mv = sh - b
        c, cap = contrib_point(mv)
        sig["brand_share"] = signal(round(sh, 1), mv, "point", c, cap)
        moves["brand_share"] = mv
        if cap:
            capped.append("brand_share")

    # B. gap to nearest competitor vs baseline (percentage point)
    b = base["comp_gap"]
    nm, ni = nearest(row)
    if ni is not None and b is not None and row.get(brand_key) is not None:
        gap_now = row[brand_key] - ni
        mv = gap_now - b
        c, cap = contrib_point(mv)
        sig["gap_to_nearest"] = signal(gap_now, mv, "point", c, cap,
                                       "nearest: %s" % nm)
        moves["gap_to_nearest"] = mv
        if cap:
            capped.append("gap_to_nearest")

    # C. brand Trends index vs baseline (log; NOT deseasonalized - 4.4 note)
    b = base["comp_index"]
    val = row.get(brand_key)
    mode = _index_mode(b)
    if val is not None and mode != "skip":
        if mode == "log":
            mv = log_move(val, b)
            c, cap = contrib_log(mv)
        else:
            mv = val - b
            c, cap = contrib_point(mv)
            small.append("brand_trends_index")
        sig["brand_trends_index"] = signal(val, mv, mode, c, cap)
        moves["brand_trends_index"] = mv
        if cap:
            capped.append("brand_trends_index")

    contribution = weighted_mean(
        [(COMPETITIVE_W[k], sig[k]["contribution"]) for k in sig])
    return {"contribution": contribution, "signals": sig, "active": bool(sig),
            "moves": moves, "capped": capped, "small_base": small}


def score_category(m, cat, cat_terms, primary, brand_key, base):
    sig, moves, capped, small = {}, {}, [], []
    row = cat.get(m) if m in cat else None
    if not row:
        return {"contribution": None, "signals": {}, "active": False,
                "moves": {}, "capped": [], "small_base": []}

    # A. brand vs primary category gap vs baseline (percentage point)
    b = base["cat_gap"]
    if row.get(brand_key) is not None and row.get(primary) is not None and b is not None:
        gap_now = row[brand_key] - row[primary]
        mv = gap_now - b
        c, cap = contrib_point(mv)
        sig["category_gap"] = signal(gap_now, mv, "point", c, cap,
                                     "primary: %s" % primary)
        moves["category_gap"] = mv
        if cap:
            capped.append("category_gap")

    # B. brand share of category attention vs baseline (percentage point)
    b = base["cat_share"]
    denom = None
    if row.get(brand_key) is not None:
        term_sum = sum(row[t] for t in cat_terms if row.get(t) is not None)
        denom = row[brand_key] + term_sum
    if denom and b is not None:
        sh = row[brand_key] / denom * 100
        mv = sh - b
        c, cap = contrib_point(mv)
        sig["category_share"] = signal(round(sh, 1), mv, "point", c, cap)
        moves["category_share"] = mv
        if cap:
            capped.append("category_share")

    contribution = weighted_mean(
        [(CATEGORY_W[k], sig[k]["contribution"]) for k in sig])
    return {"contribution": contribution, "signals": sig, "active": bool(sig),
            "moves": moves, "capped": capped, "small_base": small}


# ===========================================================================
# RISING TIDE and CATEGORY DESEASON MOVE
# ===========================================================================

def category_deseason_move(m, cat, primary, cat_primary_base):
    if m not in cat or cat_primary_base is None:
        return None
    return log_move(cat[m].get(primary), cat_primary_base)


def rising_tide(m, cat, primary, brand_key, brand_base, primary_base):
    if m not in cat or brand_base is None or primary_base is None:
        return False
    bmove = log_move(cat[m].get(brand_key), brand_base)
    cmove = log_move(cat[m].get(primary), primary_base)
    if bmove is None or cmove is None or bmove == 0:
        return False
    return ((bmove > 0) == (cmove > 0)) and abs(cmove) >= 0.5 * abs(bmove)


# ===========================================================================
# COMPOSITE, BADGE, BAND
# ===========================================================================

def composite(dim_contribs):
    active = {d: c for d, c in dim_contribs.items() if c is not None}
    if not active:
        return None, [], {}
    wsum = sum(DIM_WEIGHTS[d] for d in active)
    normw = {d: DIM_WEIGHTS[d] / wsum for d in active}
    return sum(active[d] * normw[d] for d in active), sorted(active), normw


def to_bvi(contribution):
    if contribution is None:
        return None
    return round(clamp(NEUTRAL + contribution, DISPLAY_MIN, DISPLAY_MAX), 1)


def trajectory_badge(bvi_history, band, rising):
    scored = [v for v in bvi_history if v is not None]
    if len(scored) < 2:
        return "New"
    window = scored[-BADGE_WINDOW:] if len(scored) >= BADGE_WINDOW else scored
    move = window[-1] - window[0]
    if move > band:
        return "Watch" if rising else "Improving"
    if move < -band:
        return "Declining"
    if len(window) >= 2 and window[-1] < window[-2] and window[-1] > NEUTRAL:
        return "Watch"
    return "Stable"


def uncertainty_band(dim_vols, normw):
    terms = [(normw[d] * dim_vols[d]) ** 2 for d in normw if d in dim_vols]
    return round(math.sqrt(sum(terms)), 2) if terms else 0.0


# ===========================================================================
# FULL COMPUTATION
# ===========================================================================

def _resolve_brand_key(comp, cat, brand_key):
    if brand_key is not None:
        return brand_key
    if comp and cat:
        common = set(next(iter(comp.values()))) & set(next(iter(cat.values())))
        if len(common) == 1:
            return next(iter(common))
    raise ValueError(
        "brand_key could not be resolved unambiguously. Pass the client's "
        "brand column name explicitly; do not rely on inference.")


def compute(brand_key=None, sub_vertical=None, T=None, G=None, A=None, S=None):
    """Return a chronological list of per-month result dicts.

    brand_key    : the brand's column name in the Trends exports (required or
                   unambiguously inferable).
    sub_vertical : fashion sub-vertical for the seasonal table lookup
                   (footwear, apparel, accessories...). Falls back to
                   'default' in SEASONAL_INDEX; harmless while the table is
                   empty.
    T,G,A,S      : pre-loaded parser dicts; each falls back to its load().
    No dummy data is ever substituted.
    """
    T = T if T is not None else parse_trends.load()
    G = G if G is not None else parse_gsc.load()
    A = A if A is not None else parse_ga4.load()
    S = S if S is not None else parse_social.load()

    comp, cat = T["comp"], T["cat"]
    gsc = G["months"]
    ga4, soc = A, S

    if not comp and not cat:
        return []

    brand_key = _resolve_brand_key(comp, cat, brand_key)
    rivals = ([k for k in next(iter(comp.values())) if k != brand_key]
              if comp else [])
    cat_terms = ([k for k in next(iter(cat.values())) if k != brand_key]
                 if cat else [])

    months = sorted(set(comp) | set(cat) | set(gsc) | set(soc) | set(ga4))
    if not months:
        return []

    # ---- per-metric series and season-neutral baselines (2.5) ----------
    ser = {
        "search_impr": _series(gsc, months, "br_impr"),
        "search_clicks": _series(gsc, months, "br_clicks"),
        "search_position": _series(gsc, months, "position"),
        "search_trends": {m: comp[m].get(brand_key) for m in comp},
        "dig_direct": _series(ga4, months, "direct"),
        "dig_organic": _series(ga4, months, "organic"),
        "dig_direct_pct": _series(ga4, months, "direct_pct"),
        "soc_er": _series(soc, months, "er"),
        "soc_gr": _series(soc, months, "gr"),
        "soc_reach": _series(soc, months, "reach"),
    }

    base, base_locked = {}, {}
    baseline_windows_used = {}
    for name, s in ser.items():
        b, used, locked = baseline_mean(s, months, cycle=BASELINE_CYCLES[name])
        base[name], base_locked[name] = b, locked
        baseline_windows_used[name] = used

    # Dataset-level: does any GSC-derived baseline draw on a month inside the
    # confirmed impressions logging-bug window? (Spec: flags never suppressed.)
    baseline_gsc_impressions_affected = any(
        _in_gsc_impressions_bug_window(m)
        for key in GSC_IMPRESSIONS_BASELINE_KEYS
        for m in baseline_windows_used.get(key, set())
    )

    means = {t: statistics.fmean([cat[mo][t] for mo in cat
                                  if cat[mo].get(t) is not None])
             for t in cat_terms
             if any(cat[mo].get(t) is not None for mo in cat)}
    primary = max(means, key=means.get) if means else None

    def comp_share_at(m):
        r = comp.get(m)
        if not r or r.get(brand_key) is None:
            return None
        tot = sum(r.values())
        return r[brand_key] / tot * 100 if tot else None

    def comp_gap_at(m):
        r = comp.get(m)
        if not r or r.get(brand_key) is None:
            return None
        present = [x for x in rivals if r.get(x) is not None]
        return r[brand_key] - max(r[x] for x in present) if present else None

    def cat_gap_at(m):
        r = cat.get(m)
        if not r or primary is None or r.get(brand_key) is None or r.get(primary) is None:
            return None
        return r[brand_key] - r[primary]

    def cat_share_at(m):
        r = cat.get(m)
        if not r or r.get(brand_key) is None:
            return None
        term_sum = sum(r[t] for t in cat_terms if r.get(t) is not None)
        denom = r[brand_key] + term_sum
        return r[brand_key] / denom * 100 if denom else None

    derived = {
        "comp_share": {m: comp_share_at(m) for m in comp},
        "comp_gap": {m: comp_gap_at(m) for m in comp},
        "comp_index": ser["search_trends"],
        "cat_gap": {m: cat_gap_at(m) for m in cat},
        "cat_share": {m: cat_share_at(m) for m in cat},
        "cat_brand": {m: cat[m].get(brand_key) for m in cat},
        "cat_primary": {m: cat[m].get(primary) for m in cat} if primary else {},
    }
    for name, s in derived.items():
        b, _, locked = baseline_mean(s, months, cycle=BASELINE_CYCLES[name])
        base[name], base_locked[name] = b, locked

    seasonal_active = bool(SEASONAL_INDEX)

    # ---- per-month scoring ---------------------------------------------
    results = []
    bvi_history = []
    prev_fingerprint = None
    move_log = {}

    for m in months:
        cal_month = parse_calendar_month(m)
        seas = build_month_seasonals(sub_vertical, cal_month)
        cat_deseason = (category_deseason_move(m, cat, primary, base["cat_primary"])
                        if primary else None)

        dim_objs = {
            "Search": score_search(m, gsc, comp, brand_key, base, cat_deseason, seas),
            "Digital": score_digital(m, ga4, base, seas),
            "Social": score_social(m, soc, base, seas),
            "Competitive": score_competitive(m, comp, rivals, brand_key, base),
            "Category": score_category(m, cat, cat_terms, primary, brand_key, base),
        }

        contribs = {d: (o["contribution"] if o["active"] else None)
                    for d, o in dim_objs.items()}
        contribution, active, normw = composite(contribs)
        bvi = to_bvi(contribution)

        # flags -----------------------------------------------------------
        flags = []
        flags.extend(_data_gap_flags(m, gsc, comp, cat, ga4, soc))
        for d, o in dim_objs.items():
            for s in o.get("capped", []):
                flags.append("LARGE_SWING_%s" % s.upper())
            for s in o.get("small_base", []):
                flags.append("SMALL_BASE_%s" % s.upper())
            flags.extend(o.get("flags", []))
        rt = (rising_tide(m, cat, primary, brand_key,
                          base["cat_brand"], base["cat_primary"])
              if primary else False)
        if rt:
            flags.append("RISING_TIDE")
        if m in gsc and _in_gsc_impressions_bug_window(m):
            flags.append("GSC_IMPRESSIONS_UNRELIABLE")
        if _provisional_baseline(active, base_locked):
            flags.append("PROVISIONAL_BASELINE")
        unlocked_dims = _unlocked_dimensions(active, base_locked)
        baseline_not_locked_text = None
        if unlocked_dims:
            flags.append("BASELINE_NOT_LOCKED")
            baseline_not_locked_text = _baseline_not_locked_text(unlocked_dims)
        if bvi is not None and len(active) < 2:
            flags.append("INSUFFICIENT_TIER")
            bvi = None

        fingerprint = tuple(active)
        mom_comparable = (prev_fingerprint is not None
                          and fingerprint == prev_fingerprint
                          and fingerprint != ())
        if bvi is not None and prev_fingerprint is not None and not mom_comparable:
            flags.append("SIGNAL_CHANGE")

        dim_vols = _dimension_vols(dim_objs, move_log)
        band = uncertainty_band(dim_vols, normw) if normw else 0.0
        if band and band > SIGNAL_CAP * 0.25:
            flags.append("WIDE_BAND")
        badge = trajectory_badge(bvi_history + [bvi], band, rt) if bvi is not None else "-"

        prev_bvi = next((v for v in reversed(bvi_history) if v is not None), None)
        mom_delta = (round(bvi - prev_bvi, 1)
                     if (bvi is not None and prev_bvi is not None and mom_comparable)
                     else None)

        results.append({
            "month": m,
            "calendar_month": cal_month,
            "status": "scored" if bvi is not None else "no_score",
            "bvi_score": bvi,
            "mom_delta": mom_delta,
            "badge": badge,
            "uncertainty_band": band,
            "confidence_tier": _confidence_tier(active),
            "seasonal_adjustment_active": seasonal_active,
            "active": active,
            "normalized_weights": normw,
            "rising_tide": rt,
            "flags": sorted(set(flags)),
            "baseline_gsc_impressions_affected": baseline_gsc_impressions_affected,
            "baseline_not_locked_text": baseline_not_locked_text,
            "primary_category": primary,
            "dimensions": {d: {
                "contribution": dim_objs[d]["contribution"],
                "signals": dim_objs[d]["signals"],
            } for d in DIMS},
        })
        bvi_history.append(bvi)
        if fingerprint != ():
            prev_fingerprint = fingerprint

    return results


# ---- helper predicates ----------------------------------------------------

_DIM_BASELINE_KEYS = {
    "Search": ["search_impr", "search_clicks", "search_trends"],
    "Digital": ["dig_direct", "dig_organic", "dig_direct_pct"],
    "Social": ["soc_er", "soc_reach"],
    "Competitive": ["comp_share", "comp_gap", "comp_index"],
    "Category": ["cat_gap", "cat_share"],
}


def _provisional_baseline(active, base_locked):
    """True if any active dimension has a baseline shorter than a full cycle."""
    for d in active:
        for k in _DIM_BASELINE_KEYS.get(d, []):
            if k in base_locked and base_locked[k] is False:
                return True
    return False


def _unlocked_dimensions(active, base_locked):
    """Names of active dimensions with at least one baseline still expanding
    (not yet at its full per-metric window, BASELINE_CYCLES). Order matches
    DIMS so the flag text is stable run to run."""
    unlocked = []
    for d in active:
        if any(base_locked.get(k) is False for k in _DIM_BASELINE_KEYS.get(d, [])):
            unlocked.append(d)
    return unlocked


def _baseline_not_locked_text(unlocked_dims):
    """Human-readable BASELINE_NOT_LOCKED text naming the accumulating dimensions."""
    if not unlocked_dims:
        return None
    names = ", ".join(unlocked_dims)
    return (f"Baseline still accumulating for: {names}. This score is running "
            f"against a moving reference until the full baseline window is reached.")


def _data_gap_flags(m, gsc, comp, cat, ga4, soc):
    flags = []
    if m not in gsc:
        flags.append("DATA_GAP_GSC")
    if m not in comp:
        flags.append("DATA_GAP_TRENDS1")
    if m not in cat:
        flags.append("DATA_GAP_TRENDS2")
    if m not in ga4:
        flags.append("DATA_GAP_GA4")
    if m not in soc:
        flags.append("DATA_GAP_SOCIAL")
    return flags


def _dimension_vols(dim_objs, move_log):
    for d, o in dim_objs.items():
        for name, mv in o.get("moves", {}).items():
            move_log.setdefault((d, name), []).append(mv)
    out = {}
    for d, o in dim_objs.items():
        vols = []
        for name in o.get("signals", {}):
            mode = o["signals"][name]["mode"]
            floor = VOL_FLOOR_PCT if mode in ("point", "position") else VOL_FLOOR_LOG
            sens = (PCT_POINT_SENSITIVITY if mode == "point"
                    else POSITION_SENSITIVITY if mode == "position"
                    else LOG_SENSITIVITY)
            vols.append(sens * month_to_month_vol(move_log.get((d, name), []), floor))
        if vols:
            out[d] = statistics.fmean(vols)
    return out


def _confidence_tier(active):
    a = set(active)
    if {"Social_Listening", "Paid", "Direct_Awareness"} <= a:
        return "Gold"
    if {"Social_Listening", "Paid"} <= a:
        return "Silver"
    return "Bronze"


# ===========================================================================
# HUMAN-READABLE SUMMARY
# ===========================================================================

def main():
    results = compute()
    if not results:
        print("No months to score.")
        return
    first = results[0]
    print("Primary category term: %s" % first["primary_category"])
    print("Seasonal adjustment active: %s (permanently inert, v2.2 -- see BASELINE_CYCLES)"
          % first["seasonal_adjustment_active"])
    print("Months: %d (%s -> %s)\n"
          % (len(results), results[0]["month"], results[-1]["month"]))

    print("Per-metric baseline windows (Spec 2.5, v2.2):")
    for name, cycle in BASELINE_CYCLES.items():
        print("  %-15s %2d months" % (name, cycle))
    print()

    head = ("%-9s%7s%9s%7s%9s   %-9s   %s"
            % ("Month", "BVI", "MoM", "Band", "Badge", "Tier", "Flags"))
    print(head)
    print("-" * (len(head) + 20))
    for r in results:
        bvi = ("%.1f" % r["bvi_score"]) if r["bvi_score"] is not None else "-"
        mom = ("%+.1f" % r["mom_delta"]) if r["mom_delta"] is not None else "-"
        band = ("%.1f" % r["uncertainty_band"]) if r["uncertainty_band"] else "-"
        print("%-9s%7s%9s%7s%9s   %-9s   %s"
              % (r["month"], bvi, mom, band, r["badge"],
                 r["confidence_tier"], " ".join(r["flags"]) or "-"))
        if r.get("baseline_not_locked_text"):
            print("           -> %s" % r["baseline_not_locked_text"])

    print("\nDimension baseline lock status (as of the last scored month):")
    last = results[-1]
    last_text = last.get("baseline_not_locked_text") or ""
    last_active = last.get("active") or []
    for d in DIMS:
        if d not in last_active:
            status = "inactive/no data this month"
        elif d in last_text:
            status = "still accumulating (not yet locked)"
        else:
            status = "locked"
        print("  %-13s %s" % (d, status))


if __name__ == "__main__":
    main()
