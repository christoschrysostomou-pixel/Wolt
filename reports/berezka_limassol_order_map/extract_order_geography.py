#!/usr/bin/env python3
"""Pull aggregated Berezka Cuisine Limassol order geography from Wolt Snowflake.

Requires an interactive `snow` SSO session (DoorDash Okta → Snowflake
Production Wolt). Writes only area-level counts — never street addresses.

Example:

    python3 reports/berezka_limassol_order_map/extract_order_geography.py --months 12
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUERY_TAG = "agentskills:berezka-limassol-order-map"

SNOWFLAKE_ACCOUNT = "doordash-ig78751_aws_eu_west_1"
SNOWFLAKE_WAREHOUSE = "EXPLORATION"
SNOWFLAKE_DATABASE = "PRODUCTION"
SNOWFLAKE_ROLE = "base_user"
SNOWFLAKE_USER = "christos.chrysostomou@wolt.com"
VENUE_TIMEZONE = "Asia/Nicosia"
MIN_ORDERS_PER_AREA = 5
VENUE_NAME_PATTERN = "%berezka%"

VENUE_TABLES = [
    "PRODUCTION.INTERMEDIATE.D_VENUES",
    "PRODUCTION.MERCHANT.ACCOUNT_MANAGEMENT_REPORTING",
    "PRODUCTION.DWH.D_VENUES",
    "PRODUCTION.CORE.D_VENUES",
]
PURCHASE_TABLES = [
    "PRODUCTION.INTERMEDIATE.F_PURCHASES",
    "PRODUCTION.STAGING.PURCHASES",
    "PRODUCTION.DWH.F_PURCHASES",
    "PRODUCTION.CORE.F_PURCHASES",
]

LAT_CANDIDATES = [
    "DELIVERY_LATITUDE",
    "DROPOFF_LATITUDE",
    "DROPOFF_LAT",
    "CUSTOMER_LATITUDE",
    "CUSTOMER_LAT",
    "DESTINATION_LATITUDE",
    "DESTINATION_LAT",
    "LOCATION_LATITUDE",
    "LOCATION_LAT",
    "LATITUDE",
    "LAT",
]
LNG_CANDIDATES = [
    "DELIVERY_LONGITUDE",
    "DELIVERY_LNG",
    "DROPOFF_LONGITUDE",
    "DROPOFF_LNG",
    "DROPOFF_LON",
    "CUSTOMER_LONGITUDE",
    "CUSTOMER_LNG",
    "CUSTOMER_LON",
    "DESTINATION_LONGITUDE",
    "DESTINATION_LNG",
    "LOCATION_LONGITUDE",
    "LOCATION_LNG",
    "LONGITUDE",
    "LON",
    "LNG",
]
AREA_CANDIDATES = [
    "DELIVERY_POSTAL_CODE",
    "CUSTOMER_POSTAL_CODE",
    "POSTAL_CODE",
    "ZIP_CODE",
    "DELIVERY_DISTRICT",
    "CUSTOMER_DISTRICT",
    "DISTRICT",
    "NEIGHBORHOOD",
    "NEIGHBOURHOOD",
    "CITY_DISTRICT",
    "AREA_NAME",
    "DELIVERY_CITY_AREA",
    "H3_INDEX",
    "H3_CELL",
    "GEOHASH",
]
VENUE_ID_CANDIDATES = ["VENUE_ID", "ID"]
VENUE_NAME_CANDIDATES = ["VENUE_NAME", "NAME", "PUBLIC_NAME", "BRAND_NAME"]
CITY_CANDIDATES = ["VENUE_CITY", "CITY", "CITY_NAME"]
COUNTRY_CANDIDATES = ["VENUE_COUNTRY", "COUNTRY", "COUNTRY_CODE"]
PURCHASE_ID_CANDIDATES = ["PURCHASE_ID", "ID"]
TIME_DELIVERED_CANDIDATES = [
    "TIME_DELIVERED_UTC",
    "TIME_DELIVERED",
    "DELIVERED_AT",
    "TIME_COMPLETED",
]
GOV_CANDIDATES = [
    "GOODS_ITEMS_FULL_AMOUNT",
    "GMV_LOCAL",
    "GROSS_VALUE_LOCAL",
    "ITEMS_FULL_AMOUNT",
    "TOTAL_PRICE",
]
STATUS_CANDIDATES = ["STATUS", "PURCHASE_STATUS"]
MARKETPLACE_FLAGS = ["IS_VALID_MARKETPLACE_PURCHASE", "IS_MARKETPLACE"]


class SnowflakeError(RuntimeError):
    pass


def find_snow_bin() -> str:
    plugin_root = Path(
        "/home/ubuntu/.cursor/plugins/cache/doordash-agentskills-release"
    )
    if plugin_root.exists():
        matches = sorted(plugin_root.glob("*/**/bin/snow"))
        if matches:
            return str(matches[0])
    found = shutil.which("snow")
    if not found:
        raise SnowflakeError("`snow` CLI is not on PATH")
    return found


def snow_env() -> dict[str, str]:
    env = os.environ.copy()
    env["SNOWFLAKE_CONNECTIONS_DEFAULT_ACCOUNT"] = SNOWFLAKE_ACCOUNT
    env["SNOWFLAKE_CONNECTIONS_DEFAULT_USER"] = env.get(
        "SNOWFLAKE_CONNECTIONS_DEFAULT_USER", SNOWFLAKE_USER
    )
    env["SNOWFLAKE_CONNECTIONS_DEFAULT_WAREHOUSE"] = SNOWFLAKE_WAREHOUSE
    env["SNOWFLAKE_CONNECTIONS_DEFAULT_DATABASE"] = SNOWFLAKE_DATABASE
    env["SNOWFLAKE_CONNECTIONS_DEFAULT_ROLE"] = SNOWFLAKE_ROLE
    snow_dir = str(Path(find_snow_bin()).parent)
    env["PATH"] = f"{snow_dir}:{env.get('PATH', '')}"
    return env


def tagged(sql: str) -> str:
    return f"ALTER SESSION SET QUERY_TAG = '{QUERY_TAG}'; {sql}"


def run_snow_sql(sql: str, *, fmt: str = "JSON") -> str:
    cmd = [find_snow_bin(), "sql", "-q", sql, "--format", fmt]
    proc = subprocess.run(cmd, env=snow_env(), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SnowflakeError(
            "snow sql failed.\n"
            f"stderr:\n{(proc.stderr or '')[-4000:]}\n"
            f"stdout:\n{(proc.stdout or '')[-2000:]}"
        )
    return proc.stdout


def parse_json_rows(raw: str) -> list[dict]:
    text = raw.strip()
    if not text:
        return []
    decoder = json.JSONDecoder()
    idx = 0
    docs: list[object] = []
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        doc, end = decoder.raw_decode(text, idx)
        docs.append(doc)
        idx = end
    if not docs:
        raise SnowflakeError(f"Could not parse snow JSON output:\n{text[:500]}")
    result = docs[-1]
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    if isinstance(result, dict):
        for key in ("data", "rows", "result"):
            value = result.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [result]
    return []


def table_exists(fqn: str) -> bool:
    database, schema, table = fqn.split(".")
    sql = tagged(
        f"""
        SELECT COUNT(*) AS n
        FROM {database}.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{schema}'
          AND TABLE_NAME = '{table}'
        """
    )
    try:
        rows = parse_json_rows(run_snow_sql(sql))
    except SnowflakeError:
        return False
    if not rows:
        return False
    return int(next(iter(rows[0].values()))) > 0


def describe_columns(fqn: str) -> list[str]:
    database, schema, table = fqn.split(".")
    sql = tagged(
        f"""
        SELECT COLUMN_NAME
        FROM {database}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{schema}'
          AND TABLE_NAME = '{table}'
        ORDER BY ORDINAL_POSITION
        """
    )
    names: list[str] = []
    for row in parse_json_rows(run_snow_sql(sql)):
        name = row.get("COLUMN_NAME") or row.get("column_name") or next(iter(row.values()), None)
        if name:
            names.append(str(name).upper())
    return names


def first_present(columns: list[str], candidates: list[str]) -> str | None:
    available = {c.upper() for c in columns}
    for name in candidates:
        if name.upper() in available:
            return name
    return None


def pick_table(candidates: list[str]) -> str | None:
    for fqn in candidates:
        if table_exists(fqn):
            return fqn
    return None


def search_geo_columns(limit: int = 80) -> list[dict]:
    sql = tagged(
        f"""
        SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM PRODUCTION.INFORMATION_SCHEMA.COLUMNS
        WHERE (
              COLUMN_NAME ILIKE '%LAT%'
           OR COLUMN_NAME ILIKE '%LON%'
           OR COLUMN_NAME ILIKE '%LNG%'
           OR COLUMN_NAME ILIKE '%GEOHASH%'
           OR COLUMN_NAME ILIKE '%H3%'
           OR COLUMN_NAME ILIKE '%POSTAL%'
           OR COLUMN_NAME ILIKE '%DISTRICT%'
           OR COLUMN_NAME ILIKE '%NEIGHBO%'
        )
          AND TABLE_SCHEMA IN ('INTERMEDIATE', 'STAGING', 'DWH', 'CORE', 'MERCHANT', 'PUBLIC')
        ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        LIMIT {limit}
        """
    )
    return parse_json_rows(run_snow_sql(sql))


def require_column(columns: list[str], candidates: list[str], label: str, table: str) -> str:
    found = first_present(columns, candidates)
    if not found:
        raise SnowflakeError(f"{table} is missing {label}. Tried {candidates}.")
    return found


def fetch_venues(venue_table: str, venue_cols: list[str]) -> list[dict]:
    venue_id = require_column(venue_cols, VENUE_ID_CANDIDATES, "venue id", venue_table)
    venue_name = require_column(venue_cols, VENUE_NAME_CANDIDATES, "venue name", venue_table)
    city = first_present(venue_cols, CITY_CANDIDATES)
    country = first_present(venue_cols, COUNTRY_CANDIDATES)
    extra = []
    where = [f"LOWER(v.{venue_name}) LIKE '{VENUE_NAME_PATTERN}'"]
    if city:
        extra.append(f"v.{city} AS venue_city")
        where.append(
            f"(v.{city} ILIKE '%limassol%' OR v.{city} ILIKE '%lemesos%' OR v.{city} IS NULL)"
        )
    if country:
        extra.append(f"v.{country} AS venue_country")
        where.append(
            f"(UPPER(TO_VARCHAR(v.{country})) IN ('CYP', 'CY', 'CYPRUS') OR v.{country} IS NULL)"
        )
    extra_sql = (", " + ", ".join(extra)) if extra else ""
    sql = tagged(
        f"""
        SELECT
            v.{venue_id} AS venue_id,
            v.{venue_name} AS venue_name
            {extra_sql}
        FROM {venue_table} v
        WHERE {' AND '.join(where)}
        QUALIFY ROW_NUMBER() OVER (PARTITION BY v.{venue_id} ORDER BY v.{venue_name}) = 1
        ORDER BY venue_name
        """
    )
    return parse_json_rows(run_snow_sql(sql))


def geo_select(purchase_cols: list[str], purchases_table: str) -> tuple[str, str, str]:
    """Return (area_expr, lat_expr, lng_expr) for GROUP BY grain."""
    lat = first_present(purchase_cols, LAT_CANDIDATES)
    lng = first_present(purchase_cols, LNG_CANDIDATES)
    area = first_present(purchase_cols, AREA_CANDIDATES)
    if lat and lng:
        lat_expr = f"p.{lat}"
        lng_expr = f"p.{lng}"
        # ~1.1 km cells (2 decimal degrees). Avoids depending on H3 functions.
        area_expr = (
            f"CONCAT(TO_VARCHAR(ROUND({lat_expr}::FLOAT, 2)), ',', "
            f"TO_VARCHAR(ROUND({lng_expr}::FLOAT, 2)))"
        )
        return area_expr, lat_expr, lng_expr
    if area:
        return f"TO_VARCHAR(p.{area})", "NULL", "NULL"
    raise SnowflakeError(
        f"{purchases_table} has no delivery lat/lng, H3, geohash, postal, or district column. "
        f"Columns: {purchase_cols}"
    )


def build_orders_sql(
    *,
    purchases_table: str,
    purchase_cols: list[str],
    venue_table: str,
    venue_cols: list[str],
    months: int,
) -> str:
    purchase_venue_id = require_column(purchase_cols, ["VENUE_ID"], "venue id", purchases_table)
    time_col = require_column(purchase_cols, TIME_DELIVERED_CANDIDATES, "delivered time", purchases_table)
    purchase_id = first_present(purchase_cols, PURCHASE_ID_CANDIDATES) or "*"
    gov = first_present(purchase_cols, GOV_CANDIDATES)
    status = first_present(purchase_cols, STATUS_CANDIDATES)
    marketplace = first_present(purchase_cols, MARKETPLACE_FLAGS)
    venue_id = require_column(venue_cols, VENUE_ID_CANDIDATES, "venue id", venue_table)
    venue_name = require_column(venue_cols, VENUE_NAME_CANDIDATES, "venue name", venue_table)
    city = first_present(venue_cols, CITY_CANDIDATES)
    country = first_present(venue_cols, COUNTRY_CANDIDATES)
    area_expr, lat_expr, lng_expr = geo_select(purchase_cols, purchases_table)

    filters = [
        f"LOWER(v.{venue_name}) LIKE '{VENUE_NAME_PATTERN}'",
        (
            f"CONVERT_TIMEZONE('UTC', '{VENUE_TIMEZONE}', p.{time_col}) >= "
            f"DATEADD('month', -{months}, DATE_TRUNC('month', CONVERT_TIMEZONE('UTC', '{VENUE_TIMEZONE}', CURRENT_TIMESTAMP())))"
        ),
    ]
    if city:
        filters.append(
            f"(v.{city} ILIKE '%limassol%' OR v.{city} ILIKE '%lemesos%')"
        )
    if country:
        filters.append(f"UPPER(TO_VARCHAR(v.{country})) IN ('CYP', 'CY', 'CYPRUS')")
    if status:
        filters.append(
            f"UPPER(TO_VARCHAR(p.{status})) IN ('DELIVERED', 'COMPLETED', 'OK', 'SUCCESS')"
        )
    if marketplace:
        filters.append(f"p.{marketplace} = TRUE")

    gov_expr = f"SUM(p.{gov})" if gov else "NULL"
    count_expr = (
        f"COUNT(DISTINCT p.{purchase_id})" if purchase_id != "*" else "COUNT(*)"
    )
    return tagged(
        f"""
        SELECT
            TO_VARCHAR({area_expr}) AS area_name,
            AVG({lat_expr}) AS lat,
            AVG({lng_expr}) AS lng,
            {count_expr} AS orders,
            {gov_expr} AS gov_local,
            COUNT(DISTINCT v.{venue_id}) AS venue_count
        FROM {purchases_table} p
        JOIN {venue_table} v
          ON v.{venue_id} = p.{purchase_venue_id}
        WHERE {' AND '.join(filters)}
          AND {area_expr} IS NOT NULL
        GROUP BY 1
        HAVING {count_expr} >= {MIN_ORDERS_PER_AREA}
        ORDER BY orders DESC
        """
    )


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "area_name",
        "postal_code",
        "lat",
        "lng",
        "orders",
        "gov_local",
        "venue_count",
        "share_pct",
    ]
    total = sum(float(r.get("ORDERS") or r.get("orders") or 0) for r in rows) or 1
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            orders = float(row.get("ORDERS") or row.get("orders") or 0)
            area_name = row.get("AREA_NAME") or row.get("area_name") or ""
            postal = str(row.get("POSTAL_CODE") or row.get("postal_code") or "")
            digits = str(area_name).split(".")[0]
            if not postal and digits.isdigit() and len(digits) == 4:
                postal = digits
            writer.writerow(
                {
                    "area_name": area_name,
                    "postal_code": postal,
                    "lat": row.get("LAT") or row.get("lat") or "",
                    "lng": row.get("LNG") or row.get("lng") or "",
                    "orders": int(orders),
                    "gov_local": row.get("GOV_LOCAL") or row.get("gov_local") or "",
                    "venue_count": row.get("VENUE_COUNT") or row.get("venue_count") or "",
                    "share_pct": round(100.0 * orders / total, 2),
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--output-dir", type=Path, default=HERE / "output")
    parser.add_argument("--whoami-only", action="store_true")
    parser.add_argument("--skip-geo-search", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    user = snow_env()["SNOWFLAKE_CONNECTIONS_DEFAULT_USER"]
    print(
        f"Connecting to Snowflake {SNOWFLAKE_ACCOUNT} as {user} "
        f"(warehouse={SNOWFLAKE_WAREHOUSE}, role={SNOWFLAKE_ROLE})",
        flush=True,
    )
    whoami = parse_json_rows(
        run_snow_sql(
            tagged(
                "SELECT CURRENT_USER() AS user_name, CURRENT_ACCOUNT() AS account, "
                "CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse"
            )
        )
    )
    print("session:", whoami, flush=True)
    if args.whoami_only:
        return 0

    venue_table = pick_table(VENUE_TABLES)
    purchases_table = pick_table(PURCHASE_TABLES)
    if venue_table is None:
        raise SnowflakeError(f"No venue table. Tried {VENUE_TABLES}")
    if purchases_table is None:
        raise SnowflakeError(f"No purchases table. Tried {PURCHASE_TABLES}")

    venue_cols = describe_columns(venue_table)
    purchase_cols = describe_columns(purchases_table)
    bindings = {
        "venue_table": venue_table,
        "purchases_table": purchases_table,
        "venue_cols": venue_cols,
        "purchase_cols": purchase_cols,
        "extracted_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "months": args.months,
        "min_orders_per_area": MIN_ORDERS_PER_AREA,
    }
    (args.output_dir / "snowflake_bindings.json").write_text(
        json.dumps(bindings, indent=2) + "\n", encoding="utf-8"
    )
    print(f"venues={venue_table} purchases={purchases_table}", flush=True)

    venues = fetch_venues(venue_table, venue_cols)
    (args.output_dir / "matched_venues.json").write_text(
        json.dumps(venues, indent=2) + "\n", encoding="utf-8"
    )
    print(f"matched {len(venues)} Berezka venue(s)", flush=True)
    if not venues:
        raise SnowflakeError("No Berezka venues matched in Limassol / CYP.")

    if not args.skip_geo_search:
        geo_cols = search_geo_columns()
        (args.output_dir / "geo_column_search.json").write_text(
            json.dumps(geo_cols, indent=2) + "\n", encoding="utf-8"
        )

    sql = build_orders_sql(
        purchases_table=purchases_table,
        purchase_cols=purchase_cols,
        venue_table=venue_table,
        venue_cols=venue_cols,
        months=args.months,
    )
    (args.output_dir / "generated_order_geography.sql").write_text(sql.strip() + "\n", encoding="utf-8")
    print("aggregating delivered orders by area…", flush=True)
    rows = parse_json_rows(run_snow_sql(sql))
    write_csv(rows, args.output_dir / "areas.csv")
    print(f"wrote {len(rows)} areas to {args.output_dir / 'areas.csv'}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SnowflakeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
