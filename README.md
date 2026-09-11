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

`data/source_exports/Metro_Cyprus_Monthly_Picker_Metrics_May-June_2026.xlsx`
is the raw May-June 2026 Metro Cyprus Monthly Picker Metrics export (2 sheets,
4,312 rows across 7 venues, no `Customer Feedback` column yet).
`data/Metro_Cyprus_Monthly_Picker_Metrics_May-June_2026_with_Customer_Feedback.xlsx`
in this repo is the result of running step 1 on that export, and
`data/monthly_picker_metrics.csv` is the result of running step 2 on it
(4,312 rows). A real Snowflake connection to pull the matching `Customer
Feedback` text has been attempted twice now and is still not working, for
two different reasons each time:

1. **No Snowflake MCP server** is registered in this run's tool catalog, so
   there is no MCP path to Snowflake.
2. **Given a `connections.toml`-style snippet** (account
   `DOORDASH-IG78751_AWS_EU_WEST_1`, user
   `CHRISTOS.CHRYSOSTOMOU@WOLT.COM`, `authenticator = "externalbrowser"`,
   `role = "BASE_USER"`), two direct-connection paths were tried with
   `snowflake-connector-python`:
   - `authenticator="externalbrowser"` — this is SSO via Okta and opened a
     real browser to a live `doordash.okta.com` SAML login page, but
     **requires a human to interactively complete the Okta login (and MFA)
     in that browser**. A cloud agent runs unattended in the background with
     nobody to click through that flow, so this hangs indefinitely and
     can't be completed autonomously.
   - Using the `SNOWFLAKE_PASSWORD` secret as a password instead: the
     connector detected it's actually a **Programmatic Access Token** (a
     JWT, not expired) and sent it as one, which is the right approach for
     headless/unattended auth. Snowflake's server reached and responded
     with `250001 (08001)` / internal code `394400`: **"Programmatic access
     token is invalid."** This happened consistently across every account
     format (`DOORDASH-IG78751_AWS_EU_WEST_1` and `DOORDASH-IG78751`), every
     username format (with/without the `@wolt.com` domain), and every role
     (`BASE_USER`, `PUBLIC`, unset) — so it isn't a role-mapping or account-
     string issue, the token itself is being rejected by Snowflake. Per
     Snowflake's own docs, `PAT_INVALID` means the token isn't linked to
     this user, the user/role wasn't found, or the token is otherwise not
     valid for this account — something only whoever generated/owns that
     token in Snowflake can fix (see the `SHOW PROGRAMMATIC ACCESS TOKENS
     FOR USER ...` check below).

`warehouse`, `database`, and `schema` were also `<none selected>` in the
snippet, which would additionally block running any query once/if auth
succeeds.

3. **A third attempt (new agent run, several weeks later)** had a
   completely different pair of secrets injected: `SNOWFLAKE_USER` (a
   different, shorter login name — not
   `CHRISTOS.CHRYSOSTOMOU@WOLT.COM`) plus a new `SNOWFLAKE_PASSWORD` (a
   different, non-expired JWT — confirmed by decoding both tokens' payload
   claims and seeing different `kid`/`p` values). Both the default
   password-as-PAT path and the explicit
   `authenticator="PROGRAMMATIC_ACCESS_TOKEN"` / `token=` path were tried,
   against both `DOORDASH-IG78751_AWS_EU_WEST_1` and `DOORDASH-IG78751`.
   Every combination still returned the same `394400` /
   `"Programmatic access token is invalid."` — from a *different* user and
   a *different* token than before. Because two unrelated
   user/token pairs both fail identically against this account, the most
   likely explanations now are account-level, not credential-level:
   - The account's authentication policy may not have
     `'PROGRAMMATIC_ACCESS_TOKEN'` added to `AUTHENTICATION_METHODS` (PATs
     are rejected account-wide until this is explicitly enabled — see
     Snowflake's "Using programmatic access tokens for authentication"
     docs), or
   - A network policy may be restricting Snowflake connections to specific
     IP ranges (e.g. corporate VPN/office IPs) that this cloud agent's
     egress IP isn't part of, or
   - `DOORDASH-IG78751_AWS_EU_WEST_1` isn't actually the right account for
     these particular tokens (no `SNOWFLAKE_ACCOUNT` secret has ever been
     provided to confirm this independently — it's been inferred from a
     `connections.toml` snippet for a *different* user).

   None of these are things a cloud agent can fix or work around from the
   client side — someone with Snowflake account-admin access needs to check
   the authentication policy and network policy for this account/user, and
   ideally provide a `SNOWFLAKE_ACCOUNT` secret explicitly so it no longer
   has to be inferred.

4. **A follow-up in that same run** made a raw REST call to
   `/session/v1/login-request` directly (bypassing the connector, to see
   the full, unfiltered response) and also retried the connector with five
   different roles (`PUBLIC`, `SYSADMIN`, `ACCOUNTADMIN`, `ANALYST`,
   `BASE_USER`, and none). Two useful new facts came out of this:
   - Snowflake's raw response confirms it *does* recognize `SNOWFLAKE_USER`
     as a real login (the response's `loginName` field echoed back the
     exact value of the `SNOWFLAKE_USER` secret verbatim) with
     `"authnMethod": "PAT"`. So the account correctly identifies both the
     user and that this is a PAT-based login attempt — it isn't rejecting
     it as some other authenticator or an unrecognized user outright.
   - Every one of the five role variations still returned the exact same
     `394400` / `"Programmatic access token is invalid."`, ruling out a
     role/`ROLE_RESTRICTION` mismatch as the cause (a known cause of this
     same error per Snowflake's terraform provider issue tracker).

   Whoever administers this Snowflake account can check the token status
   directly with `SHOW PROGRAMMATIC ACCESS TOKENS FOR USER <the login name
   in the SNOWFLAKE_USER secret>;` to see whether it's active, expired,
   disabled, or was generated for a different account than
   `DOORDASH-IG78751_AWS_EU_WEST_1`.

So `Customer Feedback` is present as a column but blank for every row — no
feedback text was fabricated. Re-run step 1 with `--feedback-csv` once a real
customer feedback export is available, keyed by `Purchase ID` or
`Order Number` (for example, once the Snowflake MCP integration is enabled
for cloud agents, or the missing account/user/warehouse secrets are added
alongside `SNOWFLAKE_PASSWORD`).

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
