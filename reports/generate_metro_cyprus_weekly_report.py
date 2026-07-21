#!/usr/bin/env python3
"""Generate the Metro Cyprus weekly merchant and venue PDF report.

The report is intentionally data-source agnostic. It accepts CSV exports in a
long metrics format so the same renderer can be fed from Snowflake, Looker, or
manual exports without changing the PDF layout.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--weekly-metrics",
        type=Path,
        default=Path("data/weekly_metrics.csv"),
        help="CSV with weekly metrics in long format.",
    )
    parser.add_argument(
        "--monthly-picker",
        type=Path,
        default=Path("data/monthly_picker_metrics.csv"),
        help="CSV with monthly picker detail rows.",
    )
    parser.add_argument(
        "--period-start",
        type=str,
        default=None,
        help="Report period start date, YYYY-MM-DD. Defaults to previous Monday.",
    )
    parser.add_argument(
        "--period-end",
        type=str,
        default=None,
        help="Report period end date, YYYY-MM-DD. Defaults to previous Sunday.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PDF path. Defaults to reports/output/metro_cyprus_weekly_report_<period>.pdf.",
    )
    return parser.parse_args()


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


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def output_path_for(start: date, end: date) -> Path:
    return Path(
        "reports/output/"
        f"metro_cyprus_weekly_report_{start.isoformat()}_to_{end.isoformat()}.pdf"
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


def apply_theme(fig: Figure) -> None:
    fig.patch.set_facecolor("#F7F9FB")


def add_header(fig: Figure, title: str, subtitle: str) -> None:
    fig.text(0.05, 0.955, title, fontsize=20, fontweight="bold", color="#102A43")
    fig.text(0.05, 0.925, subtitle, fontsize=10, color="#52606D")
    fig.text(0.95, 0.955, "Wolt x Metro Cyprus", ha="right", fontsize=10, color="#00AEEF")


def add_footer(fig: Figure, data_note: str) -> None:
    fig.text(0.05, 0.035, data_note, fontsize=8, color="#829AB1")
    fig.text(0.95, 0.035, "Generated by reports/generate_metro_cyprus_weekly_report.py", ha="right", fontsize=8, color="#829AB1")


def add_kpi_card(fig: Figure, x: float, y: float, w: float, h: float, title: str, value: str, accent: str) -> None:
    ax = fig.add_axes([x, y, w, h])
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D9E2EC")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axhline(0.96, color=accent, linewidth=5)
    ax.text(0.05, 0.70, title, transform=ax.transAxes, fontsize=9, color="#52606D", va="center")
    ax.text(0.05, 0.33, value, transform=ax.transAxes, fontsize=18, fontweight="bold", color="#102A43", va="center")


def add_placeholder(ax, title: str, message: str = "No source data available for this metric.") -> None:
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color="#102A43")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#D9E2EC")
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=10,
        color="#829AB1",
        wrap=True,
    )


def plot_bar(ax, records: list[MetricRecord], title: str, max_bars: int = 12) -> None:
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color="#102A43")
    if not records:
        add_placeholder(ax, title)
        return

    grouped: dict[str, float] = defaultdict(float)
    for record in records:
        label = record.dimension_value or record.venue_name or record.metric
        grouped[label] += record.value
    items = sorted(grouped.items(), key=lambda item: item[1], reverse=True)[:max_bars]
    labels = [item[0] for item in items]
    values = [item[1] for item in items]
    ax.barh(labels[::-1], values[::-1], color="#00AEEF")
    ax.grid(axis="x", color="#D9E2EC", linewidth=0.8)
    ax.tick_params(axis="both", labelsize=8, colors="#334E68")
    for spine in ax.spines.values():
        spine.set_visible(False)


def plot_line(ax, records: list[MetricRecord], title: str) -> None:
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color="#102A43")
    if not records:
        add_placeholder(ax, title)
        return

    grouped: dict[str, float] = defaultdict(float)
    for record in records:
        label = record.dimension_value or record.period_start or record.metric
        grouped[label] += record.value
    items = sorted(grouped.items(), key=lambda item: item[0])
    labels = [item[0] for item in items]
    values = [item[1] for item in items]
    ax.plot(labels, values, color="#00AEEF", marker="o", linewidth=2)
    ax.fill_between(labels, values, color="#B3ECFF", alpha=0.35)
    ax.grid(axis="y", color="#D9E2EC", linewidth=0.8)
    ax.tick_params(axis="x", labelrotation=45, labelsize=7, colors="#334E68")
    ax.tick_params(axis="y", labelsize=8, colors="#334E68")
    for spine in ax.spines.values():
        spine.set_visible(False)


def plot_metric_table(ax, records: list[MetricRecord], metrics: list[str], title: str) -> None:
    ax.set_facecolor("white")
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color="#102A43")
    ax.axis("off")
    rows = []
    for metric in metrics:
        value, unit = aggregate_metric(records, metric)
        rows.append([metric, format_value(value, unit)])
    table = ax.table(cellText=rows, colLabels=["Metric", "Value"], loc="center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.45)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#D9E2EC")
        if row == 0:
            cell.set_text_props(weight="bold", color="#102A43")
            cell.set_facecolor("#E6F7FF")
        else:
            cell.set_facecolor("white")


def plot_monthly_picker_table(ax, rows: list[dict[str, str]]) -> None:
    ax.set_facecolor("white")
    ax.set_title("Monthly Picker Metrics", loc="left", fontsize=11, fontweight="bold", color="#102A43")
    ax.axis("off")
    if not rows:
        add_placeholder(
            ax,
            "Monthly Picker Metrics",
            "No monthly picker detail export was provided.",
        )
        return
    visible_rows = [[row[column] for column in MONTHLY_PICKER_COLUMNS] for row in rows[:18]]
    table = ax.table(cellText=visible_rows, colLabels=MONTHLY_PICKER_COLUMNS, loc="center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(6)
    table.scale(1, 1.25)
    for (row_idx, _), cell in table.get_celld().items():
        cell.set_edgecolor("#D9E2EC")
        if row_idx == 0:
            cell.set_text_props(weight="bold", color="#102A43")
            cell.set_facecolor("#E6F7FF")
        else:
            cell.set_facecolor("white")


def build_merchant_preview(
    pdf: PdfPages,
    records: list[MetricRecord],
    start: date,
    end: date,
    data_note: str,
) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    apply_theme(fig)
    add_header(fig, f"{MERCHANT_NAME} Weekly Report", f"Merchant preview | {start:%d %b %Y} - {end:%d %b %Y}")

    kpis = [
        ("Group Orders", "Group orders", "#00AEEF"),
        ("Group Gross Value", "Venue Group Gross Value", "#2F80ED"),
        ("W+ Orders", "W+ Orders", "#10B981"),
        ("Ops Performance", "Ops Performance", "#F59E0B"),
        ("POFR Group", "POFR Group %", "#8B5CF6"),
        ("Lost Sales GOV", "Lost sales GOV EUR", "#EF4444"),
    ]
    positions = [
        (0.05, 0.73),
        (0.365, 0.73),
        (0.68, 0.73),
        (0.05, 0.57),
        (0.365, 0.57),
        (0.68, 0.57),
    ]
    for (title, metric, color), (x, y) in zip(kpis, positions):
        value, unit = aggregate_metric(records, metric)
        add_kpi_card(fig, x, y, 0.27, 0.12, title, format_value(value, unit), color)

    ax_orders = fig.add_axes([0.05, 0.26, 0.42, 0.22])
    plot_bar(ax_orders, records_for_metric(records, "Orders per venue"), "Orders per Venue")
    ax_gov = fig.add_axes([0.53, 0.26, 0.42, 0.22])
    plot_bar(ax_gov, records_for_metric(records, "Gross Value per Venue"), "Gross Value per Venue")
    ax_hour = fig.add_axes([0.05, 0.08, 0.42, 0.13])
    plot_line(ax_hour, records_for_metric(records, "Orders per Hour"), "Orders per Hour")
    ax_ops = fig.add_axes([0.53, 0.08, 0.42, 0.13])
    plot_metric_table(ax_ops, records, ["POFR Group %", "Substitution %", "% Unfulfilled Items", "% Late Orders"], "Operations Snapshot")

    add_footer(fig, data_note)
    pdf.savefig(fig)
    plt.close(fig)


def build_metric_section(
    pdf: PdfPages,
    title: str,
    subtitle: str,
    records: list[MetricRecord],
    metrics: list[str],
    chart_metrics: list[str],
    start: date,
    end: date,
    data_note: str,
) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    apply_theme(fig)
    add_header(fig, title, f"{subtitle} | {start:%d %b %Y} - {end:%d %b %Y}")

    table_ax = fig.add_axes([0.05, 0.12, 0.38, 0.72])
    plot_metric_table(table_ax, records, metrics, "Metric Values")

    chart_slots = [
        [0.49, 0.56, 0.43, 0.28],
        [0.49, 0.12, 0.43, 0.32],
    ]
    for slot, metric in zip(chart_slots, chart_metrics):
        ax = fig.add_axes(slot)
        metric_records = records_for_metric(records, metric)
        if "Hour" in metric or "Day" in metric:
            plot_line(ax, metric_records, metric)
        else:
            plot_bar(ax, metric_records, metric)

    add_footer(fig, data_note)
    pdf.savefig(fig)
    plt.close(fig)


def build_venue_page(
    pdf: PdfPages,
    venue_name: str,
    records: list[MetricRecord],
    start: date,
    end: date,
    data_note: str,
) -> None:
    venue_records = records_for_venue(records, venue_name)
    fig = plt.figure(figsize=(11.69, 8.27))
    apply_theme(fig)
    add_header(fig, f"{venue_name}", f"Venue performance | {start:%d %b %Y} - {end:%d %b %Y}")

    kpis = [
        ("Orders", "Orders per venue", "#00AEEF"),
        ("Gross Value", "Gross Value per Venue", "#2F80ED"),
        ("Avg Basket", "Average Basket Value per Venue", "#10B981"),
        ("POFR", "POFR %", "#8B5CF6"),
        ("Rating", "Rating per Store", "#F59E0B"),
        ("Late Orders", "% Late Orders", "#EF4444"),
    ]
    positions = [
        (0.05, 0.73),
        (0.365, 0.73),
        (0.68, 0.73),
        (0.05, 0.57),
        (0.365, 0.57),
        (0.68, 0.57),
    ]
    for (title, metric, color), (x, y) in zip(kpis, positions):
        value, unit = aggregate_metric(venue_records, metric)
        add_kpi_card(fig, x, y, 0.27, 0.12, title, format_value(value, unit), color)

    ax_day = fig.add_axes([0.05, 0.31, 0.42, 0.18])
    plot_line(ax_day, records_for_metric(venue_records, "Order per Day per Store"), "Orders per Day")
    ax_ops = fig.add_axes([0.53, 0.31, 0.42, 0.18])
    plot_metric_table(
        ax_ops,
        venue_records,
        ["Substitution %", "% Unfulfilled Items", "Punctuality per Venue", "Average Delivery Time per Venue", "Prep Time per Venue"],
        "Operations",
    )
    ax_quality = fig.add_axes([0.05, 0.08, 0.42, 0.17])
    plot_metric_table(
        ax_quality,
        venue_records,
        ["Rejections % per Venue", "Offline % per Venue (New)", "Offline Hours per Venue (New)", "Lost sales %GOV"],
        "Quality",
    )
    ax_picker = fig.add_axes([0.53, 0.08, 0.42, 0.17])
    plot_bar(ax_picker, records_for_metric(venue_records, "Picker Usage per Store"), "Picker Usage")

    add_footer(fig, data_note)
    pdf.savefig(fig)
    plt.close(fig)


def build_no_venue_page(pdf: PdfPages, start: date, end: date, data_note: str) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    apply_theme(fig)
    add_header(fig, "Per-Venue Report Pages", f"{start:%d %b %Y} - {end:%d %b %Y}")
    ax = fig.add_axes([0.12, 0.2, 0.76, 0.5])
    add_placeholder(
        ax,
        "Venue-level data required",
        "No venue-level weekly metrics were available. Once data/weekly_metrics.csv contains venue_name values, this section will render one page per Metro Cyprus venue.",
    )
    add_footer(fig, data_note)
    pdf.savefig(fig)
    plt.close(fig)


def build_monthly_picker_page(
    pdf: PdfPages,
    rows: list[dict[str, str]],
    start: date,
    end: date,
    data_note: str,
) -> None:
    fig = plt.figure(figsize=(11.69, 8.27))
    apply_theme(fig)
    add_header(fig, "Monthly Picker Metrics", f"Detail export included with weekly report | {start:%d %b %Y} - {end:%d %b %Y}")
    ax = fig.add_axes([0.03, 0.10, 0.94, 0.76])
    plot_monthly_picker_table(ax, rows)
    if len(rows) > 18:
        fig.text(0.05, 0.07, f"Showing first 18 of {len(rows)} monthly picker rows.", fontsize=8, color="#829AB1")
    add_footer(fig, data_note)
    pdf.savefig(fig)
    plt.close(fig)


def generate_report(
    weekly_records: list[MetricRecord],
    monthly_picker_rows: list[dict[str, str]],
    start: date,
    end: date,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data_note = (
        "Data source: CSV exports supplied to the generator."
        if weekly_records or monthly_picker_rows
        else "Data source unavailable in this run; all N/A sections require weekly and monthly CSV exports."
    )

    with PdfPages(output_path) as pdf:
        build_merchant_preview(pdf, weekly_records, start, end, data_note)
        venues = known_venues(weekly_records)
        if venues:
            for venue in venues:
                build_venue_page(pdf, venue, weekly_records, start, end, data_note)
        else:
            build_no_venue_page(pdf, start, end, data_note)

        build_metric_section(
            pdf,
            "Purchases",
            "Merchant and venue purchasing performance",
            weekly_records,
            PURCHASE_METRICS,
            ["Orders per venue", "Orders per Hour"],
            start,
            end,
            data_note,
        )
        build_metric_section(
            pdf,
            "Wolt+",
            "Wolt+ order and acquisition performance",
            weekly_records,
            WOLT_PLUS_METRICS,
            ["W+ Orders", "W+ New Users"],
            start,
            end,
            data_note,
        )
        build_metric_section(
            pdf,
            "Operations",
            "Fulfilment, timing, and prep performance",
            weekly_records,
            OPERATIONS_METRICS,
            ["Punctuality per Venue", "Prep Time per Venue"],
            start,
            end,
            data_note,
        )
        build_metric_section(
            pdf,
            "Quality",
            "Quality, offline, and lost-sales performance",
            weekly_records,
            QUALITY_METRICS,
            ["Rejections % per Venue", "Lost sales GOV EUR"],
            start,
            end,
            data_note,
        )
        build_metric_section(
            pdf,
            "Additions & Deductions",
            "Reason and fee breakdowns",
            weekly_records,
            ADDITION_DEDUCTION_METRICS,
            ["Rejection Reason", "Deduction Breakdown"],
            start,
            end,
            data_note,
        )
        build_metric_section(
            pdf,
            "Picker",
            "Picker usage per store",
            weekly_records,
            PICKER_METRICS,
            ["Picker Usage per Store"],
            start,
            end,
            data_note,
        )
        build_monthly_picker_page(pdf, monthly_picker_rows, start, end, data_note)


def main() -> None:
    args = parse_args()
    default_start, default_end = previous_full_week()
    start = parse_date(args.period_start, default_start)
    end = parse_date(args.period_end, default_end)
    output_path = args.output or output_path_for(start, end)

    weekly_records = load_weekly_metrics(args.weekly_metrics)
    monthly_picker_rows = load_monthly_picker(args.monthly_picker)
    generate_report(weekly_records, monthly_picker_rows, start, end, output_path)
    print(output_path)


if __name__ == "__main__":
    main()
