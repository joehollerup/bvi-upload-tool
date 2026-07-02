# BVI CSV Schema Mapping Spec v1.0

**Power Digital Marketing — Confidential**
Last updated: June 2026

This document maps raw platform CSV exports to the internal schema required by the BVI Scoring Spec v1.1. It is the normalization layer reference for the Phase 1 build. Any CSV parser built for BVI must follow these rules exactly.

---

## 1. Source File Inventory (Bronze Tier)

| Source | File format | Granularity | Months available (Keen test) | Spec reference |
|---|---|---|---|---|
| GSC ZIP | ZIP containing Chart.csv + Queries.csv + others | Daily (Chart), Aggregate (Queries) | Feb 2025 – May 2026 (16 months) | Section 4.1 Search Demand |
| Google Trends Export 1 | CSV | Monthly | Oct 2024 – May 2026 (20 months) | Section 4.1 + 4.4 Competitive Position |
| Google Trends Export 2 | CSV | Monthly | Oct 2024 – May 2026 (20 months) | Section 4.5 Category Context |
| GA4 Traffic Acquisition | CSV | Aggregate (no monthly breakdown in standard export) | Single month or full-range aggregate | Section 4.2 Digital Presence |
| Instagram | CSV (daily rows from social reporting tool) or manual entry | Daily | Jan 2025 – May 2026 (509 rows) | Section 4.3 Organic Social |
| TikTok | CSV (daily rows from social reporting tool) or manual entry | Daily | Jan 2025 – May 2026 (509 rows) | Section 4.3 Organic Social |

---

## 2. GSC ZIP

### 2.1 File detection

The upload is a ZIP file. Extract and look for `Chart.csv` and `Queries.csv`. Ignore `Pages.csv`, `Countries.csv`, `Devices.csv`, `Search appearance.csv`, and `Filters.csv`.

### 2.2 Chart.csv

**Raw schema:**

```
Date,Clicks,Impressions,CTR,Position
2025-02-01,6633,348736,1.9%,29.8
```

- `Date`: YYYY-MM-DD, one row per day
- `Clicks`: integer
- `Impressions`: integer
- `CTR`: string with `%` suffix (e.g., "1.9%"). Strip `%` and parse as float.
- `Position`: float

**Transformation: aggregate to monthly**

Group rows by YYYY-MM. Per month:
- `monthly_clicks` = SUM(Clicks)
- `monthly_impressions` = SUM(Impressions)
- `monthly_ctr` = monthly_clicks / monthly_impressions (derive, do not average the daily CTR)
- `monthly_avg_position` = AVERAGE(Position) weighted by Impressions

These are TOTAL clicks/impressions, not branded. Branded metrics require the share calculation from Queries.csv.

### 2.3 Queries.csv

**Raw schema:**

```
Top queries,Clicks,Impressions,CTR,Position
keen,637219,5986112,10.64%,2.9
keen shoes,270011,1646408,16.4%,2.4
```

- One aggregate row per query (no date dimension, covers entire export date range)
- Used once to calculate `branded_share`

**Branded share calculation (per Spec Section 4.1):**

1. Classify queries as branded or non-branded. A query is branded if it contains the brand name or common misspellings/abbreviations (e.g., "keen", "keens", "keen shoes", "keen footwear", "keen boots", "keen sandals", etc.)
2. `branded_clicks` = SUM(Clicks) for branded queries
3. `total_clicks` = SUM(Clicks) for ALL queries
4. `branded_share` = branded_clicks / total_clicks
5. Apply branded_share to each month: `monthly_branded_clicks` = monthly_clicks * branded_share
6. Same for impressions: `monthly_branded_impressions` = monthly_impressions * branded_share

**Brand name detection heuristic:**

The parser needs the client's brand name as a configuration input. Match queries where:
- Query starts with brand name (case-insensitive)
- Query contains brand name as a full word
- Query matches known variants (provide a variants list per client at onboarding)

For Keen: "keen", "keens", "keen shoes", "keen boots", "keen sandals", "keen footwear", "keen usa", "keen utility", "keen work boots", "keen hiking", "keen jasper", "keen uneek", "keen targhee", "keen newport", etc.

### 2.4 Internal schema output (Search Demand - GSC portion)

Per month, produce:

| Internal field | Source | Type |
|---|---|---|
| `branded_impressions` | monthly_impressions * branded_share | integer |
| `branded_clicks` | monthly_clicks * branded_share | integer |
| `branded_ctr` | branded_clicks / branded_impressions | float (percentage) |
| `avg_position` | weighted average from Chart.csv | float |

---

## 3. Google Trends Export 1 (Brand vs Competitors)

### 3.1 Raw schema

```
"Time","KEEN","Sorel","Salomon","red wing","brunt"
"2024-10-01",41,20,26,33,14
```

- First column: `Time`, format YYYY-MM-DD (always first of month)
- Remaining columns: brand name strings, values are Trends index 0-100
- First column after Time is assumed to be the client brand (configurable)
- Remaining columns are competitors

**No transformation needed.** Data is already monthly. Strip quotes from headers. Parse values as integers.

### 3.2 Internal schema output

Per month, produce:

| Internal field | Source | Type |
|---|---|---|
| `brand_trends_idx` | Client column value | integer |
| `competitor_trends` | Array of {name, index} for each competitor | object[] |
| `brand_trends_share` | brand_idx / SUM(all indices) * 100 | float |
| `nearest_competitor_idx` | MAX of competitor indices | integer |
| `nearest_competitor_name` | Name of competitor with highest index | string |
| `brand_vs_nearest_gap` | brand_idx - nearest_competitor_idx | integer |

### 3.3 Parsing notes

- Google Trends sometimes exports `<1` for very small values. Treat as 0.
- Values can be 0. Do not treat 0 as null.
- The header row may contain quotes. Strip them.
- Column order may vary. First data column = client brand. This must be configurable.

---

## 4. Google Trends Export 2 (Brand vs Category Terms)

### 4.1 Raw schema

```
"Time","KEEN","Hiking Boots","Work Boots","trail running"
"2024-10-01",37,19,37,11
```

Identical format to Export 1. Difference is the comparison columns are category terms, not competitor brands.

### 4.2 Internal schema output

Per month, produce:

| Internal field | Source | Type |
|---|---|---|
| `brand_trends_idx_cat` | Client column value | integer |
| `primary_cat_idx` | Primary category term value (configurable) | integer |
| `secondary_cat_indices` | Array of other category term values | integer[] |
| `brand_vs_primary_cat_gap` | brand_idx - primary_cat_idx | integer |
| `rising_tide` | Boolean, see detection logic below | boolean |

### 4.3 Rising tide detection (per Spec Section 4.5)

Requires current and prior month data. `risingTide = TRUE` when EITHER:

1. Brand index increased MoM AND primary category term increased MoM AND category increase >= 50% of brand increase
2. Brand index decreased MoM AND primary category term decreased MoM AND category decrease >= 50% of brand decrease

### 4.4 Configuration required

- Which column is the primary category term (for rising tide detection and Section 4.5 scoring)
- Client brand column (first data column by default)

---

## 5. GA4 Traffic Acquisition

### 5.1 The GA4 problem

GA4 standard Traffic Acquisition exports have no built-in monthly dimension. The export covers whatever date range is set in the GA4 UI. This creates three possible file shapes:

**Shape A: Full-range aggregate (what Keen originally uploaded)**
- One row per channel, no date column
- Covers 16+ months of data summed together
- Useless for MoM scoring
- Must be detected and rejected with a clear error message

**Shape B: Single-month export (what Keen corrected to)**
- One row per channel, no date column
- Date range metadata in the CSV header comments
- One file per month
- Workable, but requires 12-16 separate uploads for backfill

**Shape C: Exploration export with Year-month dimension (what Jon tried to enable)**
- Rows per channel per month
- Has a `Year month` column (values like `202504`)
- Single file covers all months
- Ideal but harder for end users to pull

### 5.2 Raw schema (Shape B, standard report)

```
# ----------------------------------------
# Traffic acquisition: Session primary channel group (Default Channel Group)
# Account: KEEN Footwear
# Property: 01 KEEN United States - GA4 
# ----------------------------------------
# 
# All Users
# Start date: 20260501
# End date: 20260531
Session Awin - CPA_Channel_Expanded_w_Audio_video_awin,Active users,Sessions,...
Direct,832710,891885,...
Organic,248269,347923,...
```

**Header parsing:**
- Lines starting with `#` are metadata comments
- Extract `Start date` and `End date` from comments (format: YYYYMMDD)
- Derive the target month from these dates
- The first non-comment line is the column headers

**Column header issue:**
The first column name varies by GA4 property configuration:
- Standard: `Session default channel group`
- Custom (Keen): `Session Awin - CPA_Channel_Expanded_w_Audio_video_awin`

The parser must accept ANY first column header. It's always the channel grouping column regardless of name.

### 5.3 Channel name mapping

GA4 channel group names need mapping to the two the spec cares about:

| GA4 channel name | Internal field | Notes |
|---|---|---|
| `Direct` | `direct_sessions` | Always present |
| `Organic Search` OR `Organic` | `organic_sessions` | Name varies by channel grouping |
| Grand total row OR SUM of all rows | `total_sessions` | See below |

**Grand total detection:**
- Some GA4 exports include a summary row. It may be labeled "Grand total", "(other)", or simply be absent.
- If no grand total row exists, SUM all channel rows for total_sessions.
- Per Spec Section 4.2: "Use the Grand Total row... Do not sum named channels" but this only works if the export includes it. Fallback: sum all rows.

**Critical: the column we need is `Sessions` (3rd column in Keen's export).** Not Active users, not Engaged sessions.

### 5.4 Internal schema output

Per month, produce:

| Internal field | Source | Type |
|---|---|---|
| `direct_sessions` | Sessions value from "Direct" row | integer |
| `organic_sessions` | Sessions value from "Organic" / "Organic Search" row | integer |
| `total_sessions` | Grand total or SUM of all channel Sessions | integer |
| `direct_pct` | direct_sessions / total_sessions * 100 | float |

### 5.5 Multi-month handling strategy

For Phase 1, support Shape B (single-month exports) with month derived from header metadata. Require one upload per month. This is the path of least resistance and matches what Jon already simplified to.

Phase 2: add Shape C support (Exploration export with Year-month column).

---

## 6. Instagram (CSV from social reporting tool)

### 6.1 Raw schema

```
"Date","Instagram Profile","Followers","Net Follower Growth","Followers Gained","Followers Lost","Following","Net Following Growth","Published Posts","Views","Organic Views","Paid Views","Reach","Reels Video Views","Engagements","Organic Engagements","Paid Engagements","Likes","Organic Likes","Paid Likes","Comments","Organic Comments","Paid Comments","Shares","Organic Shares","Paid Shares","Saves","Organic Saves","Paid Saves","Story Replies","Engagement Rate (per View)","Organic Engagement Rate (per View)","Paid Engagement Rate (per View)"
"01-01-2025","keen","295,379","12",...
```

- `Date`: MM-DD-YYYY format (quoted). Parse carefully: "01-01-2025" = January 1, 2025.
- All numeric values are quoted strings with comma formatting (e.g., "295,379"). Strip commas and quotes before parsing.
- One row per day.

### 6.2 Transformation: aggregate to monthly

Group rows by YYYY-MM derived from Date. Per month:

| Internal field | Aggregation | Source column |
|---|---|---|
| `ig_followers_eom` | LAST value in month | `Followers` |
| `ig_net_follower_growth` | SUM | `Net Follower Growth` |
| `ig_organic_reach` | SUM | `Reach` (use total Reach, or `Organic Views` if organic-only needed) |
| `ig_engagement_rate` | Derive: SUM(Organic Engagements) / SUM(Organic Views) * 100 | Calculated |

**Note on engagement rate:** Do not average daily engagement rates. Derive from monthly totals of engagements and views for accuracy.

**Note on reach vs views:** The spec says "organic reach" for the social dimension. The CSV has both `Reach` and `Organic Views`. Use `Reach` as the primary field (it represents unique accounts reached). If the spec intends impressions/views, use `Organic Views`.

### 6.3 Follower growth rate

`follower_growth_rate` = ig_net_follower_growth / ig_followers_start_of_month * 100

Where `ig_followers_start_of_month` = previous month's `ig_followers_eom` (or first day's `Followers` value for the first month).

---

## 7. TikTok (CSV from social reporting tool)

### 7.1 Raw schema

```
"Date","TikTok Profiles","Published Posts","Net Follower Growth","Followers","Video Views","Impressions","Engagements","Engagement Rate (per Impression)","Likes","Comments","Shares","Profile Views"
"01-01-2025","'@keenfootwear","0","5","16,096","2,856","2,856","17","0.6%",...
```

- Same date format as Instagram: MM-DD-YYYY
- Same comma-formatted quoted numbers
- `Engagement Rate (per Impression)` has `%` suffix

### 7.2 Transformation: aggregate to monthly

| Internal field | Aggregation | Source column |
|---|---|---|
| `tt_followers_eom` | LAST value in month | `Followers` |
| `tt_net_follower_growth` | SUM | `Net Follower Growth` |
| `tt_organic_views` | SUM | `Video Views` |
| `tt_engagement_rate` | Derive: SUM(Engagements) / SUM(Impressions) * 100 | Calculated |

### 7.3 Follower growth rate

Same formula as Instagram: `follower_growth_rate` = tt_net_follower_growth / tt_followers_start_of_month * 100

---

## 8. Combined Social Scoring (per Spec Section 4.3)

If both Instagram and TikTok data are present, average the platform signals before scoring:

- `combined_engagement_rate` = (ig_engagement_rate + tt_engagement_rate) / 2
- `combined_follower_growth_rate` = (ig_follower_growth_rate + tt_follower_growth_rate) / 2
- `combined_organic_reach_growth` = derived from MoM change in (ig_organic_reach + tt_organic_views)

If only one platform: use that platform's values. Flag: "Organic Social scored on [platform] only."

---

## 9. Configuration Object (per client)

Every BVI scoring run requires a client configuration:

```json
{
  "client_name": "KEEN",
  "brand_query_terms": ["keen", "keens", "keen shoes", "keen boots", "keen sandals", "keen footwear"],
  "trends_export_1": {
    "client_column": "KEEN",
    "competitors": ["Sorel", "Salomon", "red wing", "brunt"]
  },
  "trends_export_2": {
    "client_column": "KEEN",
    "primary_category_term": "Hiking Boots",
    "category_terms": ["Hiking Boots", "Work Boots", "trail running"]
  },
  "ga4": {
    "direct_channel_name": "Direct",
    "organic_channel_name": "Organic"
  },
  "scoring_months": "2025-02 to 2026-05"
}
```

**Note:** Keen's GA4 uses "Organic" not "Organic Search" because of their custom channel grouping. The parser must match flexibly.

---

## 10. Known Gotchas from Keen Test

1. **GA4 custom channel grouping** changes column 1 header AND channel row names. Parser must not hardcode either.
2. **Instagram/TikTok dates** use MM-DD-YYYY, not YYYY-MM-DD. Easy to misparse.
3. **Comma-formatted numbers** in social CSVs ("295,379") will parse as strings. Strip commas before parseInt.
4. **CTR and engagement rate fields** have `%` suffix. Strip before parsing.
5. **Quoted fields** throughout social and Trends CSVs. Strip quotes.
6. **GSC Chart.csv CTR** is a string with `%`. Derive CTR from clicks/impressions instead.
7. **First month always scores 55** per spec. This is correct behavior, not a bug. The tool must clearly label it "Baseline."

---

## 11. Validation Checklist (per file)

Before scoring, validate:

| Check | Action if failed |
|---|---|
| GSC ZIP contains Chart.csv and Queries.csv | Reject with "GSC ZIP missing required files" |
| Chart.csv has >= 2 months of daily data | Warn "Only 1 month of GSC data: baseline only, no MoM scoring possible" |
| GA4 CSV header contains Start date / End date | Reject with "Cannot determine GA4 date range" |
| GA4 has "Direct" channel row | Reject with "GA4 export missing Direct channel" |
| GA4 has organic channel row (fuzzy match) | Warn "Organic channel not found, Digital Presence partially scored" |
| Trends Export 1 has >= 2 months | Warn if only 1 month |
| Trends Export 1 first data column matches client config | Warn "Client brand column not found in Trends Export 1" |
| Social CSV has >= 2 months of daily data | Warn if only 1 month |
| All numeric fields parse correctly after cleanup | Reject rows that fail, log count of rejected rows |

---

## 12. File Manifest for Claude Code Build

The following files form the complete BVI build specification:

| File | Purpose |
|---|---|
| `BVI_Scoring_Spec_v1_1.txt` | Scoring logic, weights, scales, flags (source of truth for all calculations) |
| `BVI_Dashboard_v3_Spec.md` | UI/UX spec, component architecture, rebuild instructions (target output) |
| `BVI_CSV_Schema_Mapping_v1.md` | This document. CSV normalization rules (data input layer) |
| `bvi-demo-gold-unlocked.html` | Reference HTML artifact (visual target, dummy data) |
| Keen test CSVs (7 files) | Real-world test data for validation |

---

*End of schema mapping spec.*
