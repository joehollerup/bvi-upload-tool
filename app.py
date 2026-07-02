#!/usr/bin/env python3
"""BVI Self-Serve Upload App — Flask web app for scoring client dashboards.

Routes:
  GET  /       Upload form (Fusepoint-styled)
  POST /score  Process uploaded files and return dashboard HTML
"""

import os
import sys
import tempfile
import shutil
import traceback

from flask import Flask, request, Response

import parse_trends
import parse_gsc
import parse_ga4
import parse_social
import generate_dashboard

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB


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
    padding: 32px 16px 64px;
  }
  .page { max-width: 720px; margin: 0 auto; }
  .banner {
    background: #1F1E1D;
    border-radius: 8px;
    padding: 10px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 28px;
  }
  .banner-logo {
    font-family: 'Instrument Serif', Georgia, serif;
    font-size: 16px;
    color: #FAF7F2;
  }
  .banner-sub { font-size: 11px; color: #B5B0A6; margin-left: auto; }
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
<div class="page">

  <div class="banner">
    <span class="banner-logo">Fusepoint</span>
    <span class="banner-sub">BVI Self-Serve Tool — Internal only</span>
  </div>

  <h1>Score a Client Dashboard</h1>
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


def _score(tmpdir):
    f = request.files
    form = request.form

    # Validate required files
    missing = []
    if not f.get("gsc_zip") or f["gsc_zip"].filename == "":
        missing.append("GSC ZIP export")
    if not f.get("trends1") or f["trends1"].filename == "":
        missing.append("Google Trends Export 1 (brand vs competitors)")
    if not f.get("trends2") or f["trends2"].filename == "":
        missing.append("Google Trends Export 2 (brand vs category)")
    if missing:
        return render_form(
            error="Missing required file(s): " + ", ".join(missing)
        ), 400

    # Save required files
    gsc_zip_path = _save(f["gsc_zip"], tmpdir, "gsc.zip")
    trends1_path = _save(f["trends1"], tmpdir, "trends1.csv")
    trends2_path = _save(f["trends2"], tmpdir, "trends2.csv")

    # Save optional files
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

    # Parse Trends Export 1 to auto-detect brand_key and rivals
    try:
        T = parse_trends.load_from([trends1_path, trends2_path])
    except Exception as e:
        return render_form(error=f"Failed to parse Trends files: {e}"), 400

    comp_first = next(iter(T["comp"].values()))
    all_keys = list(comp_first.keys())
    brand_key = all_keys[0]
    rivals = all_keys[1:]  # up to 3 competitors

    # Parse GSC
    gsc_extract_dir = os.path.join(tmpdir, "gsc_extract")
    try:
        G_data = parse_gsc.load_from(gsc_zip_path, gsc_extract_dir, brand_key)
    except Exception as e:
        return render_form(error=f"Failed to parse GSC ZIP: {e}"), 400

    # Parse GA4 (optional)
    A = {}
    if ga4_paths:
        try:
            A = parse_ga4.load_from(ga4_paths)
        except Exception as e:
            return render_form(error=f"Failed to parse GA4 CSV(s): {e}"), 400

    # Parse social (optional)
    S = {}
    if ig_path or tt_path:
        try:
            S = parse_social.load_from(ig_path=ig_path, tt_path=tt_path)
        except Exception as e:
            return render_form(error=f"Failed to parse social file(s): {e}"), 400

    # Build client config
    client_name = form.get("client_name", "").strip() or brand_key
    comp_input = form.get("competitors", "").strip()
    comp_display = [c.strip() for c in comp_input.split(",") if c.strip()] if comp_input else rivals

    client_config = {
        "client_name": client_name,
        "brand_key": brand_key,
        "rivals": rivals,
        "comp_display": comp_display,
    }

    # Generate dashboard
    try:
        html = generate_dashboard.generate(client_config, T, G_data, A, S)
    except Exception as e:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        return render_form(
            error=f"Dashboard generation failed: {e}<br>"
                  f"<code style='font-size:11px;white-space:pre-wrap'>{tb}</code>"
        ), 500

    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
