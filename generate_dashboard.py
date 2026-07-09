#!/usr/bin/env python3
"""Generate a Fusepoint-branded BVI dashboard HTML for any client.

Entry point: generate(client_config, T, G_data, A, S) -> html string

client_config keys:
  client_name  - display name shown in dashboard header (e.g. "KEEN")
  brand_key    - Trends CSV column header for the brand (e.g. "KEEN")
  rivals       - list of competitor column headers from Trends Export 1 (up to 3)
  comp_display - list of competitor display names (defaults to rivals if omitted)
  primary      - primary category term from Trends Export 2
  cat2         - 2nd category term (or None)
  cat3         - 3rd category term (or None)

G_data must include "months", "position", and "ctr" keys (from parse_gsc.load_from).
S must include "net" key per month (from parse_social.load_from).
"""

import json
import os
from datetime import datetime

import score_bvi

_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(_DIR, "bvi-demo-gold-unlocked (5).html")


# ── Formatting helpers ─────────────────────────────────────────────────────

def jnum(v, dec=None):
    if v is None:
        return "null"
    if dec is not None:
        v = round(v, dec)
        return str(int(v)) if dec == 0 else str(v)
    return str(v)


def js_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def label(month):
    return datetime.strptime(month + "-01", "%Y-%m-%d").strftime("%b '%y")


def mom_pct(cur, prev):
    return None if prev in (None, 0) else (cur - prev) / prev * 100


def fmt_signed(v, pts=False):
    if v is None:
        return "—"
    if pts:
        return ("+" if v >= 0 else "") + f"{v:.0f}pts"
    return ("+" if v >= 0 else "") + f"{v:.0f}"


def sgn(v, dec=0, suf=""):
    if v is None:
        return "n/a"
    return f"{v:+.{dec}f}{suf}"


def _gap_mom_pts(cat, m, pm, primary, brand_key):
    if m not in cat or pm not in cat:
        return None
    return (cat[m][brand_key] - cat[m][primary]) - (cat[pm][brand_key] - cat[pm][primary])


# ── Data block ─────────────────────────────────────────────────────────────

def _build_data_block(cfg, T, G_data, A, S):
    brand_key = cfg["brand_key"]
    rivals = cfg["rivals"]
    primary = cfg["primary"]
    cat2 = cfg.get("cat2")
    cat3 = cfg.get("cat3")

    comp, cat, gsc = T["comp"], T["cat"], G_data["months"]
    position = G_data.get("position", {})
    ctr = G_data.get("ctr", {})

    # score_bvi v2.1 reads GSC average position from G["months"][m]["position"],
    # but parse_gsc.load_from() (unchanged parser) returns it as a separate
    # top-level G_data["position"] dict. Build a scoring-only G view that nests
    # it where the engine expects it, without touching the parser or G_data.
    G_for_scoring = {
        **G_data,
        "months": {
            mo: ({**vals, "position": position[mo]} if mo in position else dict(vals))
            for mo, vals in gsc.items()
        },
    }

    # Score results keyed by month
    results = {r["month"]: r for r in score_bvi.compute(
        brand_key=brand_key, T=T, G=G_for_scoring, A=A, S=S
    )}

    comp_months = sorted(comp)
    months = sorted(set(comp) | set(cat) | set(gsc) | set(S) | set(A))
    window = months[-12:]

    DLAB = {"Search": "Search Demand", "Social": "Organic Social",
            "Competitive": "Competitive Position", "Category": "Category Context"}

    rows = []
    for m in window:
        i = months.index(m)
        pm = months[i - 1] if i > 0 else None
        r = results.get(m, {})

        # GSC branded metrics
        impr_k = round(gsc[m]["br_impr"] / 1000) if m in gsc else None
        clk_k = round(gsc[m]["br_clicks"] / 1000) if m in gsc else None
        impr_d = mom_pct(gsc[m]["br_impr"], gsc[pm]["br_impr"]) if m in gsc and pm in gsc else None
        clk_d = mom_pct(gsc[m]["br_clicks"], gsc[pm]["br_clicks"]) if m in gsc and pm in gsc else None
        ctr_d = (ctr[m] - ctr[pm]) if m in ctr and pm in ctr else None
        pos_d = (position[m] - position[pm]) if m in position and pm in position else None

        # Trends — this month may have no Trends data even if other sources do
        has_comp = m in comp
        kg = comp[m][brand_key] if has_comp else None
        kg_prev = comp[pm][brand_key] if pm in comp else None
        ti_d = (kg - kg_prev) if kg is not None and kg_prev is not None else None
        yoy = None
        if has_comp and i >= 12:
            back_idx = comp_months.index(m) - 12 if m in comp_months and comp_months.index(m) >= 12 else None
            if back_idx is not None:
                back = comp_months[back_idx]
                yoy = mom_pct(kg, comp[back][brand_key])

        share = (kg / sum(comp[m].values()) * 100) if has_comp and comp[m] else None
        share_prev = comp[pm][brand_key] / sum(comp[pm].values()) * 100 if pm in comp and comp[pm] else None
        share_d = (share - share_prev) if share is not None and share_prev is not None else None

        # GA4
        has_ga = m in A
        ds = round(A[m]["direct"] / 1000) if has_ga else None
        os_ = round(A[m]["organic"] / 1000) if has_ga else None
        dpct = round(A[m]["direct_pct"]) if has_ga else None
        total_k = round(A[m]["total"] / 1000) if has_ga else None

        # Social
        er = S[m]["er"] if m in S else None
        er_d = (S[m]["er"] - S[pm]["er"]) if m in S and pm in S else None
        gr = S[m]["gr"] if m in S else None
        gr_d = (S[m]["gr"] - S[pm]["gr"]
                if m in S and pm in S and S[m]["gr"] is not None and S[pm]["gr"] is not None
                else None)
        reach_k = round(S[m]["reach"] / 1000) if m in S else None
        net = S[m].get("net") if m in S else None

        # Category
        cat_primary = cat[m][primary] if m in cat else None
        # v2.1: rising_tide is a top-level boolean on the result, not a nested
        # Category signal (the old engine scored rising-tide as a signal itself).
        rising = bool(r.get("rising_tide", False))

        bvi = round(r["bvi_score"]) if r.get("bvi_score") is not None else None
        # v2.1: "badge" replaces "momentum" (Improving/Watch/Declining/Stable/New/-
        # instead of Rising/Declining/Stable).
        momentum = r.get("badge", "—")

        # Competitor slots (sm=rivals[0], car=rivals[1], ted=rivals[2])
        sm_v = comp[m][rivals[0]] if m in comp and len(rivals) > 0 else None
        car_v = comp[m][rivals[1]] if m in comp and len(rivals) > 1 else None
        ted_v = comp[m][rivals[2]] if m in comp and len(rivals) > 2 else None

        # Narratives
        what = (f"BVI {bvi} ({momentum}). "
                f"Branded impressions {fmt_signed(impr_d)}% MoM, "
                f"branded clicks {fmt_signed(clk_d)}% MoM, "
                f"Trends index {fmt_signed(ti_d, pts=True)}.")
        kg_disp = kg if kg is not None else "—"
        cat_primary_disp = cat_primary if cat_primary is not None else "—"
        catctx = (f"Brand Trends index ({kg_disp}) vs. primary category \"{primary}\" "
                  f"({cat_primary_disp}). Rising tide {'active' if rising else 'not detected'}."
                  if has_comp or m in cat else
                  "No Trends data for this month.")

        # Nearest competitor
        rival_idx = {r: comp[m][r] for r in rivals if r in comp.get(m, {})}
        nearest = max(rival_idx, key=rival_idx.get) if rival_idx else (rivals[0] if rivals else "")
        nval = comp.get(m, {}).get(nearest, 0)
        share_disp = round(share) if share is not None else "—"
        compshift = (f"Nearest competitor {nearest} at index {nval}; "
                     f"{brand_key} brand share {share_disp}% of tracked Trends."
                     if has_comp else
                     "No Trends data for this month — competitive position unavailable.")

        prior_bvi = (round(results[pm]["bvi_score"])
                     if pm in results and results[pm].get("bvi_score") is not None else None)
        bvi_delta = (bvi - prior_bvi) if (bvi is not None and prior_bvi is not None) else None

        # v2.1: dimensions[d]["score"] (0-100, neutral=55) is now
        # dimensions[d]["contribution"] (BVI points, neutral=0).
        dscore = {d: r["dimensions"][d]["contribution"] for d in
                  ("Search", "Social", "Competitive", "Category")
                  if r.get("dimensions", {}).get(d, {}).get("contribution") is not None}
        DETAIL = {
            "Search": f"branded impressions {sgn(impr_d)}%, Trends index {sgn(ti_d, suf='pts')}",
            "Social": f"engagement rate {sgn(er_d, 2, 'pts')}, follower growth {sgn(gr_d, 2, 'pts')}",
            "Competitive": f"brand share {sgn(share_d, 1, 'pts')} vs {nearest}",
            "Category": f'brand-vs-"{primary}" gap {sgn(_gap_mom_pts(cat, m, pm, primary, brand_key), suf="pts")}',
        }
        if not dscore:
            driver = "Search"
        elif bvi_delta is not None and bvi_delta > 0:
            driver = max(dscore, key=lambda k: dscore[k])
        elif bvi_delta is not None and bvi_delta < 0:
            driver = min(dscore, key=lambda k: dscore[k])
        else:
            driver = max(dscore, key=lambda k: abs(dscore[k]))
        if bvi_delta is None:
            move = ""
        elif bvi_delta > 0:
            move = f", up {bvi_delta} MoM"
        elif bvi_delta < 0:
            move = f", down {abs(bvi_delta)} MoM"
        else:
            move = ", unchanged MoM"
        why = (f"BVI {bvi}{move}. "
               f"Movement led by {DLAB.get(driver, driver)} ({DETAIL.get(driver, '')}).")
        if rising:
            why += (f' Rising-tide flag active — "{primary}" moved with the brand, '
                    f"so part of the shift is category-wide, not brand-specific.")

        delta_str = (f" ({'+' if bvi_delta and bvi_delta >= 0 else ''}{bvi_delta} pts MoM)"
                     if bvi_delta is not None else "")
        if momentum == "Declining":
            reco = (f"BVI slipped{delta_str} — treat as a watch month and confirm the dip "
                    f"persists before changing strategy. "
                    f"{DLAB.get(driver, driver)} was the main drag ({DETAIL.get(driver, '')}).")
        elif momentum == "Improving":
            reco = (f"Momentum positive{delta_str}. "
                    f"{DLAB.get(driver, driver)} led the move ({DETAIL.get(driver, '')}) — "
                    f"reinforce this channel and feature in client reporting.")
        else:
            reco = (f"BVI held steady{delta_str}. "
                    f"Signals mixed — {DLAB.get(driver, driver)} had the widest swing "
                    f"({DETAIL.get(driver, '')}). Hold course and watch next month.")
        if rising:
            reco += (f' Rising-tide note: "{primary}" category moved with the brand '
                     f"this month — discount Trends-based gains when reporting.")
        elif share_d is not None and share_d >= 2:
            reco += f" Lead with competitive share gains vs {nearest} (+{round(share_d)} pts)."
        elif share_d is not None and share_d <= -2:
            reco += f" Watch share erosion vs {nearest} ({round(share_d)} pts); audit branded search coverage."

        obj = (
            f'{{bvi:{jnum(bvi)},status:"live",'
            f'impressions:{jnum(impr_k)},impressionsDelta:{jnum(impr_d,0)},'
            f'clicks:{jnum(clk_k)},clicksDelta:{jnum(clk_d,0)},'
            f'ctr:{jnum(ctr.get(m),2)},ctrDelta:{jnum(ctr_d,2)},'
            f'position:{jnum(position.get(m),1)},positionDelta:{jnum(pos_d,1)},'
            f'trendsIdx:{jnum(kg)},trendsIdxDelta:{jnum(ti_d,0)},trendsYoY:{jnum(yoy,0)},'
            f'directSessions:{jnum(ds)},directSessionsDelta:null,'
            f'directPct:{jnum(dpct)},directPctDelta:null,'
            f'organicSessions:{jnum(os_)},organicSessionsDelta:null,'
            f'totalSessions:{jnum(total_k)},totalSessionsDelta:null,'
            f'brandedOrganic:null,brandedOrganicDelta:null,'
            f'followerGrowthRate:{jnum(gr,2)},followerGrowthRateDelta:{jnum(gr_d,2)},'
            f'netFollowerGrowth:{jnum(net)},reach:{jnum(reach_k)},'
            f'engagementRate:{jnum(er,2)},engagementRateDelta:{jnum(er_d,2)},'
            f'kgTrends:{jnum(kg)},smTrends:{jnum(sm_v)},'
            f'carTrends:{jnum(car_v)},tedTrends:{jnum(ted_v)},'
            f'kgVol:null,smVol:null,carVol:null,tedVol:null,'
            f'brandShare:{jnum(share,0)},brandShareDelta:{jnum(share_d,0)},'
            f'catTrends:{jnum(cat_primary)},catVol:null,catVolDelta:null,'
            f'risingTide:{"true" if rising else "false"},'
            f'mentionVol:null,mentionVolDelta:null,sentimentPct:null,sentimentDelta:null,'
            f'sov:null,sovDelta:null,earnedReach:null,influencerReach:null,emv:null,'
            f'kgSentiment:null,smSentiment:null,carSentiment:null,tedSentiment:null,'
            f'brandedCpmGoogle:null,brandedCpmMeta:null,cpmGoogleDelta:null,cpmMetaDelta:null,'
            f'impressionShare:null,impressionShareDelta:null,paidCtr:null,paidCtrDelta:null,'
            f'whatMoved:{js_str(what)},whyItMoved:{js_str(why)},'
            f'categoryContext:{js_str(catctx)},competitiveShift:{js_str(compshift)},'
            f'recommendation:{js_str(reco)}}}'
        )

        # Storage dict: JS obj string + cat series values needed to rebuild CAT_TRENDS arrays
        storage = {
            "obj": obj,
            "catTrends": cat_primary,
            "cat2Trends": cat[m].get(cat2) if m in cat and cat2 else None,
            "cat3Trends": cat[m].get(cat3) if m in cat and cat3 else None,
        }
        rows.append((m, obj, storage))

    months_lbls = ",".join(f'"{label(m)}"' for m, _, _s in rows)
    cat_p = ",".join(str(cat.get(m, {}).get(primary, "null")) for m, _, _s in rows)
    cat_2 = ",".join(str(cat.get(m, {}).get(cat2, "null")) if cat2 else "null" for m, _, _s in rows)
    cat_3 = ",".join(str(cat.get(m, {}).get(cat3, "null")) if cat3 else "null" for m, _, _s in rows)
    raw_js = ",\n  ".join(obj for _, obj, _s in rows)

    block = (
        "// ── DATA ────────────────────────────────────────────────────────────────────\n"
        f"const MONTHS = [{months_lbls}];\n"
        f"const CAT_TRENDS  = [{cat_p}];\n"
        f"const CAT_TRENDS2 = [{cat_2}];\n"
        f"const CAT_TRENDS3 = [{cat_3}];\n\n"
        f"const RAW = [\n  {raw_js}\n];\n\n"
        "const SURVEYS = [];\n\n"
        "// ── STATE ────────────────────────────────────────────────────────────────────\n"
    )
    month_rows = [(m, storage) for m, _, storage in rows]
    return block, month_rows, results


# ── Replacement list ────────────────────────────────────────────────────────

def _get_repl_list(cfg):
    client_name = cfg["client_name"]
    rivals = cfg["rivals"]
    comp_display = cfg.get("comp_display", rivals)
    # Pad to 3 slots
    while len(comp_display) < 3:
        comp_display.append(f"Competitor {len(comp_display) + 1}")

    primary = cfg.get("primary") or "Category"
    cat2 = cfg.get("cat2") or "Category 2"
    cat3 = cfg.get("cat3") or "Category 3"

    # Title-case helper for competitor display names
    def disp(s):
        return s.strip()

    c1, c2, c3 = disp(comp_display[0]), disp(comp_display[1]), disp(comp_display[2])

    return [
        # ── Client / competitor name swaps ────────────────────────────────────
        (f"BVI Dashboard — Kurt Geiger London (Demo)",
         f"BVI Dashboard — {client_name} (Bronze)"),
        ("Kurt Geiger London", client_name),
        ("Kurt Geiger", client_name),
        ("Steve Madden", c1),
        ("Carvela", c2),
        ("Ted Baker", c3),
        ('"women\'s shoes"', f'"{primary}"'),
        ('"luxury footwear"', f'"{cat2}"'),
        ('"designer shoes"', f'"{cat3}"'),
        ("All tiers unlocked", "Bronze tier"),
        ("dummy data", "data"),
        ('tier: "gold"', 'tier: "bronze"'),
        ("<!-- DEMO BANNER -->", "<!-- VERSION BANNER -->"),
        ("Prototype Demo Mode", "BVI v1.01 — Prototype"),
        ('<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:#E3FF43;color:#2B2A29;font-weight:700">Demo</span>', ""),
        ('<span style="font-size:9px;padding:1px 6px;border-radius:3px;background:#E3FF43;color:#2B2A29;font-weight:700;margin-right:4px">Demo</span>', ""),
        # Null guards
        ('d.directSessions.toLocaleString()+"K"',
         '(d.directSessions!=null?d.directSessions.toLocaleString()+"K":"—")'),
        ('d.organicSessions.toLocaleString()+"K"',
         '(d.organicSessions!=null?d.organicSessions.toLocaleString()+"K":"—")'),
        ('d.catVol.toLocaleString()+"K"',
         '(d.catVol!=null?d.catVol.toLocaleString()+"K":"—")'),
        ('d.netFollowerGrowth.toLocaleString()',
         '(d.netFollowerGrowth!=null?d.netFollowerGrowth.toLocaleString():"—")'),
        ('d.reach.toLocaleString()',
         '(d.reach!=null?d.reach.toLocaleString():"—")'),
        ('d.directPct+"%"', '(d.directPct!=null?d.directPct+"%":"—")'),
        ('d.brandedOrganic+"%"', '(d.brandedOrganic!=null?d.brandedOrganic+"%":"—")'),
        ('${d.directPct}%', '${d.directPct!=null?d.directPct+"%":"—"}'),
        ('${d.brandedOrganic}%', '${d.brandedOrganic!=null?d.brandedOrganic+"%":"—"}'),
        ('${br.vol}K', '${br.vol!=null?br.vol+"K":"—"}'),
        # BUG: renderSearch crashed on d.impressions/d.clicks.toLocaleString() when
        # a month has GSC/Trends data but no branded GSC metrics (or vice versa)
        ('d.impressions.toLocaleString()+"K"',
         '(d.impressions!=null?d.impressions.toLocaleString()+"K":"—")'),
        ('d.clicks.toLocaleString()+"K"',
         '(d.clicks!=null?d.clicks.toLocaleString()+"K":"—")'),
        # Same pattern in renderListening/renderPaid/renderAwareness — these
        # dimensions are always null in Bronze tier today, but guard anyway
        # so a future tier unlock can't hit the same crash.
        ('d.mentionVol.toLocaleString()',
         '(d.mentionVol!=null?d.mentionVol.toLocaleString():"—")'),
        ('d.earnedReach.toLocaleString()+"K"',
         '(d.earnedReach!=null?d.earnedReach.toLocaleString()+"K":"—")'),
        ('d.influencerReach.toLocaleString()+"K"',
         '(d.influencerReach!=null?d.influencerReach.toLocaleString()+"K":"—")'),
        ('survey.sampleSize.toLocaleString()',
         '(survey.sampleSize!=null?survey.sampleSize.toLocaleString():"—")'),
        # Cleanup: the bare d.reach guard above leaves a stray "—K" when reach is
        # null (guard wraps toLocaleString() but the +"K" suffix is outside it).
        ('(d.reach!=null?d.reach.toLocaleString():"—")+"K"',
         '(d.reach!=null?d.reach.toLocaleString()+"K":"—")'),
        # BUG-2: Add "Total sessions" metric card to Digital tab
        ('${metricCard("Total organic sessions",(d.organicSessions!=null?d.organicSessions.toLocaleString()+"K":"—"),d.organicSessionsDelta,"%","","GA4 — Session channel group = Organic Search.")}',
         '${metricCard("Total organic sessions",(d.organicSessions!=null?d.organicSessions.toLocaleString()+"K":"—"),d.organicSessionsDelta,"%","","GA4 — Session channel group = Organic Search.")}\n'
         '    ${metricCard("Total sessions",(d.totalSessions!=null?d.totalSessions.toLocaleString()+"K":"—"),d.totalSessionsDelta,"%","","GA4 — Grand Total row across all channels.")}'),
        # UX-8: Remove "Why this matters" tab
        ('{id:"methodology",label:"Why this matters"},', ''),
        ('else if(activeTab==="methodology") tabContent = renderMethodology();', ''),
        # UX-2: Filter methodology modal scales
        ('${SCALES.map(sc=>`<div class="card" style="padding:10px 12px">',
         '${SCALES.filter(sc=>spec.signals.some(sig=>sig.s.toLowerCase()'
         '.startsWith(sc.name.split(\' \')[0].toLowerCase()))).map(sc=>`<div class="card" style="padding:10px 12px">'),
        # UX-3a: Digital no-data guard
        ('if(dimId==="digital") {\n    const pos=[d.directPctDelta',
         'if(dimId==="digital") {\n'
         '    if(d.directSessions==null&&d.organicSessions==null)return null;\n'
         '    const pos=[d.directPctDelta'),
        # UX-3b: Digital tab message
        ('function renderDigital(d) {\n  return `<div class="grid2">',
         'function renderDigital(d) {\n'
         '  if(d.directSessions==null&&d.organicSessions==null)return `'
         '<div style="padding:32px 0;text-align:center">'
         '<div style="font-size:14px;font-weight:600;color:#ABABAB;margin-bottom:6px">No GA4 data for this period</div>'
         '<div style="font-size:12px;color:#ABABAB;line-height:1.6">Traffic acquisition data is available for months where GA4 was connected.</div>'
         '</div>`;\n'
         '  return `<div class="grid2">'),
        # UX-4a: showTip popover
        ('const STATUS_CFG = {',
         'function showTip(el,text){'
         'let t=document.getElementById(\'_fp_tip\');'
         'if(!t){'
         't=document.createElement(\'div\');t.id=\'_fp_tip\';'
         't.style.cssText=\'position:fixed;z-index:9999;max-width:220px;background:#1F1E1D;'
         'color:#FAF7F2;font-size:11px;line-height:1.5;padding:8px 10px;border-radius:6px;'
         'pointer-events:none;opacity:0;transition:opacity .15s;box-shadow:0 2px 8px rgba(0,0,0,.25)\';'
         'document.body.appendChild(t);'
         'document.addEventListener(\'click\',()=>{t.style.opacity=\'0\';},true);}'
         't.textContent=text;const r=el.getBoundingClientRect();'
         't.style.left=Math.min(r.left,window.innerWidth-230)+\'px\';'
         't.style.top=(r.bottom+6)+\'px\';t.style.opacity=\'1\';event.stopPropagation();}\n'
         'const STATUS_CFG = {'),
        # UX-4b: ? bubble onclick
        ('<span title="${tip}" style="width:14px;height:14px;border-radius:50%;'
         'background:rgba(171,171,171,.25);display:inline-flex;align-items:center;'
         'justify-content:center;font-size:10px;color:#ABABAB;cursor:help;font-weight:700">?</span>',
         '<span onclick="event.stopPropagation();showTip(this,\'${tip}\')" '
         'style="width:14px;height:14px;border-radius:50%;background:rgba(171,171,171,.25);'
         'display:inline-flex;align-items:center;justify-content:center;'
         'font-size:10px;color:#ABABAB;cursor:pointer;font-weight:700">?</span>'),
        # UX-5a: MoM text per dimension
        ('const factors = info.factors || [];',
         'const factors = info.factors || [];\n'
         '  const momText = {'
         'search:d.impressionsDelta!=null?(d.impressionsDelta>0?"+":"")+d.impressionsDelta+"% MoM":null,'
         'digital:d.directPctDelta!=null?(d.directPctDelta>0?"+":"")+d.directPctDelta+" pts MoM":null,'
         'social:d.engagementRateDelta!=null?((d.engagementRateDelta>0?"+":"")+parseFloat(d.engagementRateDelta).toFixed(1)+" pts MoM"):null,'
         'competitive:d.brandShareDelta!=null?(d.brandShareDelta>0?"+":"")+d.brandShareDelta+" pts MoM":null,'
         'category:prev&&d.catTrends!=null&&prev.catTrends!=null?((d.catTrends-prev.catTrends>=0?"+":"")+(d.catTrends-prev.catTrends)+" pts MoM"):null'
         '}[dimId]||null;'),
        # UX-5b: append MoM to status badge
        ('white-space:nowrap">${info.status}</span>',
         'white-space:nowrap">${info.status}${momText?" "+momText:""}</span>'),
        # UX-6a–c: Category chart line colors
        ('stroke="#B4B2A9" stroke-width="1" stroke-dasharray="2,4"',
         'stroke="#3B82C4" stroke-width="1.5" stroke-dasharray="4,3"'),
        ('stroke="${B.lightPurple}" stroke-width="1" stroke-dasharray="2,3"',
         'stroke="#2D9C6B" stroke-width="1.5" stroke-dasharray="5,3"'),
        ('stroke="${B.gray}" stroke-width="1.5" stroke-dasharray="3,3"',
         'stroke="#D97706" stroke-width="1.5" stroke-dasharray="3,3"'),
        # UX-6d–f: Category legend colors (these run AFTER name swaps, so use new names)
        (f'{{color:B.gray,bold:false,label:`"{primary}"',
         f'{{color:"#D97706",bold:false,label:`"{primary}"'),
        (f'{{color:B.lightPurple,bold:false,label:`"{cat2}"',
         f'{{color:"#2D9C6B",bold:false,label:`"{cat2}"'),
        (f'{{color:"#B4B2A9",bold:false,label:`"{cat3}"',
         f'{{color:"#3B82C4",bold:false,label:`"{cat3}"'),
        # UX-6g: highlight dot on primary category line
        ('cy="${yp(RAW[idx].catTrends)}" r="3" fill="${B.gray}"',
         'cy="${yp(RAW[idx].catTrends)}" r="3" fill="#D97706"'),
        # ── BRAND-1: Fusepoint visual reskin ─────────────────────────────────
        ("@import url('https://fonts.googleapis.com/css2?family=Darker+Grotesque:wght@400;600;700&display=swap');",
         "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap');"),
        ("font-family:'Darker Grotesque',Arial,Helvetica,sans-serif;background:#F5F5F5;color:#2B2A29;",
         "font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#FAF7F2;color:#1F1E1D;"),
        ("button{font-family:'Darker Grotesque',Arial,Helvetica,sans-serif;",
         "button{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;"),
        ("font-family:'Darker Grotesque',Arial,sans-serif;",
         "font-family:'Inter',sans-serif;"),
        ('font-family="\'Darker Grotesque\',Arial,sans-serif"',
         'font-family="\'Inter\',sans-serif"'),
        ('.card{background:#fff;border:0.5px solid rgba(171,171,171,0.3);',
         '.card{background:#FFFFFF;border:0.5px solid #E5E2DC;'),
        ('.purple-card{background:#7756FF;',
         '.purple-card{background:#1F1E1D;'),
        ('.dark-card{background:#2B2A29;',
         '.dark-card{background:#1F1E1D;'),
        ('.label{font-size:10px;color:#ABABAB;',
         '.label{font-size:10px;color:#8A8782;'),
        ('.big-num{font-size:22px;font-weight:700;color:#2B2A29;',
         '.big-num{font-size:22px;font-weight:700;color:#1F1E1D;'),
        ('.dim-expand{background:#F5F5F5;',
         '.dim-expand{background:#F5F0E6;'),
        ('.dim-row{border-bottom:0.5px solid rgba(171,171,171,.15)}',
         '.dim-row{border-bottom:0.5px solid #E5E2DC}'),
        ('.tab-btn.active{font-weight:700;color:#7756FF;background:rgba(119,86,255,.05);border-bottom:2px solid #7756FF}',
         '.tab-btn.active{font-weight:700;color:#1F1E1D;background:rgba(255,207,112,.12);border-bottom:2px solid #FFCF70}'),
        ('.tab-btn:hover:not(.active){color:#2B2A29}',
         '.tab-btn:hover:not(.active){color:#1F1E1D}'),
        ('.modal-box{background:#F5F5F5;',
         '.modal-box{background:#FAF7F2;'),
        ('.modal-header{background:#2B2A29;',
         '.modal-header{background:#1F1E1D;'),
        ('class="label" style="color:#AFAAF9;margin-bottom:3px">Scoring methodology',
         'class="label" style="color:#B5B0A6;margin-bottom:3px">Scoring methodology'),
        ('font-size:18px;font-weight:700;color:#F5F5F5',
         'font-size:18px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif;color:#FAF7F2'),
        ('.note-box{padding:8px 12px;background:#F5F5F5;',
         '.note-box{padding:8px 12px;background:#F5F0E6;'),
        ('.signal-tag{font-size:11px;padding:3px 10px;border-radius:4px;background:rgba(119,86,255,.1);color:#7756FF;font-weight:600}',
         '.signal-tag{font-size:11px;padding:3px 10px;border-radius:4px;background:rgba(255,207,112,.25);color:#1F1E1D;font-weight:600}'),
        ('nearBlack:"#2B2A29", purple:"#7756FF", lightPurple:"#AFAAF9"',
         'nearBlack:"#1F1E1D", purple:"#FFCF70", lightPurple:"#B5B0A6"'),
        ('gray:"#ABABAB", offWhite:"#F5F5F5", yellow:"#E3FF43"',
         'gray:"#8A8782", offWhite:"#FAF7F2", yellow:"#FFCF70"'),
        ('font-size:58px;font-weight:700;color:#F5F5F5;line-height:1',
         'font-size:58px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif;color:#FAF7F2;line-height:1'),
        # Client name font: runs AFTER name swap, so target client_name
        (f'font-size:20px;font-weight:700">{client_name}',
         f"font-size:30px;font-weight:400;font-family:'Instrument Serif',Georgia,serif\">{client_name}"),
        ('font-size:11px;color:#ABABAB">Power Digital Marketing \xb7 Monthly brand health report',
         'font-size:11px;color:#6B6864">Power Digital Marketing \xb7 Monthly brand health report'),
        ('border:0.5px solid #7756FF;background:transparent;color:#7756FF;cursor:pointer;'
         "font-family:'Inter',sans-serif;font-weight:600",
         'border:0.5px solid #1F1E1D;background:transparent;color:#1F1E1D;cursor:pointer;'
         "font-family:'Inter',sans-serif;font-weight:600"),
        ('font-size:24px;font-weight:700;color:#7756FF',
         'font-size:24px;font-weight:700;color:#1F1E1D'),
        ('stroke="${B.purple}" stroke-width="2.5"',
         'stroke="#1F1E1D" stroke-width="2.5"'),
        ('r="4" fill="${B.purple}"',
         'r="4" fill="#1F1E1D"'),
        # Category chart legend brand entry (runs AFTER name swap)
        (f'{{color:B.purple,bold:true,label:`{client_name} (',
         f'{{color:"#1F1E1D",bold:true,label:`{client_name} ('),
        ('font-weight:${br.client?700:400};color:${br.client?B.purple:B.nearBlack}',
         'font-weight:${br.client?700:400};color:${B.nearBlack}'),
        ('font-size:14px;font-weight:700;color:${br.client?B.purple:B.nearBlack}">${br.idx}',
         'font-size:14px;font-weight:700;color:${B.nearBlack}">${br.idx}'),
        ('background:#E3FF43;border-radius:6px;padding:8px 16px;margin-bottom:12px;'
         'display:flex;align-items:center;justify-content:space-between',
         'background:#1F1E1D;border-radius:6px;padding:8px 16px;margin-bottom:12px;'
         'display:flex;align-items:center;justify-content:space-between'),
        ('font-size:11px;font-weight:700;color:#2B2A29;text-transform:uppercase;'
         'letter-spacing:.07em">BVI v1.01',
         'font-size:11px;font-weight:600;color:#FAF7F2;text-transform:uppercase;'
         'letter-spacing:.07em">BVI v1.01'),
        ('font-size:11px;color:#2B2A29;opacity:.7">Bronze tier',
         'font-size:11px;color:#B5B0A6">Bronze tier'),
        ('font-size:10px;font-weight:700;color:#2B2A29;opacity:.6">'
         'Power Digital Marketing — Internal only',
         'font-size:10px;font-weight:400;color:#B5B0A6">'
         'Power Digital Marketing — Internal only'),
        ('gap:10px">\n        <span style="font-size:11px;font-weight:600;color:#FAF7F2;',
         'gap:14px">'
         '<img src="FusepointLogo.svg" alt="Fusepoint" height="24" '
         'style="display:block;opacity:.85;filter:brightness(0) invert(1)">'
         '<span style="font-size:11px;font-weight:600;color:#FAF7F2;'),
        ('#ABABAB', '#8A8782'),
        ('#2B2A29', '#1F1E1D'),
        ('#F5F5F5', '#FAF7F2'),
        # Awareness funnel
        ('width:${m.val}%;background:#7756FF;border-radius:4px',
         'width:${m.val}%;background:#FFCF70;border-radius:4px'),
        # Silver tier preview buttons
        ('border:0.5px solid #AFAAF9;background:transparent;color:#7756FF;font-weight:600">Preview Silver',
         'border:0.5px solid #E5E2DC;background:transparent;color:#1F1E1D;font-weight:600">Preview Silver'),
        ('#7756FF', '#1F1E1D'),
        # ── Round 2 polish ────────────────────────────────────────────────────
        ('display:grid;grid-template-columns:180px 1fr;gap:12px;margin-bottom:12px',
         'display:grid;grid-template-columns:240px 1fr;gap:12px;margin-bottom:12px'),
        ('${sparklineSVG(144,44,idx)}',
         '${sparklineSVG(200,52,idx)}'),
        ('stroke="${B.lightPurple}" stroke-width="1" opacity="0.4" stroke-dasharray="2,3"',
         'stroke="${B.lightPurple}" stroke-width="1.5" opacity="0.8" stroke-dasharray="2,3"'),
        ('border-top:0.5px solid rgba(175,170,249,.25)',
         'border-top:0.5px solid rgba(250,247,242,.15)'),
        ('color:#AFAAF9"><div style="width:10px;height:2px;background:#F5F5F5"></div> BVI</div>',
         'color:#B5B0A6"><div style="width:10px;height:2px;background:#FAF7F2"></div> BVI</div>'),
        ('color:#AFAAF9"><div style="width:10px;height:2px;background:#AFAAF9;opacity:.6"></div> Cat.',
         'color:#B5B0A6"><div style="width:10px;height:2px;background:#B5B0A6"></div> Cat.'),
        ('color:#AFAAF9;margin-bottom:4px">BVI Score',
         'color:#B5B0A6;margin-bottom:4px">BVI Score'),
        ('color:#AFAAF9;margin-bottom:10px">out of 100',
         'color:#B5B0A6;margin-bottom:10px">out of 100'),
        ('"#CDF8FF"', '"#FFCF70"'),
        ('"#FFBAFB"', '"#FAF7F2"'),
        ('color:#E3FF43;margin-right:10px">Recommendation',
         'color:#FFCF70;margin-right:10px">Recommendation'),
        ('stroke:"#E3FF43"', 'stroke:"#FFCF70"'),
        ('{label:"What moved",text:d.whatMoved,color:B.purple},',
         '{label:"What moved",text:d.whatMoved,color:B.purple,labelColor:B.nearBlack},'),
        ('style="color:${q.color};margin-bottom:5px;display:flex',
         'style="color:${q.labelColor||q.color};margin-bottom:5px;display:flex'),
        ('<div style="font-size:14px;font-weight:700">${MONTHS[idx]}</div>',
         '<div style="font-size:15px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif">${MONTHS[idx]}</div>'),
        ('style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;'
         'color:${isBackfill?"#BA7517":"#0F6E56"}">${isBackfill?"Backfill":"Live"}',
         'style="display:inline-block;margin-top:3px;font-size:8px;padding:1px 7px;border-radius:3px;'
         'font-weight:700;text-transform:uppercase;letter-spacing:.04em;'
         'background:${isBackfill?"rgba(186,117,23,.1)":"rgba(15,110,86,.1)"};'
         'color:${isBackfill?"#BA7517":"#0F6E56"}">${isBackfill?"Backfill":"Live"}'),
        ('text-align:center;min-width:76px',
         'text-align:center;min-width:90px'),
        ('border:1px solid rgba(175,170,249,.5);border-radius:8px;padding:14px 16px;background:rgba(175,170,249,.08)',
         'border:0.5px solid #E5E2DC;border-radius:8px;padding:14px 16px;background:#FFFFFF'),
        ('background:#AFAAF9;color:#26215C;font-weight:700">Silver',
         'background:#E5E2DC;color:#4A4845;font-weight:700">Silver'),
        ('border:1px solid rgba(227,255,67,.4);border-radius:8px;padding:14px 16px;background:rgba(227,255,67,.06)',
         'border:0.5px solid rgba(255,207,112,.5);border-radius:8px;padding:14px 16px;background:rgba(255,207,112,.06)'),
        ('background:#E3FF43;color:#2B2A29;font-weight:700">Gold',
         'background:#FFCF70;color:#1F1E1D;font-weight:700">Gold'),
        ('border:0.5px solid #E3FF43;background:transparent;color:#2B2A29;font-weight:600">Preview Gold',
         'border:0.5px solid #FFCF70;background:transparent;color:#1F1E1D;font-weight:600">Preview Gold'),
        ('"#26215C":B.nearBlack', '"#1F1E1D":B.nearBlack'),
        ('#AFAAF9', '#B5B0A6'),
        ('#E3FF43', '#FFCF70'),
        ('#26215C', '#1F1E1D'),
    ]


# ── Chart fixes ─────────────────────────────────────────────────────────────

_CHART_FIXES = [
    ("const minV=38, maxV=78, n=RAW.length;",
     "const n=RAW.length; const _b=RAW.map(m=>m.bvi).filter(v=>v!=null), "
     "_lo=Math.min(..._b), _hi=Math.max(..._b), _pad=Math.max(2,(_hi-_lo)*0.1); "
     "const minV=_lo-_pad, maxV=_hi+_pad, clamp=v=>Math.max(minV,Math.min(maxV,v));"),
    ("const W=620, H=170, pad={l:32,r:12,t:14,b:22}, minV=38, maxV=78, n=RAW.length;",
     "const W=620, H=170, pad={l:32,r:16,t:16,b:22}, n=RAW.length; "
     "const _b=RAW.map(m=>m.bvi).filter(v=>v!=null), _lo=Math.min(..._b), "
     "_hi=Math.max(..._b), _pad=Math.max(3,(_hi-_lo)*0.1); "
     "const minV=_lo-_pad, maxV=_hi+_pad, clamp=v=>Math.max(minV,Math.min(maxV,v));"),
    ("CAT_TRENDS.map((v,i)=>`${xp(i).toFixed(1)},${yp(v).toFixed(1)}`)",
     "CAT_TRENDS.map((v,i)=>`${xp(i).toFixed(1)},${yp(clamp(v)).toFixed(1)}`)"),
    ("[45,55,65].map(v=>",
     "[Math.round((minV+(maxV-minV)*0.25)/5)*5,Math.round((minV+(maxV-minV)*0.5)/5)*5,"
     "Math.round((minV+(maxV-minV)*0.75)/5)*5].map(v=>"),
    ('text-anchor="middle" font-family="\'Inter\',sans-serif" font-weight="${i===curIdx?700:400}">${MONTHS[i]}',
     'text-anchor="${i===0?\'start\':i===n-1?\'end\':\'middle\'}" font-family="\'Inter\',sans-serif" font-weight="${i===curIdx?700:400}">${MONTHS[i]}'),
    ("const W=580,H=130,pad={l:28,r:8,t:10,b:22},minV=35,maxV=75,n=RAW.length;",
     "const W=580,H=130,pad={l:28,r:10,t:12,b:22},n=RAW.length; "
     "const _cv=[...RAW.map(m=>m.kgTrends),...RAW.map(m=>m.catTrends),...CAT_TRENDS2,...CAT_TRENDS3]"
     ".filter(v=>v!=null),_lo=Math.min(..._cv),_hi=Math.max(..._cv),_pad=Math.max(3,(_hi-_lo)*0.08); "
     "const minV=_lo-_pad,maxV=_hi+_pad;"),
    ("[40,50,60,70].map(v=>",
     "[Math.round((minV+(maxV-minV)*0.2)/10)*10,Math.round((minV+(maxV-minV)*0.5)/10)*10,"
     "Math.round((minV+(maxV-minV)*0.8)/10)*10].map(v=>"),
    ('text-anchor="middle" font-family="\'Inter\',sans-serif" font-weight="${i===idx?700:400}">${MONTHS[i]}',
     'text-anchor="${i===0?\'start\':i===n-1?\'end\':\'middle\'}" font-family="\'Inter\',sans-serif" font-weight="${i===idx?700:400}">${MONTHS[i]}'),
]


# ── Public entry point ──────────────────────────────────────────────────────

def _apply_template(block, cfg):
    """Splice block into the template and apply all replacements. Returns html string."""
    html = open(SRC).read()
    start = html.index("// ── DATA")
    end = html.index("// ── STATE") + len("// ── STATE ────────────────────────────────────────────────────────────────────\n")
    html = html[:start] + block + html[end:]
    for old, new in _get_repl_list(cfg):
        html = html.replace(old, new)
    for old, new in _CHART_FIXES:
        if old in html:
            html = html.replace(old, new)
    return html


def _resolve_category_terms(cfg, brand_key, cat):
    """Auto-detect primary/cat2/cat3 from Trends Export 2 if not already set on cfg."""
    cat_terms = [k for k in next(iter(cat.values())) if k != brand_key]
    means = {t: sum(cat[mo][t] for mo in cat) / len(cat) for t in cat_terms}
    sorted_terms = sorted(cat_terms, key=lambda t: means[t], reverse=True)
    cfg.setdefault("primary", sorted_terms[0] if sorted_terms else "Category")
    cfg.setdefault("cat2", sorted_terms[1] if len(sorted_terms) > 1 else cfg["primary"])
    cfg.setdefault("cat3", sorted_terms[2] if len(sorted_terms) > 2 else cfg["primary"])
    return cfg


def generate(client_config, T, G_data, A, S):
    """Build dashboard. Returns (html, month_rows, results, resolved_config).

    month_rows: list of (month_str, storage_dict) — store in score_runs.
    results: dict keyed by month from score_bvi.compute().
    resolved_config: client_config plus auto-detected primary/cat2/cat3 —
        callers must persist THIS dict (not the original client_config) so
        primary/cat2/cat3 survive into the clients table.
    """
    cfg = dict(client_config)
    brand_key = cfg["brand_key"]
    cfg = _resolve_category_terms(cfg, brand_key, T["cat"])

    block, month_rows, results = _build_data_block(cfg, T, G_data, A, S)
    html = _apply_template(block, cfg)
    return html, month_rows, results, cfg


def generate_from_stored_rows(client_config, stored_rows):
    """Reconstruct dashboard HTML from DB rows without re-parsing CSVs.

    stored_rows: list of dicts with keys: month, obj, catTrends, cat2Trends, cat3Trends.
    """
    cfg = dict(client_config)
    sorted_rows = sorted(stored_rows, key=lambda r: r["month"])

    months_lbls = ",".join(f'"{label(r["month"])}"' for r in sorted_rows)
    cat_p = ",".join(str(r["catTrends"]) if r.get("catTrends") is not None else "null" for r in sorted_rows)
    cat_2 = ",".join(str(r["cat2Trends"]) if r.get("cat2Trends") is not None else "null" for r in sorted_rows)
    cat_3 = ",".join(str(r["cat3Trends"]) if r.get("cat3Trends") is not None else "null" for r in sorted_rows)
    raw_js = ",\n  ".join(r["obj"] for r in sorted_rows)

    block = (
        "// ── DATA ────────────────────────────────────────────────────────────────────\n"
        f"const MONTHS = [{months_lbls}];\n"
        f"const CAT_TRENDS  = [{cat_p}];\n"
        f"const CAT_TRENDS2 = [{cat_2}];\n"
        f"const CAT_TRENDS3 = [{cat_3}];\n\n"
        f"const RAW = [\n  {raw_js}\n];\n\n"
        "const SURVEYS = [];\n\n"
        "// ── STATE ────────────────────────────────────────────────────────────────────\n"
    )
    return _apply_template(block, cfg)
