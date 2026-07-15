"""Metric computations shared by the merchant preview and per-venue pages.

Every function takes tidy dataframes conforming to :mod:`wolt_report.schema` and
returns plain pandas objects / dicts, keeping the reporting layer free of
business logic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import schema
from .loader import ReportData


def _pct(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) * 100.0 if denominator else 0.0


def kpis(orders: pd.DataFrame) -> dict:
    """Headline KPIs for a set of orders (merchant-wide or a single venue)."""
    n = len(orders)
    total_items = int(orders["item_count"].sum()) if n else 0
    delivered = orders[~orders["is_rejected"] & ~orders["is_cancelled"]]
    ratings = orders["rating"].dropna()

    pofr = _pct(orders["is_pofr"].sum(), n)
    punctual = _pct(delivered["is_punctual"].sum(), len(delivered)) if len(delivered) else 0.0
    late = _pct(orders["is_late"].sum(), n)
    rejection = _pct(orders["is_rejected"].sum(), n)
    substitution = _pct(orders["substituted_items"].sum(), total_items)
    unfulfilled = _pct(orders["unfulfilled_items"].sum(), total_items)

    # Ops performance: blended score of the operational levers (0-100).
    ops_performance = float(np.mean([
        pofr,
        punctual,
        100 - min(late, 100),
        100 - min(rejection * 5, 100),
    ]))

    return {
        "orders": n,
        "gov": float(orders["gross_value"].sum()),
        "items": total_items,
        "avg_basket": float(orders["basket_value"].mean()) if n else 0.0,
        "wolt_plus_orders": int(orders["is_wolt_plus"].sum()),
        "wolt_plus_new_users": int(orders["is_new_wolt_plus"].sum()),
        "pofr_pct": pofr,
        "punctuality_pct": punctual,
        "late_orders_pct": late,
        "rejection_pct": rejection,
        "substitution_pct": substitution,
        "unfulfilled_pct": unfulfilled,
        "ops_performance": ops_performance,
        "avg_delivery_min": float(delivered["delivery_time_min"].mean()) if len(delivered) else 0.0,
        "avg_prep_min": float(delivered["prep_time_min"].mean()) if len(delivered) else 0.0,
        "avg_marker_ready_min": float(delivered["marketplace_ready_min"].mean()) if len(delivered) else 0.0,
        "avg_rating": float(ratings.mean()) if len(ratings) else float("nan"),
        "rating_count": int(len(ratings)),
    }


def orders_per_venue(orders: pd.DataFrame) -> pd.Series:
    return orders.groupby("venue_name").size().sort_values(ascending=False)


def gov_per_venue(orders: pd.DataFrame) -> pd.Series:
    return orders.groupby("venue_name")["gross_value"].sum().sort_values(ascending=False)


def avg_basket_per_venue(orders: pd.DataFrame) -> pd.Series:
    return orders.groupby("venue_name")["basket_value"].mean().sort_values(ascending=False)


def orders_per_hour(orders: pd.DataFrame) -> pd.Series:
    hours = orders["order_datetime"].dt.hour
    counts = hours.value_counts().reindex(range(24), fill_value=0).sort_index()
    return counts


def orders_per_day_per_store(orders: pd.DataFrame) -> pd.DataFrame:
    df = orders.copy()
    df["date"] = df["order_datetime"].dt.date
    pivot = df.pivot_table(
        index="date", columns="venue_name", values="purchase_id",
        aggfunc="count", fill_value=0,
    ).sort_index()
    return pivot


def orders_per_day(orders: pd.DataFrame) -> pd.Series:
    s = orders.copy()
    s["date"] = s["order_datetime"].dt.date
    return s.groupby("date").size().sort_index()


def wolt_plus_per_venue(orders: pd.DataFrame) -> pd.DataFrame:
    grouped = orders.groupby("venue_name").agg(
        wolt_plus_orders=("is_wolt_plus", "sum"),
        wolt_plus_new_users=("is_new_wolt_plus", "sum"),
    )
    return grouped.sort_values("wolt_plus_orders", ascending=False)


def _venue_pct(orders: pd.DataFrame, flag: str) -> pd.Series:
    grp = orders.groupby("venue_name")
    return (grp[flag].sum() / grp.size() * 100.0)


def operations_by_venue(orders: pd.DataFrame) -> pd.DataFrame:
    grp = orders.groupby("venue_name")
    total_items = grp["item_count"].sum()
    delivered = orders[~orders["is_rejected"] & ~orders["is_cancelled"]]
    dgrp = delivered.groupby("venue_name")

    df = pd.DataFrame({
        "pofr_pct": grp["is_pofr"].mean() * 100.0,
        "punctuality_pct": dgrp["is_punctual"].mean() * 100.0,
        "late_orders_pct": grp["is_late"].mean() * 100.0,
        "substitution_pct": grp["substituted_items"].sum() / total_items * 100.0,
        "unfulfilled_pct": grp["unfulfilled_items"].sum() / total_items * 100.0,
        "avg_delivery_min": dgrp["delivery_time_min"].mean(),
        "avg_prep_min": dgrp["prep_time_min"].mean(),
        "avg_marker_ready_min": dgrp["marketplace_ready_min"].mean(),
    })
    df["ops_performance"] = df[["pofr_pct", "punctuality_pct"]].mean(axis=1)
    return df


def quality_by_venue(orders: pd.DataFrame, offline: pd.DataFrame) -> pd.DataFrame:
    grp = orders.groupby("venue_name")
    rejection = grp["is_rejected"].mean() * 100.0
    rating = grp["rating"].mean()

    off = offline.groupby("venue_name").agg(
        offline_hours=("offline_hours", "sum"),
        open_hours=("open_hours", "sum"),
    )
    off["offline_pct"] = off["offline_hours"] / off["open_hours"] * 100.0

    df = pd.DataFrame({
        "rejection_pct": rejection,
        "avg_rating": rating,
    }).join(off[["offline_hours", "offline_pct"]], how="outer")
    return df


def lost_sales_breakdown(orders: pd.DataFrame) -> pd.DataFrame:
    """Lost sales € and % of GOV by reason."""
    total_gov = float(orders["gross_value"].sum())
    rows = []
    for reason in schema.LOST_SALES_REASONS:
        eur = float(orders.loc[orders["lost_sales_reason"] == reason, "lost_sales_gov"].sum())
        rows.append({"reason": reason, "lost_eur": eur, "pct_gov": _pct(eur, total_gov)})
    df = pd.DataFrame(rows).set_index("reason")
    return df


def rejection_reasons(orders: pd.DataFrame) -> pd.Series:
    rejected = orders[orders["is_rejected"] & (orders["rejection_reason"] != "")]
    if rejected.empty:
        return pd.Series(dtype=int)
    return rejected["rejection_reason"].value_counts()


def financial_breakdown(financials: pd.DataFrame, group: str) -> pd.Series:
    sub = financials[financials["group"] == group]
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.groupby("category")["amount"].sum().sort_values(ascending=False)


def picker_usage_by_venue(picker_usage: pd.DataFrame) -> pd.DataFrame:
    grp = picker_usage.groupby("venue_name").agg(
        orders_total=("orders_total", "sum"),
        orders_picked=("orders_picked", "sum"),
    )
    grp["picker_usage_pct"] = grp["orders_picked"] / grp["orders_total"] * 100.0
    return grp.sort_values("picker_usage_pct", ascending=False)


def monthly_picker_table(monthly_picker: pd.DataFrame, limit: int | None = None) -> pd.DataFrame:
    df = monthly_picker.sort_values("dynamic_time_delivered", ascending=False)
    if limit:
        df = df.head(limit)
    return df.reset_index(drop=True)
