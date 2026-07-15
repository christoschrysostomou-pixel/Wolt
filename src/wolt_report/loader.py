"""Data loading abstraction.

Two implementations are provided:

* :class:`CsvLoader` reads tidy CSV exports from ``data_dir``. This is the
  default and works entirely offline.
* :class:`SnowflakeLoader` runs the SQL in ``queries.sql`` against Snowflake.
  It requires ``snowflake-connector-python`` and credentials supplied through
  environment variables. It is intentionally lazy-imported so the rest of the
  package has no hard dependency on Snowflake.

Both return a :class:`ReportData` bundle whose dataframes conform to the columns
declared in :mod:`wolt_report.schema`.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import schema
from .config import Config

_DATETIME_COLS = {
    "orders": ["order_datetime", "delivered_datetime"],
    "monthly_picker": ["dynamic_time_delivered"],
}
_DATE_COLS = {
    "offline": ["date"],
    "picker_usage": ["date"],
}


@dataclass
class ReportData:
    orders: pd.DataFrame
    offline: pd.DataFrame
    financials: pd.DataFrame
    picker_usage: pd.DataFrame
    monthly_picker: pd.DataFrame

    def for_venue(self, venue_id: str) -> "ReportData":
        return ReportData(
            orders=self.orders[self.orders["venue_id"] == venue_id].copy(),
            offline=self.offline[self.offline["venue_id"] == venue_id].copy(),
            financials=self.financials[self.financials["venue_id"] == venue_id].copy(),
            picker_usage=self.picker_usage[self.picker_usage["venue_id"] == venue_id].copy(),
            monthly_picker=self.monthly_picker[
                self.monthly_picker["venue_name"].isin(
                    self.orders.loc[self.orders["venue_id"] == venue_id, "venue_name"].unique()
                )
            ].copy(),
        )


class BaseLoader:
    def __init__(self, config: Config):
        self.config = config

    def load(self) -> ReportData:  # pragma: no cover - interface
        raise NotImplementedError


class CsvLoader(BaseLoader):
    """Read tidy CSV exports from ``config.data_dir``."""

    FILES = {
        "orders": "orders.csv",
        "offline": "offline.csv",
        "financials": "financials.csv",
        "picker_usage": "picker_usage.csv",
        "monthly_picker": "monthly_picker.csv",
    }

    def load(self) -> ReportData:
        frames: dict[str, pd.DataFrame] = {}
        for key, filename in self.FILES.items():
            path = self.config.data_dir / filename
            if not path.exists():
                raise FileNotFoundError(
                    f"Expected data file not found: {path}. Generate sample data "
                    f"with `python -m wolt_report.cli --generate-sample` or export "
                    f"real data to this location."
                )
            df = pd.read_csv(path)
            for col in _DATETIME_COLS.get(key, []):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
            for col in _DATE_COLS.get(key, []):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col]).dt.date
            frames[key] = df
        return ReportData(**frames)


class SnowflakeLoader(BaseLoader):
    """Pull live data from Snowflake using the queries in ``queries.sql``.

    Credentials are read from the environment:
        SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (or
        SNOWFLAKE_AUTHENTICATOR / SNOWFLAKE_TOKEN), SNOWFLAKE_WAREHOUSE,
        SNOWFLAKE_DATABASE, SNOWFLAKE_SCHEMA, SNOWFLAKE_ROLE.
    """

    def _connect(self):  # pragma: no cover - needs live credentials
        import snowflake.connector  # lazy import

        return snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"],
            user=os.environ["SNOWFLAKE_USER"],
            password=os.environ.get("SNOWFLAKE_PASSWORD"),
            authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR"),
            token=os.environ.get("SNOWFLAKE_TOKEN"),
            warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"),
            database=os.environ.get("SNOWFLAKE_DATABASE"),
            schema=os.environ.get("SNOWFLAKE_SCHEMA"),
            role=os.environ.get("SNOWFLAKE_ROLE"),
        )

    def _queries(self) -> dict[str, str]:
        text = (Path(__file__).parent / "queries.sql").read_text(encoding="utf-8")
        queries: dict[str, str] = {}
        current: str | None = None
        buf: list[str] = []
        for line in text.splitlines():
            if line.startswith("-- name:"):
                if current:
                    queries[current] = "\n".join(buf).strip()
                current = line.split(":", 1)[1].strip()
                buf = []
            elif current:
                buf.append(line)
        if current:
            queries[current] = "\n".join(buf).strip()
        return queries

    def load(self) -> ReportData:  # pragma: no cover - needs live credentials
        params = {
            "start_date": self.config.period.start.isoformat(),
            "end_date": self.config.period.end.isoformat(),
            "venue_ids": tuple(self.config.venue_ids),
            # Monthly picker metrics use a month-to-date window ending at the
            # report end date.
            "month_start": self.config.period.end.replace(day=1).isoformat(),
        }
        queries = self._queries()
        conn = self._connect()
        try:
            frames: dict[str, pd.DataFrame] = {}
            for key in ["orders", "offline", "financials", "picker_usage", "monthly_picker"]:
                cur = conn.cursor()
                try:
                    cur.execute(queries[key], params)
                    cols = [c[0].lower() for c in cur.description]
                    frames[key] = pd.DataFrame(cur.fetchall(), columns=cols)
                finally:
                    cur.close()
        finally:
            conn.close()

        for col in _DATETIME_COLS["orders"]:
            frames["orders"][col] = pd.to_datetime(frames["orders"][col])
        frames["monthly_picker"]["dynamic_time_delivered"] = pd.to_datetime(
            frames["monthly_picker"]["dynamic_time_delivered"]
        )
        for key in ("offline", "picker_usage"):
            frames[key]["date"] = pd.to_datetime(frames[key]["date"]).dt.date
        return ReportData(**frames)


def get_loader(config: Config) -> BaseLoader:
    source = config.data_source.lower()
    if source == "snowflake":
        return SnowflakeLoader(config)
    if source == "csv":
        return CsvLoader(config)
    raise ValueError(f"Unknown data_source: {config.data_source!r}")


def _validate(df: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Table '{name}' is missing columns: {missing}")


def validate(data: ReportData) -> None:
    """Sanity-check that loaded data matches the declared schema."""
    _validate(data.orders, schema.ORDERS_COLUMNS, "orders")
    _validate(data.offline, schema.OFFLINE_COLUMNS, "offline")
    _validate(data.financials, schema.FINANCIALS_COLUMNS, "financials")
    _validate(data.picker_usage, schema.PICKER_USAGE_COLUMNS, "picker_usage")
    _validate(data.monthly_picker, schema.MONTHLY_PICKER_COLUMNS, "monthly_picker")


__all__ = [
    "ReportData",
    "BaseLoader",
    "CsvLoader",
    "SnowflakeLoader",
    "get_loader",
    "validate",
]
