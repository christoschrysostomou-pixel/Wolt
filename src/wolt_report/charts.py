"""Matplotlib chart helpers.

Each function renders a single chart and returns it as PNG bytes (``BytesIO``)
so it can be embedded into the ReportLab PDF. A consistent Wolt-inspired style
is applied across every chart.
"""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Wolt-inspired palette.
WOLT_BLUE = "#00C2E8"
WOLT_DARK = "#032E3F"
WOLT_NAVY = "#00688B"
ACCENT = "#FFCF3F"
GOOD = "#2BB673"
WARN = "#F5A623"
BAD = "#E5484D"
GREY = "#8A9BA8"
PALETTE = [WOLT_BLUE, WOLT_NAVY, ACCENT, GOOD, "#B57BEE", "#F5847A", "#5CC8C2", GREY]

plt.rcParams.update({
    "font.size": 9,
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#D5DDE2",
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": "#EDF1F3",
    "grid.linewidth": 0.8,
    "axes.axisbelow": True,
    "axes.titlesize": 10,
    "axes.titleweight": "bold",
    "axes.titlecolor": WOLT_DARK,
    "figure.dpi": 150,
})


def _fig_to_png(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def _style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _label_bars(ax, bars, fmt="{:.0f}", horizontal=False, pad=3):
    for bar in bars:
        if horizontal:
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height() / 2, " " + fmt.format(width),
                    va="center", ha="left", fontsize=8, color=WOLT_DARK)
        else:
            height = bar.get_height()
            ax.annotate(fmt.format(height), (bar.get_x() + bar.get_width() / 2, height),
                        textcoords="offset points", xytext=(0, pad), ha="center",
                        fontsize=8, color=WOLT_DARK)


def hbar(series, title, fmt="{:.0f}", color=WOLT_BLUE, figsize=(5.2, 2.8),
         target=None, target_label=None, lower_is_better=False):
    fig, ax = plt.subplots(figsize=figsize)
    labels = [str(i) for i in series.index]
    values = list(series.values)
    colors = color
    if target is not None:
        colors = [
            (GOOD if (v <= target) == lower_is_better else BAD) if False else
            (_kpi_color(v, target, lower_is_better)) for v in values
        ]
    bars = ax.barh(labels, values, color=colors, height=0.62)
    ax.invert_yaxis()
    _label_bars(ax, bars, fmt=fmt, horizontal=True)
    if target is not None:
        ax.axvline(target, color=WOLT_DARK, linestyle="--", linewidth=1)
        if target_label:
            ax.text(target, -0.6, target_label, color=WOLT_DARK, fontsize=7,
                    ha="center", va="bottom")
    ax.set_title(title)
    ax.margins(x=0.18)
    _style_axes(ax)
    ax.tick_params(length=0)
    return _fig_to_png(fig)


def _kpi_color(value, target, lower_is_better):
    if lower_is_better:
        if value <= target:
            return GOOD
        if value <= target * 1.5:
            return WARN
        return BAD
    else:
        if value >= target:
            return GOOD
        if value >= target * 0.9:
            return WARN
        return BAD


def vbar(series, title, fmt="{:.0f}", color=WOLT_BLUE, figsize=(5.2, 2.6), rotate=0):
    fig, ax = plt.subplots(figsize=figsize)
    labels = [str(i) for i in series.index]
    bars = ax.bar(labels, list(series.values), color=color, width=0.62)
    _label_bars(ax, bars, fmt=fmt)
    ax.set_title(title)
    if rotate:
        plt.setp(ax.get_xticklabels(), rotation=rotate, ha="right")
    ax.margins(y=0.18)
    _style_axes(ax)
    ax.tick_params(length=0)
    return _fig_to_png(fig)


def line(series, title, fmt="{:.0f}", color=WOLT_NAVY, figsize=(5.2, 2.6),
         xlabel=None, fill=True, marker="o"):
    fig, ax = plt.subplots(figsize=figsize)
    x = [str(i) for i in series.index]
    y = list(series.values)
    ax.plot(x, y, color=color, marker=marker, markersize=4, linewidth=2)
    if fill:
        ax.fill_between(range(len(x)), y, color=color, alpha=0.12)
    ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8)
    ax.margins(y=0.2)
    _style_axes(ax)
    ax.tick_params(length=0)
    return _fig_to_png(fig)


def grouped_lines(df, title, figsize=(6.6, 3.0), xlabel=None):
    fig, ax = plt.subplots(figsize=figsize)
    x = [str(i) for i in df.index]
    for i, col in enumerate(df.columns):
        ax.plot(x, df[col].values, marker="o", markersize=3, linewidth=1.6,
                color=PALETTE[i % len(PALETTE)], label=str(col))
    ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8)
    ax.legend(fontsize=7, ncol=min(len(df.columns), 3), loc="upper center",
              bbox_to_anchor=(0.5, -0.18), frameon=False)
    _style_axes(ax)
    ax.tick_params(length=0)
    return _fig_to_png(fig)


def stacked_bar(df, title, figsize=(6.6, 3.0), xlabel=None):
    fig, ax = plt.subplots(figsize=figsize)
    x = [str(i) for i in df.index]
    bottom = [0.0] * len(df)
    for i, col in enumerate(df.columns):
        vals = list(df[col].values)
        ax.bar(x, vals, bottom=bottom, label=str(col),
               color=PALETTE[i % len(PALETTE)], width=0.6)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=8)
    ax.legend(fontsize=7, ncol=min(len(df.columns), 3), loc="upper center",
              bbox_to_anchor=(0.5, -0.18), frameon=False)
    _style_axes(ax)
    ax.tick_params(length=0)
    return _fig_to_png(fig)


def donut(series, title, figsize=(4.2, 3.0), fmt="{:.0f}", value_suffix=""):
    fig, ax = plt.subplots(figsize=figsize)
    values = list(series.values)
    labels = [str(i) for i in series.index]
    if not values or sum(values) == 0:
        ax.text(0.5, 0.5, "No data", ha="center", va="center")
        ax.axis("off")
        ax.set_title(title)
        return _fig_to_png(fig)
    wedges, _ = ax.pie(values, colors=PALETTE[: len(values)], startangle=90,
                       wedgeprops=dict(width=0.42, edgecolor="white"))
    total = sum(values)
    legend_labels = [
        f"{lab} — {fmt.format(val)}{value_suffix} ({val / total * 100:.0f}%)"
        for lab, val in zip(labels, values)
    ]
    ax.legend(wedges, legend_labels, fontsize=7, loc="center left",
              bbox_to_anchor=(0.98, 0.5), frameon=False)
    ax.set_title(title)
    ax.axis("equal")
    return _fig_to_png(fig)


def lost_sales_combo(df, title, currency="€", figsize=(5.6, 2.9)):
    """Bar (€ lost) with a % of GOV line overlay."""
    fig, ax = plt.subplots(figsize=figsize)
    x = [str(i) for i in df.index]
    bars = ax.bar(x, df["lost_eur"].values, color=WOLT_BLUE, width=0.6)
    for bar, v in zip(bars, df["lost_eur"].values):
        ax.annotate(f"{currency}{v:,.0f}", (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 3), ha="center",
                    fontsize=7.5, color=WOLT_DARK)
    ax.set_ylabel(f"Lost sales ({currency})", fontsize=8)
    ax2 = ax.twinx()
    ax2.plot(x, df["pct_gov"].values, color=BAD, marker="o", markersize=5, linewidth=2)
    for xi, v in zip(x, df["pct_gov"].values):
        ax2.annotate(f"{v:.2f}%", (xi, v), textcoords="offset points",
                     xytext=(0, -12), ha="center", fontsize=7.5, color=BAD)
    ax2.set_ylabel("% of GOV", fontsize=8, color=BAD)
    ax2.tick_params(axis="y", colors=BAD)
    ax2.grid(False)
    ax.set_title(title)
    ax.margins(y=0.22)
    _style_axes(ax)
    ax.tick_params(length=0)
    return _fig_to_png(fig)


def gauge(value, target, title, lower_is_better=False, fmt="{:.1f}",
          suffix="", figsize=(3.0, 2.0), vmax=None):
    """Simple horizontal progress-style gauge for a single KPI vs target."""
    fig, ax = plt.subplots(figsize=figsize)
    color = _kpi_color(value, target, lower_is_better)
    vmax = vmax or max(value, target) * 1.25
    ax.barh([0], [vmax], color="#EDF1F3", height=0.5)
    ax.barh([0], [min(value, vmax)], color=color, height=0.5)
    ax.axvline(target, color=WOLT_DARK, linestyle="--", linewidth=1.2)
    ax.text(target, 0.42, f"target {fmt.format(target)}{suffix}", fontsize=7,
            ha="center", color=WOLT_DARK)
    ax.text(0, -0.55, f"{fmt.format(value)}{suffix}", fontsize=15,
            fontweight="bold", color=color, ha="left", va="center")
    ax.set_xlim(0, vmax)
    ax.set_ylim(-0.9, 0.9)
    ax.set_title(title, loc="left")
    ax.axis("off")
    return _fig_to_png(fig)
