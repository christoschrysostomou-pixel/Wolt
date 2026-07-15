"""Command-line entrypoint for generating the weekly report.

Examples
--------
Generate sample data and build the PDF (default, fully offline)::

    python -m wolt_report.cli --generate-sample

Build from existing CSVs in data/ ::

    python -m wolt_report.cli

Build against live Snowflake (set data_source: snowflake in config.yaml and
export SNOWFLAKE_* credentials)::

    python -m wolt_report.cli --config config.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .loader import get_loader, validate
from .report import ReportBuilder
from .sample_data import write_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Wolt weekly merchant report (PDF).")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--generate-sample", action="store_true",
                        help="(Re)generate synthetic sample CSVs before building.")
    parser.add_argument("--output", default=None, help="Output PDF path (overrides config).")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    print(f"Merchant : {config.merchant_name}")
    print(f"Period   : {config.period.label} ({config.period.iso_week})")
    print(f"Venues   : {', '.join(v.name for v in config.venues)}")
    print(f"Source   : {config.data_source}")

    sample = False
    if args.generate_sample:
        print("Generating synthetic sample data ...")
        out = write_sample(config)
        print(f"  wrote sample CSVs to {out}")
        sample = True
    elif config.data_source == "csv":
        # If CSVs are missing, generate sample data automatically.
        if not (config.data_dir / "orders.csv").exists():
            print("No CSV data found; generating sample data ...")
            write_sample(config)
            sample = True
        else:
            # Heuristic: sample data is flagged unless the user explicitly
            # exported real CSVs. We assume csv source without a marker is real.
            sample = (config.data_dir / ".sample").exists()

    if args.generate_sample:
        (config.data_dir / ".sample").write_text("synthetic sample data\n", encoding="utf-8")
    if sample and not (config.data_dir / ".sample").exists():
        (config.data_dir / ".sample").write_text("synthetic sample data\n", encoding="utf-8")

    loader = get_loader(config)
    data = loader.load()
    validate(data)
    print(f"Loaded   : {len(data.orders):,} orders, "
          f"{len(data.monthly_picker):,} monthly picker rows")

    output = Path(args.output) if args.output else (
        config.output_dir / f"{_slug(config.merchant_name)}_weekly_{config.period.iso_week}.pdf")
    builder = ReportBuilder(config, data, sample=sample)
    path = builder.build(output)
    print(f"Report   : {path}")
    return 0


def _slug(text: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in text).strip("-")


if __name__ == "__main__":
    sys.exit(main())
