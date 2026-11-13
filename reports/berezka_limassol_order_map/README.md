# Berezka Cuisine — Limassol order geography

Merchant-facing map of **where Wolt customers of Berezka Cuisine are**,
for advertising planning. It colours official Cyprus **postal-code areas**
across greater Limassol and ranks the busiest ones. It never plots
individual delivery addresses. Kitchen pins are a separate layer.

Open this file in a browser:

`reports/berezka_limassol_order_map/output/berezka_limassol_order_map.html`

## What you should see

1. Grey postal-code polygons covering Erimi → Agios Tychonas (the city,
   not just the seven kitchens).
2. After you load an order CSV: **orange choropleth + a ranking table**
   of the areas with the most delivered orders.
3. Areas with fewer than **5** orders stay uncoloured.

Until a CSV is loaded, there is no customer heatmap — this Cloud Agent
cannot finish DoorDash Okta SSO against Wolt Snowflake Production, so
live order counts are not in the file.

## Fastest way to get the heatmap (Looker)

1. Open [looker.wolt.com](https://looker.wolt.com) on your laptop.
2. Explore **core / f_purchases**.
3. Filters:
   - Venue Name contains `Berezka`
   - Venue City / Country = Limassol / CYP
   - Time Delivered = last 12 months
   - Marketplace delivered orders only
4. Dimension: **delivery postal code** (best), or delivery H3 / lat-lng.
   Do not add street address.
5. Measure: count of purchases (and GOV if you want it).
6. Export CSV and drop it on the map page (or save as
   `output/looker_areas.csv` and re-run the renderer below).

Useful CSV columns (header names can vary):

`postal_code,orders`

or

`lat,lng,orders`

or one row per order with a postal code — the page aggregates and then
drops areas under 5 orders.

## Local Snowflake (same map)

On your Mac, complete the Okta window `snow` opens
(`christos.chrysostomou@wolt.com`, account `doordash-ig78751_aws_eu_west_1`):

```bash
python3 reports/berezka_limassol_order_map/extract_order_geography.py --months 12
python3 reports/berezka_limassol_order_map/render_map.py
```

## Partner Hub

If the merchant already has **Insights → heatmap** in Partner Hub, that
is the live product view. This pack is the branded, shareable overview
plus an area ranking for ads.

## Scope the extractor uses

- Brand match: venue name `ILIKE '%berezka%'`
- Geography: Limassol / CYP
- Default window: last 12 calendar months, `TIME_DELIVERED` in `Asia/Nicosia`
- Channel: marketplace delivered orders when the flag exists
- Grain: ~1 km cells or postal / district; Looker H3 also works
- Privacy: areas with fewer than 5 orders are omitted
