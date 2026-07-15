-- Snowflake queries backing the weekly Metro Cyprus report.
--
-- IMPORTANT: table/column names below are placeholders that follow common Wolt
-- analytics naming. Adapt the FROM/JOIN clauses and column expressions to your
-- warehouse's actual schema. Each query is bound with the parameters:
--   %(start_date)s, %(end_date)s   -> report window (inclusive)
--   %(venue_ids)s                  -> tuple of venue ids
--   %(month_start)s                -> first day of the report's month
--
-- Every query MUST return exactly the columns declared in wolt_report/schema.py.

-- name: orders
SELECT
    o.purchase_id                                   AS purchase_id,
    o.order_number                                  AS order_number,
    o.venue_id                                      AS venue_id,
    v.venue_name                                    AS venue_name,
    o.order_ts_local                                AS order_datetime,
    o.delivered_ts_local                            AS delivered_datetime,
    o.gross_order_value                             AS gross_value,
    o.basket_value                                  AS basket_value,
    o.item_count                                    AS item_count,
    o.is_wolt_plus                                  AS is_wolt_plus,
    o.is_new_wolt_plus_user                         AS is_new_wolt_plus,
    o.prep_time_minutes                             AS prep_time_min,
    o.delivery_time_minutes                         AS delivery_time_min,
    o.marketplace_ready_minutes                     AS marketplace_ready_min,
    o.delivered_on_time                             AS is_punctual,
    o.delivered_late                                AS is_late,
    o.is_perfect_order                              AS is_pofr,
    o.is_rejected                                   AS is_rejected,
    COALESCE(o.rejection_reason, '')                AS rejection_reason,
    o.is_cancelled                                  AS is_cancelled,
    o.customer_rating                               AS rating,
    o.substituted_item_count                        AS substituted_items,
    o.unfulfilled_item_count                        AS unfulfilled_items,
    o.lost_sales_gov_eur                            AS lost_sales_gov,
    COALESCE(o.lost_sales_reason, '')               AS lost_sales_reason,
    o.used_picker_app                               AS used_picker
FROM analytics.merchant_orders o
JOIN analytics.venues v ON v.venue_id = o.venue_id
WHERE o.venue_id IN (%(venue_ids)s)
  AND o.order_ts_local::date BETWEEN %(start_date)s AND %(end_date)s;

-- name: offline
SELECT
    s.venue_id                          AS venue_id,
    v.venue_name                        AS venue_name,
    s.business_date                     AS date,
    s.offline_hours                     AS offline_hours,
    s.scheduled_open_hours              AS open_hours
FROM analytics.venue_availability_daily s
JOIN analytics.venues v ON v.venue_id = s.venue_id
WHERE s.venue_id IN (%(venue_ids)s)
  AND s.business_date BETWEEN %(start_date)s AND %(end_date)s;

-- name: financials
-- Union of additions, deductions and courier-fee line items.
SELECT
    f.venue_id      AS venue_id,
    v.venue_name    AS venue_name,
    f.fee_group     AS "group",        -- 'addition' | 'deduction' | 'courier_fee'
    f.fee_category  AS category,
    SUM(ABS(f.amount_eur)) AS amount
FROM analytics.merchant_financial_line_items f
JOIN analytics.venues v ON v.venue_id = f.venue_id
WHERE f.venue_id IN (%(venue_ids)s)
  AND f.business_date BETWEEN %(start_date)s AND %(end_date)s
GROUP BY f.venue_id, v.venue_name, f.fee_group, f.fee_category;

-- name: picker_usage
SELECT
    p.venue_id                  AS venue_id,
    v.venue_name                AS venue_name,
    p.business_date             AS date,
    p.orders_total              AS orders_total,
    p.orders_via_picker_app     AS orders_picked
FROM analytics.picker_usage_daily p
JOIN analytics.venues v ON v.venue_id = p.venue_id
WHERE p.venue_id IN (%(venue_ids)s)
  AND p.business_date BETWEEN %(start_date)s AND %(end_date)s;

-- name: monthly_picker
-- Month-to-date order-level export used for the "Monthly Picker Metrics" table.
SELECT
    v.venue_name                        AS venue_name,
    o.purchase_id                       AS purchase_id,
    o.delivered_ts_local                AS dynamic_time_delivered,
    o.order_number                      AS order_number,
    o.goods_rating                      AS rating_of_goods,
    o.goods_items_full_amount_eur       AS goods_items_full_amount
FROM analytics.merchant_orders o
JOIN analytics.venues v ON v.venue_id = o.venue_id
WHERE o.venue_id IN (%(venue_ids)s)
  AND o.used_picker_app = TRUE
  AND o.order_ts_local::date BETWEEN %(month_start)s AND %(end_date)s;
