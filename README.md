# Wolt Reports

This repository contains report generators for Metro Cyprus weekly merchant
and venue reporting. The same underlying data can be exported as a PDF (with
charts) or as a downloadable spreadsheet compatible with Google Sheets.

## Metro Cyprus weekly report

The generator creates a multi-page PDF where page 1 is a merchant-level preview
and the following pages cover venue-level performance and the requested metric
sections:

- Purchases
  - Group orders for the total merchant
  - Orders per venue
  - Venue Group Gross Value
  - Gross Value per Venue
  - Orders per Hour
  - Order per Day per Store
  - Average Basket Value per Venue
- Wolt+
  - W+ Orders
  - W+ New Users
- Operations
  - POFR Group %
  - POFR %
  - Substitution %
  - % Unfulfilled Items
  - Ops Performance
  - Punctuality per Venue
  - Average Delivery Time per Venue
  - Prep Time per Venue
  - Marker Ready Performance
  - % Late Orders
- Quality
  - Rejections % per Venue
  - Rating per Store
  - Offline % per Venue (New)
  - Offline Hours per Venue (New)
  - Lost sales %GOV and GOV EUR
  - Rejections
  - Substitutions
  - Cancellation
  - Unfulfilled items
- Additions & Deductions
  - Rejection Reason
  - Addition Breakdown
  - Deduction Breakdown
  - Courier Fee Breakdown
- Picker
  - Picker Usage per Store
- Monthly Picker Metrics
  - Venue Name
  - Purchase ID
  - Dynamic Time Delivered
  - Order Number
  - Rating of Goods
  - Goods Items Full Amount
  - Customer Feedback, where available

## Data inputs

The weekly report uses a long-format CSV so exports from Snowflake, Looker, or a
manual spreadsheet can be used without changing the PDF layout.

Copy the templates and populate them:

```bash
cp data/weekly_metrics_template.csv data/weekly_metrics.csv
cp data/monthly_picker_metrics_template.csv data/monthly_picker_metrics.csv
```

Alternatively, use the Google Sheets-compatible workbook:

```bash
python3 reports/create_google_sheets_template.py
```

This creates `data/metro_cyprus_report_google_sheets_template.xlsx`, which can
be uploaded to Google Drive and opened with Google Sheets. After populating the
tabs, download them as CSV files named:

- `data/weekly_metrics.csv`
- `data/monthly_picker_metrics.csv`

`data/weekly_metrics.csv` columns:

| Column | Description |
| --- | --- |
| `period_start` | Start date for the metric row, `YYYY-MM-DD`. |
| `period_end` | End date for the metric row, `YYYY-MM-DD`. |
| `metric` | Metric name. Use the names listed in the report sections above. |
| `venue_name` | Venue name. Leave blank for merchant-level totals. |
| `value` | Numeric metric value. |
| `unit` | Optional unit, for example `%`, `EUR`, `min`, or `orders`. |
| `dimension` | Optional dimension name for chart series, for example `hour`, `day`, or `reason`. |
| `dimension_value` | Optional dimension value, for example `13:00`, `Monday`, or a rejection reason. |

`data/monthly_picker_metrics.csv` must contain the columns in
`data/monthly_picker_metrics_template.csv`. `Customer Feedback` may be left
blank when no feedback is available, and older exports without that column are
still accepted.

### Importing a Monthly Picker Metrics workbook (e.g. from Snowflake)

If you have a Monthly Picker Metrics export as an `.xlsx` workbook (one sheet
per month, with `Venue Name`, `Purchase ID`, `Dynamic Time Delivered`,
`Order Number`, `Rating of Goods`, and `Goods Items Full Amount` columns),
use these two scripts instead of hand-editing CSV:

1. Add a `Customer Feedback` column to the workbook (blank by default, or
   merged in from a feedback lookup CSV keyed by `Purchase ID` or
   `Order Number`):

   ```bash
   python3 reports/add_customer_feedback_column.py \
     path/to/Monthly_Picker_Metrics.xlsx \
     data/Metro_Cyprus_Monthly_Picker_Metrics_with_Customer_Feedback.xlsx \
     --feedback-csv path/to/customer_feedback_export.csv   # optional
   ```

   The `--feedback-csv` must have a `Customer Feedback` column plus one of
   `Purchase ID` or `Order Number` to match on. Without `--feedback-csv`, the
   column is added but left blank for every row — this script never invents
   feedback text.

2. Export the (optionally augmented) workbook into the pipeline's CSV schema,
   combining every monthly sheet into one file:

   ```bash
   python3 reports/export_monthly_picker_csv.py \
     data/Metro_Cyprus_Monthly_Picker_Metrics_with_Customer_Feedback.xlsx \
     --output data/monthly_picker_metrics.csv
   ```

3. Regenerate the reports (see below) to pick up the new data.

`data/Metro_Cyprus_Monthly_Picker_Metrics_May-June_2026_with_Customer_Feedback.xlsx`
in this repo is the result of running step 1 on the May-June 2026 Metro
Cyprus Monthly Picker Metrics export, and `data/monthly_picker_metrics.csv`
is the result of running step 2 on it (4,312 rows). The Snowflake MCP
connection was unavailable when this was generated (no working Snowflake
tool access and no connection parameters besides a redacted password in this
environment), so `Customer Feedback` is present as a column but blank for
every row — no feedback text was fabricated. Re-run step 1 with
`--feedback-csv` once a real customer feedback export is available, keyed by
`Purchase ID` or `Order Number`.

## Generate the reports

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Generate last week's PDF report:

```bash
python3 reports/generate_metro_cyprus_weekly_report.py
```

Generate last week's report as a downloadable spreadsheet (`.xlsx`), openable
directly in Google Sheets or Excel:

```bash
python3 reports/generate_metro_cyprus_weekly_sheet.py
```

The spreadsheet mirrors the PDF: a `Merchant Overview` tab, a `Venue Summary`
tab (one row per venue), one tab per metric section (Purchases, Wolt+,
Operations, Quality, Additions & Deductions, Picker), and a
`Monthly Picker Metrics` tab. To open it in Google Sheets, upload the
generated `.xlsx` file to Google Drive, then right-click it and choose
**Open with > Google Sheets** (or use **File > Import** from within Sheets).

Both generators accept the same period flags:

```bash
python3 reports/generate_metro_cyprus_weekly_report.py \
  --period-start 2026-07-06 \
  --period-end 2026-07-12

python3 reports/generate_metro_cyprus_weekly_sheet.py \
  --period-start 2026-07-06 \
  --period-end 2026-07-12
```

Both write output to `reports/output/` by default, and both read from
`reports/metro_cyprus_data.py`'s shared loaders so the PDF and spreadsheet
never drift from each other.

## Current generated artifacts

The Snowflake MCP connection was unavailable in this run, so the weekly
metrics (Purchases, Wolt+, Operations, Quality, Additions & Deductions,
Picker, and per-venue pages) in the generated Metro Cyprus PDF and
spreadsheet for `2026-07-06` to `2026-07-12` are still explicitly marked
`N/A` — no values were fabricated. The **Monthly Picker Metrics** section,
however, is populated with the real May-June 2026 export (4,312 rows across
7 venues), with `Customer Feedback` present but blank for the same reason.
Regenerate both after the weekly source exports are added:

- `reports/output/metro_cyprus_weekly_report_2026-07-06_to_2026-07-12.pdf`
- `reports/output/metro_cyprus_weekly_report_2026-07-06_to_2026-07-12.xlsx`
