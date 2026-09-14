#!/usr/bin/env python3
"""Import a flat Monthly Picker Metrics CSV export (e.g. from Snowflake/Looker).

Unlike ``add_customer_feedback_column.py`` + ``export_monthly_picker_csv.py``
(which start from an .xlsx workbook with one sheet per month and merge in a
separate feedback lookup), this script starts from a single flat CSV that
already has the "Customer Feedback" column populated -- the shape produced
when someone exports Monthly Picker Metrics *with* feedback already joined
in (for example, from a Snowflake/Looker query).

It produces both pipeline artifacts in one step:

1. ``data/monthly_picker_metrics.csv`` -- the long CSV consumed by
   ``reports/generate_metro_cyprus_weekly_report.py`` and
   ``reports/generate_metro_cyprus_weekly_sheet.py``, with
   "Dynamic Time Delivered" normalized to ISO-ish "YYYY-MM-DD[ HH:MM:SS]".
2. An .xlsx workbook with one sheet per calendar month found in the data
   (named e.g. "May 2026"), matching the shape of the workbooks produced by
   ``reports/add_customer_feedback_column.py``.

No feedback text is ever invented here -- rows without feedback in the input
are written through with an empty "Customer Feedback" cell.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from reports.metro_cyprus_data import MONTHLY_PICKER_COLUMNS  # noqa: E402

_INPUT_DATE_FORMATS = ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Flat Monthly Picker Metrics CSV export.")
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path("data/monthly_picker_metrics.csv"),
        help="Destination for the pipeline CSV, defaults to data/monthly_picker_metrics.csv.",
    )
    parser.add_argument(
        "--xlsx-output",
        type=Path,
        default=None,
        help="Optional destination for a regenerated .xlsx workbook (one sheet per month).",
    )
    return parser.parse_args()


def _normalize_date(value: str) -> tuple[str, datetime | None]:
    value = value.strip()
    if not value:
        return "", None
    for fmt in _INPUT_DATE_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if parsed.time() == datetime.min.time():
            return parsed.strftime("%Y-%m-%d"), parsed
        return parsed.strftime("%Y-%m-%d %H:%M:%S"), parsed
    return value, None


def load_rows(input_path: Path) -> list[dict[str, str]]:
    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in MONTHLY_PICKER_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{input_path} is missing required columns: {', '.join(missing)}")

        rows = []
        for row in reader:
            purchase_id = (row.get("Purchase ID") or "").strip()
            if not purchase_id:
                continue
            normalized_date, parsed = _normalize_date(row.get("Dynamic Time Delivered") or "")
            rows.append(
                {
                    "Venue Name": (row.get("Venue Name") or "").strip(),
                    "Purchase ID": purchase_id,
                    "Dynamic Time Delivered": normalized_date,
                    "_parsed_date": parsed,
                    "Order Number": (row.get("Order Number") or "").strip(),
                    "Rating of Goods": (row.get("Rating of Goods") or "").strip(),
                    "Goods Items Full Amount": (row.get("Goods Items Full Amount") or "").strip(),
                    "Customer Feedback": (row.get("Customer Feedback") or "").strip(),
                }
            )
        return rows


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(MONTHLY_PICKER_COLUMNS)
        for row in rows:
            writer.writerow([row.get(column, "") for column in MONTHLY_PICKER_COLUMNS])


def write_xlsx(rows: list[dict[str, str]], output_path: Path) -> dict[str, int]:
    by_month: dict[str, list[dict[str, str]]] = {}
    undated: list[dict[str, str]] = []
    for row in rows:
        parsed = row.get("_parsed_date")
        if parsed is None:
            undated.append(row)
            continue
        month_key = parsed.strftime("%B %Y")
        by_month.setdefault(month_key, []).append(row)

    workbook = Workbook()
    workbook.remove(workbook.active)

    def month_sort_key(name: str) -> datetime:
        return datetime.strptime(name, "%B %Y")

    summary: dict[str, int] = {}
    for month_key in sorted(by_month, key=month_sort_key):
        month_rows = sorted(by_month[month_key], key=lambda r: r.get("_parsed_date") or datetime.min)
        sheet = workbook.create_sheet(title=month_key)
        header = ["", *MONTHLY_PICKER_COLUMNS]
        sheet.append(header)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for idx, row in enumerate(month_rows, start=1):
            sheet.append([idx, *[row.get(column, "") for column in MONTHLY_PICKER_COLUMNS]])
        for column_cells in sheet.columns:
            length = max((len(str(cell.value)) for cell in column_cells if cell.value is not None), default=10)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(length + 2, 10), 60)
        summary[month_key] = len(month_rows)

    if undated:
        sheet = workbook.create_sheet(title="Undated")
        sheet.append(["", *MONTHLY_PICKER_COLUMNS])
        for idx, row in enumerate(undated, start=1):
            sheet.append([idx, *[row.get(column, "") for column in MONTHLY_PICKER_COLUMNS]])
        summary["Undated"] = len(undated)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    return summary


def main() -> None:
    args = parse_args()
    rows = load_rows(args.input)
    write_csv(rows, args.csv_output)
    with_feedback = sum(1 for row in rows if row.get("Customer Feedback"))
    print(f"Wrote {len(rows)} rows ({with_feedback} with Customer Feedback) to {args.csv_output}")

    if args.xlsx_output is not None:
        summary = write_xlsx(rows, args.xlsx_output)
        for sheet_name, count in summary.items():
            print(f"  {sheet_name}: {count} rows")
        print(args.xlsx_output)


if __name__ == "__main__":
    main()
