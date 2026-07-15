"""Canonical data schema for the weekly report.

The report is built from a small set of tidy tables. Each table is documented
here with the columns it must contain. Both the CSV loader and the Snowflake
loader are expected to return dataframes with exactly these columns so the rest
of the pipeline is source-agnostic.

Tables
------
orders
    One row per purchase (order). This is the primary fact table and drives
    almost every metric.
offline
    One row per venue per day describing how long the venue was offline vs. how
    many hours it was scheduled to be open.
financials
    One row per (venue, category) line item for additions, deductions and
    courier fee breakdowns.
picker_usage
    One row per venue per day describing picker-app usage.
monthly_picker
    Item/order level export for the "Monthly Picker Metrics" table.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# orders (one row per purchase)
# ---------------------------------------------------------------------------
ORDERS_COLUMNS = [
    "purchase_id",          # str, unique order id
    "order_number",         # str, human friendly order number
    "venue_id",             # str, matches config venues
    "venue_name",           # str
    "order_datetime",       # datetime (local, tz-aware or naive local)
    "delivered_datetime",   # datetime, when the order was delivered
    "gross_value",          # float, GOV in merchant currency (€)
    "basket_value",         # float, item subtotal (€)
    "item_count",           # int, number of items ordered
    "is_wolt_plus",         # bool, order placed by a Wolt+ subscriber
    "is_new_wolt_plus",     # bool, order from a newly-acquired Wolt+ user
    "prep_time_min",        # float, minutes to prepare
    "delivery_time_min",    # float, minutes from order to delivery
    "marketplace_ready_min",# float, "marker ready" time in minutes
    "is_punctual",          # bool, delivered on time
    "is_late",              # bool, order delivered late
    "is_pofr",              # bool, perfect order fulfilment (no issues)
    "is_rejected",          # bool, order rejected by the venue
    "rejection_reason",     # str or "", reason when rejected
    "is_cancelled",         # bool, order cancelled
    "rating",               # float or NaN, customer rating 1-5
    "substituted_items",    # int, number of substituted items
    "unfulfilled_items",    # int, number of unfulfilled items
    "lost_sales_gov",       # float, € of lost sales attributed to this order
    "lost_sales_reason",    # str, one of Rejections/Substitutions/
                            #      Cancellation/Unfulfilled (or "")
    "used_picker",          # bool, order fulfilled using the Picker app
]

# ---------------------------------------------------------------------------
# offline (one row per venue per day)
# ---------------------------------------------------------------------------
OFFLINE_COLUMNS = [
    "venue_id",
    "venue_name",
    "date",             # date
    "offline_hours",    # float, hours venue was offline during opening hours
    "open_hours",       # float, scheduled open hours
]

# ---------------------------------------------------------------------------
# financials (additions / deductions / courier fee line items)
# ---------------------------------------------------------------------------
# `group` is one of: "addition", "deduction", "courier_fee"
FINANCIALS_COLUMNS = [
    "venue_id",
    "venue_name",
    "group",        # str: addition | deduction | courier_fee
    "category",     # str: human readable line item
    "amount",       # float, € (positive magnitude)
]

# ---------------------------------------------------------------------------
# picker_usage (one row per venue per day)
# ---------------------------------------------------------------------------
PICKER_USAGE_COLUMNS = [
    "venue_id",
    "venue_name",
    "date",
    "orders_total",     # int, total orders in the day
    "orders_picked",    # int, orders handled through the Picker app
]

# ---------------------------------------------------------------------------
# monthly_picker (order/item level export)
# ---------------------------------------------------------------------------
MONTHLY_PICKER_COLUMNS = [
    "venue_name",
    "purchase_id",
    "dynamic_time_delivered",   # datetime, delivery timestamp
    "order_number",
    "rating_of_goods",          # float or NaN
    "goods_items_full_amount",  # float, € value of goods
]

LOST_SALES_REASONS = [
    "Rejections",
    "Substitutions",
    "Cancellation",
    "Unfulfilled",
]
