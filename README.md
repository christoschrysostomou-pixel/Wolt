# Wolt — Metro Cyprus picker metrics

Extracts the Monthly Picker Metrics file for METRO Express Cyprus venues
from Wolt Snowflake. The May–June 2026 source file is a Looker
`core/f_purchases` export with these columns:

- Venue Name
- Purchase ID
- Dynamic Time Delivered
- Order Number
- Rating of Goods
- Goods Items Full Amount
- Customer Feedback

## August 2026 extract

```bash
python3 reports/extract_metro_cyprus_picker_metrics.py --month 2026-08
```

This writes:

`data/Metro_Cyprus_Monthly_Picker_Metrics_August_2026_with_customer_comments.csv`

The extractor uses the `snow` CLI against **Snowflake Production (Wolt)**:

| Setting | Value |
| --- | --- |
| Account | `doordash-ig78751_aws_eu_west_1` |
| Role | `base_user` |
| Warehouse | `EXPLORATION` |
| Database | `PRODUCTION` |
| Timezone | `Asia/Nicosia` |
| Venues | METRO Express Agias Fylaxeos, Aglantzia, Larnaca, Mouttagiaka, Paralimni, Platy, Strovolos |

SSO opens DoorDash Okta for **Snowflake Production (Wolt)**. Complete that
browser login as `christos.chrysostomou@wolt.com`, then re-run the command.
The session is cached for a few hours.

A programmatic access token in this environment was rejected by Snowflake
(`394400 Programmatic access token is invalid`), so interactive SSO is
required.

## What the query does

1. Load the Wolt semantic-layer bootstrap.
2. Resolve `f_purchases` / `d_venues` (and ratings if they are not already
   on the purchase fact).
3. Keep delivered purchases whose local delivered timestamp falls in the
   requested calendar month.
4. Format `Dynamic Time Delivered` as `DD/MM/YYYY HH24:MI`, matching the
   May–June file.

The May–June file had 55,601 rows (27,741 in May, 27,860 in June) across
the same seven venues, with 116 non-empty customer comments. August should
be a similar full-month delivered-order extract, not the earlier 4,312-row
subset.
