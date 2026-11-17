# Power BI build guide

How to build the report on top of the SQL Server tables. Allow 2-4 sessions. Build it yourself and make the design calls your own: in interviews you'll be asked why each visual is there.

**Files in this folder**
- `measures.dax`: every DAX measure, with comments
- `xsbi-theme.json`: report theme (colours, fonts)
- this guide, including expected values to check your numbers against

---

## 1. Load the data

1. Run the pipeline first: `python run_pipeline.py`.
2. Power BI Desktop  **Get data  SQL Server**. Server `localhost` (or your instance name), database `XSBI`, **Import** mode.
3. Select `xsbi.DimCountry`, `xsbi.DimDate`, `xsbi.DimMetric`, `xsbi.DimSegment`, `xsbi.FactMetric`  **Load**. Skip the views and `LoadLog`.
4. Rename the tables to drop the `xsbi ` prefix (e.g. `FactMetric`). `measures.dax` uses these names.

## 2. Relationships (Model view)

Create four relationships, all **many-to-one, single direction**, fact  dimension:

| From (many) | To (one) |
|---|---|
| `FactMetric[DateKey]` | `DimDate[DateKey]` |
| `FactMetric[SegmentKey]` | `DimSegment[SegmentKey]` |
| `FactMetric[MetricKey]` | `DimMetric[MetricKey]` |
| `FactMetric[CountryKey]` | `DimCountry[CountryKey]` |

**Delete any relationship Power BI auto-creates between `DimSegment` and `DimCountry`.** With it, country filters could reach the fact table by two paths (ambiguous model). For NZ-only pages, filter on `DimSegment[CountryCode]`; for the comparison page, use `DimCountry[CountryName]`.

## 3. Table settings

- `DimDate`: **don't mark it as a date table.** It has one row per month (XSBI is monthly) and Power BI requires every calendar day. No measure needs it: they set their own date ranges. Sort `YearMonth` by `YearMonthSort`.
- Turn off **Auto date/time**: File  Options and settings  Options  Current file  Data Load. On line charts, use `DimDate[Date]` with the X axis type set to **Continuous**.
- `DimMetric`: sort `MetricName` by `SortOrder`. Check `HigherIsBetter` loaded as **True/False**.
- Hide all key columns (`*Key`), `SortOrder`, `YearMonthSort`, and `FactMetric[Value]` (so every visual uses the measures).
- Set **Summarize by: None** on numeric dimension columns (`Year`, `Quarter`, `MonthNumber`).

## 4. Measures

1. **Home  Enter data**, name the table `_Measures`, load it (one empty column is fine; delete it after adding a measure).
2. Add each measure from `measures.dax`. Put them in display folders matching the comments (Core, Latest vs 2019, Cash flow, Jobs, Formatting).
3. Formats:
   - `Value`, `Value 3M Avg`, `Latest 3M Avg`, `Avg 2019`, `Net Job Creators`: decimal, 1 place.
   - `Change vs 2019`, `Change vs 2019 (Better +)`, `Sales Change vs 2019`, `Late Days Change vs 2019`: custom format `+0.0;-0.0;0.0`.

**Why every measure averages:** XSBI values are growth rates, days and shares of firms, not amounts. Summing them is meaningless, and averaging across regions is unweighted (Xero doesn't publish region sizes). Say so in the report notes and in interviews.

## 5. Theme

**View  Themes  Browse for themes**  `xsbi-theme.json`.

## 6. Pages

Page filter on pages 1-4: `DimSegment[CountryCode] = NZ`. Add a card with `[Source Note]` at the bottom of every page (licence requirement and good practice).

### Page 1: National overview
*Question: how are NZ small businesses doing compared with before COVID?*
- **Page filter:** `DimSegment[SegmentType] = National`.
- **Five cards** (Sales growth, Jobs growth, Wages growth, Time to be paid, Late payments): each a card with `[Latest 3M Avg]`, filtered to one metric, with `[Change vs 2019]` as a subtitle or a second card. Font colour: conditional formatting  field value  `[Colour Change vs 2019]`.
- **Line chart:** X = `DimDate[Date]`, Y = `[Value 3M Avg]`, legend = `DimMetric[MetricName]`, filter metrics to Sales, Jobs, Wages growth. Add a constant line at 0.
- **Line chart:** `[Net Job Creators]` by month: hiring momentum in one line.

### Page 2: Regions
*Question: which regions are recovering?*
- **Page filter:** `SegmentType = Region`.
- **Matrix (heatmap):** rows = `SegmentName`, columns = `MetricName`, values = `[Change vs 2019]`. Background colour  field value  `[Colour Change vs 2019]`. This is the page's main visual.
- **Bar chart:** `[Latest 3M Avg]` by region with a metric slicer.
- Note: Power BI's built-in maps won't reliably place "Marlborough & Nelson & Tasman". A matrix reads better anyway; a Shape Map with a Stats NZ regional TopoJSON file is an optional extra later.

### Page 3: Industries
*Question: which industries are growing, and which are hiring?*
- **Page filter:** `SegmentType = Industry`.
- **Matrix heatmap:** rows = industries, columns = `DimDate[QuarterLabel]` (last 8 quarters), values = `[Value]` for Sales growth. Background colour scale: diverging, centre 0.
- **Bar chart:** `[Net Job Creators]` by industry, latest quarter.

### Page 4: Cash-flow stress (the key insight page)
*Question: where are small businesses selling less and being paid later than before COVID?*
- **Scatter chart:** X = `[Sales Change vs 2019]`, Y = `[Late Days Change vs 2019]`, values (details) = `SegmentName`, legend = `SegmentType`. Add X and Y constant lines at 0 (Analytics pane). Top-left quadrant = stress.
- **Table:** `SegmentName`, `SegmentType`, `[Sales Change vs 2019]`, `[Late Days Change vs 2019]`, `[Cash Flow Status]` with font colour from `[Colour Cash Flow Status]`; sort by `[Cash Flow Status Sort]`.
- **Text box:** your written finding (see section 7).

### Page 5: International comparison
*Question: how does NZ compare with Xero's other four markets?*
- **No country page filter.** Filter `SegmentType = National`.
- **Metric slicer** (single select): `DimMetric[MetricName]`. Only Sales growth, Time to be paid and Late payments exist for all five countries; Jobs and Wages cover NZ, AU and UK only. Say so in a subtitle.
- **Line chart:** X = `Date`, Y = `[Value 3M Avg]`, legend = `DimCountry[CountryName]`. Highlight NZ (format  series colours).
- **Bar chart:** `[Latest 3M Avg]` by country, sorted.

## 7. Check your numbers

If your report matches these, the model and measures are right. Latest = Jul-Sep 2026 average; change = vs 2019 average.

**NZ national**

| Metric | Latest 3M avg | Change vs 2019 |
|---|---|---|
| Sales growth (% y/y) | 5.6 | +0.1 |
| Jobs growth (% y/y) | 2.5 | +0.2 |
| Wages growth (% y/y) | 1.3 | -2.5 |
| Time to be paid (days) | 25.4 | -1.1 |
| Late payments (days) | 5.2 | -2.6 |
| Job creators (% of firms) | 30.7 | -5.7 |
| Job downsizers (% of firms) | 26.2 | -1.0 |

**NZ cash-flow status** (threshold: 1 point / 1 day)

| Status | Regions | Industries |
|---|---|---|
| Stress | Hawke's Bay (sales -3.8, late +2.1 days) | none |
| Watch | Marlborough & Nelson & Tasman (sales -3.3), Wellington (sales -2.6), Taranaki (sales -1.9) | Health Care and Social Assistance (late +4.6 days), Other Services (sales -4.2), Administrative and Support Services (sales -1.5), Professional, Scientific and Technical Services (sales -1.2) |
| OK | the other 8 | the other 6 |

**International, latest 3M avg**

| Country | Sales growth (% y/y) | Late payments (days) | Time to be paid (days) |
|---|---|---|---|
| New Zealand | 5.6 | 5.2 | 25.4 |
| Australia | 5.2 | 6.9 | 24.3 |
| United States | 4.3 | 8.6 | 29.7 |
| United Kingdom | 4.0 | 8.0 | 29.5 |
| Canada | 2.0 | 10.5 | 28.4 |

## 8. Story leads for the write-up

Starting points to investigate and put in your own words, not conclusions:
- **Sales have recovered, wages haven't.** NZ sales growth is back at its 2019 pace, but wage growth is 2.5 points below it, and the share of firms adding staff is down 5.7 points.
- **Hawke's Bay is the one region under real cash-flow stress.** What else happened there? (Look for local factors before claiming a cause.)
- **Health care is being paid much later** than in 2019 (+4.6 days) while every other industry is paid faster. Who are its customers?
- **NZ leads Xero's five markets** on sales growth and has the shortest late payments.

## 9. Finish

- Save as `powerbi/XSBI Small Business Health.pbix`.
- Export a screenshot of each page to `powerbi/screenshots/` for the GitHub README.
- Note in the README which findings you investigated and what you concluded.

