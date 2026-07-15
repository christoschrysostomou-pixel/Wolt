#!/usr/bin/env python3
"""
Metro Cyprus — Wolt Weekly Performance Report Generator
Generates a professional multi-page PDF with charts for all venue metrics.

Usage:
    python generate_report.py [--output output/Metro_Cyprus_Weekly_Report.pdf]

Data: Uses realistic mock data for the last completed Mon–Sun week.
      Replace `make_data()` with live Snowflake queries when credentials
      are available.
"""
import argparse
import io
import os
import random
import warnings
from datetime import datetime, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────
# GLOBAL CONFIGURATION
# ──────────────────────────────────────────────────────────────
MERCHANT = "Metro Cyprus"
TODAY = datetime(2026, 7, 15)

# Last full Mon–Sun week relative to TODAY
_wday = TODAY.weekday()          # Wednesday → 2
WEEK_END = TODAY - timedelta(days=_wday + 1)      # Sun 12 Jul
WEEK_START = WEEK_END - timedelta(days=6)          # Mon 6 Jul
DATE_STR = f"{WEEK_START.strftime('%d %b')} – {WEEK_END.strftime('%d %b %Y')}"

VENUES = ["Engomi", "Strovolos", "Limassol", "Larnaca", "Paphos"]

# Brand colour palette
C: dict[str, str] = {
    "blue":   "#009DE0",
    "dark":   "#1E2A3A",
    "teal":   "#00B2CA",
    "green":  "#27AE60",
    "orange": "#F39C12",
    "red":    "#E74C3C",
    "purple": "#8E44AD",
    "light":  "#F8F9FA",
    "border": "#DEE2E6",
    "text":   "#2C3E50",
    "muted":  "#7F8C8D",
    "white":  "#FFFFFF",
}

# Page geometry
PW, PH = A4
MAR = 1.5 * cm
CW = PW - 2 * MAR   # usable content width ≈ 176 mm


# ──────────────────────────────────────────────────────────────
# MOCK DATA GENERATION
# ──────────────────────────────────────────────────────────────
np.random.seed(42)
random.seed(42)


def _dates():
    return [WEEK_START + timedelta(days=i) for i in range(7)]


def make_data() -> dict:
    """
    Build a dictionary that mimics what a live Snowflake pull would return.
    Keys:
        venue     → dict[venue_name, pd.DataFrame]   (one row per day)
        hourly    → dict[venue_name, np.ndarray(24)] (orders per hour)
        add_deduct→ dict[venue_name, dict]
        picker    → pd.DataFrame  (individual picker transactions)
    """
    # Per-venue baseline parameters: (daily_orders, avg_basket_€, pofr_mean, picker_pct)
    params = {
        "Engomi":    (185, 44.0, 0.932, 0.88),
        "Strovolos": (162, 41.0, 0.918, 0.83),
        "Limassol":  (148, 38.0, 0.941, 0.90),
        "Larnaca":   (118, 36.0, 0.905, 0.78),
        "Paphos":    ( 92, 34.0, 0.921, 0.82),
    }

    venue_df: dict[str, pd.DataFrame] = {}
    for v, (base, abv_mu, pofr_mu, picker_mu) in params.items():
        rows = []
        for d in _dates():
            weekend_boost = 1.28 if d.weekday() >= 5 else 1.0
            orders = max(30, int(base * weekend_boost * np.random.uniform(0.88, 1.12)))
            abv = max(15.0, float(np.random.normal(abv_mu, 4.0)))
            rows.append({
                "date":        d,
                "orders":      orders,
                "gov":         orders * abv,
                "abv":         abv,
                # Wolt+
                "wplus_orders":int(orders * np.random.uniform(0.14, 0.26)),
                "wplus_new":   int(np.random.randint(3, 14)),
                # Operations
                "pofr":        float(min(1.0, np.random.normal(pofr_mu, 0.018))),
                "sub_pct":     float(np.random.uniform(0.018, 0.072)),
                "unful_pct":   float(np.random.uniform(0.008, 0.042)),
                "punct":       float(np.random.uniform(0.862, 0.951)),
                "del_time":    float(max(15.0, np.random.normal(36, 5))),
                "prep_time":   float(max(5.0,  np.random.normal(16, 3))),
                "mrkr_ready":  float(np.random.uniform(0.84, 0.95)),
                "late_pct":    float(np.random.uniform(0.048, 0.162)),
                # Quality
                "rej_pct":     float(np.random.uniform(0.012, 0.052)),
                "rating":      float(np.random.uniform(4.12, 4.79)),
                "offline_pct": float(np.random.uniform(0.008, 0.038)),
                "offline_hrs": float(np.random.uniform(0.4, 4.2)),
                "cancel_pct":  float(np.random.uniform(0.008, 0.032)),
                # Picker
                "picker_pct":  float(min(1.0, np.random.normal(picker_mu, 0.06))),
            })
        df = pd.DataFrame(rows)
        df["picker_orders"] = (df["orders"] * df["picker_pct"]).astype(int)
        venue_df[v] = df

    # Hourly distribution template (peaks at lunch & dinner)
    h_tpl = np.array([
        0.3, 0.2, 0.1, 0.1, 0.1, 0.2, 0.6, 1.1,
        2.9, 4.6, 6.3, 7.9, 9.0, 7.6, 5.9, 4.9,
        5.3, 7.2, 8.3, 8.6, 6.3, 4.2, 2.7, 1.1,
    ])
    h_tpl /= h_tpl.sum()
    hourly: dict[str, np.ndarray] = {}
    for v in VENUES:
        tot = int(venue_df[v]["orders"].sum())
        noise = np.random.uniform(0.92, 1.08, 24)
        dist = h_tpl * noise
        dist /= dist.sum()
        hourly[v] = (dist * tot).astype(int)

    # Additions & Deductions + breakdowns per venue
    add_deduct: dict[str, dict] = {}
    for v in VENUES:
        scale = venue_df[v]["gov"].sum() / 10_000

        rr: dict[str, float] = {
            "Item Unavailable": float(np.random.uniform(0.36, 0.44)),
            "Item Expired":     float(np.random.uniform(0.16, 0.24)),
            "Quality Issue":    float(np.random.uniform(0.10, 0.16)),
            "Wrong Item":       float(np.random.uniform(0.08, 0.13)),
            "Damaged Pkg":      float(np.random.uniform(0.04, 0.08)),
        }
        rr["Other"] = max(0.0, 1.0 - sum(rr.values()))

        cf: dict[str, float] = {
            "Standard":  float(np.random.uniform(0.55, 0.63)),
            "Express":   float(np.random.uniform(0.16, 0.22)),
            "Wolt+":     float(np.random.uniform(0.12, 0.18)),
        }
        cf["Other"] = max(0.0, 1.0 - sum(cf.values()))

        add_deduct[v] = {
            "additions": {
                "Courier Fee Subsidy": float(np.random.uniform(400,  1200)) * scale,
                "Promotional Credits": float(np.random.uniform(180,   600)) * scale,
                "Campaign Bonus":      float(np.random.uniform( 80,   320)) * scale,
                "Service Fee":         float(np.random.uniform( 40,   150)) * scale,
            },
            "deductions": {
                "Rejection Comp.":   -float(np.random.uniform( 80, 380)) * scale,
                "Late Penalty":      -float(np.random.uniform( 40, 180)) * scale,
                "Quality Deduction": -float(np.random.uniform( 25, 120)) * scale,
                "Adjustment":        -float(np.random.uniform( 15,  60)) * scale,
            },
            "rej_reasons":  rr,
            "courier_fees": cf,
        }

    # Picker detail records (individual transactions)
    records = []
    for v in VENUES:
        for _, row in venue_df[v].iterrows():
            n_samples = min(int(row["picker_orders"]), 18)
            for _ in range(n_samples):
                dt = row["date"] + timedelta(
                    hours=random.randint(9, 21), minutes=random.randint(0, 59)
                )
                records.append({
                    "Venue Name":               v,
                    "Purchase ID":              f"PO{random.randint(100_000, 999_999)}",
                    "Dynamic Time Delivered":   dt.strftime("%Y-%m-%d %H:%M"),
                    "Order Number":             f"WLT{random.randint(1_000_000, 9_999_999)}",
                    "Rating of Goods":          round(random.uniform(3.4, 5.0), 1),
                    "Goods Items Full Amount":  round(random.uniform(12, 135), 2),
                })

    return {
        "venue":      venue_df,
        "hourly":     hourly,
        "add_deduct": add_deduct,
        "picker":     pd.DataFrame(records),
    }


# ──────────────────────────────────────────────────────────────
# CHART HELPERS
# ──────────────────────────────────────────────────────────────
def _apply_style():
    plt.rcParams.update({
        "figure.facecolor":   "white",
        "axes.facecolor":     "white",
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "axes.linewidth":     0.7,
        "axes.grid":          True,
        "axes.grid.axis":     "y",
        "grid.alpha":         0.4,
        "grid.linewidth":     0.5,
        "font.family":        "DejaVu Sans",
        "font.size":          8.5,
        "axes.titlesize":     10,
        "axes.titleweight":   "bold",
        "axes.titlepad":      7,
        "axes.labelsize":     8,
        "xtick.labelsize":    7.5,
        "ytick.labelsize":    7.5,
        "legend.fontsize":    7.5,
    })


def _save_fig(fig, dpi=150) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    buf.seek(0)
    plt.close(fig)
    return buf


def _color(value: float, lo: float, hi: float, good_above=True) -> str:
    """Return green/orange/red depending on thresholds."""
    if good_above:
        return C["green"] if value >= hi else (C["orange"] if value >= lo else C["red"])
    return C["green"] if value <= lo else (C["orange"] if value <= hi else C["red"])


def _bar_label(ax, bars, fmt="{:.1f}", suffix=""):
    """Manually annotate bars (compatible with all matplotlib versions)."""
    for bar in bars:
        h = bar.get_height()
        ax.annotate(
            fmt.format(h) + suffix,
            xy=(bar.get_x() + bar.get_width() / 2, h),
            xytext=(0, 3), textcoords="offset points",
            ha="center", va="bottom", fontsize=7.5, fontweight="bold",
        )


# ── All-venue summary charts ──────────────────────────────────

def chart_orders_trend(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    xl = [d.strftime("%a %d/%m") for d in _dates()]
    pal = [C["blue"], C["teal"], C["green"], C["orange"], C["red"]]
    for i, v in enumerate(VENUES):
        df = D["venue"][v].sort_values("date")
        ax.plot(xl, df["orders"].values, marker="o", ms=4.5, lw=2.0,
                color=pal[i], label=v, alpha=0.9)
    ax.set_title("Daily Orders – All Venues")
    ax.set_ylabel("Orders")
    ax.legend(ncol=3, loc="upper left", framealpha=0.9)
    ax.set_ylim(bottom=0)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_gov_venue(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    vals = [D["venue"][v]["gov"].sum() / 1000 for v in VENUES]
    bars = ax.bar(VENUES, vals, color=C["teal"], alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="€{:.1f}K")
    ax.set_title("GOV by Venue (€K)")
    ax.set_ylim(0, max(vals) * 1.2)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_orders_venue(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 3.0))
    vals = [int(D["venue"][v]["orders"].sum()) for v in VENUES]
    bars = ax.bar(VENUES, vals, color=C["blue"], alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.0f}")
    ax.set_title("Total Orders by Venue")
    ax.set_ylim(0, max(vals) * 1.2)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_hourly(D: dict, venue: str | None = None) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(6.0, 2.8))
    vals = D["hourly"][venue] if venue else np.sum(
        [D["hourly"][v] for v in VENUES], axis=0)
    color = C["blue"] if venue else C["teal"]
    title = f"Orders by Hour – {venue}" if venue else "Orders by Hour (All Venues)"
    ax.bar(range(24), vals, color=color, alpha=0.82, width=0.82,
           edgecolor="white", linewidth=0.3)
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f"{h:02d}h" for h in range(0, 24, 2)], fontsize=7)
    ax.set_title(title)
    ax.set_ylabel("Orders")
    ax.set_xlim(-0.6, 23.6)
    ax.grid(axis="x", alpha=0)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_heatmap(D: dict) -> io.BytesIO:
    _apply_style()
    ds = _dates()
    matrix = np.array([
        [D["venue"][v].sort_values("date")["orders"].values[j] for j in range(7)]
        for v in VENUES
    ])
    fig, ax = plt.subplots(figsize=(8.0, 2.8))
    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=matrix.min() * 0.8)
    ax.set_xticks(range(7))
    ax.set_xticklabels([d.strftime("%a %d/%m") for d in ds], fontsize=7.5)
    ax.set_yticks(range(len(VENUES)))
    ax.set_yticklabels(VENUES, fontsize=7.5)
    ax.set_title("Orders per Day per Store")
    for i in range(len(VENUES)):
        for j in range(7):
            val = matrix[i, j]
            ax.text(j, i, str(val), ha="center", va="center", fontsize=7.5,
                    fontweight="bold",
                    color="white" if val > matrix.max() * 0.55 else "#2C3E50")
    plt.colorbar(im, ax=ax, shrink=0.85, aspect=12)
    ax.grid(False)
    for sp_ in ax.spines.values():
        sp_.set_visible(False)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_avg_basket(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["abv"].mean() for v in VENUES]
    bars = ax.bar(VENUES, vals, color=C["green"], alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="€{:.2f}")
    ax.set_title("Avg Basket Value by Venue")
    ax.set_ylabel("€")
    ax.set_ylim(0, max(vals) * 1.2)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_pofr(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["pofr"].mean() * 100 for v in VENUES]
    clrs = [_color(x, 88, 93) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.1f}", suffix="%")
    ax.axhline(93, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target 93%")
    ax.set_title("POFR % by Venue")
    ax.set_ylabel("%")
    ax.set_ylim(80, 100)
    ax.legend(loc="lower right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_punctuality(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["punct"].mean() * 100 for v in VENUES]
    clrs = [_color(x, 85, 90) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.1f}", suffix="%")
    ax.axhline(90, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target 90%")
    ax.set_title("Punctuality by Venue")
    ax.set_ylabel("%")
    ax.set_ylim(75, 100)
    ax.legend(loc="lower right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_delivery_time(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["del_time"].mean() for v in VENUES]
    bars = ax.bar(VENUES, vals, color=C["blue"], alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.0f}", suffix=" min")
    ax.set_title("Avg Delivery Time by Venue")
    ax.set_ylabel("Minutes")
    ax.set_ylim(0, max(vals) * 1.25)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_prep_time(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["prep_time"].mean() for v in VENUES]
    bars = ax.bar(VENUES, vals, color=C["teal"], alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.0f}", suffix=" min")
    ax.set_title("Avg Prep Time by Venue")
    ax.set_ylabel("Minutes")
    ax.set_ylim(0, max(vals) * 1.25)
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_marker_ready(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["mrkr_ready"].mean() * 100 for v in VENUES]
    clrs = [_color(x, 85, 90) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.1f}", suffix="%")
    ax.axhline(90, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target 90%")
    ax.set_title("Marker Ready Performance")
    ax.set_ylabel("%")
    ax.set_ylim(75, 100)
    ax.legend(loc="lower right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_late_orders(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["late_pct"].mean() * 100 for v in VENUES]
    clrs = [_color(x, 8, 12, good_above=False) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.1f}", suffix="%")
    ax.axhline(8, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target <8%")
    ax.set_title("% Late Orders by Venue")
    ax.set_ylabel("%")
    ax.set_ylim(0, max(vals) * 1.3)
    ax.legend(loc="upper right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_rejection(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["rej_pct"].mean() * 100 for v in VENUES]
    clrs = [_color(x, 2, 4, good_above=False) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.2f}", suffix="%")
    ax.axhline(2, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target <2%")
    ax.set_title("Rejection % by Venue")
    ax.set_ylabel("%")
    ax.set_ylim(0, max(vals) * 1.35)
    ax.legend(loc="upper right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_rating(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    vals = [D["venue"][v]["rating"].mean() for v in VENUES]
    clrs = [_color(x, 4.2, 4.5) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.2f}", suffix="★")
    ax.axhline(4.5, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target 4.5★")
    ax.set_title("Customer Rating by Venue")
    ax.set_ylabel("Rating")
    ax.set_ylim(3.8, 5.0)
    ax.legend(loc="lower right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_offline(D: dict) -> io.BytesIO:
    _apply_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.0, 2.8))
    v1 = [D["venue"][v]["offline_pct"].mean() * 100 for v in VENUES]
    bars1 = ax1.bar(VENUES, v1, color=C["red"], alpha=0.78, width=0.6,
                    edgecolor="white", linewidth=0.5)
    _bar_label(ax1, bars1, fmt="{:.2f}", suffix="%")
    ax1.set_title("Offline % by Venue", fontsize=9.5)
    ax1.set_ylabel("%")
    ax1.set_ylim(0, max(v1) * 1.4)

    v2 = [D["venue"][v]["offline_hrs"].mean() for v in VENUES]
    bars2 = ax2.bar(VENUES, v2, color=C["orange"], alpha=0.78, width=0.6,
                    edgecolor="white", linewidth=0.5)
    _bar_label(ax2, bars2, fmt="{:.1f}", suffix="h")
    ax2.set_title("Avg Offline Hours/Day", fontsize=9.5)
    ax2.set_ylabel("Hours")
    ax2.set_ylim(0, max(v2) * 1.4)

    fig.tight_layout(pad=1.2)
    return _save_fig(fig)


def chart_picker_usage(D: dict) -> io.BytesIO:
    _apply_style()
    fig, ax = plt.subplots(figsize=(6.0, 2.8))
    vals = [D["venue"][v]["picker_pct"].mean() * 100 for v in VENUES]
    clrs = [_color(x, 75, 85) for x in vals]
    bars = ax.bar(VENUES, vals, color=clrs, alpha=0.85, width=0.6,
                  edgecolor="white", linewidth=0.5)
    _bar_label(ax, bars, fmt="{:.1f}", suffix="%")
    ax.axhline(85, color=C["green"], ls="--", lw=1.4, alpha=0.8, label="Target 85%")
    ax.set_title("Picker Usage % by Store")
    ax.set_ylabel("%")
    ax.set_ylim(60, 100)
    ax.legend(loc="lower right")
    fig.tight_layout(pad=0.7)
    return _save_fig(fig)


def chart_pie(data_dict: dict, title: str) -> io.BytesIO | None:
    _apply_style()
    labels = list(data_dict.keys())
    vals = [abs(float(x)) for x in data_dict.values()]
    if sum(vals) == 0:
        return None
    fig, ax = plt.subplots(figsize=(4.5, 3.0))
    pal = [C["blue"], C["teal"], C["green"], C["orange"], C["red"], C["muted"], C["purple"]]
    wedges, texts, autotexts = ax.pie(
        vals, labels=labels, autopct="%1.1f%%",
        colors=pal[: len(labels)], startangle=90,
        pctdistance=0.72, labeldistance=1.08,
    )
    for t in texts:
        t.set_fontsize(7)
    for at in autotexts:
        at.set_fontsize(7)
        at.set_fontweight("bold")
    ax.set_title(title, fontsize=9.5)
    fig.tight_layout(pad=0.5)
    return _save_fig(fig)


# ──────────────────────────────────────────────────────────────
# REPORTLAB STYLE HELPERS
# ──────────────────────────────────────────────────────────────
def _ps(name: str, **kw) -> ParagraphStyle:
    defaults = dict(fontName="Helvetica", fontSize=9,
                    textColor=colors.HexColor(C["text"]))
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)


def _rc(hex_str: str) -> colors.HexColor:
    return colors.HexColor(hex_str)


STYLES: dict[str, ParagraphStyle] = {
    "h1":        _ps("h1",  fontName="Helvetica-Bold", fontSize=26,
                     textColor=_rc(C["white"]), alignment=TA_CENTER),
    "h2":        _ps("h2",  fontSize=13, textColor=_rc("#BDE3F7"), alignment=TA_CENTER),
    "h3":        _ps("h3",  fontName="Helvetica-Bold", fontSize=11,
                     textColor=_rc(C["dark"]), spaceBefore=4, spaceAfter=3),
    "sec":       _ps("sec", fontName="Helvetica-Bold", fontSize=11,
                     textColor=colors.white),
    "body":      _ps("body", fontSize=8.5, spaceAfter=3),
    "th":        _ps("th",  fontName="Helvetica-Bold", fontSize=8,
                     textColor=colors.white, alignment=TA_CENTER),
    "td":        _ps("td",  fontSize=7.5, alignment=TA_CENTER),
    "td_l":      _ps("td_l", fontSize=7.5, alignment=TA_LEFT),
    "kpi_val":   _ps("kpi_val", fontName="Helvetica-Bold", fontSize=17,
                     textColor=colors.white, alignment=TA_CENTER),
    "kpi_unit":  _ps("kpi_unit", fontSize=7.5, textColor=_rc("#BDE3F7"), alignment=TA_CENTER),
    "kpi_lbl":   _ps("kpi_lbl", fontSize=6.5, textColor=_rc("#DEF0FA"), alignment=TA_CENTER),
    "cov_stat":  _ps("cov_stat", fontName="Helvetica-Bold", fontSize=22,
                     textColor=colors.white, alignment=TA_CENTER),
    "cov_lbl":   _ps("cov_lbl", fontSize=9, textColor=_rc("#BDE3F7"), alignment=TA_CENTER),
    "venue_hdr": _ps("venue_hdr", fontName="Helvetica-Bold", fontSize=15,
                     textColor=colors.white),
}


def sp(h: float = 0.3):
    return Spacer(1, h * cm)


def sec_bar(title: str, col: str | None = None) -> Table:
    bg = _rc(col or C["blue"])
    t = Table([[Paragraph(f"  {title}", STYLES["sec"])]],
              colWidths=[CW], rowHeights=[0.72 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",(0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def kpi_row(items: list[tuple]) -> Table:
    """
    items = [(label, value_str, unit_str, bg_hex), ...]
    Renders a horizontal strip of coloured KPI cards.
    """
    n = len(items)
    cw = CW / n
    cells = []
    for lbl, val, unit, bg in items:
        inner = Table(
            [[Paragraph(str(val),  STYLES["kpi_val"])],
             [Paragraph(str(unit), STYLES["kpi_unit"])],
             [Paragraph(str(lbl),  STYLES["kpi_lbl"])]],
            colWidths=[cw - 0.28 * cm],
            rowHeights=[0.68 * cm, 0.38 * cm, 0.32 * cm],
        )
        inner.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), _rc(bg)),
            ("TOPPADDING",    (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LEFTPADDING",   (0, 0), (-1, -1), 2),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ]))
        cells.append(inner)

    row = Table([cells], colWidths=[cw] * n, rowHeights=[1.48 * cm])
    row.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row


def rl_img(buf: io.BytesIO, w: float, max_h: float | None = None) -> Image:
    buf.seek(0)
    img = Image(buf)
    ratio = img.imageHeight / float(img.imageWidth)
    h = w * ratio
    if max_h and h > max_h:
        h = max_h
        w = h / ratio
    img.drawWidth = w
    img.drawHeight = h
    return img


def two_imgs(b1: io.BytesIO, b2: io.BytesIO,
             w1: float | None = None, w2: float | None = None,
             max_h: float = 6.5 * cm) -> Table:
    w1 = w1 if w1 is not None else CW * 0.52
    w2 = w2 if w2 is not None else CW - w1
    i1 = rl_img(b1, w1 - 0.1 * cm, max_h)
    i2 = rl_img(b2, w2 - 0.1 * cm, max_h)
    t = Table([[i1, i2]], colWidths=[w1, w2])
    t.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def mk_table(headers: list[str], rows: list[list],
             cws: list[float] | None = None) -> Table:
    n = len(headers)
    col_widths = cws or [CW / n] * n
    data = [[Paragraph(h, STYLES["th"]) for h in headers]]
    for i, r in enumerate(rows):
        row_style = STYLES["td"]
        data.append([Paragraph(str(x), row_style) for x in r])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    base = [
        ("BACKGROUND",    (0, 0), (-1, 0), _rc(C["dark"])),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("GRID",          (0, 0), (-1, -1), 0.4, _rc(C["border"])),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]
    # Alternating row backgrounds
    for i in range(1, len(rows) + 1):
        bg = "#F5F7FA" if i % 2 == 0 else C["white"]
        base.append(("BACKGROUND", (0, i), (-1, i), _rc(bg)))
    # Bold last row if it looks like a total row
    if rows and str(rows[-1][0]).upper().startswith("TOTAL"):
        last = len(rows)
        base += [
            ("FONTNAME",   (0, last), (-1, last), "Helvetica-Bold"),
            ("BACKGROUND", (0, last), (-1, last), _rc("#EAF4FB")),
        ]
    t.setStyle(TableStyle(base))
    return t


# ──────────────────────────────────────────────────────────────
# PAGE BACKGROUND CALLBACKS
# ──────────────────────────────────────────────────────────────
def cb_cover(c, doc):
    c.saveState()
    c.setFillColor(_rc(C["dark"]))
    c.rect(0, 0, PW, PH, fill=1, stroke=0)
    # Horizontal accent stripes
    c.setFillColor(_rc(C["blue"]))
    c.rect(0, PH * 0.375, PW, 5, fill=1, stroke=0)
    c.setFillColor(_rc(C["teal"]))
    c.rect(0, PH * 0.378, PW, 2, fill=1, stroke=0)
    # Decorative circles
    c.setFillColor(_rc("#162238"))
    c.circle(PW * 0.88, PH * 0.88, 105, fill=1, stroke=0)
    c.circle(PW * 0.08, PH * 0.10,  70, fill=1, stroke=0)
    c.circle(PW * 0.50, PH * 0.04,  40, fill=1, stroke=0)
    c.restoreState()


def cb_page(c, doc):
    if doc.page == 1:
        cb_cover(c, doc)
        return
    c.saveState()
    # Header bar
    c.setFillColor(_rc(C["dark"]))
    c.rect(0, PH - 1.55 * cm, PW, 1.55 * cm, fill=1, stroke=0)
    c.setFillColor(_rc(C["blue"]))
    c.rect(0, PH - 1.60 * cm, PW, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MAR, PH - 1.05 * cm, MERCHANT)
    c.setFont("Helvetica", 8)
    c.drawRightString(PW - MAR, PH - 1.05 * cm,
                      f"Weekly Performance Report  •  {DATE_STR}")
    # Footer bar
    c.setFillColor(_rc(C["border"]))
    c.rect(0, 0, PW, 0.65 * cm, fill=1, stroke=0)
    c.setFillColor(_rc(C["muted"]))
    c.setFont("Helvetica", 6.5)
    c.drawString(MAR, 0.20 * cm,
                 f"Confidential  •  {MERCHANT}  •  {TODAY.strftime('%d %B %Y')}")
    c.drawRightString(PW - MAR, 0.20 * cm, f"Page {doc.page}")
    c.restoreState()


# ──────────────────────────────────────────────────────────────
# STORY BUILDER
# ──────────────────────────────────────────────────────────────
def build_story(D: dict) -> list:  # noqa: C901
    story = []
    vd = D["venue"]
    hd = D["hourly"]
    ad = D["add_deduct"]

    # ──────────────────────────────────────────────────────────
    # COVER PAGE
    # ──────────────────────────────────────────────────────────
    total_orders = int(sum(vd[v]["orders"].sum() for v in VENUES))
    total_gov    = float(sum(vd[v]["gov"].sum()    for v in VENUES))
    total_wp     = int(sum(vd[v]["wplus_orders"].sum() for v in VENUES))
    avg_basket   = total_gov / total_orders

    story += [sp(4.5), Paragraph(MERCHANT, STYLES["h1"]), sp(0.25),
              Paragraph("Weekly Performance Report", STYLES["h2"]), sp(0.2),
              Paragraph(DATE_STR, _ps("dr", fontName="Helvetica-Bold", fontSize=13,
                                      textColor=_rc(C["teal"]), alignment=TA_CENTER)),
              sp(2.2)]

    stat = Table(
        [[Paragraph(f"{total_orders:,}", STYLES["cov_stat"]),
          Paragraph(f"€{total_gov/1000:.1f}K", STYLES["cov_stat"]),
          Paragraph(str(len(VENUES)), STYLES["cov_stat"])],
         [Paragraph("Total Orders", STYLES["cov_lbl"]),
          Paragraph("Gross Order Value", STYLES["cov_lbl"]),
          Paragraph("Active Venues", STYLES["cov_lbl"])]],
        colWidths=[CW / 3] * 3, rowHeights=[0.9 * cm, 0.4 * cm],
    )
    stat.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEAFTER", (0, 0), (1, 1), 0.8, _rc("#3A5A8A")),
    ]))
    story += [stat, sp(1.5),
              Paragraph("   •   ".join(VENUES),
                        _ps("vl", fontSize=9, textColor=_rc("#BDE3F7"), alignment=TA_CENTER)),
              sp(0.6),
              Paragraph(
                  f"Powered by Wolt Analytics  •  Confidential  •  "
                  f"Generated {TODAY.strftime('%d %B %Y')}",
                  _ps("ft", fontSize=7.5, textColor=_rc("#6A9EC5"), alignment=TA_CENTER)),
              PageBreak()]

    # ──────────────────────────────────────────────────────────
    # MERCHANT OVERVIEW  (page 2+)
    # ──────────────────────────────────────────────────────────
    avg_pofr = float(np.mean([vd[v]["pofr"].mean()      for v in VENUES]))
    avg_punc = float(np.mean([vd[v]["punct"].mean()      for v in VENUES]))
    avg_del  = float(np.mean([vd[v]["del_time"].mean()   for v in VENUES]))
    avg_prep = float(np.mean([vd[v]["prep_time"].mean()  for v in VENUES]))
    avg_rat  = float(np.mean([vd[v]["rating"].mean()     for v in VENUES]))

    story += [sec_bar("MERCHANT OVERVIEW", C["dark"]), sp(0.25)]

    story.append(kpi_row([
        ("Total Orders",      f"{total_orders:,}",       "this week",        C["blue"]),
        ("Gross Order Value", f"€{total_gov/1000:.1f}K", "this week",        C["teal"]),
        ("Avg Basket Value",  f"€{avg_basket:.2f}",      "per order",        C["dark"]),
        ("Wolt+ Orders",      f"{total_wp:,}",
         f"{total_wp/total_orders*100:.1f}% of total",                       C["purple"]),
        ("Group POFR",        f"{avg_pofr*100:.1f}%",    "avg all venues",
         _color(avg_pofr * 100, 88, 93)),
    ]))
    story.append(sp(0.2))
    story.append(kpi_row([
        ("Avg Rating",      f"{avg_rat:.2f}★",        "group avg",
         C["green"] if avg_rat >= 4.5 else C["blue"]),
        ("Punctuality",     f"{avg_punc*100:.1f}%",   "group avg",
         _color(avg_punc * 100, 85, 90)),
        ("Avg Delivery",    f"{avg_del:.0f} min",     "door-to-door",        C["blue"]),
        ("Avg Prep Time",   f"{avg_prep:.0f} min",    "pick & pack",         C["teal"]),
        ("Active Venues",   str(len(VENUES)),          "Metro Cyprus",        C["dark"]),
    ]))
    story.append(sp(0.35))

    # PURCHASES overview
    story += [sec_bar("PURCHASES", C["blue"]), sp(0.2)]
    story.append(two_imgs(chart_orders_trend(D), chart_gov_venue(D),
                          CW * 0.57, CW * 0.43, max_h=5.8 * cm))
    story.append(sp(0.2))
    story.append(two_imgs(chart_orders_venue(D), chart_hourly(D),
                          CW * 0.44, CW * 0.56, max_h=5.4 * cm))
    story.append(sp(0.2))
    story.append(rl_img(chart_heatmap(D), CW, max_h=5.0 * cm))
    story.append(sp(0.2))
    story.append(two_imgs(chart_avg_basket(D), chart_rating(D),
                          CW * 0.44, CW * 0.56, max_h=5.4 * cm))
    story.append(sp(0.35))

    # OPERATIONS overview
    story += [sec_bar("OPERATIONS OVERVIEW", C["orange"]), sp(0.2)]
    story.append(two_imgs(chart_pofr(D), chart_punctuality(D),
                          CW * 0.5, CW * 0.5, max_h=5.2 * cm))
    story.append(sp(0.2))
    story.append(two_imgs(chart_delivery_time(D), chart_prep_time(D),
                          CW * 0.5, CW * 0.5, max_h=5.2 * cm))
    story.append(sp(0.2))
    story.append(two_imgs(chart_marker_ready(D), chart_late_orders(D),
                          CW * 0.5, CW * 0.5, max_h=5.2 * cm))
    story.append(sp(0.35))

    # QUALITY overview
    story += [sec_bar("QUALITY OVERVIEW", C["red"]), sp(0.2)]
    story.append(two_imgs(chart_rejection(D), chart_offline(D),
                          CW * 0.35, CW * 0.65, max_h=5.4 * cm))
    story.append(PageBreak())

    # ──────────────────────────────────────────────────────────
    # PER-VENUE SECTIONS
    # ──────────────────────────────────────────────────────────
    for venue in VENUES:
        df = vd[venue]

        # Venue header bar
        vh = Table([[Paragraph(f"  {venue}  |  {DATE_STR}", STYLES["venue_hdr"])]],
                   colWidths=[CW], rowHeights=[1.1 * cm])
        vh.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _rc(C["dark"])),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",(0, 0), (-1, -1), 8),
        ]))
        story += [vh, sp(0.3)]

        # ── PURCHASES ──────────────────────────────────────────
        v_orders = int(df["orders"].sum())
        v_gov    = float(df["gov"].sum())
        v_abv    = float(df["abv"].mean())
        peak_day = df.sort_values("orders", ascending=False)["date"].iloc[0].strftime("%a %d")

        story += [sec_bar("PURCHASES", C["blue"]), sp(0.2)]
        story.append(kpi_row([
            ("Total Orders", f"{v_orders:,}",       "this week",     C["blue"]),
            ("GOV",          f"€{v_gov/1000:.1f}K", "this week",     C["teal"]),
            ("Avg Basket",   f"€{v_abv:.2f}",       "per order",     C["dark"]),
            ("Peak Day",     peak_day,               "highest orders", C["green"]),
        ]))
        story.append(sp(0.2))
        story.append(two_imgs(chart_hourly(D, venue), chart_avg_basket(D),
                              CW * 0.54, CW * 0.46, max_h=5.2 * cm))
        story.append(sp(0.2))

        daily = df.sort_values("date")
        story.append(mk_table(
            ["Day", "Date", "Orders", "GOV (€)", "Avg Basket (€)"],
            [[row["date"].strftime("%A"), row["date"].strftime("%d %b"),
              int(row["orders"]), f"€{row['gov']:.0f}", f"€{row['abv']:.2f}"]
             for _, row in daily.iterrows()],
            cws=[CW * 0.20, CW * 0.15, CW * 0.15, CW * 0.25, CW * 0.25],
        ))
        story.append(sp(0.3))

        # ── WOLT+ ──────────────────────────────────────────────
        wp_orders = int(df["wplus_orders"].sum())
        wp_new    = int(df["wplus_new"].sum())

        story += [sec_bar("WOLT+", C["purple"]), sp(0.2)]
        story.append(kpi_row([
            ("W+ Orders",     f"{wp_orders:,}",
             f"{wp_orders/v_orders*100:.1f}% of total", C["purple"]),
            ("W+ New Users",  f"{wp_new}",              "this week",   "#9B59B6"),
            ("W+ Avg Basket", f"€{v_abv*1.11:.2f}",
             f"vs €{v_abv:.2f} regular",               C["dark"]),
        ]))
        story.append(sp(0.3))

        # ── OPERATIONS ─────────────────────────────────────────
        pofr  = float(df["pofr"].mean())
        sub   = float(df["sub_pct"].mean())
        unful = float(df["unful_pct"].mean())
        punc  = float(df["punct"].mean())
        delt  = float(df["del_time"].mean())
        prep  = float(df["prep_time"].mean())
        mrkr  = float(df["mrkr_ready"].mean())
        late  = float(df["late_pct"].mean())

        story += [sec_bar("OPERATIONS", C["orange"]), sp(0.2)]
        story.append(kpi_row([
            ("POFR",           f"{pofr*100:.1f}%",   "Picked on 1st Request",
             _color(pofr * 100, 88, 93)),
            ("Substitution %", f"{sub*100:.2f}%",    "of items",
             _color(sub * 100, 3, 6, good_above=False)),
            ("Unfulfilled %",  f"{unful*100:.2f}%",  "of items",
             _color(unful * 100, 2, 4, good_above=False)),
            ("Punctuality",    f"{punc*100:.1f}%",   "on-time delivery",
             _color(punc * 100, 85, 90)),
        ]))
        story.append(sp(0.2))
        story.append(kpi_row([
            ("Avg Delivery", f"{delt:.0f} min",   "door-to-door",  C["blue"]),
            ("Prep Time",    f"{prep:.0f} min",   "pick & pack",   C["teal"]),
            ("Marker Ready", f"{mrkr*100:.1f}%",  "ready on time",
             _color(mrkr * 100, 85, 90)),
            ("Late Orders",  f"{late*100:.1f}%",  "of all orders",
             _color(late * 100, 8, 12, good_above=False)),
        ]))
        story.append(sp(0.2))
        story.append(two_imgs(chart_pofr(D), chart_punctuality(D),
                              CW * 0.5, CW * 0.5, max_h=5.0 * cm))
        story.append(sp(0.2))
        story.append(two_imgs(chart_delivery_time(D), chart_prep_time(D),
                              CW * 0.5, CW * 0.5, max_h=5.0 * cm))
        story.append(sp(0.2))
        story.append(two_imgs(chart_marker_ready(D), chart_late_orders(D),
                              CW * 0.5, CW * 0.5, max_h=5.0 * cm))
        story.append(sp(0.3))

        # ── QUALITY ────────────────────────────────────────────
        rej  = float(df["rej_pct"].mean())
        rat  = float(df["rating"].mean())
        offp = float(df["offline_pct"].mean())
        offh = float(df["offline_hrs"].mean())
        canc = float(df["cancel_pct"].mean())

        story += [sec_bar("QUALITY", C["red"]), sp(0.2)]
        story.append(kpi_row([
            ("Rejection %",   f"{rej*100:.2f}%",   "of orders",
             _color(rej * 100, 2, 4, good_above=False)),
            ("Rating",        f"{rat:.2f}★",        "customer rating",
             _color(rat, 4.2, 4.5)),
            ("Offline %",     f"{offp*100:.2f}%",   "downtime",
             _color(offp * 100, 1, 3, good_above=False)),
            ("Offline Hours", f"{offh:.1f} hrs",    "avg per day",
             _color(offh, 1, 3, good_above=False)),
            ("Cancellation",  f"{canc*100:.2f}%",   "of orders",
             _color(canc * 100, 1, 3, good_above=False)),
        ]))
        story.append(sp(0.2))

        # Lost-sales breakdown (Rejections / Substitutions / Cancellations / Unfulfilled)
        lost = {
            "Rejections":        rej  * v_gov,
            "Substitutions":     sub  * v_gov * 0.30,
            "Cancellations":     canc * v_gov,
            "Unfulfilled Items": unful * v_gov,
        }
        total_lost = sum(lost.values())
        story.append(Paragraph("Lost Sales – %GOV & GOV €", STYLES["h3"]))
        story.append(mk_table(
            ["Category", "Est. GOV Loss (€)", "% of Weekly GOV"],
            [[cat, f"€{val:.2f}", f"{val/v_gov*100:.3f}%"] for cat, val in lost.items()]
            + [["TOTAL", f"€{total_lost:.2f}", f"{total_lost/v_gov*100:.3f}%"]],
            cws=[CW * 0.40, CW * 0.35, CW * 0.25],
        ))
        story.append(sp(0.2))
        story.append(two_imgs(chart_rejection(D), chart_offline(D),
                              CW * 0.35, CW * 0.65, max_h=5.2 * cm))
        story.append(sp(0.3))

        # ── ADDITIONS & DEDUCTIONS ─────────────────────────────
        story += [sec_bar("ADDITIONS & DEDUCTIONS", C["dark"]), sp(0.2)]

        rj_pie = chart_pie(ad[venue]["rej_reasons"], f"Rejection Reasons – {venue}")
        cf_pie = chart_pie(ad[venue]["courier_fees"], f"Courier Fee Breakdown – {venue}")
        if rj_pie and cf_pie:
            story.append(two_imgs(rj_pie, cf_pie, CW * 0.5, CW * 0.5, max_h=5.2 * cm))
            story.append(sp(0.2))

        adds = ad[venue]["additions"]
        total_add = sum(adds.values())
        story.append(Paragraph("Addition Breakdown", STYLES["h3"]))
        story.append(mk_table(
            ["Category", "Amount (€)", "% of Additions"],
            [[cat, f"€{val:.2f}", f"{val/total_add*100:.1f}%"]
             for cat, val in adds.items()]
            + [["TOTAL", f"€{total_add:.2f}", "100.0%"]],
            cws=[CW * 0.45, CW * 0.30, CW * 0.25],
        ))
        story.append(sp(0.2))

        deds = ad[venue]["deductions"]
        total_ded = sum(deds.values())
        story.append(Paragraph("Deduction Breakdown", STYLES["h3"]))
        story.append(mk_table(
            ["Category", "Amount (€)", "% of Deductions"],
            [[cat, f"€{abs(val):.2f}", f"{abs(val)/abs(total_ded)*100:.1f}%"]
             for cat, val in deds.items()]
            + [["TOTAL", f"€{abs(total_ded):.2f}", "100.0%"]],
            cws=[CW * 0.45, CW * 0.30, CW * 0.25],
        ))
        story.append(sp(0.3))

        # ── PICKER ─────────────────────────────────────────────
        pk_orders = int(df["picker_orders"].sum())
        pk_pct    = float(df["picker_pct"].mean() * 100)

        story += [sec_bar("PICKER", C["teal"]), sp(0.2)]
        story.append(kpi_row([
            ("Picker Usage %",  f"{pk_pct:.1f}%",         "of orders via picker",
             _color(pk_pct, 75, 85)),
            ("Picker Orders",   f"{pk_orders:,}",          "this week",             C["teal"]),
            ("Non-Picker Ord.", f"{v_orders-pk_orders:,}", "this week",             C["dark"]),
        ]))
        story.append(sp(0.2))
        story.append(rl_img(chart_picker_usage(D), CW, max_h=4.8 * cm))
        story.append(PageBreak())

    # ──────────────────────────────────────────────────────────
    # MONTHLY PICKER METRICS
    # ──────────────────────────────────────────────────────────
    pk_df = D["picker"]
    story += [sec_bar("MONTHLY PICKER METRICS", C["dark"]), sp(0.25)]
    story.append(kpi_row([
        ("Total Records",    f"{len(pk_df):,}",
         "picker transactions",                                          C["blue"]),
        ("Avg Goods Rating", f"{pk_df['Rating of Goods'].mean():.2f}★",
         "quality rating",                                              C["green"]),
        ("Avg Item Amount",  f"€{pk_df['Goods Items Full Amount'].mean():.2f}",
         "per picker order",                                            C["teal"]),
        ("Venues",           str(pk_df["Venue Name"].nunique()),
         "active",                                                      C["dark"]),
    ]))
    story.append(sp(0.3))

    show_n = min(60, len(pk_df))
    story.append(Paragraph(
        f"Showing {show_n} of {len(pk_df)} records (sampled across all venues and dates)",
        STYLES["body"],
    ))
    story.append(sp(0.15))

    show_df = pk_df.head(show_n)
    story.append(mk_table(
        ["Venue Name", "Purchase ID", "Time Delivered", "Order Number", "Rating", "Amount (€)"],
        [[r["Venue Name"], r["Purchase ID"], r["Dynamic Time Delivered"],
          r["Order Number"], f'{r["Rating of Goods"]:.1f}★',
          f'€{r["Goods Items Full Amount"]:.2f}']
         for _, r in show_df.iterrows()],
        cws=[CW * 0.14, CW * 0.13, CW * 0.20, CW * 0.18, CW * 0.14, CW * 0.21],
    ))

    return story


# ──────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Generate Metro Cyprus Wolt Weekly PDF Report"
    )
    parser.add_argument(
        "--output", default="output/Metro_Cyprus_Weekly_Report.pdf",
        help="Output PDF file path (default: output/Metro_Cyprus_Weekly_Report.pdf)",
    )
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    print(f"[1/3] Generating data for {DATE_STR} …")
    D = make_data()

    print("[2/3] Building story (charts + layout) …")
    story = build_story(D)

    print("[3/3] Rendering PDF …")
    doc = SimpleDocTemplate(
        args.output,
        pagesize=A4,
        leftMargin=MAR,
        rightMargin=MAR,
        topMargin=1.85 * cm,
        bottomMargin=1.0 * cm,
        title=f"{MERCHANT} – Weekly Performance Report",
        author="Wolt Analytics",
        subject=f"Week of {DATE_STR}",
    )
    doc.build(story, onFirstPage=cb_page, onLaterPages=cb_page)
    print(f"✓  Report saved to: {args.output}")


if __name__ == "__main__":
    main()
