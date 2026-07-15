# Wolt — Weekly Merchant Report (Metro Cyprus)

Generates a polished, multi-page **PDF report with charts** for a Wolt merchant.
Page 1 is a merchant-wide preview; every following page breaks down a single
venue. Built for **Metro Cyprus**, but fully config-driven so it works for any
merchant/venue set.

> ⚠️ **Data note.** The live data warehouse (Snowflake) was **not reachable**
> from the build environment, so the committed report is rendered from
> **deterministic synthetic sample data** (clearly labelled "SAMPLE DATA" in the
> footer and on the cover). The full pipeline — schema, metrics, charts and SQL —
> is production-ready: point `data_source: snowflake` in `config.yaml` and supply
> credentials to produce a report from real figures. See
> [Connecting to real data](#connecting-to-real-data).

The latest generated report lives at
[`output/metro-cyprus_weekly_2026-W28.pdf`](output/metro-cyprus_weekly_2026-W28.pdf)
(last full ISO week: **06–12 Jul 2026**).

## What's in the report

**Page 1 — Merchant preview (whole of Metro Cyprus)**

- KPI cards: total orders, group gross value, avg basket, Wolt+ orders/new
  users, group POFR, punctuality, rejections, avg delivery, avg rating
- Orders per venue, Gross value per venue
- Orders per day (group), Orders per hour (group)
- Lost sales by reason (€ + % of GOV), Rating per store

**Per-venue pages** (one section per venue) with all requested metrics:

| Section | Metrics |
| --- | --- |
| **Purchases** | Group orders (merchant), Orders per venue, Venue group gross value, Gross value per venue, Orders per hour, Orders per day per store, Average basket value per venue |
| **Wolt+** | W+ Orders, W+ New Users |
| **Operations** | POFR Group %, POFR %, Substitution %, % Unfulfilled Items, Ops Performance, Punctuality per venue, Average delivery time per venue, Prep time per venue, Marker ready performance, % Late orders |
| **Quality** | Rejections % per venue, Rating per store, Offline % per venue (new), Offline hours per venue (new), Lost sales %GOV & GOV € (Rejections / Substitutions / Cancellation / Unfulfilled items) |
| **Additions & Deductions** | Rejection reason, Addition breakdown, Deduction breakdown, Courier fee breakdown |
| **Picker** | Picker usage per store |

**Appendix — Monthly Picker Metrics** (month-to-date, all venues): Venue Name,
Purchase ID, Dynamic Time Delivered, Order Number, Rating of Goods, Goods Items
Full Amount.

## Quick start

```bash
# 1. Install dependencies (a virtualenv is recommended)
pip install -r requirements.txt      # or: pip install -e .

# 2. Generate sample data and build the PDF (fully offline)
PYTHONPATH=src python -m wolt_report.cli --generate-sample

# -> output/metro-cyprus_weekly_2026-W28.pdf
```

If installed with `pip install -e .` you can use the console script instead:

```bash
wolt-report --generate-sample
```

Subsequent runs reuse the CSVs in `data/`; omit `--generate-sample` to rebuild
the PDF from existing data.

## Configuration

Everything is driven by [`config.yaml`](config.yaml):

- `merchant` — name, currency, timezone
- `period` — `week: last` (previous full Mon–Sun ISO week) or an explicit
  `start`/`end`
- `venues` — the list of stores (id + display name)
- `data_source` — `csv` (default, offline) or `snowflake`
- `targets` — KPI thresholds that colour cards/charts green / amber / red

## Connecting to real data

1. Set `data_source: snowflake` in `config.yaml`.
2. Install the connector: `pip install -e ".[snowflake]"`.
3. Export credentials:

   ```bash
   export SNOWFLAKE_ACCOUNT=... SNOWFLAKE_USER=... SNOWFLAKE_PASSWORD=...
   export SNOWFLAKE_WAREHOUSE=... SNOWFLAKE_DATABASE=... SNOWFLAKE_SCHEMA=... SNOWFLAKE_ROLE=...
   ```

4. Adapt the table/column names in
   [`src/wolt_report/queries.sql`](src/wolt_report/queries.sql) to your
   warehouse schema. Each query is bound with `start_date`, `end_date`,
   `venue_ids` and `month_start`, and must return the columns declared in
   [`src/wolt_report/schema.py`](src/wolt_report/schema.py).
5. Run `wolt-report`.

Alternatively, export your own CSVs into `data/` matching `schema.py` and keep
`data_source: csv`.

## Project layout

```
config.yaml                     # merchant / venues / period / targets
requirements.txt / pyproject.toml
src/wolt_report/
  config.py        # config + reporting-period resolution
  schema.py        # canonical table/column definitions
  loader.py        # CsvLoader + SnowflakeLoader
  queries.sql      # documented Snowflake SQL (one query per table)
  sample_data.py   # deterministic synthetic data generator
  metrics.py       # all metric computations
  charts.py        # matplotlib chart helpers (Wolt-styled)
  report.py        # ReportLab PDF assembly
  cli.py           # command-line entrypoint
data/              # CSV inputs (generated sample or real exports)
output/            # generated PDF(s)
```
