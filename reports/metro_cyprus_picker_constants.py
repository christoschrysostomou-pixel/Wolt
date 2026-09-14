"""Shared constants for Metro Cyprus monthly picker-metrics extracts.

The May–June 2026 source file is a Looker-style export of delivered Wolt
grocery orders for the seven METRO Express Cyprus venues, with optional
goods ratings and customer comments.
"""

from __future__ import annotations

MONTHLY_PICKER_COLUMNS = [
    "Venue Name",
    "Purchase ID",
    "Dynamic Time Delivered",
    "Order Number",
    "Rating of Goods",
    "Goods Items Full Amount",
    "Customer Feedback",
]

METRO_CYPRUS_VENUE_NAMES = [
    "METRO Express Agias Fylaxeos",
    "METRO Express Aglantzia",
    "METRO Express Larnaca",
    "METRO Express Mouttagiaka",
    "METRO Express Paralimni",
    "METRO Express Platy",
    "METRO Express Strovolos",
]

# Looker "Dynamic Time Delivered" follows the venue local clock.
VENUE_TIMEZONE = "Asia/Nicosia"

# Wolt prod Snowflake (Looker explore core/f_purchases).
SNOWFLAKE_ACCOUNT = "doordash-ig78751_aws_eu_west_1"
SNOWFLAKE_WAREHOUSE = "EXPLORATION"
SNOWFLAKE_DATABASE = "PRODUCTION"
SNOWFLAKE_ROLE = "base_user"
SNOWFLAKE_USER = "christos.chrysostomou@wolt.com"
QUERY_TAG = "agentskills:using-snowflake"
