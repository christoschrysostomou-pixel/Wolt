# Wolt Reports

This repository contains a PDF report generator for Metro Cyprus weekly
merchant and venue reporting.

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

## Generate the PDF

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Generate last week's report:

```bash
python3 reports/generate_metro_cyprus_weekly_report.py
```

Generate a specific reporting period:

```bash
python3 reports/generate_metro_cyprus_weekly_report.py \
  --period-start 2026-07-06 \
  --period-end 2026-07-12
```

The output is written to `reports/output/` by default.

## Current generated artifact

The Snowflake MCP connection was unavailable in this run, so the generated
Metro Cyprus PDF for `2026-07-06` to `2026-07-12` is a structured report shell
with every unavailable chart and KPI explicitly marked `N/A`. It should be
regenerated after the source exports are added.
