"""Configuration loading and reporting-period resolution."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Venue:
    venue_id: str
    name: str


@dataclass
class Period:
    start: dt.date
    end: dt.date  # inclusive

    @property
    def label(self) -> str:
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y}"

    @property
    def iso_week(self) -> str:
        iso = self.start.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def contains(self, when: dt.date) -> bool:
        return self.start <= when <= self.end


@dataclass
class Config:
    merchant_name: str
    currency: str
    currency_symbol: str
    timezone: str
    venues: list[Venue]
    period: Period
    data_source: str
    data_dir: Path
    output_dir: Path
    targets: dict[str, float] = field(default_factory=dict)

    @property
    def venue_ids(self) -> list[str]:
        return [v.venue_id for v in self.venues]


def _resolve_period(raw: dict[str, Any], today: dt.date | None = None) -> Period:
    today = today or dt.date.today()
    start_raw = raw.get("start")
    end_raw = raw.get("end")
    if start_raw and end_raw:
        start = _as_date(start_raw)
        end = _as_date(end_raw)
        return Period(start=start, end=end)

    # Default: previous full ISO week (Monday-Sunday).
    this_monday = today - dt.timedelta(days=today.weekday())
    last_monday = this_monday - dt.timedelta(days=7)
    last_sunday = last_monday + dt.timedelta(days=6)
    return Period(start=last_monday, end=last_sunday)


def _as_date(value: Any) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def load_config(path: str | Path, today: dt.date | None = None) -> Config:
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    merchant = raw.get("merchant", {})
    venues = [Venue(venue_id=v["venue_id"], name=v["name"]) for v in raw.get("venues", [])]
    period = _resolve_period(raw.get("period", {}), today=today)

    base = path.parent
    return Config(
        merchant_name=merchant.get("name", "Merchant"),
        currency=merchant.get("currency", "EUR"),
        currency_symbol=merchant.get("currency_symbol", "€"),
        timezone=merchant.get("timezone", "UTC"),
        venues=venues,
        period=period,
        data_source=raw.get("data_source", "csv"),
        data_dir=(base / raw.get("data_dir", "data")).resolve(),
        output_dir=(base / raw.get("output_dir", "output")).resolve(),
        targets=raw.get("targets", {}) or {},
    )
