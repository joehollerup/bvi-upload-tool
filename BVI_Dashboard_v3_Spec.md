# Brand Velocity Index — Dashboard v3 Spec
**Power Digital Marketing — Confidential**
Last updated: June 2026

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Features & Functionality](#2-features--functionality)
3. [Data Architecture](#3-data-architecture)
4. [Logic & Decision Trees](#4-logic--decision-trees)
5. [UI/UX Spec](#5-uiux-spec)
6. [Technical Implementation](#6-technical-implementation)
7. [Known Limitations & Assumptions](#7-known-limitations--assumptions)
8. [Rebuild Instructions](#8-rebuild-instructions)

---

## 1. Product Overview

### What This Is

`bvi-dashboard-v3.html` is a standalone, self-contained HTML file that renders a fully interactive React-based brand health dashboard for a single client. It is a **demo/presentation artifact** — not a data-ingestion app. All data is hardcoded. There is no upload flow, no persistent storage, and no live data connections.

This file is the **visual and functional reference implementation** of the Brand Velocity Index (BVI) product, built with Kurt Geiger London dummy data. It demonstrates what a fully scored, multi-tier BVI client view looks like. It is used to:

- Show clients and stakeholders what a finished BVI report looks like
- Demo all three tiers (Bronze, Silver, Gold) interactively
- Serve as the UX target for the in-progress data-ingestion app (bvi-app, built separately in Claude Projects)

### What Problem It Solves

PDM lacked a way to demonstrate brand health measurement concretely to fashion/retail clients. This artifact gives Account Directors a fully interactive, client-ready demo they can open in any browser, no installation required.

### Who It's For

- **Primary users:** PDM Account Directors and Account Managers, for client demos and internal QBR prep
- **Secondary users:** Clients (Kurt Geiger London), who receive the HTML file directly or via hosted link
- **Build audience:** Engineers and product managers building the production BVI data-ingestion app

---

## 2. Features & Functionality

### 2.1 Global Controls

#### Month Navigator
- Left/right arrows step through 12 months of data (May '25 → Apr '26)
- Current month label displayed center with "Backfill" or "Live" status badge
- Backfill months: amber badge — data reconstructed from historical exports
- Live months: green badge — data pulled in real time at the time of the scoring run
- Left arrow disabled at month index 0; right arrow disabled at index 11

#### Tier Toggle
- Three buttons: Bronze / Silver / Gold
- **Bronze:** Search Demand, Digital Presence, Competitive Position, Category Context active. Organic Social active for live months only. Social Listening and Direct Awareness locked/hidden.
- **Silver:** Adds Social Listening tab and Paid Brand Efficiency signal status row. BVI score +1pt adjustment applied.
- **Gold:** Adds Direct Awareness tab with staleness indicator. BVI score +3pt adjustment applied.
- Switching tier is instant — no reload, no data change. Tab list and Signal Status rows update immediately.

#### BVI Score Adjustment (Tier)
- Bronze: raw score
- Silver: raw score + 1 (capped at 100)
- Gold: raw score + 3 (capped at 100)
- This is a **display-only adjustment** in the demo. In the production scoring app, tier affects which signals are included in the weighted average, not a flat offset.

---

### 2.2 Summary Panel

Left column: BVI score card (purple)
- Large BVI score (adjusted for tier)
- "out of 100" label
- MoM delta with directional arrow (↑/↓/→) and pts label
- Confidence tier badge (Bronze/Silver/Gold) — amber/light purple/yellow-green respectively
- Backfill months show "Bronze" confidence badge regardless of tier toggle
- Sparkline: 12-month mini trend, BVI line (white) and category line (light purple dashed), current month dot highlighted

Right column: 4-quadrant narrative grid
- **What moved:** key metric change(s) driving the BVI this month
- **Why it moved:** contextual explanation (brand-driven vs. category-driven vs. seasonal)
- **Category context:** brand vs. category index comparison; Rising Tide flag shown as amber badge if active
- **Competitive shift:** summary of nearest competitor movement

Below grid: Recommendation card (dark background, yellow-green "RECOMMENDATION" label)

---

### 2.3 12-Month Trend Chart

Full-width SVG chart showing:
- BVI over time — backfill months as dashed light purple line, live months as solid purple line
- A dashed connector between last backfill and first live month
- Category Trends index as a dashed gray line
- Current month highlighted with a filled purple dot (outer circle) and white inner dot
- Rising tide months get a yellow-green outer ring on the dot
- Y-axis labels at 45, 55, 65
- X-axis: abbreviated month labels, current month in purple bold

Chart is responsive (SVG viewBox scales to container width).

Legend row above chart: BVI live, BVI backfill, Category "women's shoes", Rising tide (only shown when applicable).

---

### 2.4 Signal Status Panel

Left panel of a two-column row (paired with Competitive Position panel).

**Header:** "Signal status" + subtitle "Click any dimension to see how the status is calculated"

**Rows (always present):**
1. Search Demand — base tier
2. Digital Presence — base tier
3. Organic Social — base tier (locked/greyed for backfill months; locked if no social data)
4. Competitive Position — base tier
5. Paid Brand Efficiency — silver tier (locked if Bronze active)
6. Direct Awareness — gold tier (locked if Bronze or Silver active)

**Each row:**
- Colored dot (black = base, light purple = silver, yellow-green = gold)
- Dimension name
- Status badge: Improving / Stable / Declining / Watch
  - Improving: dark green on green bg
  - Stable: gray on gray bg
  - Declining: red on red bg
  - Watch: amber on amber bg
- Click to expand: shows "Contributing factors" table and "How this status is calculated" methodology note
- Locked rows: greyed out, "—" value, tier badge shown (Silver/Gold)
- "No data" rows: greyed, no status badge (used for backfill months where social data unavailable)

**Status calculation logic (per dimension):**
- See Section 4 for full decision trees

---

### 2.5 Competitive Position Panel

Right panel of the same two-column row.

Shows 4 brands sorted descending by Trends index:
- Rank number (#1–#4)
- Brand name (client name in purple bold)
- Trends index /100
- Estimated monthly search volume (SEMrush, in thousands)
- Horizontal bar proportional to `(trendsIdx / 70) * 100%`

---

### 2.6 Signal Tabs

Tab bar with tabs depending on active tier:
- Always present: Search Demand, Digital Presence, Organic Social, Competitive Position, Category Context, Why This Matters
- Silver+: Social Listening
- Gold+: Direct Awareness (with colored staleness dot: green/amber/red)

Active tab: purple underline border, purple text, light purple background tint.

**Search Demand Tab**
- 4-metric grid: Branded impressions, Branded clicks, Branded CTR, Avg position
- 2-metric grid: Google Trends index, Trends YoY change
- Source note at bottom
- Each MetricCard: label, value, MoM delta badge (green/red arrow + value)

**Digital Presence Tab**
- 2×2 grid: Direct sessions, Direct % of total sessions, Total organic sessions, Branded organic split

**Organic Social Tab**
- Backfill months / no data: centered message explaining 90-day platform limit
- Live months with data: 2×2 grid: Follower growth rate, Net follower growth, Organic reach, Engagement rate
- Source note at bottom

**Competitive Position Tab (signal detail)**
- Ranked list of all 4 brands by Trends index (same layout as sidebar panel but with more context)
- Secondary metric column: SEMrush est. monthly volume
- Share of branded search callout card (SEMrush est. vol / sum of all 4)
- Source note at bottom

**Category Context Tab**
- Active category terms panel:
  - Google Trends Export 2 sub-panel: 3 terms with roles (Primary/Secondary/Tertiary) and "Chart line" badge on primary
  - SEMrush sub-panel: 3 terms with monthly volume estimates and roles
  - Footer note: terms set at onboarding, held constant
- 3-metric grid: Category Trends index, Brand vs. category gap, Category keyword volume
- Full multi-line chart: Kurt Geiger vs. all 3 category terms (4 lines)
  - Kurt Geiger: solid purple, 2.5px
  - "women's shoes" (primary): dashed gray, 1.5px
  - "luxury footwear": dashed light purple, 1px
  - "designer shoes": dashed gray-lighter, 1px
  - Current month: vertical dashed line + filled dots on each series
  - Legend below chart
- Rising tide status card: green (no pattern) or amber (pattern detected), with explanation text

**Social Listening Tab (Silver+)**
- Not available for backfill months: centered message
- Live months: 4-metric grid: Mention volume, Sentiment % positive, Share of voice, Earned reach
- Competitive sentiment table: all 4 brands with % positive, sorted descending, horizontal bars
- Influencer reach + EMV cards (2-column)

**Direct Awareness Tab (Gold+)**
- Not available for backfill months before first survey
- Survey metadata header: source, fielded date, sample size, audience type
- Staleness tag: "Survey data · [date]" (green), "Survey from [date] · refresh recommended" (amber), "Survey from [date] · overdue" (red)
- Staleness warning banner if amber or stale
- 4 awareness metric cards: Unaided recall, Aided awareness, Consideration, Preference
  - Each card: %, delta vs prior survey (or "First survey — no prior data"), survey question note
- Awareness funnel: horizontal bars for all 4 metrics
- Footer note on sample size display and audience type

**Why This Matters Tab (Methodology)**
- Intro card: dark background, why brand measurement is hard, link to full methodology briefing
- 4-stat row: McKinsey 45%, Ekimetrics 5–24mo, Kantar 2×, BCG $1.85
- 4-mechanism cards (2×2): Long-term carryover, Brand amplifies performance, Pricing power, Cost of cutting
- BVI measurement clarity card: Reliably tracks / Measures with caveats / Requires MMM layer
- 40–60 rule: text + illustrative bar chart showing peak ROI zone

---

### 2.7 Upsell Cards

Shown at bottom of page when tier is Bronze or Silver. Never shown at Gold.
- Bronze: 3 cards (Social Listening, Paid Brand Efficiency, Direct Awareness)
- Silver: 1 card (Direct Awareness)
- Each card: title, description, tier badge, "Add [tier] tier ↗" button (button is decorative — no action wired)

---

### 2.8 Backfill Banner

Shown when the selected month is a backfill month:
> "Backfill month — Base tier signals only. Organic Social unavailable prior to January 2026 (90-day native platform limit). Listening and survey data also unavailable for backfill months."

---

## 3. Data Architecture

### 3.1 All Data is Hardcoded

This artifact has **no external data connections**. There is no API call, no file upload, no localStorage, no persistent storage of any kind. All data is declared as JavaScript constants at the top of the `<script>` block.

### 3.2 Primary Data Object: `RAW`

`RAW` is an array of 12 objects, one per month (May '25 → Apr '26). Each object contains every metric for that month across all tiers.

**Key fields per month object:**

| Field | Type | Description |
|---|---|---|
| `bvi` | number | Base BVI score (Bronze, raw) |
| `status` | string | `"backfill"` or `"live"` |
| `impressions` | number | Branded impressions (thousands) |
| `impressionsDelta` | number \| null | MoM % change |
| `clicks` | number | Branded clicks (thousands) |
| `clicksDelta` | number \| null | MoM % change |
| `ctr` | number | Branded CTR % |
| `ctrDelta` | number \| null | MoM pts change |
| `position` | number | Avg position |
| `positionDelta` | number \| null | MoM position change (negative = improved) |
| `trendsIdx` | number | Google Trends index (client brand) |
| `trendsIdxDelta` | number \| null | MoM pts change |
| `trendsYoY` | number \| null | YoY % change (null for backfill) |
| `directSessions` | number | Direct sessions (thousands) |
| `directSessionsDelta` | number \| null | MoM % change |
| `directPct` | number | Direct % of total sessions |
| `directPctDelta` | number \| null | MoM pts change |
| `organicSessions` | number | Total organic sessions (thousands) |
| `organicSessionsDelta` | number \| null | MoM % change |
| `brandedOrganic` | number | Branded organic split % |
| `brandedOrganicDelta` | number \| null | MoM pts change |
| `followerGrowthRate` | number \| null | null for backfill |
| `followerGrowthRateDelta` | number \| null | null for backfill or first live month |
| `netFollowerGrowth` | number \| null | |
| `reach` | number \| null | Organic reach (thousands) |
| `engagementRate` | number \| null | % |
| `engagementRateDelta` | number \| null | pts |
| `kgTrends` | number | Kurt Geiger Trends index |
| `smTrends` | number | Steve Madden Trends index |
| `carTrends` | number | Carvela Trends index |
| `tedTrends` | number | Ted Baker Trends index |
| `kgVol` | number | Kurt Geiger SEMrush est. volume (K) |
| `smVol`, `carVol`, `tedVol` | number | Same for competitors |
| `brandShare` | number | Brand share of branded search % |
| `brandShareDelta` | number \| null | MoM pts change |
| `catTrends` | number | Primary category Trends index |
| `catVol` | number | Category keyword volume (K) |
| `catVolDelta` | number \| null | MoM % change |
| `risingTide` | boolean | Rising tide flag |
| `searchScore` | number | Pre-calculated dimension score (display only in demo) |
| `digitalScore` | number | |
| `socialScore` | number \| null | null for backfill |
| `compScore` | number | |
| `mentionVol` | number \| null | Silver — null for backfill |
| `mentionVolDelta` | number \| null | |
| `sentimentPct` | number \| null | |
| `sentimentDelta` | number \| null | |
| `sov` | number \| null | Share of voice % |
| `sovDelta` | number \| null | |
| `earnedReach` | number \| null | Thousands |
| `influencerReach` | number \| null | Thousands |
| `emv` | number \| null | Earned media value (thousands $) |
| `kgSentiment`, `smSentiment`, `carSentiment`, `tedSentiment` | number \| null | Competitive sentiment % positive |
| `brandedCpmGoogle` | number \| null | Silver |
| `brandedCpmMeta` | number \| null | Silver |
| `cpmGoogleDelta`, `cpmMetaDelta` | number \| null | MoM % change |
| `impressionShare` | number \| null | Paid impression share % |
| `impressionShareDelta` | number \| null | pts |
| `paidCtr` | number \| null | Paid branded CTR % |
| `paidCtrDelta` | number \| null | pts |
| `whatMoved` | string | Narrative: what changed |
| `whyItMoved` | string | Narrative: why it changed |
| `categoryContext` | string | Narrative: category context |
| `competitiveShift` | string | Narrative: competitor movement |
| `recommendation` | string | Actionable recommendation |

**Null convention:** `null` means "not available for this period" — always from missing platform data, backfill limitation, or first-month baseline. Displayed as "—" in the UI.

---

### 3.3 Supporting Data Constants

| Constant | Type | Description |
|---|---|---|
| `MONTHS` | string[12] | Month labels: `["May '25", ..., "Apr '26"]` |
| `CAT_TRENDS` | number[12] | Primary category Trends index (from `RAW`) |
| `CAT_TRENDS_2` | number[12] | "luxury footwear" Trends index |
| `CAT_TRENDS_3` | number[12] | "designer shoes" Trends index |
| `SURVEYS` | object[] | Gold tier survey data (2 surveys: Jan '26, Apr '26) |
| `CAT_CONFIG` | object | Category term definitions, SEMrush terms, set date |
| `STATUS_CONFIG` | object | Status → color/bg/border map for all 4 status types |
| `B` | object | Brand color constants |

### 3.4 Survey Data Structure

```js
{
  monthIdx: 8,              // 0-indexed month position in RAW
  date: "Jan 2026",         // Display label
  fieldingDate: "...",      // Exact field window
  sampleSize: 800,
  audienceType: "Cold / prospective",
  source: "PDM Survey (Pollfish)",
  unaidedRecall: 12,        // %
  aidedAwareness: 38,       // %
  consideration: 24,        // %
  preference: 9             // %
}
```

Survey data **carries forward** — if the current month has no survey, the most recent prior survey is displayed with a staleness flag.

---

### 3.5 State

Managed by React `useState`. Three state variables:

| State | Initial | Description |
|---|---|---|
| `idx` | 11 | Currently selected month index (0–11). Defaults to latest (Apr '26). |
| `tier` | `"bronze"` | Active tier: `"bronze"`, `"silver"`, `"gold"` |
| `tab` | `"search"` | Active signal tab ID |

Tab list is derived via `useMemo` from `tier` and `idx` — it rebuilds when either changes. If the active tab is no longer in the derived tab list (e.g., switching from Gold → Bronze removes the `"awareness"` tab), the active tab resets to `"search"`.

---

## 4. Logic & Decision Trees

### 4.1 Signal Status Calculation

`calcDimStatus(dimId, d, prev)` — returns a status object `{ status, headline, factors[], method }` or `null` if no data available.

**Search Demand:**
1. Collect deltas: `[impressionsDelta, clicksDelta, trendsIdxDelta]` (filter nulls)
2. If `d.risingTide === true` → status = `"Watch"` (overrides count logic)
3. Count positives and negatives in the delta array
4. `pos >= 2` → `"Improving"`
5. `neg >= 2` → `"Declining"`
6. Otherwise → `"Stable"`

**Digital Presence:**
1. Count positives in `[directPctDelta, brandedOrganicDelta]`
2. Count negatives in same array
3. `pos >= 2` → `"Improving"`, `neg >= 2` → `"Declining"`, else → `"Stable"`

**Organic Social:**
1. If `followerGrowthRate === null` → return `null` (no data)
2. `erD = engagementRateDelta ?? 0`, `grD = followerGrowthRateDelta ?? 0`
3. `erD > 0 && grD >= 0` → `"Improving"`
4. `erD < 0 && grD < 0` → `"Declining"`
5. Either one negative → `"Watch"`
6. Else → `"Stable"`

**Competitive Position:**
1. `shareD = brandShareDelta ?? 0`
2. Calculate gap to nearest competitor; compare to prior month gap
3. `shareD >= 2` → `"Improving"`
4. `shareD <= -3` → `"Declining"`
5. `gapChg < -3` → `"Watch"`
6. Else → `"Stable"`

**Social Listening:**
1. If `mentionVol === null` → return `null`
2. `volUp = mentionVolDelta > 0`, `sentUp = sentimentDelta >= 0`
3. `volUp && sentUp` → `"Improving"`
4. `volUp && !sentUp` → `"Watch"` (volume up but quality declining)
5. `!volUp && !sentUp` → `"Declining"`
6. Else → `"Stable"`

**Paid Brand Efficiency:**
1. If `brandedCpmGoogle === null` → return `null`
2. `cpmDown = cpmGoogleDelta < 0`, `isUp = impressionShareDelta > 0`
3. `cpmDown && isUp` → `"Improving"`
4. `!cpmDown && !isUp` → `"Watch"`
5. Else → `"Stable"`

---

### 4.2 Survey Staleness

`getStaleness(surveyMonthIdx, currentMonthIdx)`:
- `monthsAgo = currentMonthIdx - surveyMonthIdx`
- `<= 1` → `"fresh"` (green)
- `<= 3` → `"amber"`
- `> 3` → `"stale"` (red)

`getSurveyForMonth(monthIdx)`:
- Find all surveys where `monthIdx <= currentMonthIdx`
- Return the last one (most recent at or before current month)
- Return `null` if none found

---

### 4.3 BVI Score Tier Adjustment

```js
adjustedBVI = isGold
  ? Math.min(100, d.bvi + 3)
  : isSilver
  ? Math.min(100, d.bvi + 1)
  : d.bvi
```

This is a **demo-only flat offset**. The production app calculates BVI from weighted dimension scores — Silver and Gold add more dimensions to the weighted average, naturally producing higher scores when those signals are healthy.

---

### 4.4 Tab Derivation

```js
const TABS = useMemo(() => {
  const base = [search, digital, social, competitive, category, methodology];
  if (isSilver) base.push(listening);
  if (isGold) {
    // compute staleness dot color for the tab
    base.push({ id: "awareness", dot: color });
  }
  return base;
}, [tier, idx, isSilver, isGold]);
```

If `tab` not in `tabIds` after rebuild → `activeTab = "search"`.

---

### 4.5 Sparkline Rendering

Two polylines in the mini sparkline on the score card:
1. Backfill months only (filtered from RAW)
2. Live months only
Current month: filled white circle, r=3.5px.
Category line: light purple, low opacity, dashed.

Main trend chart: same structure but larger, with additional features (connector line, rising tide ring, axis labels, month labels).

---

### 4.6 Rising Tide Flag

Pre-computed per month in `RAW` as a boolean. In the production app this would be computed from:
1. Brand Trends index moved in direction X
2. Primary category term moved in direction X
3. Category movement ≥ 50% of brand movement magnitude

In this demo artifact, `risingTide` is a hardcoded boolean per month object.

---

## 5. UI/UX Spec

### 5.1 Layout

- Max width: 1140px, centered, 20px padding all sides
- No sidebar — single-column scroll with section blocks
- Light theme (`#F5F5F5` body background)
- All component backgrounds: white (`#FFFFFF`) or off-white (`#F5F5F5`)
- Score card: purple (`#7756FF`)
- Dark recommendation card: near-black (`#2B2A29`)

### 5.2 Brand Colors

| Token | Hex | Usage |
|---|---|---|
| `B.purple` | `#7756FF` | Primary, score card bg, active states, data bars |
| `B.lightPurple` | `#AFAAF9` | Secondary, sparkline, category lines, Silver tier |
| `B.nearBlack` | `#2B2A29` | Body text, recommendation card bg |
| `B.offWhite` | `#F5F5F5` | Page background, inner panels |
| `B.white` | `#FFFFFF` | Card backgrounds |
| `B.gray` | `#ABABAB` | Secondary text, borders, chart gridlines |
| `B.yellow` | `#E3FF43` | Gold tier accent, rising tide indicator, recommendation label |

Status colors:
- Improving: text `#0F6E56`, bg `#E1F5EE`, border `#5DCAA5`
- Stable: text `#5F5E5A`, bg `#F1EFE8`, border `#B4B2A9`
- Declining: text `#C0392B`, bg `#FDECEA`, border `#F09595`
- Watch: text `#BA7517`, bg `#FAF0DA`, border `#FAC775`

### 5.3 Typography

All text: `'Darker Grotesque', Arial, Helvetica, sans-serif`
Imported from Google Fonts in `<head>`: weights 400, 600, 700.

Font sizes used:
- 58px: BVI score (score card)
- 28px: Awareness metric values
- 24px: Stat values (methodology)
- 22px: MetricCard values
- 20px: Header brand name
- 14–16px: General body, labels
- 11–13px: Subtitles, descriptions, tab content prose
- 9–10px: Labels, tooltips, footnotes, chart axes

### 5.4 Components

**MetricCard**
- Props: label, value, delta, suffix, tooltip, inverse, accent, sub
- `accent=true` → purple background (used for BVI card child)
- `inverse=true` → lower = better (position)
- Tooltip: `?` circle; hover shows floating text bubble above
- Delta badge: up arrow green, down arrow red, flat arrow gray

**Delta**
- Inline component
- Positive (or negative if inverse=true) → green bg/text
- Zero → gray
- Null/undefined → "—" in gray

**Tooltip**
- Hover-only, no click required
- Absolute positioned, 240px max width, dark bg
- Arrow pointer below tooltip bubble
- Z-index 999

**DimRow (Signal Status)**
- Click to toggle expansion
- Expansion shows: factors table + methodology note
- Factors table: label, optional note, value (green or red based on `positive`)
- Locked state: `opacity: 0.38`, no click handler, tier badge shown
- "No data" state: same opacity, "No data" text

**CompRow (Competitor)**
- Rank, name, Trends index /100, SEMrush volume
- Horizontal bar: proportional to `(trendsIdx / 70) * 100%`
- Client brand: purple bold

**TrendChart**
- SVG, responsive via viewBox
- Fixed internal dimensions: 620×170, padding L:32 R:12 T:14 B:22
- Y range: 38–78 (displayed grid lines at 45, 55, 65)

### 5.5 States

**Empty/unavailable states:**
- Backfill month → social, listening, survey tabs show centered "no data" message
- No survey yet → Direct Awareness tab shows "No survey data yet"

**Loading states:**
- None. All data is synchronous/hardcoded. No loading spinners exist.

**Error states:**
- None defined. No network calls in this artifact.

**Transition states:**
- Tier toggle: instant re-render, no animation
- Tab switch: instant, no animation
- DimRow expand/collapse: chevron rotates 180° via CSS `transform: rotate` with 0.2s transition
- Bar charts: `transition: width 0.3s–0.4s ease` on some horizontal bars

---

## 6. Technical Implementation

### 6.1 Tech Stack

| Layer | Technology |
|---|---|
| Markup | HTML5 |
| Styling | Inline styles (no CSS classes, no stylesheet beyond global reset) |
| JS runtime | Babel Standalone (transpiles JSX in the browser) |
| UI framework | React 18 (UMD build via unpkg CDN) |
| Rendering | ReactDOM.createRoot |
| Charts | Hand-coded SVG (no chart library) |
| Fonts | Google Fonts CDN |
| Build | None — single HTML file, no bundler, no build step |

### 6.2 CDN Dependencies

```html
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
```

All loaded from unpkg. Requires internet access to load. If offline, file will not render (React and Babel will be undefined).

### 6.3 React Usage Pattern

All components are plain function declarations — **no `export default`**. This is intentional: Babel Standalone in a single HTML file does not support ES module syntax. `export default` causes a silent render failure.

Hooks used: `useState`, `useMemo`. No `useEffect`, no `useRef`, no context.

### 6.4 Script Tag

```html
<script type="text/babel">
  // All component and app code lives here
</script>
```

Babel Standalone intercepts `type="text/babel"` scripts and transpiles JSX before execution.

### 6.5 Storage

**None.** No `localStorage`, no `sessionStorage`, no cookies, no Claude artifact storage API, no API calls of any kind. This is a fully static display artifact.

### 6.6 Performance Notes

- Babel Standalone transpiles ~850 lines of JSX in the browser on every load. First render is slightly slower than a pre-compiled bundle (typically <1s on modern hardware).
- All 12 months of data are in memory at all times — trivial footprint (~50KB of JS data).
- SVG charts are re-rendered on every state change. At 12 data points each, this is not a performance concern.

### 6.7 File Size

~850 lines, ~95KB unminified HTML. Fully self-contained.

---

## 7. Known Limitations & Assumptions

### 7.1 What It Explicitly Doesn't Do

- **No data ingestion.** Users cannot upload files. All data is hardcoded. The upload flow, parsers, and scoring engine live in a separate artifact (the BVI App, in active development).
- **No persistent storage.** Refreshing the page resets to month 11 (Apr '26) at Bronze tier.
- **No Claude API calls.** Narratives (`whatMoved`, `whyItMoved`, etc.) are pre-written strings in the data object. The production app calls Claude API once per month to generate these.
- **No PDF/export.** There is no "download report" or "export PDF" function.
- **No multi-client support.** Hardcoded to Kurt Geiger London. One client only.
- **No Silver or Gold data-ingestion logic.** Silver/Gold data (Meltwater, paid, survey) is also hardcoded. The toggle is a demo mode, not a real tier unlock.
- **No offline support.** Requires CDN access for React and Babel.
- **No mobile layout.** Built for desktop viewport (minimum ~1000px wide). Below that, content wraps imperfectly.

### 7.2 Hardcoded Assumptions

- Client: Kurt Geiger London
- Competitors: Steve Madden, Carvela, Ted Baker
- Category terms: "women's shoes", "luxury footwear", "designer shoes"
- Tracking window: May 2025 – April 2026 (12 months)
- Backfill: May '25 – Dec '25 (8 months), Live: Jan '26 – Apr '26 (4 months)
- Social data only available from Jan '26 (90-day native platform limit)
- Primary category term for rising tide and chart = "women's shoes"
- Surveys fielded in Jan '26 (n=800) and Apr '26 (n=850)

### 7.3 Demo-Specific Simplifications

- **BVI tier adjustment is a flat offset** (+1 Silver, +3 Gold), not a proper weighted average recalculation.
- **Status calculations** (`calcDimStatus`) use the pre-delta values from the current data object, but do not re-derive deltas from the raw signal arrays — they trust the pre-computed delta fields in `RAW`.
- **Upsell buttons** (`Add Silver tier ↗`, `Add Gold tier ↗`) have no wired action.
- **`bvi-why-brand-measurement-matters.html` link** in the Methodology tab opens a separate companion file — not bundled in this artifact.

### 7.4 Open Questions (for production app)

- Volume-adjusted MoM scoring: does a 15% MoM change on 10K impressions score the same as 15% on 2M impressions? Parked for Tim/Austin review.
- Social data historical backfill: 90-day limit on platform exports means social scores will always start blank and accumulate forward.
- SEMrush ingestion: currently manual entry in v1. CSV parser planned for v2.

---

## 8. Rebuild Instructions

### 8.1 If Starting From Scratch

A developer handed this spec should be able to rebuild the artifact with the following approach:

**1. File structure**
Single `.html` file. Head contains: charset, viewport, Google Fonts import (Darker Grotesque 400/600/700), CDN scripts for React 18, ReactDOM 18, Babel Standalone, global CSS reset (box-sizing, margin/padding 0). Body: `<div id="root">`. Script tag with `type="text/babel"`.

**2. Data layer**
Declare all data as `const` at the top of the Babel script block:
- `B` object with all brand color tokens
- `MONTHS` array (12 strings)
- `RAW` array (12 objects, one per month — see Section 3.2 for all fields)
- `CAT_TRENDS_2`, `CAT_TRENDS_3` arrays (secondary category term trend lines)
- `SURVEYS` array (2 survey objects — see Section 3.3)
- `CAT_CONFIG` object (term definitions, roles, set date)
- `STATUS_CONFIG` object (status → colors)

**3. Utility components (build first)**
- `Tooltip` — hover tooltip wrapper
- `Delta` — MoM delta badge (positive/negative/neutral/null)
- `MetricCard` — labeled metric tile with value and delta

**4. Chart components**
- `TrendChart` — full 12-month BVI + category SVG chart
- Inline SVG in `CategoryTab` for brand vs. category terms

**5. Helper functions**
- `getSurveyForMonth(monthIdx)` — returns latest survey at or before idx
- `getStaleness(surveyMonthIdx, currentMonthIdx)` — returns "fresh"/"amber"/"stale"
- `calcDimStatus(dimId, d, prev)` — see Section 4.1 for full logic per dimension

**6. Tab content components**
Build each as a pure display component receiving `d` (current month data) and `prev` (prior month) as props:
- `SearchTab`, `DigitalTab`, `SocialTab`, `CompTab`, `CategoryTab`
- `ListeningTab`, `DirectAwarenessTab`, `MethodologyTab`
- `UpsellCard` (single card)

**7. Signal status components**
- `CompRow` — competitor list row
- `DimRow` — expandable signal status row (calls `calcDimStatus` internally)

**8. Main App component**
Three `useState` calls: `idx` (11), `tier` ("bronze"), `tab` ("search").
`useMemo` for TABS array (derives from tier + idx).
Guard: if `tab` not in `tabIds`, reset to `"search"`.
Render: header, tier toggle, month nav, backfill banner (conditional), summary panel (BVI card + narrative grid), trend chart, signal status + competitive position row, signal tab bar + tab content, upsell section (conditional).

**9. Mount**
```js
ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
```

### 8.2 Critical Rules for the Rebuild

1. **No `export default`.** Babel Standalone in a script tag does not support ES modules. Use plain `function ComponentName()` declarations.
2. **No curly/smart quotes in JS.** Use ASCII straight quotes only (`'` and `"`). Smart quotes (`'`, `'`, `"`, `"`) silently break Babel parsing.
3. **No external style libraries.** All styling is inline `style={{}}` on JSX elements. Tailwind, Bootstrap, and CSS modules are not used and should not be introduced.
4. **No `import` statements.** Everything is globally available via UMD CDN scripts (`React`, `ReactDOM`). Destructure from `React` at the top: `const { useState, useMemo } = React;`
5. **`null` means no data.** Fields are null when the platform doesn't provide data for that period. Never substitute 0 for null — it would produce misleading delta calculations.
6. **SVG charts are hand-coded.** Do not introduce Recharts, Chart.js, or D3 — they require bundled builds and won't work in this single-file Babel context without significant setup.

### 8.3 What to Keep Identical in a Rebuild

- All PDM brand color tokens (`B.*`)
- All signal status color tokens (`STATUS_CONFIG`)
- Font family and all import weights
- Status calculation logic in `calcDimStatus` (exact thresholds match the BVI Scoring Spec v1.2)
- Staleness thresholds for surveys (≤1 month = fresh, ≤3 months = amber, >3 = stale)
- Rising tide visual treatment (yellow-green ring on sparkline dot)
- Tab derivation logic (Silver adds listening, Gold adds awareness with staleness dot)
- Backfill banner condition and wording
- Upsell card conditional logic (show when not Gold, show appropriate tier cards)

---

*End of specification. Source of truth for BVI scoring logic: `BVI_Scoring_Spec_v1_2.txt`. Source of truth for PDM brand application: `pdm-brand-guidelines` skill.*
