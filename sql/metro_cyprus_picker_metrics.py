"""SQL templates for Metro Cyprus monthly picker-metrics extracts."""

from __future__ import annotations

EXTRACT_SQL_TEMPLATE = r"""
ALTER SESSION SET QUERY_TAG = '{query_tag}';

WITH venues AS (
    SELECT
        {venue_id_col} AS venue_id,
        {venue_name_col} AS venue_name
    FROM {venues_table}
    WHERE {venue_name_col} IN ({venue_literals})
),
purchases AS (
    SELECT
        p.{purchase_id_col} AS purchase_id,
        p.{purchase_venue_id_col} AS venue_id,
        p.{time_delivered_col} AS time_delivered_utc,
        p.{order_number_col} AS order_number,
        p.{goods_amount_col} AS goods_items_full_amount
        {purchase_rating_select}
    FROM {purchases_table} p
    WHERE p.{time_delivered_col} >= {start_utc_expr}
      AND p.{time_delivered_col} <  {end_utc_expr}
      {status_filter}
)
SELECT
    v.venue_name AS "Venue Name",
    p.purchase_id AS "Purchase ID",
    TO_CHAR(
        CONVERT_TIMEZONE('UTC', '{timezone}', p.time_delivered_utc),
        'DD/MM/YYYY HH24:MI'
    ) AS "Dynamic Time Delivered",
    p.order_number AS "Order Number",
    {rating_select} AS "Rating of Goods",
    p.goods_items_full_amount AS "Goods Items Full Amount",
    {feedback_select} AS "Customer Feedback"
FROM purchases p
INNER JOIN venues v
    ON v.venue_id = p.venue_id
{ratings_join}
ORDER BY p.time_delivered_utc DESC, p.purchase_id
"""
