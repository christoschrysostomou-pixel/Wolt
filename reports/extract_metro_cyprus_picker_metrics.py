#!/usr/bin/env python3
"""Extract Metro Cyprus monthly picker metrics from Wolt Snowflake.

Recreates the May–June 2026 Looker `core/f_purchases` export for another
month (default: August 2026).

Requires an interactive Snowflake SSO session via the `snow` CLI
(DoorDash Okta → Snowflake Production (Wolt)).

Example:

    python3 reports/extract_metro_cyprus_picker_metrics.py --month 2026-08
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from reports.metro_cyprus_picker_constants import (  # noqa: E402
    METRO_CYPRUS_VENUE_NAMES,
    MONTHLY_PICKER_COLUMNS,
    QUERY_TAG,
    SNOWFLAKE_ACCOUNT,
    SNOWFLAKE_DATABASE,
    SNOWFLAKE_ROLE,
    SNOWFLAKE_USER,
    SNOWFLAKE_WAREHOUSE,
    VENUE_TIMEZONE,
)
from sql.metro_cyprus_picker_metrics import EXTRACT_SQL_TEMPLATE  # noqa: E402


class SnowflakeError(RuntimeError):
    pass


PURCHASE_TABLE_CANDIDATES = [
    "PRODUCTION.DWH.F_PURCHASES",
    "PRODUCTION.DBT.F_PURCHASES",
    "PRODUCTION.CORE.F_PURCHASES",
    "PRODUCTION.ANALYTICS.F_PURCHASES",
    "PRODUCTION.PUBLIC.F_PURCHASES",
]
VENUE_TABLE_CANDIDATES = [
    "PRODUCTION.DWH.D_VENUES",
    "PRODUCTION.DBT.D_VENUES",
    "PRODUCTION.CORE.D_VENUES",
    "PRODUCTION.ANALYTICS.D_VENUES",
    "PRODUCTION.PUBLIC.D_VENUES",
]
RATING_TABLE_CANDIDATES = [
    "PRODUCTION.DWH.F_PURCHASE_RATINGS",
    "PRODUCTION.DWH.F_PURCHASE_REVIEWS",
    "PRODUCTION.DBT.F_PURCHASE_RATINGS",
    "PRODUCTION.CORE.F_PURCHASE_RATINGS",
    "PRODUCTION.ANALYTICS.F_PURCHASE_RATINGS",
]

PURCHASE_ID_COLS = ["PURCHASE_ID", "ID"]
VENUE_ID_COLS = ["VENUE_ID", "ID"]
VENUE_NAME_COLS = ["VENUE_NAME", "NAME", "PUBLIC_NAME"]
TIME_DELIVERED_COLS = ["TIME_DELIVERED", "DELIVERED_AT", "TIME_COMPLETED", "DELIVERY_TIME"]
ORDER_NUMBER_COLS = ["VENUE_CONTENT_ID", "ORDER_NUMBER", "PURCHASE_NUMBER", "SHORT_CODE"]
GOODS_AMOUNT_COLS = [
    "GOODS_ITEMS_FULL_AMOUNT",
    "ITEMS_FULL_AMOUNT",
    "GOODS_GMV",
    "GMV_LOCAL",
    "TOTAL_PRICE",
    "ITEM_TOTAL",
    "REVENUE_LOCAL",
    "GROSS_VALUE_LOCAL",
]
STATUS_COLS = ["STATUS", "PURCHASE_STATUS", "DELIVERY_STATUS"]
RATING_COLS = ["RATING_OF_GOODS", "GOODS_RATING", "FOOD_RATING", "ITEM_RATING", "RATING"]
FEEDBACK_COLS = [
    "CUSTOMER_FEEDBACK",
    "CUSTOMER_COMMENT",
    "COMMENT_GOODS",
    "GOODS_COMMENT",
    "COMMENT",
    "RATING_COMMENT",
]


def find_snow_bin() -> str:
    plugin = Path(
        "/home/ubuntu/.cursor/plugins/cache/doordash-agentskills-release/"
        "20544622/a813d4ff37a257ec3ebb6b813399aba5e7e6fd53/bin/snow"
    )
    if plugin.exists():
        return str(plugin)
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
    snow = find_snow_bin()
    snow_dir = str(Path(snow).parent)
    env["PATH"] = f"{snow_dir}:{env.get('PATH', '')}"
    return env


def run_snow_sql(sql: str, *, fmt: str = "JSON") -> str:
    cmd = [find_snow_bin(), "sql", "-q", sql, "--format", fmt]
    proc = subprocess.run(cmd, env=snow_env(), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SnowflakeError(
            "snow sql failed.\n"
            f"stderr:\n{proc.stderr[-4000:]}\n"
            f"stdout:\n{proc.stdout[-2000:]}"
        )
    return proc.stdout


def tagged(sql: str) -> str:
    return f"ALTER SESSION SET QUERY_TAG = '{QUERY_TAG}'; {sql}"


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
    rows = parse_json_rows(run_snow_sql(sql))
    names: list[str] = []
    for row in rows:
        name = row.get("COLUMN_NAME") or row.get("column_name")
        if not name:
            name = next(iter(row.values()), None)
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


def search_tables(name_like: str, limit: int = 30) -> list[str]:
    sql = tagged(
        f"""
        SELECT TABLE_CATALOG || '.' || TABLE_SCHEMA || '.' || TABLE_NAME AS FQN
        FROM PRODUCTION.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME ILIKE '%{name_like}%'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
        LIMIT {limit}
        """
    )
    rows = parse_json_rows(run_snow_sql(sql))
    out: list[str] = []
    for row in rows:
        fqn = row.get("FQN") or row.get("fqn") or next(iter(row.values()), None)
        if fqn:
            out.append(str(fqn))
    return out


def sql_str_list(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    year, mon = (int(part) for part in month.split("-", 1))
    start = dt.date(year, mon, 1)
    end = dt.date(year + 1, 1, 1) if mon == 12 else dt.date(year, mon + 1, 1)
    return start, end


def utc_bound_expr(local_date: dt.date) -> str:
    local_ts = f"{local_date.isoformat()} 00:00:00"
    return (
        f"CONVERT_TIMEZONE('{VENUE_TIMEZONE}', 'UTC', TO_TIMESTAMP_NTZ('{local_ts}'))"
    )


def bootstrap_semantic_layer(path: Path) -> None:
    sql = tagged(
        """
        SELECT content
        FROM PRODUCTION._PRETZEL.SEMANTIC_MODEL_DOCS
        WHERE doc_type = 'bootstrap'
        ORDER BY version DESC
        LIMIT 1
        """
    )
    path.write_text(run_snow_sql(sql, fmt="CSV"), encoding="utf-8")


def require_column(columns: list[str], candidates: list[str], label: str, table: str) -> str:
    found = first_present(columns, candidates)
    if not found:
        raise SnowflakeError(
            f"{table} is missing {label}. Tried {candidates}. Columns: {columns}"
        )
    return found


def resolve_bindings() -> dict[str, str]:
    purchases_table = pick_table(PURCHASE_TABLE_CANDIDATES)
    venues_table = pick_table(VENUE_TABLE_CANDIDATES)
    if purchases_table is None:
        raise SnowflakeError(
            "Could not find a purchases fact table. "
            f"Tried {PURCHASE_TABLE_CANDIDATES}. Matches: {search_tables('PURCHASE')[:20]}"
        )
    if venues_table is None:
        raise SnowflakeError(
            "Could not find a venues dimension table. "
            f"Tried {VENUE_TABLE_CANDIDATES}. Matches: {search_tables('VENUE')[:20]}"
        )

    purchase_cols = describe_columns(purchases_table)
    venue_cols = describe_columns(venues_table)

    purchase_id_col = require_column(purchase_cols, PURCHASE_ID_COLS, "purchase id", purchases_table)
    purchase_venue_id_col = require_column(purchase_cols, ["VENUE_ID"], "venue id", purchases_table)
    time_delivered_col = require_column(
        purchase_cols, TIME_DELIVERED_COLS, "delivered timestamp", purchases_table
    )
    order_number_col = require_column(
        purchase_cols, ORDER_NUMBER_COLS, "order number", purchases_table
    )
    goods_amount_col = require_column(
        purchase_cols, GOODS_AMOUNT_COLS, "goods amount", purchases_table
    )
    venue_id_col = require_column(venue_cols, VENUE_ID_COLS, "venue id", venues_table)
    venue_name_col = require_column(venue_cols, VENUE_NAME_COLS, "venue name", venues_table)

    status_col = first_present(purchase_cols, STATUS_COLS)
    status_filter = ""
    if status_col:
        status_filter = (
            f"AND UPPER(TO_VARCHAR(p.{status_col})) IN "
            f"('DELIVERED', 'COMPLETED', 'OK', 'SUCCESS')"
        )

    purchase_rating_col = first_present(purchase_cols, RATING_COLS)
    purchase_feedback_col = first_present(purchase_cols, FEEDBACK_COLS)

    purchase_rating_select = ""
    ratings_join = ""
    rating_select = "NULL"
    feedback_select = "NULL"

    if purchase_rating_col:
        purchase_rating_select = f", p.{purchase_rating_col} AS rating_of_goods"
        rating_select = "p.rating_of_goods"
        if purchase_feedback_col:
            purchase_rating_select += f", p.{purchase_feedback_col} AS customer_feedback"
            feedback_select = "p.customer_feedback"
        else:
            purchase_rating_select += ", NULL AS customer_feedback"
            feedback_select = "p.customer_feedback"
    else:
        ratings_table = pick_table(RATING_TABLE_CANDIDATES)
        if ratings_table:
            rating_cols = describe_columns(ratings_table)
            rating_col = first_present(rating_cols, RATING_COLS)
            feedback_col = first_present(rating_cols, FEEDBACK_COLS)
            rating_purchase_id = first_present(rating_cols, PURCHASE_ID_COLS)
            if rating_col and rating_purchase_id:
                rating_select = f"r.{rating_col}"
                feedback_select = f"r.{feedback_col}" if feedback_col else "NULL"
                ratings_join = (
                    f"LEFT JOIN {ratings_table} r ON r.{rating_purchase_id} = p.purchase_id"
                )

    return {
        "purchases_table": purchases_table,
        "venues_table": venues_table,
        "purchase_id_col": purchase_id_col,
        "purchase_venue_id_col": purchase_venue_id_col,
        "time_delivered_col": time_delivered_col,
        "order_number_col": order_number_col,
        "goods_amount_col": goods_amount_col,
        "venue_id_col": venue_id_col,
        "venue_name_col": venue_name_col,
        "purchase_rating_select": purchase_rating_select,
        "rating_select": rating_select,
        "feedback_select": feedback_select,
        "ratings_join": ratings_join,
        "status_filter": status_filter,
        "purchase_cols": ",".join(purchase_cols),
        "venue_cols": ",".join(venue_cols),
    }


def build_extract_sql(bindings: dict[str, str], start: dt.date, end: dt.date) -> str:
    return EXTRACT_SQL_TEMPLATE.format(
        query_tag=QUERY_TAG,
        venue_id_col=bindings["venue_id_col"],
        venue_name_col=bindings["venue_name_col"],
        venues_table=bindings["venues_table"],
        venue_literals=sql_str_list(METRO_CYPRUS_VENUE_NAMES),
        purchase_id_col=bindings["purchase_id_col"],
        purchase_venue_id_col=bindings["purchase_venue_id_col"],
        time_delivered_col=bindings["time_delivered_col"],
        order_number_col=bindings["order_number_col"],
        goods_amount_col=bindings["goods_amount_col"],
        purchases_table=bindings["purchases_table"],
        start_utc_expr=utc_bound_expr(start),
        end_utc_expr=utc_bound_expr(end),
        status_filter=bindings["status_filter"],
        timezone=VENUE_TIMEZONE,
        rating_select=bindings["rating_select"],
        feedback_select=bindings["feedback_select"],
        ratings_join=bindings["ratings_join"],
        purchase_rating_select=bindings["purchase_rating_select"],
    )


def format_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.10f}".rstrip("0").rstrip(".")
    text = str(value).strip()
    if text.lower() in {"none", "null"}:
        return ""
    return text


def row_value(row: dict, column: str) -> object:
    for key, value in row.items():
        if str(key).strip('"').lower() == column.lower():
            return value
    return None


def write_csv(rows: list[dict], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MONTHLY_PICKER_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {column: format_cell(row_value(row, column)) for column in MONTHLY_PICKER_COLUMNS}
            )
    return len(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", default="2026-08", help="Calendar month, YYYY-MM.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/Metro_Cyprus_Monthly_Picker_Metrics_August_2026_with_customer_comments.csv"
        ),
    )
    parser.add_argument(
        "--bindings-json",
        type=Path,
        default=Path("data/snowflake_picker_bindings.json"),
    )
    parser.add_argument(
        "--sql-out",
        type=Path,
        default=Path("sql/generated_metro_cyprus_picker_metrics.sql"),
    )
    parser.add_argument("--skip-bootstrap", action="store_true")
    parser.add_argument("--whoami-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    start, end = month_bounds(args.month)
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
                "CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse, "
                "CURRENT_DATABASE() AS database"
            )
        )
    )
    print("session:", whoami, flush=True)
    if args.whoami_only:
        return 0

    if not args.skip_bootstrap:
        bootstrap_path = Path("/tmp/wolt_semantic_bootstrap.csv")
        print("Loading Wolt semantic-layer bootstrap…", flush=True)
        try:
            bootstrap_semantic_layer(bootstrap_path)
            print(
                f"Wrote bootstrap to {bootstrap_path} ({bootstrap_path.stat().st_size} bytes)",
                flush=True,
            )
        except SnowflakeError as exc:
            print(f"WARNING: semantic bootstrap failed (continuing): {exc}", flush=True)

    print("Resolving purchases/venues/ratings tables…", flush=True)
    bindings = resolve_bindings()
    args.bindings_json.parent.mkdir(parents=True, exist_ok=True)
    args.bindings_json.write_text(json.dumps(bindings, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote bindings to {args.bindings_json}", flush=True)

    sql = build_extract_sql(bindings, start, end)
    args.sql_out.parent.mkdir(parents=True, exist_ok=True)
    args.sql_out.write_text(sql.strip() + "\n", encoding="utf-8")
    print(f"Wrote SQL to {args.sql_out}", flush=True)

    print(f"Extracting {args.month} ({start} ≤ t < {end})…", flush=True)
    raw = run_snow_sql(sql, fmt="CSV")
    lines = raw.splitlines()
    header_idx = 0
    for idx, line in enumerate(lines):
        if "venue name" in line.lower() and "purchase id" in line.lower():
            header_idx = idx
            break
    csv_text = "\n".join(lines[header_idx:]) + "\n"
    tmp_csv = Path("/tmp/metro_cyprus_picker_extract_raw.csv")
    tmp_csv.write_text(csv_text, encoding="utf-8")
    with tmp_csv.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    count = write_csv(rows, args.output)
    print(f"Wrote {count} rows to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SnowflakeError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(2)
