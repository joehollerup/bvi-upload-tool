#!/usr/bin/env python3
"""BVI Self-Serve Upload App — Flask web app for scoring client dashboards.

Routes:
  GET  /              Home page — client list
  GET  /new           Upload form (Fusepoint-styled)
  POST /score         Process uploaded files → redirect to /client/<id>
  GET  /client/<id>   Client dashboard
"""

import os
import sys
import tempfile
import shutil
import traceback
import json
from datetime import datetime

from flask import Flask, request, Response, redirect, url_for

import parse_trends
import parse_gsc
import parse_ga4
import parse_social
import generate_dashboard
import db

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

db.init_db()


# ── Home page ────────────────────────────────────────────────────────────────

_NAV = """
<nav>
  <div class="nav-inner">
    <span class="nav-logo">Fusepoint</span>
    <span class="nav-title">Brand Velocity Index</span>
    {nav_right}
  </div>
</nav>"""

_SHARED_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #FAF7F2;
    color: #1F1E1D;
    min-height: 100vh;
  }
  nav {
    background: #1F1E1D;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .nav-inner {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 24px;
    height: 48px;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .nav-logo {
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 16px;
    color: #FAF7F2;
  }
  .nav-title {
    font-size: 11px;
    color: #6B6864;
    margin-right: auto;
  }
  a.btn-primary {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    padding: 7px 16px;
    border-radius: 6px;
    background: #FFCF70;
    color: #1F1E1D;
    text-decoration: none;
    transition: opacity .15s;
  }
  a.btn-primary:hover { opacity: .85; }
  a.btn-ghost {
    font-size: 13px;
    font-weight: 500;
    color: #B5B0A6;
    text-decoration: none;
    transition: color .15s;
  }
  a.btn-ghost:hover { color: #FAF7F2; }"""


def _fmt_month(m):
    if not m:
        return "—"
    try:
        return datetime.strptime(m + "-01", "%Y-%m-%d").strftime("%b '%y")
    except Exception:
        return m


def render_home():
    rows = db.get_all_clients_with_latest_run()

    # Build card HTML
    if not rows:
        cards_html = """
      <div class="empty">
        <div class="empty-icon">◻</div>
        <div class="empty-title">No clients yet</div>
        <div class="empty-sub">Upload a client's data exports to generate their first BVI dashboard.</div>
        <a class="btn-new" href="/new" style="margin-top:20px">+ New client</a>
      </div>"""
    else:
        cards = []
        for r in rows:
            cfg = json.loads(r["config_json"]) if r["config_json"] else {}
            rivals = cfg.get("rivals", [])
            n_comp = len(rivals)

            # Count unique category terms
            cat_terms = {t for t in [cfg.get("primary"), cfg.get("cat2"), cfg.get("cat3")] if t}
            n_cat = len(cat_terms)

            bvi = round(r["bvi_score"]) if r["bvi_score"] is not None else None
            momentum = r["momentum"] or ""
            month_label = _fmt_month(r["month"])

            if momentum == "Rising":
                mom_style = "color:#0F6E56"
                mom_arrow = "↑"
            elif momentum == "Declining":
                mom_style = "color:#BA7517"
                mom_arrow = "↓"
            else:
                mom_style = "color:#8A8782"
                mom_arrow = "→"

            bvi_chip = (
                f'<span class="bvi-chip">{bvi}</span>'
                if bvi is not None else ""
            )

            comp_str = f'{n_comp} competitor{"s" if n_comp != 1 else ""}'
            cat_str = f'{n_cat} category term{"s" if n_cat != 1 else ""}'

            cards.append(f"""
        <a class="client-card" href="/client/{r['id']}">
          <div class="card-header">
            <span class="card-name">{r['name']}</span>
            {bvi_chip}
          </div>
          <div class="card-slug">{r['brand_key']}</div>
          <div class="card-meta">{comp_str} · {cat_str}</div>
          {f'<div class="card-momentum" style="{mom_style}">{mom_arrow} {momentum} · {month_label}</div>' if momentum else f'<div class="card-momentum" style="color:#C5C0BA">{month_label or "No data yet"}</div>'}
        </a>""")

        cards_html = f'<div class="card-grid">{"".join(cards)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BVI — Clients</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #FAF7F2;
    color: #1F1E1D;
    display: flex;
    height: 100vh;
    overflow: hidden;
  }}

  /* ── Sidebar ── */
  .sidebar {{
    width: 216px;
    flex-shrink: 0;
    background: #FFFFFF;
    border-right: 0.5px solid #E5E2DC;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }}
  .sidebar-logo {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 18px 16px 16px;
    border-bottom: 0.5px solid #E5E2DC;
  }}
  .logo-mark {{
    width: 28px;
    height: 28px;
    background: #FFCF70;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 15px;
    color: #1F1E1D;
    flex-shrink: 0;
  }}
  .logo-text {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 15px;
    color: #1F1E1D;
  }}
  .sidebar-nav {{
    flex: 1;
    padding: 8px;
    overflow-y: auto;
  }}
  .nav-item {{
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    color: #6B6864;
    text-decoration: none;
    transition: background .1s, color .1s;
  }}
  .nav-item:hover {{ background: #F5F0E6; color: #1F1E1D; }}
  .nav-item.active {{
    background: #F5F0E6;
    color: #1F1E1D;
    border-left: 2px solid #FFCF70;
    padding-left: 8px;
  }}
  .nav-item svg {{ flex-shrink: 0; opacity: .7; }}
  .nav-item.active svg {{ opacity: 1; }}
  .sidebar-footer {{
    padding: 12px 16px;
    border-top: 0.5px solid #E5E2DC;
    font-size: 11px;
    color: #8A8782;
    line-height: 1.5;
  }}

  /* ── Main ── */
  .main {{
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 28px 32px 0;
    flex-shrink: 0;
  }}
  .topbar-left h1 {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 24px;
    font-weight: 400;
    color: #1F1E1D;
    margin-bottom: 3px;
  }}
  .topbar-left p {{
    font-size: 13px;
    color: #8A8782;
  }}
  a.btn-new {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    padding: 8px 18px;
    border-radius: 7px;
    background: #FFCF70;
    color: #1F1E1D;
    text-decoration: none;
    white-space: nowrap;
    transition: opacity .15s;
  }}
  a.btn-new:hover {{ opacity: .85; }}
  .content {{
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px 48px;
  }}

  /* ── Cards ── */
  .card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }}
  .client-card {{
    background: #FFFFFF;
    border: 0.5px solid #E5E2DC;
    border-radius: 8px;
    padding: 18px 20px;
    text-decoration: none;
    color: inherit;
    display: flex;
    flex-direction: column;
    gap: 5px;
    transition: box-shadow .15s, border-color .15s;
  }}
  .client-card:hover {{
    box-shadow: 0 2px 12px rgba(31,30,29,.07);
    border-color: #D0CBC3;
  }}
  .card-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 2px;
  }}
  .card-name {{
    font-size: 15px;
    font-weight: 600;
    color: #1F1E1D;
    line-height: 1.3;
  }}
  .bvi-chip {{
    font-size: 12px;
    font-weight: 700;
    color: #1F1E1D;
    background: #F5F0E6;
    border-radius: 5px;
    padding: 2px 8px;
    flex-shrink: 0;
    margin-top: 1px;
  }}
  .card-slug {{
    font-family: 'SF Mono', 'Fira Mono', ui-monospace, monospace;
    font-size: 11px;
    color: #8A8782;
    margin-bottom: 4px;
  }}
  .card-meta {{
    font-size: 12px;
    color: #6B6864;
  }}
  .card-momentum {{
    font-size: 11px;
    font-weight: 500;
    margin-top: 2px;
  }}

  /* ── Empty state ── */
  .empty {{
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 80px 20px;
    text-align: center;
  }}
  .empty-icon {{ font-size: 28px; color: #C5C0BA; margin-bottom: 14px; }}
  .empty-title {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 20px;
    margin-bottom: 8px;
  }}
  .empty-sub {{ font-size: 13px; color: #6B6864; max-width: 320px; line-height: 1.6; }}
</style>
</head>
<body>

<aside class="sidebar">
  <div class="sidebar-logo">
    <div class="logo-mark">F</div>
    <span class="logo-text">Fusepoint</span>
  </div>
  <nav class="sidebar-nav">
    <a class="nav-item active" href="/">
      <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
        <rect x="1" y="1" width="5.5" height="5.5" rx="1" fill="currentColor"/>
        <rect x="8.5" y="1" width="5.5" height="5.5" rx="1" fill="currentColor"/>
        <rect x="1" y="8.5" width="5.5" height="5.5" rx="1" fill="currentColor"/>
        <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1" fill="currentColor"/>
      </svg>
      Clients
    </a>
  </nav>
  <div class="sidebar-footer">
    BVI Self-Serve · Internal
  </div>
</aside>

<div class="main">
  <div class="topbar">
    <div class="topbar-left">
      <h1>Clients</h1>
      <p>Brands you score each month.</p>
    </div>
    <a class="btn-new" href="/new">+ New client</a>
  </div>
  <div class="content">
    {cards_html}
  </div>
</div>

</body>
</html>"""


# ── Upload form ─────────────────────────────────────────────────────────────

FORM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BVI Score — Upload Client Data</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #FAF7F2;
    color: #1F1E1D;
    min-height: 100vh;
    padding: 0 0 64px;
  }
  .page { max-width: 720px; margin: 0 auto; padding: 0 16px; }
  nav {
    background: #1F1E1D;
    position: sticky;
    top: 0;
    z-index: 100;
    margin-bottom: 32px;
  }
  .nav-inner {
    max-width: 720px;
    margin: 0 auto;
    padding: 0 16px;
    height: 48px;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .nav-logo {
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 16px;
    color: #FAF7F2;
  }
  .nav-title { font-size: 11px; color: #6B6864; margin-right: auto; }
  .nav-back {
    font-size: 12px;
    font-weight: 500;
    color: #B5B0A6;
    text-decoration: none;
  }
  .nav-back:hover { color: #FAF7F2; }
  h1 {
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 28px;
    font-weight: 400;
    margin-bottom: 6px;
  }
  .subtitle { font-size: 13px; color: #6B6864; margin-bottom: 28px; }
  .card {
    background: #FFFFFF;
    border: 0.5px solid #E5E2DC;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }
  .card-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #8A8782;
    margin-bottom: 14px;
  }
  .field { margin-bottom: 14px; }
  .field:last-child { margin-bottom: 0; }
  label { display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; }
  label .opt { font-weight: 400; color: #8A8782; }
  .hint { font-size: 11px; color: #8A8782; margin-top: 3px; line-height: 1.5; }
  input[type=text], input[type=file] {
    width: 100%;
    font-family: inherit;
    font-size: 13px;
    padding: 8px 10px;
    border: 0.5px solid #E5E2DC;
    border-radius: 5px;
    background: #FAF7F2;
    color: #1F1E1D;
    outline: none;
    transition: border-color .15s;
  }
  input[type=text]:focus, input[type=file]:focus {
    border-color: #FFCF70;
    background: #FFFFFF;
  }
  input[type=file] { padding: 6px 10px; cursor: pointer; }
  .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .divider {
    border: none;
    border-top: 0.5px solid #E5E2DC;
    margin: 20px 0;
  }
  .file-section { margin-bottom: 0; }
  .badge-required {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .04em;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(255, 207, 112, .25);
    color: #1F1E1D;
    margin-left: 6px;
    vertical-align: middle;
  }
  .badge-optional {
    display: inline-block;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .04em;
    padding: 1px 6px;
    border-radius: 3px;
    background: #F5F0E6;
    color: #8A8782;
    margin-left: 6px;
    vertical-align: middle;
  }
  .submit-row { margin-top: 24px; }
  button[type=submit] {
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 28px;
    border: none;
    border-radius: 6px;
    background: #1F1E1D;
    color: #FAF7F2;
    cursor: pointer;
    transition: opacity .15s;
  }
  button[type=submit]:hover { opacity: .85; }
  .error-banner {
    background: #FFF3F3;
    border: 0.5px solid #F5A0A0;
    border-radius: 6px;
    padding: 12px 16px;
    margin-bottom: 20px;
    font-size: 13px;
    color: #B91C1C;
    line-height: 1.6;
  }
  .error-banner strong { display: block; margin-bottom: 4px; }
</style>
</head>
<body>
<nav>
  <div class="nav-inner">
    <span class="nav-logo">Fusepoint</span>
    <span class="nav-title">Brand Velocity Index</span>
    <a class="nav-back" href="/">← All Clients</a>
  </div>
</nav>
<div class="page">

  <h1 style="font-family:'Instrument Serif',Georgia,serif;font-size:28px;font-weight:400;margin-bottom:6px">Score a Client Dashboard</h1>
  <p class="subtitle">Upload the client's data exports to generate a scored BVI dashboard.</p>

  {error_block}

  <form method="POST" action="/score" enctype="multipart/form-data">

    <div class="card">
      <div class="card-title">Client Info</div>
      <div class="row2">
        <div class="field">
          <label>Client Name</label>
          <input type="text" name="client_name" placeholder="e.g. KEEN" required>
          <div class="hint">Shown in the dashboard header.</div>
        </div>
        <div class="field">
          <label>Competitors <span class="hint" style="display:inline">(comma-separated)</span></label>
          <input type="text" name="competitors" placeholder="e.g. Salomon, Red Wing, Sorel">
          <div class="hint">Display names for the 3 competitor slots. Must match Trends Export 1 column order.</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Search Files</div>

      <div class="field">
        <label>
          GSC ZIP Export
          <span class="badge-required">Required</span>
        </label>
        <input type="file" name="gsc_zip" accept=".zip" required>
        <div class="hint">
          Google Search Console → Performance → Export → Download ZIP.
          The ZIP must contain <strong>Queries.csv</strong> and <strong>Chart.csv</strong>.
        </div>
      </div>

      <hr class="divider">

      <div class="field">
        <label>
          Google Trends Export 1 — Brand vs Competitors
          <span class="badge-required">Required</span>
        </label>
        <input type="file" name="trends1" accept=".csv" required>
        <div class="hint">
          Google Trends → compare the brand name + up to 3 competitors → Export CSV.
          First column = brand; remaining columns = competitors.
        </div>
      </div>

      <div class="field">
        <label>
          Google Trends Export 2 — Brand vs Category Terms
          <span class="badge-required">Required</span>
        </label>
        <input type="file" name="trends2" accept=".csv" required>
        <div class="hint">
          Same as Export 1 but compare the brand against 2–3 category search terms
          (e.g. "Hiking Boots", "Work Boots", "trail running").
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">GA4 Traffic</div>
      <div class="field">
        <label>
          GA4 Traffic Acquisition CSVs
          <span class="badge-optional">Optional</span>
        </label>
        <input type="file" name="ga4_files" accept=".csv" multiple>
        <div class="hint">
          GA4 → Reports → Acquisition → Traffic acquisition → Export CSV.
          Upload one CSV per month (single-month exports only — aggregate exports are skipped).
          Ctrl/Cmd+click to select multiple files.
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Social Media</div>
      <div class="row2">
        <div class="field">
          <label>
            Instagram Manual Numbers
            <span class="badge-optional">Optional</span>
          </label>
          <input type="file" name="instagram" accept=".csv">
          <div class="hint">
            Monthly Instagram metrics CSV with columns: Date, Followers, Net Follower Growth,
            Engagements, Views/Impressions, Reach.
          </div>
        </div>
        <div class="field">
          <label>
            TikTok Manual Numbers
            <span class="badge-optional">Optional</span>
          </label>
          <input type="file" name="tiktok" accept=".csv">
          <div class="hint">
            Same format as Instagram — monthly TikTok metrics.
          </div>
        </div>
      </div>
    </div>

    <div class="submit-row">
      <button type="submit">Score Dashboard →</button>
    </div>

  </form>
</div>
</body>
</html>"""


def render_form(error=None):
    if error:
        error_block = f'<div class="error-banner"><strong>Error</strong>{error}</div>'
    else:
        error_block = ""
    return FORM_HTML.replace("{error_block}", error_block)


@app.route("/", methods=["GET"])
def index():
    return render_home()


@app.route("/new", methods=["GET"])
def new_client():
    return render_form()


# ── Score route ─────────────────────────────────────────────────────────────

@app.route("/score", methods=["POST"])
def score():
    tmpdir = tempfile.mkdtemp(prefix="bvi_")
    try:
        return _score(tmpdir)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        msg = f"<br><code style='font-size:12px;white-space:pre-wrap'>{tb}</code>"
        return render_form(error=msg), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _save(file_obj, tmpdir, name):
    path = os.path.join(tmpdir, name)
    file_obj.save(path)
    return path


def _parse_uploads(tmpdir):
    """Save and parse all uploaded files from the current request.

    Returns (T, brand_key, rivals, G_data, A, S).
    Raises ValueError with a user-facing message on missing/invalid files.
    """
    f = request.files

    missing = []
    if not f.get("gsc_zip") or f["gsc_zip"].filename == "":
        missing.append("GSC ZIP export")
    if not f.get("trends1") or f["trends1"].filename == "":
        missing.append("Google Trends Export 1 (brand vs competitors)")
    if not f.get("trends2") or f["trends2"].filename == "":
        missing.append("Google Trends Export 2 (brand vs category)")
    if missing:
        raise ValueError("Missing required file(s): " + ", ".join(missing))

    gsc_zip_path = _save(f["gsc_zip"], tmpdir, "gsc.zip")
    trends1_path = _save(f["trends1"], tmpdir, "trends1.csv")
    trends2_path = _save(f["trends2"], tmpdir, "trends2.csv")

    ga4_paths = []
    for i, ga4_file in enumerate(f.getlist("ga4_files")):
        if ga4_file and ga4_file.filename:
            ga4_paths.append(_save(ga4_file, tmpdir, f"ga4_{i}.csv"))

    ig_path = None
    if f.get("instagram") and f["instagram"].filename:
        ig_path = _save(f["instagram"], tmpdir, "instagram.csv")

    tt_path = None
    if f.get("tiktok") and f["tiktok"].filename:
        tt_path = _save(f["tiktok"], tmpdir, "tiktok.csv")

    try:
        T = parse_trends.load_from([trends1_path, trends2_path])
    except Exception as e:
        raise ValueError(f"Failed to parse Trends files: {e}")

    comp_first = next(iter(T["comp"].values()))
    all_keys = list(comp_first.keys())
    brand_key = all_keys[0]
    rivals = all_keys[1:]

    gsc_extract_dir = os.path.join(tmpdir, "gsc_extract")
    try:
        G_data = parse_gsc.load_from(gsc_zip_path, gsc_extract_dir, brand_key)
    except Exception as e:
        raise ValueError(f"Failed to parse GSC ZIP: {e}")

    A = {}
    if ga4_paths:
        try:
            A = parse_ga4.load_from(ga4_paths)
        except Exception as e:
            raise ValueError(f"Failed to parse GA4 CSV(s): {e}")

    S = {}
    if ig_path or tt_path:
        try:
            S = parse_social.load_from(ig_path=ig_path, tt_path=tt_path)
        except Exception as e:
            raise ValueError(f"Failed to parse social file(s): {e}")

    return T, brand_key, rivals, G_data, A, S


def _score(tmpdir):
    try:
        T, brand_key, rivals, G_data, A, S = _parse_uploads(tmpdir)
    except ValueError as e:
        return render_form(error=str(e)), 400

    form = request.form
    client_name = form.get("client_name", "").strip() or brand_key
    comp_input = form.get("competitors", "").strip()
    comp_display = [c.strip() for c in comp_input.split(",") if c.strip()] if comp_input else rivals

    client_config = {
        "client_name": client_name,
        "brand_key": brand_key,
        "rivals": rivals,
        "comp_display": comp_display,
    }

    try:
        html, month_rows, results, client_config = generate_dashboard.generate(
            client_config, T, G_data, A, S
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        return render_form(
            error=f"Dashboard generation failed: {e}<br>"
                  f"<code style='font-size:11px;white-space:pre-wrap'>{tb}</code>"
        ), 500

    try:
        client_id = db.upsert_client(client_config)
        db.save_score_runs(client_id, month_rows, results)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        return Response(html, mimetype="text/html")

    return redirect(url_for("client_detail", client_id=client_id))


@app.route("/client/<int:client_id>")
def client_detail(client_id):
    client = db.get_client(client_id)
    if not client:
        return render_form(error=f"Client {client_id} not found."), 404

    runs = db.get_score_runs(client_id)
    if not runs:
        return render_form(error=f"No score data found for client {client_id}."), 404

    client_config = json.loads(client["config_json"])

    stored_rows = []
    for run in runs:
        storage = json.loads(run["dashboard_data_json"])
        storage["month"] = run["month"]
        stored_rows.append(storage)

    try:
        html = generate_dashboard.generate_from_stored_rows(client_config, stored_rows)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        return render_form(
            error=f"Dashboard reconstruction failed: {e}<br>"
                  f"<code style='font-size:11px;white-space:pre-wrap'>{tb}</code>"
        ), 500

    # Inject floating admin buttons — avoids z-index battles with the dashboard's own nav
    fab_css = (
        "<style>"
        "#_fp_back{position:fixed;bottom:24px;left:24px;z-index:99999;"
        "background:#1F1E1D;color:#B5B0A6;font-size:12px;font-weight:500;"
        "padding:8px 14px;border-radius:6px;text-decoration:none;"
        "font-family:Inter,-apple-system,sans-serif;"
        "box-shadow:0 2px 8px rgba(0,0,0,.25);transition:color .15s}"
        "#_fp_back:hover{color:#FAF7F2}"
        "#_fp_update{position:fixed;bottom:24px;right:24px;z-index:99999;"
        "background:#FFCF70;color:#1F1E1D;font-size:13px;font-weight:600;"
        "padding:10px 20px;border-radius:8px;text-decoration:none;"
        "font-family:Inter,-apple-system,sans-serif;"
        "box-shadow:0 2px 12px rgba(0,0,0,.2);transition:opacity .15s}"
        "#_fp_update:hover{opacity:.85}"
        "</style>"
    )
    fab_html = (
        f'<a id="_fp_back" href="/">← Clients</a>'
        f'<a id="_fp_update" href="/client/{client_id}/update">+ Add Monthly Data</a>'
    )
    html = html.replace("</body>", fab_css + fab_html + "</body>", 1)

    return Response(html, mimetype="text/html")


# ── Update form ──────────────────────────────────────────────────────────────

def render_update_form(client_config, client_id, error=None):
    name = client_config.get("client_name", "")
    brand_key = client_config.get("brand_key", "")
    rivals = client_config.get("rivals", [])
    comp_display = client_config.get("comp_display", rivals)
    comp_value = ", ".join(comp_display)

    primary = client_config.get("primary", "")
    cat2 = client_config.get("cat2", "")
    cat3 = client_config.get("cat3", "")
    cat_terms = ", ".join(t for t in [primary, cat2, cat3] if t and t != primary or t == primary)
    # deduplicate while preserving order
    seen, cat_list = set(), []
    for t in [primary, cat2, cat3]:
        if t and t not in seen:
            seen.add(t)
            cat_list.append(t)
    cat_terms = ", ".join(f'"{t}"' for t in cat_list)

    error_block = (
        f'<div class="error-banner"><strong>Error</strong> {error}</div>'
        if error else ""
    )

    rivals_display = ", ".join(rivals) if rivals else "none detected yet"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Add Monthly Data — {name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #FAF7F2;
    color: #1F1E1D;
    min-height: 100vh;
    padding: 0 0 64px;
  }}
  .page {{ max-width: 720px; margin: 0 auto; padding: 0 16px; }}
  nav {{
    background: #1F1E1D;
    position: sticky;
    top: 0;
    z-index: 100;
    margin-bottom: 32px;
  }}
  .nav-inner {{
    max-width: 720px;
    margin: 0 auto;
    padding: 0 16px;
    height: 48px;
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .nav-logo {{ font-family: 'Instrument Serif', Georgia, serif; font-size: 16px; color: #FAF7F2; }}
  .nav-title {{ font-size: 11px; color: #6B6864; margin-right: auto; }}
  .nav-back {{ font-size: 12px; font-weight: 500; color: #B5B0A6; text-decoration: none; }}
  .nav-back:hover {{ color: #FAF7F2; }}
  h1 {{
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 28px;
    font-weight: 400;
    margin-bottom: 6px;
  }}
  .subtitle {{ font-size: 13px; color: #6B6864; margin-bottom: 28px; }}
  .card {{
    background: #FFFFFF;
    border: 0.5px solid #E5E2DC;
    border-radius: 8px;
    padding: 20px 24px;
    margin-bottom: 16px;
  }}
  .card-title {{
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #8A8782;
    margin-bottom: 14px;
  }}
  .info-row {{
    font-size: 12px;
    color: #6B6864;
    background: #F5F0E6;
    border-radius: 5px;
    padding: 8px 12px;
    line-height: 1.6;
    margin-bottom: 14px;
  }}
  .info-row strong {{ color: #1F1E1D; font-weight: 600; }}
  .field {{ margin-bottom: 14px; }}
  .field:last-child {{ margin-bottom: 0; }}
  label {{ display: block; font-size: 13px; font-weight: 500; margin-bottom: 4px; }}
  .hint {{ font-size: 11px; color: #8A8782; margin-top: 3px; line-height: 1.5; }}
  input[type=text], input[type=file] {{
    width: 100%;
    font-family: inherit;
    font-size: 13px;
    padding: 8px 10px;
    border: 0.5px solid #E5E2DC;
    border-radius: 5px;
    background: #FAF7F2;
    color: #1F1E1D;
    outline: none;
    transition: border-color .15s;
  }}
  input[type=text]:focus, input[type=file]:focus {{
    border-color: #FFCF70;
    background: #FFFFFF;
  }}
  input[type=file] {{ padding: 6px 10px; cursor: pointer; }}
  .row2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
  .divider {{ border: none; border-top: 0.5px solid #E5E2DC; margin: 20px 0; }}
  .badge-required {{
    display: inline-block;
    font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
    padding: 1px 6px; border-radius: 3px;
    background: rgba(255,207,112,.25); color: #1F1E1D;
    margin-left: 6px; vertical-align: middle;
  }}
  .badge-optional {{
    display: inline-block;
    font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
    padding: 1px 6px; border-radius: 3px;
    background: #F5F0E6; color: #8A8782;
    margin-left: 6px; vertical-align: middle;
  }}
  .submit-row {{ margin-top: 24px; display: flex; align-items: center; gap: 16px; }}
  button[type=submit] {{
    font-family: 'Inter', sans-serif;
    font-size: 14px; font-weight: 600;
    padding: 10px 28px;
    border: none; border-radius: 6px;
    background: #FFCF70; color: #1F1E1D;
    cursor: pointer; transition: opacity .15s;
  }}
  button[type=submit]:hover {{ opacity: .85; }}
  .cancel-link {{ font-size: 13px; color: #8A8782; text-decoration: none; }}
  .cancel-link:hover {{ color: #1F1E1D; }}
  .error-banner {{
    background: #FFF3F3; border: 0.5px solid #F5A0A0;
    border-radius: 6px; padding: 12px 16px; margin-bottom: 20px;
    font-size: 13px; color: #B91C1C; line-height: 1.6;
  }}
  .error-banner strong {{ display: block; margin-bottom: 4px; }}
</style>
</head>
<body>
<nav>
  <div class="nav-inner">
    <span class="nav-logo">Fusepoint</span>
    <span class="nav-title">Brand Velocity Index</span>
    <a class="nav-back" href="/client/{client_id}">← {name}</a>
  </div>
</nav>
<div class="page">

  <h1>Add Monthly Data</h1>
  <p class="subtitle">Upload new exports to add or refresh months in the {name} dashboard.</p>

  {error_block}

  <form method="POST" action="/client/{client_id}/update" enctype="multipart/form-data">

    <div class="card">
      <div class="card-title">Client Config</div>
      <div class="info-row">
        <strong>Brand key:</strong> {brand_key} &nbsp;·&nbsp;
        <strong>Rivals:</strong> {rivals_display}
        {f' &nbsp;·&nbsp; <strong>Category terms:</strong> {cat_terms}' if cat_terms else ''}
        <br>Brand key and category terms are re-detected from your Trends exports on each upload.
      </div>
      <div class="row2">
        <div class="field">
          <label>Client Name</label>
          <input type="text" name="client_name" value="{name}" required>
          <div class="hint">Shown in the dashboard header.</div>
        </div>
        <div class="field">
          <label>Competitors <span style="font-weight:400;color:#8A8782;font-size:11px">(comma-separated)</span></label>
          <input type="text" name="competitors" value="{comp_value}">
          <div class="hint">Display names matching Trends Export 1 column order.</div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Search Files</div>
      <div class="field">
        <label>GSC ZIP Export <span class="badge-required">Required</span></label>
        <input type="file" name="gsc_zip" accept=".zip" required>
        <div class="hint">Google Search Console → Performance → Export → Download ZIP.</div>
      </div>
      <hr class="divider">
      <div class="field">
        <label>Google Trends Export 1 — Brand vs Competitors <span class="badge-required">Required</span></label>
        <input type="file" name="trends1" accept=".csv" required>
        <div class="hint">First column = brand key; remaining columns = competitors.</div>
      </div>
      <div class="field">
        <label>Google Trends Export 2 — Brand vs Category Terms <span class="badge-required">Required</span></label>
        <input type="file" name="trends2" accept=".csv" required>
        <div class="hint">Brand vs 2–3 category search terms.</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">GA4 Traffic</div>
      <div class="field">
        <label>GA4 Traffic Acquisition CSVs <span class="badge-optional">Optional</span></label>
        <input type="file" name="ga4_files" accept=".csv" multiple>
        <div class="hint">One CSV per month. Ctrl/Cmd+click to select multiple.</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">Social Media</div>
      <div class="row2">
        <div class="field">
          <label>Instagram Manual Numbers <span class="badge-optional">Optional</span></label>
          <input type="file" name="instagram" accept=".csv">
          <div class="hint">Monthly Instagram metrics CSV.</div>
        </div>
        <div class="field">
          <label>TikTok Manual Numbers <span class="badge-optional">Optional</span></label>
          <input type="file" name="tiktok" accept=".csv">
          <div class="hint">Same format as Instagram.</div>
        </div>
      </div>
    </div>

    <div class="submit-row">
      <button type="submit">Score New Data →</button>
      <a class="cancel-link" href="/client/{client_id}">Cancel</a>
    </div>

  </form>
</div>
</body>
</html>"""


@app.route("/client/<int:client_id>/update", methods=["GET"])
def update_form(client_id):
    client = db.get_client(client_id)
    if not client:
        return render_form(error=f"Client {client_id} not found."), 404
    client_config = json.loads(client["config_json"])
    return render_update_form(client_config, client_id)


@app.route("/client/<int:client_id>/update", methods=["POST"])
def update_score(client_id):
    client = db.get_client(client_id)
    if not client:
        return render_form(error=f"Client {client_id} not found."), 404
    existing_config = json.loads(client["config_json"])

    tmpdir = tempfile.mkdtemp(prefix="bvi_")
    try:
        return _update_score(client_id, existing_config, tmpdir)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        msg = f"<br><code style='font-size:12px;white-space:pre-wrap'>{tb}</code>"
        return render_update_form(existing_config, client_id, error=msg), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _update_score(client_id, existing_config, tmpdir):
    try:
        T, brand_key, rivals, G_data, A, S = _parse_uploads(tmpdir)
    except ValueError as e:
        return render_update_form(existing_config, client_id, error=str(e)), 400

    form = request.form
    client_name = form.get("client_name", "").strip() or existing_config.get("client_name", brand_key)
    comp_input = form.get("competitors", "").strip()
    comp_display = [c.strip() for c in comp_input.split(",") if c.strip()] if comp_input else rivals

    # Preserve previously detected category terms; generate() will re-detect and setdefault
    client_config = {
        **existing_config,
        "client_name": client_name,
        "brand_key": brand_key,
        "rivals": rivals,
        "comp_display": comp_display,
    }

    try:
        _html, month_rows, results, client_config = generate_dashboard.generate(
            client_config, T, G_data, A, S
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        return render_update_form(
            existing_config, client_id,
            error=f"Scoring failed: {e}<br>"
                  f"<code style='font-size:11px;white-space:pre-wrap'>{tb}</code>"
        ), 500

    try:
        db.upsert_client(client_config)
        db.save_score_runs(client_id, month_rows, results)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)

    return redirect(url_for("client_detail", client_id=client_id))


if __name__ == "__main__":
    app.run(debug=True, port=5050)
