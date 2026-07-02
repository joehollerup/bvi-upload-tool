#!/usr/bin/env python3
"""Build keen_bvi_dashboard.html from the Kurt Geiger demo by swapping in KEEN data.

Generates the dashboard's flat RAW schema directly from the four parsers + the
BVI scorer (native-schema approach), renames Kurt Geiger -> KEEN and the
competitor / category labels, and locks the default tier to Bronze. Fields with
no KEEN source (SEMrush volumes, Silver/Gold metrics) are null -> shown as "—".
"""

import re
from datetime import datetime

import parse_trends
import parse_gsc
import parse_ga4
import parse_social
import score_bvi

SRC = "bvi-demo-gold-unlocked (5).html"
OUT = "keen_bvi_dashboard.html"

# Display slots: dashboard has 3 competitor columns (sm/car/ted). KEEN has 4
# rivals; map the three strongest by Trends, drop the smallest (brunt).
COMP_MAP = [("smTrends", "Salomon"), ("carTrends", "red wing"), ("tedTrends", "Sorel")]
PRIMARY = "Work Boots"      # primary category term (highest mean index)
CAT2, CAT3 = "Hiking Boots", "trail running"


def jnum(v, dec=None):
    if v is None:
        return "null"
    if dec is not None:
        v = round(v, dec)
        return str(int(v)) if dec == 0 else str(v)
    return str(v)


def mom_pct(cur, prev):
    return None if prev in (None, 0) else (cur - prev) / prev * 100


def label(month):
    return datetime.strptime(month + "-01", "%Y-%m-%d").strftime("%b '%y")


def main():
    T = parse_trends.load()
    G = parse_gsc.load()
    A = parse_ga4.load()
    S = parse_social.load()
    comp, cat, gsc = T["comp"], T["cat"], G["months"]
    results = {r["month"]: r for r in score_bvi.compute()}

    # Per-platform net follower growth (combined) and month list for YoY lookups.
    plats = {lab: parse_social.parse(p, e, d, rc)
             for lab, p, e, d, rc in parse_social.PLATFORMS}
    comp_months = sorted(comp)

    # Impression-weighted avg position + CTR per month from Chart.csv.
    chart = parse_gsc.read_rows(parse_gsc.find_file("Chart.csv"))[1:]
    pos_acc, ctr = {}, {}
    for date, clicks, impr, c_ctr, c_pos, *_ in chart:
        mo = date[:7]
        a = pos_acc.setdefault(mo, [0.0, 0])
        a[0] += float(c_pos) * int(impr)
        a[1] += int(impr)
    position = {mo: a[0] / a[1] for mo, a in pos_acc.items()}
    for mo, m in gsc.items():
        ctr[mo] = m["clicks"] / m["impr"] * 100

    months = sorted(set(comp) | set(cat) | set(gsc) | set(S) | set(A))
    window = months[-12:]   # Jun '25 -> May '26

    rows = []
    for m in window:
        i = months.index(m)
        pm = months[i - 1]
        r = results[m]

        def gd(table, key, fn=lambda x: x):  # safe delta helper
            if m in table and pm in table:
                return fn(table[m][key]), fn(table[pm][key])
            return (table[m][key] if m in table else None), None

        # Search / GSC branded metrics
        impr_k = round(gsc[m]["br_impr"] / 1000) if m in gsc else None
        clk_k = round(gsc[m]["br_clicks"] / 1000) if m in gsc else None
        impr_d = mom_pct(gsc[m]["br_impr"], gsc[pm]["br_impr"]) if m in gsc and pm in gsc else None
        clk_d = mom_pct(gsc[m]["br_clicks"], gsc[pm]["br_clicks"]) if m in gsc and pm in gsc else None
        ctr_d = (ctr[m] - ctr[pm]) if m in ctr and pm in ctr else None
        pos_d = (position[m] - position[pm]) if m in position and pm in position else None

        # Trends (brand + competitors), share, gap
        kg = comp[m]["KEEN"]
        kg_prev = comp[pm]["KEEN"] if pm in comp else None
        ti_d = (kg - kg_prev) if kg_prev is not None else None        # pts
        yoy = None
        if i >= 12:
            back = comp_months[comp_months.index(m) - 12] if m in comp_months and comp_months.index(m) >= 12 else None
            if back:
                yoy = mom_pct(kg, comp[back]["KEEN"])
        share = kg / sum(comp[m].values()) * 100
        share_prev = comp[pm]["KEEN"] / sum(comp[pm].values()) * 100 if pm in comp else None
        share_d = (share - share_prev) if share_prev is not None else None

        # GA4 (only 2026-05 has data; never a prior -> deltas null)
        has_ga = m in A
        ds = round(A[m]["direct"] / 1000) if has_ga else None
        os_ = round(A[m]["organic"] / 1000) if has_ga else None
        dpct = round(A[m]["direct_pct"]) if has_ga else None

        # Social (combined)
        er = S[m]["er"] if m in S else None
        er_d = (S[m]["er"] - S[pm]["er"]) if m in S and pm in S else None
        gr = S[m]["gr"] if m in S else None
        gr_d = (S[m]["gr"] - S[pm]["gr"]) if m in S and pm in S and S[m]["gr"] is not None and S[pm]["gr"] is not None else None
        reach_k = round(S[m]["reach"] / 1000) if m in S else None
        net = sum(plats[lab][m]["net"] for lab in plats if m in plats[lab]) or None

        # Category
        cat_primary = cat[m][PRIMARY]
        gap = kg - cat_primary  # for narrative (Export 1 brand vs Export 2 cat; display-only)
        rising = r["dimensions"]["Category"]["signals"]["rising_tide"]["value"]
        rising = bool(rising)

        bvi = round(r["bvi_score"]) if r["bvi_score"] is not None else None

        # Factual narratives (derived from data only; interpretive fields left null -> "—")
        what = (f"BVI {bvi} ({r['momentum']}). "
                f"Branded impressions {fmt_signed(impr_d)}% MoM, "
                f"branded clicks {fmt_signed(clk_d)}% MoM, "
                f"Trends index {fmt_signed(ti_d, pts=True)}.")
        catctx = (f"Brand Trends index ({kg}) vs. primary category \"{PRIMARY}\" "
                  f"({cat_primary}). Rising tide {'active' if rising else 'not detected'}.")
        nearest = max(["Salomon", "red wing", "Sorel"], key=lambda n: comp[m][n])
        ndisp = {"red wing": "Red Wing"}.get(nearest, nearest)
        compshift = (f"Nearest competitor {ndisp} at index {comp[m][nearest]}; "
                     f"KEEN brand share {round(share)}% of tracked Trends.")

        # ── Rule-based narrative (Phase 1; Claude API narrative is Phase 2) ──
        prior_bvi = (round(results[pm]["bvi_score"])
                     if pm in results and results[pm]["bvi_score"] is not None else None)
        bvi_delta = (bvi - prior_bvi) if (bvi is not None and prior_bvi is not None) else None
        dscore = {d: r["dimensions"][d]["score"] for d in
                  ("Search", "Social", "Competitive", "Category")
                  if r["dimensions"][d]["score"] is not None}
        DLAB = {"Search": "Search Demand", "Social": "Organic Social",
                "Competitive": "Competitive Position", "Category": "Category Context"}
        DETAIL = {
            "Search": f"branded impressions {sgn(impr_d)}%, Trends index {sgn(ti_d, suf='pts')}",
            "Social": f"engagement rate {sgn(er_d, 2, 'pts')}, follower growth {sgn(gr_d, 2, 'pts')}",
            "Competitive": f"brand share {sgn(share_d, 1, 'pts')} vs {ndisp}",
            "Category": f'brand-vs-"{PRIMARY}" gap {sgn(gap_mom_pts(cat, m, pm, PRIMARY), suf="pts")}',
        }
        # Driver aligns with the BVI direction: top scorer when rising, lowest
        # when falling, else the most pronounced swing.
        if not dscore:
            driver = "Search"
        elif bvi_delta is not None and bvi_delta > 0:
            driver = max(dscore, key=lambda k: dscore[k])
        elif bvi_delta is not None and bvi_delta < 0:
            driver = min(dscore, key=lambda k: dscore[k])
        else:
            driver = max(dscore, key=lambda k: abs(dscore[k] - 55))
        if bvi_delta is None:
            move = ""
        elif bvi_delta > 0:
            move = f", up {bvi_delta} MoM"
        elif bvi_delta < 0:
            move = f", down {abs(bvi_delta)} MoM"
        else:
            move = ", unchanged MoM"
        why = (f"BVI {bvi}{move}. "
               f"Movement led by {DLAB[driver]} ({DETAIL[driver]}).")
        if rising:
            why += (f' Rising-tide flag active — "{PRIMARY}" moved with the brand, '
                    f"so part of the shift is category-wide, not brand-specific.")

        delta_str = (f" ({'+' if bvi_delta >= 0 else ''}{bvi_delta} pts MoM)"
                     if bvi_delta is not None else "")
        if r["momentum"] == "Declining":
            reco = (f"BVI slipped{delta_str} — treat as a watch month and confirm the dip "
                    f"persists before changing strategy. "
                    f"{DLAB.get(driver, driver)} was the main drag ({DETAIL.get(driver, '')}).")
        elif r["momentum"] == "Rising":
            reco = (f"Momentum positive{delta_str}. "
                    f"{DLAB.get(driver, driver)} led the move ({DETAIL.get(driver, '')}) — "
                    f"reinforce this channel and feature in client reporting.")
        else:
            reco = (f"BVI held steady{delta_str}. "
                    f"Signals mixed — {DLAB.get(driver, driver)} had the widest swing "
                    f"({DETAIL.get(driver, '')}). Hold course and watch next month.")
        if rising:
            reco += (f" Rising-tide note: \"{PRIMARY}\" category moved with the brand "
                     f"this month — discount Trends-based gains when reporting.")
        elif share_d is not None and share_d >= 2:
            reco += f" Lead with competitive share gains vs {ndisp} (+{round(share_d)} pts)."
        elif share_d is not None and share_d <= -2:
            reco += f" Watch share erosion vs {ndisp} ({round(share_d)} pts); audit branded search coverage."

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
            f'brandedOrganic:null,brandedOrganicDelta:null,'
            f'followerGrowthRate:{jnum(gr,2)},followerGrowthRateDelta:{jnum(gr_d,2)},'
            f'netFollowerGrowth:{jnum(net)},reach:{jnum(reach_k)},'
            f'engagementRate:{jnum(er,2)},engagementRateDelta:{jnum(er_d,2)},'
            f'kgTrends:{jnum(kg)},smTrends:{jnum(comp[m]["Salomon"])},'
            f'carTrends:{jnum(comp[m]["red wing"])},tedTrends:{jnum(comp[m]["Sorel"])},'
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
        rows.append((m, obj))

    months_lbls = ",".join(f'"{label(m)}"' for m, _ in rows)
    cat_p = ",".join(str(cat[m][PRIMARY]) for m, _ in rows)
    cat_2 = ",".join(str(cat[m][CAT2]) for m, _ in rows)
    cat_3 = ",".join(str(cat[m][CAT3]) for m, _ in rows)
    raw_js = ",\n  ".join(obj for _, obj in rows)

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

    html = open(SRC).read()
    start = html.index("// ── DATA")
    end = html.index("// ── STATE") + len("// ── STATE ────────────────────────────────────────────────────────────────────\n")
    html = html[:start] + block + html[end:]

    # Name / label / tier swaps
    repl = [
        ("BVI Dashboard — Kurt Geiger London (Demo)", "BVI Dashboard — KEEN (Bronze)"),
        ("Kurt Geiger London", "KEEN"),
        ("Kurt Geiger", "KEEN"),
        ("Steve Madden", "Salomon"),
        ("Carvela", "Red Wing"),
        ("Ted Baker", "Sorel"),
        ('"women\'s shoes"', '"Work Boots"'),
        ('"luxury footwear"', '"Hiking Boots"'),
        ('"designer shoes"', '"trail running"'),
        ("All tiers unlocked", "Bronze tier"),
        ("dummy data", "data"),
        ('tier: "gold"', 'tier: "bronze"'),
        # Drop demo framing -> version label; remove all "Demo" badges.
        ("<!-- DEMO BANNER -->", "<!-- VERSION BANNER -->"),
        ("Prototype Demo Mode", "BVI v1.01 — Prototype"),
        ('<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:#E3FF43;color:#2B2A29;font-weight:700">Demo</span>', ""),
        ('<span style="font-size:9px;padding:1px 6px;border-radius:3px;background:#E3FF43;color:#2B2A29;font-weight:700;margin-right:4px">Demo</span>', ""),
        # Null-guards: fields with no KEEN source render as "—" (spec 3.2),
        # and never crash on null.toLocaleString() when a tab is opened.
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
        # UX-8: Remove "Why this matters" tab entirely
        ('{id:"methodology",label:"Why this matters"},', ''),
        ('else if(activeTab==="methodology") tabContent = renderMethodology();', ''),
        # UX-2: Filter methodology modal scales to only show those the dimension uses
        ('${SCALES.map(sc=>`<div class="card" style="padding:10px 12px">',
         '${SCALES.filter(sc=>spec.signals.some(sig=>sig.s.toLowerCase()'
         '.startsWith(sc.name.split(\' \')[0].toLowerCase()))).map(sc=>`<div class="card" style="padding:10px 12px">'),
        # UX-3a: Digital no-data → null return from calcDimStatus (shows "No data" in sidebar)
        ('if(dimId==="digital") {\n    const pos=[d.directPctDelta',
         'if(dimId==="digital") {\n'
         '    if(d.directSessions==null&&d.organicSessions==null)return null;\n'
         '    const pos=[d.directPctDelta'),
        # UX-3b: Digital tab shows message instead of all-dashes when GA4 absent
        ('function renderDigital(d) {\n  return `<div class="grid2">',
         'function renderDigital(d) {\n'
         '  if(d.directSessions==null&&d.organicSessions==null)return `'
         '<div style="padding:32px 0;text-align:center">'
         '<div style="font-size:14px;font-weight:600;color:#ABABAB;margin-bottom:6px">No GA4 data for this period</div>'
         '<div style="font-size:12px;color:#ABABAB;line-height:1.6">Traffic acquisition data is available for months where GA4 was connected.</div>'
         '</div>`;\n'
         '  return `<div class="grid2">'),
        # UX-4a: Inject showTip click-popover function (native title attribute doesn\'t fire on click)
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
        # UX-4b: Replace title attribute with onclick handler on metric card ? bubble
        ('<span title="${tip}" style="width:14px;height:14px;border-radius:50%;'
         'background:rgba(171,171,171,.25);display:inline-flex;align-items:center;'
         'justify-content:center;font-size:10px;color:#ABABAB;cursor:help;font-weight:700">?</span>',
         '<span onclick="event.stopPropagation();showTip(this,\'${tip}\')" '
         'style="width:14px;height:14px;border-radius:50%;background:rgba(171,171,171,.25);'
         'display:inline-flex;align-items:center;justify-content:center;'
         'font-size:10px;color:#ABABAB;cursor:pointer;font-weight:700">?</span>'),
        # UX-5a: Compute MoM text value per dimension for badge display
        ('const factors = info.factors || [];',
         'const factors = info.factors || [];\n'
         '  const momText = {'
         'search:d.impressionsDelta!=null?(d.impressionsDelta>0?"+":"")+d.impressionsDelta+"% MoM":null,'
         'digital:d.directPctDelta!=null?(d.directPctDelta>0?"+":"")+d.directPctDelta+" pts MoM":null,'
         'social:d.engagementRateDelta!=null?((d.engagementRateDelta>0?"+":"")+parseFloat(d.engagementRateDelta).toFixed(1)+" pts MoM"):null,'
         'competitive:d.brandShareDelta!=null?(d.brandShareDelta>0?"+":"")+d.brandShareDelta+" pts MoM":null,'
         'category:prev&&d.catTrends!=null&&prev.catTrends!=null?((d.catTrends-prev.catTrends>=0?"+":"")+(d.catTrends-prev.catTrends)+" pts MoM"):null'
         '}[dimId]||null;'),
        # UX-5b: Append MoM change to the status badge text
        ('white-space:nowrap">${info.status}</span>',
         'white-space:nowrap">${info.status}${momText?" "+momText:""}</span>'),
        # UX-6a–c: Distinct colors for each category chart line
        ('stroke="#B4B2A9" stroke-width="1" stroke-dasharray="2,4"',
         'stroke="#3B82C4" stroke-width="1.5" stroke-dasharray="4,3"'),
        ('stroke="${B.lightPurple}" stroke-width="1" stroke-dasharray="2,3"',
         'stroke="#2D9C6B" stroke-width="1.5" stroke-dasharray="5,3"'),
        ('stroke="${B.gray}" stroke-width="1.5" stroke-dasharray="3,3"',
         'stroke="#D97706" stroke-width="1.5" stroke-dasharray="3,3"'),
        # UX-6d–f: Update legend colors to match (names already replaced earlier in list)
        ('{color:B.gray,bold:false,label:`"Work Boots"',
         '{color:"#D97706",bold:false,label:`"Work Boots"'),
        ('{color:B.lightPurple,bold:false,label:`"Hiking Boots"',
         '{color:"#2D9C6B",bold:false,label:`"Hiking Boots"'),
        ('{color:"#B4B2A9",bold:false,label:`"trail running"',
         '{color:"#3B82C4",bold:false,label:`"trail running"'),
        # UX-6g: Update the highlight dot on Work Boots line
        ('cy="${yp(RAW[idx].catTrends)}" r="3" fill="${B.gray}"',
         'cy="${yp(RAW[idx].catTrends)}" r="3" fill="#D97706"'),
        # ── BRAND-1: Fusepoint visual reskin ─────────────────────────────────
        # Google Fonts: Darker Grotesque → Inter + Instrument Serif
        ("@import url('https://fonts.googleapis.com/css2?family=Darker+Grotesque:wght@400;600;700&display=swap');",
         "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap');"),
        # Body: cream canvas, fp-text-primary, Inter
        ("font-family:'Darker Grotesque',Arial,Helvetica,sans-serif;background:#F5F5F5;color:#2B2A29;",
         "font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;background:#FAF7F2;color:#1F1E1D;"),
        # Button CSS font
        ("button{font-family:'Darker Grotesque',Arial,Helvetica,sans-serif;",
         "button{font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;"),
        # Inline CSS-format font references (button, modal)
        ("font-family:'Darker Grotesque',Arial,sans-serif;",
         "font-family:'Inter',sans-serif;"),
        # SVG HTML-attribute-format font
        ('font-family="\'Darker Grotesque\',Arial,sans-serif"',
         'font-family="\'Inter\',sans-serif"'),
        # Card border: fp-border warm token
        ('.card{background:#fff;border:0.5px solid rgba(171,171,171,0.3);',
         '.card{background:#FFFFFF;border:0.5px solid #E5E2DC;'),
        # BVI score card: purple → fp-dark (the one dark section per page)
        ('.purple-card{background:#7756FF;',
         '.purple-card{background:#1F1E1D;'),
        # Dark card: fp-dark
        ('.dark-card{background:#2B2A29;',
         '.dark-card{background:#1F1E1D;'),
        # Label CSS: fp-text-quaternary
        ('.label{font-size:10px;color:#ABABAB;',
         '.label{font-size:10px;color:#8A8782;'),
        # Big-num CSS: fp-text-primary
        ('.big-num{font-size:22px;font-weight:700;color:#2B2A29;',
         '.big-num{font-size:22px;font-weight:700;color:#1F1E1D;'),
        # Dim-expand: warm surface tint
        ('.dim-expand{background:#F5F5F5;',
         '.dim-expand{background:#F5F0E6;'),
        # Dim-row border: fp-border
        ('.dim-row{border-bottom:0.5px solid rgba(171,171,171,.15)}',
         '.dim-row{border-bottom:0.5px solid #E5E2DC}'),
        # Tab active: fp-accent underline + yellow highlight
        ('.tab-btn.active{font-weight:700;color:#7756FF;background:rgba(119,86,255,.05);border-bottom:2px solid #7756FF}',
         '.tab-btn.active{font-weight:700;color:#1F1E1D;background:rgba(255,207,112,.12);border-bottom:2px solid #FFCF70}'),
        # Tab hover: fp-text-primary
        ('.tab-btn:hover:not(.active){color:#2B2A29}',
         '.tab-btn:hover:not(.active){color:#1F1E1D}'),
        # Modal box: fp-canvas
        ('.modal-box{background:#F5F5F5;',
         '.modal-box{background:#FAF7F2;'),
        # Modal header: fp-dark
        ('.modal-header{background:#2B2A29;',
         '.modal-header{background:#1F1E1D;'),
        # Modal methodology label: fp-text-on-dark-muted
        ('class="label" style="color:#AFAAF9;margin-bottom:3px">Scoring methodology',
         'class="label" style="color:#B5B0A6;margin-bottom:3px">Scoring methodology'),
        # Modal title: Instrument Serif + fp-text-on-dark
        ('font-size:18px;font-weight:700;color:#F5F5F5',
         'font-size:18px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif;color:#FAF7F2'),
        # Note box: warm surface tint
        ('.note-box{padding:8px 12px;background:#F5F5F5;',
         '.note-box{padding:8px 12px;background:#F5F0E6;'),
        # Signal tag: fp-accent background, fp-dark text
        ('.signal-tag{font-size:11px;padding:3px 10px;border-radius:4px;background:rgba(119,86,255,.1);color:#7756FF;font-weight:600}',
         '.signal-tag{font-size:11px;padding:3px 10px;border-radius:4px;background:rgba(255,207,112,.25);color:#1F1E1D;font-weight:600}'),
        # B object: update nearBlack, purple, lightPurple to fp tokens
        ('nearBlack:"#2B2A29", purple:"#7756FF", lightPurple:"#AFAAF9"',
         'nearBlack:"#1F1E1D", purple:"#FFCF70", lightPurple:"#B5B0A6"'),
        # B object: update gray, offWhite, yellow
        ('gray:"#ABABAB", offWhite:"#F5F5F5", yellow:"#E3FF43"',
         'gray:"#8A8782", offWhite:"#FAF7F2", yellow:"#FFCF70"'),
        # BVI score number: Instrument Serif display + fp-canvas color
        ('font-size:58px;font-weight:700;color:#F5F5F5;line-height:1',
         'font-size:58px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif;color:#FAF7F2;line-height:1'),
        # KEEN client name: Instrument Serif editorial headline, larger for visibility
        ('font-size:20px;font-weight:700">KEEN',
         'font-size:30px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif">KEEN'),
        # "Power Digital Marketing" sub-header: fp-text-tertiary
        ('font-size:11px;color:#ABABAB">Power Digital Marketing \xb7 Monthly brand health report',
         'font-size:11px;color:#6B6864">Power Digital Marketing \xb7 Monthly brand health report'),
        # "Scoring spec" button: purple → fp-dark (after font already changed by item above)
        ('border:0.5px solid #7756FF;background:transparent;color:#7756FF;cursor:pointer;'
         "font-family:'Inter',sans-serif;font-weight:600",
         'border:0.5px solid #1F1E1D;background:transparent;color:#1F1E1D;cursor:pointer;'
         "font-family:'Inter',sans-serif;font-weight:600"),
        # Brand share stat: hardcoded purple → fp-dark
        ('font-size:24px;font-weight:700;color:#7756FF',
         'font-size:24px;font-weight:700;color:#1F1E1D'),
        # Category chart: KEEN brand line → fp-dark (yellow line on cream = poor contrast)
        ('stroke="${B.purple}" stroke-width="2.5"',
         'stroke="#1F1E1D" stroke-width="2.5"'),
        # Category chart: KEEN brand highlight dot → fp-dark
        ('r="4" fill="${B.purple}"',
         'r="4" fill="#1F1E1D"'),
        # Category chart legend: KEEN brand color → fp-dark
        ('{color:B.purple,bold:true,label:`KEEN (',
         '{color:"#1F1E1D",bold:true,label:`KEEN ('),
        # Competitive brand name text: yellow on white = bad contrast → fp-dark (bold preserves distinction)
        ('font-weight:${br.client?700:400};color:${br.client?B.purple:B.nearBlack}',
         'font-weight:${br.client?700:400};color:${B.nearBlack}'),
        # Competitive brand index number: same fix
        ('font-size:14px;font-weight:700;color:${br.client?B.purple:B.nearBlack}">${br.idx}',
         'font-size:14px;font-weight:700;color:${B.nearBlack}">${br.idx}'),
        # Nav banner background: lime → fp-dark (nav bar = the one dark section per page)
        ('background:#E3FF43;border-radius:6px;padding:8px 16px;margin-bottom:12px;'
         'display:flex;align-items:center;justify-content:space-between',
         'background:#1F1E1D;border-radius:6px;padding:8px 16px;margin-bottom:12px;'
         'display:flex;align-items:center;justify-content:space-between'),
        # Banner primary text: dark → fp-text-on-dark
        ('font-size:11px;font-weight:700;color:#2B2A29;text-transform:uppercase;'
         'letter-spacing:.07em">BVI v1.01',
         'font-size:11px;font-weight:600;color:#FAF7F2;text-transform:uppercase;'
         'letter-spacing:.07em">BVI v1.01'),
        # Banner secondary text: opacity approach → direct fp-on-dark-muted color
        ('font-size:11px;color:#2B2A29;opacity:.7">Bronze tier',
         'font-size:11px;color:#B5B0A6">Bronze tier'),
        # Banner right "Power Digital" text
        ('font-size:10px;font-weight:700;color:#2B2A29;opacity:.6">'
         'Power Digital Marketing — Internal only',
         'font-size:10px;font-weight:400;color:#B5B0A6">'
         'Power Digital Marketing — Internal only'),
        # Inject Fusepoint logo into banner flex container
        ('gap:10px">\n        <span style="font-size:11px;font-weight:600;color:#FAF7F2;',
         'gap:14px">'
         '<img src="FusepointLogo.svg" alt="Fusepoint" height="24" '
         'style="display:block;opacity:.85;filter:brightness(0) invert(1)">'
         '<span style="font-size:11px;font-weight:600;color:#FAF7F2;'),
        # Global warm-gray sweep: #ABABAB → fp-text-quaternary (#8A8782)
        ('#ABABAB', '#8A8782'),
        # Global dark sweep: remaining #2B2A29 → fp-dark (#1F1E1D)
        ('#2B2A29', '#1F1E1D'),
        # Global canvas sweep: remaining #F5F5F5 → fp-canvas (#FAF7F2)
        ('#F5F5F5', '#FAF7F2'),
        # Awareness funnel progress bar: purple fill → fp-accent yellow
        ('width:${m.val}%;background:#7756FF;border-radius:4px',
         'width:${m.val}%;background:#FFCF70;border-radius:4px'),
        # Silver tier preview buttons: purple text → fp-dark
        ('border:0.5px solid #AFAAF9;background:transparent;color:#7756FF;font-weight:600">Preview Silver',
         'border:0.5px solid #E5E2DC;background:transparent;color:#1F1E1D;font-weight:600">Preview Silver'),
        # Global purple sweep: all remaining #7756FF → fp-dark (#1F1E1D)
        ('#7756FF', '#1F1E1D'),

        # ── Round 2 polish: score card, header, upsell section ───────────────
        # BVI score card: widen from 180px to 240px for better proportions
        ('display:grid;grid-template-columns:180px 1fr;gap:12px;margin-bottom:12px',
         'display:grid;grid-template-columns:240px 1fr;gap:12px;margin-bottom:12px'),
        # Sparkline: increase size to fill wider card
        ('${sparklineSVG(144,44,idx)}',
         '${sparklineSVG(200,52,idx)}'),
        # Sparkline: category dotted line — increase weight + opacity for dark-bg contrast
        ('stroke="${B.lightPurple}" stroke-width="1" opacity="0.4" stroke-dasharray="2,3"',
         'stroke="${B.lightPurple}" stroke-width="1.5" opacity="0.8" stroke-dasharray="2,3"'),
        # Sparkline separator border: old lightPurple rgba → fp-on-dark subtle
        ('border-top:0.5px solid rgba(175,170,249,.25)',
         'border-top:0.5px solid rgba(250,247,242,.15)'),
        # Sparkline legend label text: old lightPurple → fp-on-dark-muted
        ('color:#AFAAF9"><div style="width:10px;height:2px;background:#F5F5F5"></div> BVI</div>',
         'color:#B5B0A6"><div style="width:10px;height:2px;background:#FAF7F2"></div> BVI</div>'),
        ('color:#AFAAF9"><div style="width:10px;height:2px;background:#AFAAF9;opacity:.6"></div> Cat.',
         'color:#B5B0A6"><div style="width:10px;height:2px;background:#B5B0A6"></div> Cat.'),
        # Dark card: "BVI Score" label and "out of 100" → fp-on-dark-muted
        ('color:#AFAAF9;margin-bottom:4px">BVI Score',
         'color:#B5B0A6;margin-bottom:4px">BVI Score'),
        ('color:#AFAAF9;margin-bottom:10px">out of 100',
         'color:#B5B0A6;margin-bottom:10px">out of 100'),
        # Dark card MoM delta: old brand cyan/pink → fp colors
        ('"#CDF8FF"', '"#FFCF70"'),
        ('"#FFBAFB"', '"#FAF7F2"'),
        # Recommendation label: neon lime → fp-accent yellow
        ('color:#E3FF43;margin-right:10px">Recommendation',
         'color:#FFCF70;margin-right:10px">Recommendation'),
        # Trend chart legend rising tide marker: neon lime → fp-accent yellow
        ('stroke:"#E3FF43"', 'stroke:"#FFCF70"'),
        # "What moved" card: yellow text on white = low contrast → dark label, yellow border only
        ('{label:"What moved",text:d.whatMoved,color:B.purple},',
         '{label:"What moved",text:d.whatMoved,color:B.purple,labelColor:B.nearBlack},'),
        ('style="color:${q.color};margin-bottom:5px;display:flex',
         'style="color:${q.labelColor||q.color};margin-bottom:5px;display:flex'),
        # Date navigator: month → Instrument Serif, status → badge chip
        ('<div style="font-size:14px;font-weight:700">${MONTHS[idx]}</div>',
         '<div style="font-size:15px;font-weight:400;font-family:\'Instrument Serif\',Georgia,serif">${MONTHS[idx]}</div>'),
        ('style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;'
         'color:${isBackfill?"#BA7517":"#0F6E56"}">${isBackfill?"Backfill":"Live"}',
         'style="display:inline-block;margin-top:3px;font-size:8px;padding:1px 7px;border-radius:3px;'
         'font-weight:700;text-transform:uppercase;letter-spacing:.04em;'
         'background:${isBackfill?"rgba(186,117,23,.1)":"rgba(15,110,86,.1)"};'
         'color:${isBackfill?"#BA7517":"#0F6E56"}">${isBackfill?"Backfill":"Live"}'),
        # Date navigator outer container: widen min-width
        ('text-align:center;min-width:76px',
         'text-align:center;min-width:90px'),
        # Unlock section: Silver cards → fp neutral surface
        ('border:1px solid rgba(175,170,249,.5);border-radius:8px;padding:14px 16px;background:rgba(175,170,249,.08)',
         'border:0.5px solid #E5E2DC;border-radius:8px;padding:14px 16px;background:#FFFFFF'),
        # Silver badge → fp neutral
        ('background:#AFAAF9;color:#26215C;font-weight:700">Silver',
         'background:#E5E2DC;color:#4A4845;font-weight:700">Silver'),
        # Unlock section: Gold card → fp-accent yellow tint
        ('border:1px solid rgba(227,255,67,.4);border-radius:8px;padding:14px 16px;background:rgba(227,255,67,.06)',
         'border:0.5px solid rgba(255,207,112,.5);border-radius:8px;padding:14px 16px;background:rgba(255,207,112,.06)'),
        # Gold badge → fp-accent yellow
        ('background:#E3FF43;color:#2B2A29;font-weight:700">Gold',
         'background:#FFCF70;color:#1F1E1D;font-weight:700">Gold'),
        # Gold preview button border → fp-accent yellow
        ('border:0.5px solid #E3FF43;background:transparent;color:#2B2A29;font-weight:600">Preview Gold',
         'border:0.5px solid #FFCF70;background:transparent;color:#1F1E1D;font-weight:600">Preview Gold'),
        # Tier button active Silver text: old dark purple → fp-dark
        ('"#26215C":B.nearBlack', '"#1F1E1D":B.nearBlack'),
        # Global sweeps: catch remaining old-palette stragglers
        ('#AFAAF9', '#B5B0A6'),
        ('#E3FF43', '#FFCF70'),
        ('#26215C', '#1F1E1D'),
    ]
    for a, b in repl:
        html = html.replace(a, b)

    # ── Chart fixes: KEEN's BVI (31–74) and category (→100) exceed the demo's
    # fixed 38–78 axis, clipping the charts. Make the y-domain dynamic, clamp
    # the category reference line into the viewport, and anchor edge x-labels. ──
    chart_fixes = [
        # Sparkline: domain from BVI values + clamp helper
        ("const minV=38, maxV=78, n=RAW.length;",
         "const n=RAW.length; const _b=RAW.map(m=>m.bvi).filter(v=>v!=null), "
         "_lo=Math.min(..._b), _hi=Math.max(..._b), _pad=Math.max(2,(_hi-_lo)*0.1); "
         "const minV=_lo-_pad, maxV=_hi+_pad, clamp=v=>Math.max(minV,Math.min(maxV,v));"),
        # Main trend chart: domain from BVI, clamp helper, extra top/right padding
        ("const W=620, H=170, pad={l:32,r:12,t:14,b:22}, minV=38, maxV=78, n=RAW.length;",
         "const W=620, H=170, pad={l:32,r:16,t:16,b:22}, n=RAW.length; "
         "const _b=RAW.map(m=>m.bvi).filter(v=>v!=null), _lo=Math.min(..._b), "
         "_hi=Math.max(..._b), _pad=Math.max(3,(_hi-_lo)*0.1); "
         "const minV=_lo-_pad, maxV=_hi+_pad, clamp=v=>Math.max(minV,Math.min(maxV,v));"),
        # Clamp the category reference line (sparkline + trend chart)
        ("CAT_TRENDS.map((v,i)=>`${xp(i).toFixed(1)},${yp(v).toFixed(1)}`)",
         "CAT_TRENDS.map((v,i)=>`${xp(i).toFixed(1)},${yp(clamp(v)).toFixed(1)}`)"),
        # Main chart gridlines spread across the dynamic domain
        ("[45,55,65].map(v=>",
         "[Math.round((minV+(maxV-minV)*0.25)/5)*5,Math.round((minV+(maxV-minV)*0.5)/5)*5,"
         "Math.round((minV+(maxV-minV)*0.75)/5)*5].map(v=>"),
        # Main chart: anchor first/last x-label inside the viewBox
        ('text-anchor="middle" font-family="\'Inter\',sans-serif" font-weight="${i===curIdx?700:400}">${MONTHS[i]}',
         'text-anchor="${i===0?\'start\':i===n-1?\'end\':\'middle\'}" font-family="\'Inter\',sans-serif" font-weight="${i===curIdx?700:400}">${MONTHS[i]}'),
        # Category-tab chart: domain from all plotted series
        ("const W=580,H=130,pad={l:28,r:8,t:10,b:22},minV=35,maxV=75,n=RAW.length;",
         "const W=580,H=130,pad={l:28,r:10,t:12,b:22},n=RAW.length; "
         "const _cv=[...RAW.map(m=>m.kgTrends),...RAW.map(m=>m.catTrends),...CAT_TRENDS2,...CAT_TRENDS3]"
         ".filter(v=>v!=null),_lo=Math.min(..._cv),_hi=Math.max(..._cv),_pad=Math.max(3,(_hi-_lo)*0.08); "
         "const minV=_lo-_pad,maxV=_hi+_pad;"),
        # Category-tab chart gridlines across dynamic domain
        ("[40,50,60,70].map(v=>",
         "[Math.round((minV+(maxV-minV)*0.2)/10)*10,Math.round((minV+(maxV-minV)*0.5)/10)*10,"
         "Math.round((minV+(maxV-minV)*0.8)/10)*10].map(v=>"),
        # Category-tab chart x-labels anchored at edges
        ('text-anchor="middle" font-family="\'Inter\',sans-serif" font-weight="${i===idx?700:400}">${MONTHS[i]}',
         'text-anchor="${i===0?\'start\':i===n-1?\'end\':\'middle\'}" font-family="\'Inter\',sans-serif" font-weight="${i===idx?700:400}">${MONTHS[i]}'),
    ]
    for a, b in chart_fixes:
        assert a in html, f"chart-fix target not found: {a[:48]}"
        html = html.replace(a, b)

    open(OUT, "w").write(html)
    print(f"Wrote {OUT}: {len(rows)} months ({rows[0][0]} -> {rows[-1][0]})")
    print("MONTHS:", months_lbls)


def fmt_signed(v, pts=False):
    if v is None:
        return "—"
    return ("+" if v >= 0 else "") + (f"{v:.0f}" + ("pts" if pts else "") if pts else f"{v:.0f}")


def js_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def sgn(v, dec=0, suf=""):
    """Signed number for narratives: +6, -10pts, etc. 'n/a' when None."""
    if v is None:
        return "n/a"
    return f"{v:+.{dec}f}{suf}"


def gap_mom_pts(cat, m, pm, primary):
    """MoM change (pts) in the KEEN-vs-primary-category index gap."""
    if m not in cat or pm not in cat:
        return None
    return (cat[m]["KEEN"] - cat[m][primary]) - (cat[pm]["KEEN"] - cat[pm][primary])


if __name__ == "__main__":
    main()
