"""Shared data model for Metro Cyprus weekly report generators.

Both the PDF and spreadsheet report generators read the same long-format CSV
exports and share the metric constants, loading, and aggregation logic so the
two outputs never drift from each other.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

MERCHANT_NAME = "Metro Cyprus"

PURCHASE_METRICS = [
    "Group orders",
    "Orders per venue",
    "Venue Group Gross Value",
    "Gross Value per Venue",
    "Orders per Hour",
    "Order per Day per Store",
    "Average Basket Value per Venue",
]

WOLT_PLUS_METRICS = [
    "W+ Orders",
    "W+ New Users",
]

OPERATIONS_METRICS = [
    "POFR Group %",
    "POFR %",
    "Substitution %",
    "% Unfulfilled Items",
    "Ops Performance",
    "Punctuality per Venue",
    "Average Delivery Time per Venue",
    "Prep Time per Venue",
    "Marker Ready Performance",
    "% Late Orders",
]

QUALITY_METRICS = [
    "Rejections % per Venue",
    "Rating per Store",
    "Offline % per Venue (New)",
    "Offline Hours per Venue (New)",
    "Lost sales %GOV",
    "Lost sales GOV EUR",
    "Rejections",
    "Substitutions",
    "Cancellation",
    "Unfulfilled items",
]

ADDITION_DEDUCTION_METRICS = [
    "Rejection Reason",
    "Addition Breakdown",
    "Deduction Breakdown",
    "Courier Fee Breakdown",
]

PICKER_METRICS = [
    "Picker Usage per Store",
]

MONTHLY_PICKER_COLUMNS = [
    "Venue Name",
    "Purchase ID",
    "Dynamic Time Delivered",
    "Order Number",
    "Rating of Goods",
    "Goods Items Full Amount",
    "Customer Feedback",
]
OPTIONAL_MONTHLY_PICKER_COLUMNS = {"Customer Feedback"}

ALL_WEEKLY_METRICS = (
    PURCHASE_METRICS
    + WOLT_PLUS_METRICS
    + OPERATIONS_METRICS
    + QUALITY_METRICS
    + ADDITION_DEDUCTION_METRICS
    + PICKER_METRICS
)

REPORT_SECTIONS = [
    ("Purchases", PURCHASE_METRICS),
    ("Wolt+", WOLT_PLUS_METRICS),
    ("Operations", OPERATIONS_METRICS),
    ("Quality", QUALITY_METRICS),
    ("Additions & Deductions", ADDITION_DEDUCTION_METRICS),
    ("Picker", PICKER_METRICS),
]

PER_VENUE_SUMMARY_METRICS = [
    "Orders per venue",
    "Gross Value per Venue",
    "Average Basket Value per Venue",
    "POFR %",
    "Substitution %",
    "% Unfulfilled Items",
    "Punctuality per Venue",
    "Average Delivery Time per Venue",
    "Prep Time per Venue",
    "% Late Orders",
    "Rejections % per Venue",
    "Rating per Store",
    "Offline % per Venue (New)",
    "Offline Hours per Venue (New)",
    "Lost sales %GOV",
    "Picker Usage per Store",
]

COUNT_OR_CURRENCY_HINTS = (
    "orders",
    "gross value",
    "gov",
    "hours",
    "items",
    "addition",
    "deduction",
    "courier fee",
    "rejections",
    "substitutions",
    "cancellation",
)


@dataclass(frozen=True)
class MetricRecord:
    metric: str
    value: float
    venue_name: str = ""
    unit: str = ""
    dimension: str = ""
    dimension_value: str = ""
    period_start: str = ""
    period_end: str = ""


def previous_full_week(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(days=1)
    return start, end


def parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    return datetime.strptime(value, "%Y-%m-%d").date()


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_weekly_metrics(path: Path) -> list[MetricRecord]:
    if not path.exists():
        return []

    records: list[MetricRecord] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            metric = clean(row.get("metric"))
            raw_value = clean(row.get("value"))
            if not metric and not raw_value:
                continue
            if not metric:
                raise ValueError(f"{path}:{line_number} is missing metric")
            try:
                value = float(raw_value)
            except ValueError as exc:
                raise ValueError(
                    f"{path}:{line_number} has non-numeric value {raw_value!r}"
                ) from exc

            records.append(
                MetricRecord(
                    metric=metric,
                    value=value,
                    venue_name=clean(row.get("venue_name")),
                    unit=clean(row.get("unit")),
                    dimension=clean(row.get("dimension")),
                    dimension_value=clean(row.get("dimension_value")),
                    period_start=clean(row.get("period_start")),
                    period_end=clean(row.get("period_end")),
                )
            )
    return records


def load_monthly_picker(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [
            column
            for column in MONTHLY_PICKER_COLUMNS
            if column not in OPTIONAL_MONTHLY_PICKER_COLUMNS and column not in reader.fieldnames
        ]
        if missing:
            raise ValueError(
                f"{path} is missing required monthly picker columns: {', '.join(missing)}"
            )
        return [{column: clean(row.get(column)) for column in MONTHLY_PICKER_COLUMNS} for row in reader]


def output_path_for(start: date, end: date, extension: str) -> Path:
    return Path(
        "reports/output/"
        f"metro_cyprus_weekly_report_{start.isoformat()}_to_{end.isoformat()}.{extension}"
    )


def records_for_metric(records: Iterable[MetricRecord], metric: str) -> list[MetricRecord]:
    return [record for record in records if record.metric == metric]


def records_for_venue(records: Iterable[MetricRecord], venue_name: str) -> list[MetricRecord]:
    return [record for record in records if record.venue_name == venue_name]


def known_venues(records: Iterable[MetricRecord]) -> list[str]:
    return sorted({record.venue_name for record in records if record.venue_name})


def aggregate_metric(records: Iterable[MetricRecord], metric: str) -> tuple[float | None, str]:
    metric_records = records_for_metric(records, metric)
    if not metric_records:
        return None, ""

    values = [record.value for record in metric_records]
    unit = next((record.unit for record in metric_records if record.unit), "")
    metric_lower = metric.lower()
    if "%" in metric or "rating" in metric_lower or "time" in metric_lower or "performance" in metric_lower:
        return sum(values) / len(values), unit
    if any(hint in metric_lower for hint in COUNT_OR_CURRENCY_HINTS):
        return sum(values), unit
    return sum(values) / len(values), unit


def format_value(value: float | None, unit: str = "") -> str:
    if value is None:
        return "N/A"
    if unit == "%":
        return f"{value:.1f}%"
    if unit.upper() in {"EUR", "€"}:
        return f"EUR {value:,.0f}"
    if unit.lower() in {"min", "mins", "minutes"}:
        return f"{value:.1f} min"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return f"{value:.0f}"
    return f"{value:.1f}{unit and ' ' + unit}"
