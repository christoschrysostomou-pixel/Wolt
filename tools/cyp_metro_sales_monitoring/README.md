# CYP Metro Sales Monitoring — weekly data updater

`update_data_sheet.py` fills missing weeks in `CYP Metro Sales Monitoring.xlsx`.

## Why this is a manual/semi-automated step

The workbook's `Data` sheet is a static paste of numbers pulled from the
Looker explore
[`core/f_purchases`](https://looker.wolt.com/explore/core/f_purchases) (via
Snowflake). It is **not** a live query embedded in the workbook, so new weeks
have to be fetched from Looker and written into the sheet each time.

This cloud agent run was **not able to pull the missing weeks
automatically** because:

- Looker (`looker.wolt.com`) requires an interactive SSO login (Okta/SAML);
  there is no Looker API key (`client_id`/`client_secret`) available to the
  agent to call the Looker API instead.
- Only a `SNOWFLAKE_PASSWORD` secret is available in this environment. There
  is no `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_WAREHOUSE`,
  `SNOWFLAKE_DATABASE`/`SNOWFLAKE_SCHEMA`, or `SNOWFLAKE_ROLE`, so a direct
  Snowflake connection can't be established. Guessing these values against a
  real production account isn't safe (risk of lockouts/security alerts), so
  the agent did not attempt it.

## How to unblock this

Pick whichever is easiest:

1. **Add full Snowflake credentials as Cursor secrets** (Cloud Agents →
   Secrets): `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_WAREHOUSE`,
   `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`, `SNOWFLAKE_ROLE` (in addition to
   the existing `SNOWFLAKE_PASSWORD`). A future agent run can then query the
   `f_purchases` fact table directly with `snowflake-connector-python`
   (already used/installed in this run).
2. **Add a Looker API3 key** as secrets (`LOOKER_BASE_URL`,
   `LOOKER_CLIENT_ID`, `LOOKER_CLIENT_SECRET`, from Looker → Admin → Users →
   your user → Edit → API3 Keys). A future agent run can then call the
   Looker API to re-run the existing explore
   (`qid=xrppw8Pk44opZhGDqHkdTI`) headlessly.
3. **Export manually**: open the Looker explore, group by
   "Purchases Time Delivered Week of Year", and download "Number of Orders"
   and "GOV (Gross Order Value) Total Euro" for 2025 from the first
   incomplete week (currently week 39) through the last fully completed
   week. Save it as a CSV with columns `week,orders,gov` and run the script
   below.

## Usage

```bash
pip install openpyxl

python update_data_sheet.py \
  --workbook "CYP Metro Sales Monitoring.xlsx" \
  --year 2025 \
  --input new_weeks.csv \
  --output "CYP Metro Sales Monitoring (updated).xlsx"
```

`new_weeks.csv` example:

```csv
week,orders,gov
39,5312,318204.12
40,5401,322987.60
```

The script only overwrites the weeks listed in the CSV, recomputes the
`% Change` / `% GOV` (year-over-year) columns from the existing prior-year
values already in the sheet, and leaves the `Analysis` sheet's formulas
untouched (they recalc automatically from `Data` when the file is opened in
Excel).
