# Berezka Cuisine — Limassol order geography

Merchant-facing map of **where Wolt customers of Berezka Cuisine are**,
for advertising planning. The map is aggregated to ~1 km cells or postal
codes. It never writes individual delivery addresses.

## What this cloud run could and could not do

Wolt Snowflake Production (`doordash-ig78751_aws_eu_west_1`) requires
DoorDash Okta SSO. In this Cloud Agent the sign-in browser runs inside
the VM, so the session never completes. The same blocker stopped the
Metro Cyprus extracts in this repo.

Until SSO works on **your laptop**, this folder ships:

1. **Kitchen coverage** from public Wolt / [berezka.cy/en/shops](https://berezka.cy/en/shops) listings (7 Limassol venues, Erimi → Agios Tychonas).
2. An extractor that pulls **aggregated** order geography once Snowflake is signed in.
3. A renderer that turns that aggregate (or a Looker CSV) into a shareable HTML map.

This is **not** a substitute for the order heatmap. Kitchen pins show
where food is prepared, not where demand is.

## Fastest ways to get the real heatmap

### A. Local Cursor (preferred)

On your Mac, in this repo:

```bash
python3 reports/berezka_limassol_order_map/extract_order_geography.py --months 12
python3 reports/berezka_limassol_order_map/render_map.py
open reports/berezka_limassol_order_map/output/berezka_limassol_order_map.html
```

Complete the Okta window when `snow` opens it. User:
`christos.chrysostomou@wolt.com`. Account: `doordash-ig78751_aws_eu_west_1`.

### B. Looker export (no Python)

1. Open [looker.wolt.com](https://looker.wolt.com).
2. Explore **core / f_purchases** (same explore as the Metro Cyprus sales file).
3. Filters:
   - Venue Name contains `Berezka`
   - Venue City / Country = Limassol / CYP
   - Time Delivered = last 12 months
   - Marketplace delivered orders only
4. Dimensions: delivery H3 / geohash / postal code / neighbourhood
   (whatever the explore exposes — **not** street address).
5. Measures: count of purchases, GOV EUR.
6. Export CSV and drop it here as `output/looker_areas.csv` with columns:

   `area_name,lat,lng,orders,gov_eur,venue_name` (venue_name optional)

7. Render:

```bash
python3 reports/berezka_limassol_order_map/render_map.py --csv reports/berezka_limassol_order_map/output/looker_areas.csv
```

### C. Partner Hub

If the merchant already has **Insights → heatmap** in Partner Hub, that
is the live product view. This pack is for a branded, shareable overview
plus area ranking for ads.

## Privacy

The extractor drops any area with fewer than **5** delivered orders
before writing files. Do not add street-level columns to the Looker
export if you will send the HTML to the merchant.

## Scope the extractor uses

- Brand match: venue name `ILIKE '%berezka%'`
- Geography: Limassol / CYP
- Default window: last 12 calendar months, `TIME_DELIVERED` in `Asia/Nicosia`
- Channel: marketplace delivered orders when the flag exists
- Grain: ~1 km rounded lat/lng cells when coordinates exist; otherwise postal / district. Looker H3 is also fine if you export from the explore.
