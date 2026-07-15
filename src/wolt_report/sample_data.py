"""Deterministic synthetic data generator.

Produces realistic-looking (but fabricated) data for Metro Cyprus so the report
renders end-to-end without a live warehouse connection. The generator is seeded
so output is stable across runs.

NOTE: numbers produced here are SAMPLE DATA, not real Metro Cyprus figures.
Swap the data source to Snowflake (see config.yaml + loader.py) for real data.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import schema
from .config import Config

# Per-venue "personality" so venues differ in a believable way.
# (base daily orders, avg basket €, quality factor 0..1 higher=better)
_VENUE_PROFILE = {
    "metro-strovolos": (135, 34.0, 0.93),
    "metro-nicosia-centre": (110, 31.5, 0.88),
    "metro-limassol": (125, 33.0, 0.90),
    "metro-larnaca": (78, 29.0, 0.82),
    "metro-paphos": (64, 30.5, 0.79),
}

# Hourly demand weights across a 24h day (grocery pattern: midday + evening).
_HOUR_WEIGHTS = np.array([
    0.1, 0.05, 0.03, 0.02, 0.02, 0.05, 0.2, 0.6, 1.1, 1.6, 2.2, 2.6,
    2.4, 2.0, 1.7, 1.6, 1.9, 2.4, 2.7, 2.3, 1.6, 1.0, 0.6, 0.3,
])

_REJECTION_REASONS = [
    ("Item out of stock", 0.42),
    ("Store too busy", 0.24),
    ("Closing soon", 0.14),
    ("Technical issue", 0.11),
    ("Other", 0.09),
]

_ADDITIONS = [
    ("Marketing co-funding refund", 0.30),
    ("Service fee rebate", 0.22),
    ("Compensation reversal", 0.20),
    ("Promotion reimbursement", 0.18),
    ("Adjustment credit", 0.10),
]
_DEDUCTIONS = [
    ("Wolt commission", 0.45),
    ("Customer compensation", 0.20),
    ("Marketing spend", 0.18),
    ("Refunds", 0.12),
    ("Other fees", 0.05),
]
_COURIER_FEES = [
    ("Base delivery fee", 0.55),
    ("Distance surcharge", 0.22),
    ("Peak / surge fee", 0.15),
    ("Small order fee", 0.08),
]


def _rng(seed_text: str) -> np.random.Generator:
    seed = abs(hash(seed_text)) % (2**32)
    return np.random.default_rng(seed)


def _weighted_amounts(rng, items, total):
    weights = np.array([w for _, w in items])
    weights = weights / weights.sum()
    noise = rng.normal(1.0, 0.08, size=len(items)).clip(0.6, 1.4)
    amounts = weights * noise
    amounts = amounts / amounts.sum() * total
    return [(name, round(float(a), 2)) for (name, _), a in zip(items, amounts)]


def generate(config: Config) -> dict[str, pd.DataFrame]:
    period = config.period
    days = [period.start + dt.timedelta(days=i) for i in range((period.end - period.start).days + 1)]

    orders_rows: list[dict] = []
    offline_rows: list[dict] = []
    picker_rows: list[dict] = []
    financial_rows: list[dict] = []
    monthly_rows: list[dict] = []

    order_counter = 0
    for venue in config.venues:
        base_orders, avg_basket, quality = _VENUE_PROFILE.get(
            venue.venue_id, (90, 31.0, 0.85)
        )
        rng = _rng(venue.venue_id + period.iso_week)

        for day in days:
            # Weekend uplift.
            weekend = 1.18 if day.weekday() >= 5 else 1.0
            day_orders = int(rng.normal(base_orders * weekend, base_orders * 0.08))
            day_orders = max(day_orders, 10)

            # Distribute across hours.
            hour_probs = _HOUR_WEIGHTS / _HOUR_WEIGHTS.sum()
            hours = rng.choice(np.arange(24), size=day_orders, p=hour_probs)

            picker_orders_today = 0
            for hour in hours:
                order_counter += 1
                minute = int(rng.integers(0, 60))
                order_dt = dt.datetime.combine(day, dt.time(int(hour), minute))

                item_count = int(max(1, rng.normal(11, 4)))
                basket = float(max(6.0, rng.normal(avg_basket, avg_basket * 0.28)))
                # Gross value = basket + delivery/fees.
                gross = round(basket + rng.normal(3.2, 0.8), 2)
                basket = round(basket, 2)

                prep = float(max(3.0, rng.normal(10.5 + (1 - quality) * 4, 2.4)))
                mkr = float(max(2.0, rng.normal(6.5 + (1 - quality) * 3, 1.8)))
                delivery = float(max(12.0, rng.normal(29 + (1 - quality) * 12, 5.5)))
                delivered_dt = order_dt + dt.timedelta(minutes=delivery)

                punctual = rng.random() < (0.90 + quality * 0.08)
                is_late = not punctual and rng.random() < 0.85

                rejected = rng.random() < (0.035 * (1.6 - quality))
                rejection_reason = ""
                if rejected:
                    r = rng.random()
                    cum = 0.0
                    for reason, p in _REJECTION_REASONS:
                        cum += p
                        if r <= cum:
                            rejection_reason = reason
                            break

                cancelled = (not rejected) and rng.random() < 0.012
                substituted = int(rng.random() < (0.06 * (1.5 - quality))) * int(rng.integers(1, 3))
                unfulfilled = int(rng.random() < (0.03 * (1.6 - quality))) * int(rng.integers(1, 3))

                has_issue = rejected or cancelled or substituted > 0 or unfulfilled > 0
                is_pofr = not has_issue

                # Rating only present for a subset of delivered orders.
                rating = np.nan
                if not (rejected or cancelled) and rng.random() < 0.55:
                    base_rating = 3.6 + quality * 1.4
                    rating = float(np.clip(rng.normal(base_rating, 0.7), 1, 5))
                    rating = round(rating, 1)

                # Lost sales attribution.
                lost_gov = 0.0
                lost_reason = ""
                if rejected:
                    lost_gov, lost_reason = round(gross, 2), "Rejections"
                elif cancelled:
                    lost_gov, lost_reason = round(gross, 2), "Cancellation"
                elif unfulfilled > 0:
                    lost_gov, lost_reason = round(basket / max(item_count, 1) * unfulfilled, 2), "Unfulfilled"
                elif substituted > 0:
                    lost_gov, lost_reason = round(basket / max(item_count, 1) * substituted * 0.4, 2), "Substitutions"

                used_picker = rng.random() < (0.55 + quality * 0.3)
                if used_picker:
                    picker_orders_today += 1

                is_wolt_plus = rng.random() < 0.42
                is_new_wp = is_wolt_plus and rng.random() < 0.11

                order_number = f"WOLT-{day:%y%m%d}-{order_counter:05d}"
                purchase_id = f"pur_{order_counter:07d}"

                orders_rows.append({
                    "purchase_id": purchase_id,
                    "order_number": order_number,
                    "venue_id": venue.venue_id,
                    "venue_name": venue.name,
                    "order_datetime": order_dt,
                    "delivered_datetime": delivered_dt,
                    "gross_value": gross,
                    "basket_value": basket,
                    "item_count": item_count,
                    "is_wolt_plus": is_wolt_plus,
                    "is_new_wolt_plus": is_new_wp,
                    "prep_time_min": round(prep, 1),
                    "delivery_time_min": round(delivery, 1),
                    "marketplace_ready_min": round(mkr, 1),
                    "is_punctual": punctual,
                    "is_late": is_late,
                    "is_pofr": is_pofr,
                    "is_rejected": rejected,
                    "rejection_reason": rejection_reason,
                    "is_cancelled": cancelled,
                    "rating": rating,
                    "substituted_items": substituted,
                    "unfulfilled_items": unfulfilled,
                    "lost_sales_gov": lost_gov,
                    "lost_sales_reason": lost_reason,
                    "used_picker": used_picker,
                })

            # Offline hours for the day.
            open_hours = 15.0
            offline = float(np.clip(rng.normal((1 - quality) * 1.6, 0.4), 0, 6))
            offline_rows.append({
                "venue_id": venue.venue_id,
                "venue_name": venue.name,
                "date": day,
                "offline_hours": round(offline, 2),
                "open_hours": open_hours,
            })

            picker_rows.append({
                "venue_id": venue.venue_id,
                "venue_name": venue.name,
                "date": day,
                "orders_total": day_orders,
                "orders_picked": picker_orders_today,
            })

    orders_df = pd.DataFrame(orders_rows, columns=schema.ORDERS_COLUMNS)

    # Financial breakdowns per venue derived from that venue's GOV.
    for venue in config.venues:
        rng = _rng("fin" + venue.venue_id + period.iso_week)
        gov = float(orders_df.loc[orders_df["venue_id"] == venue.venue_id, "gross_value"].sum())
        for name, amount in _weighted_amounts(rng, _ADDITIONS, gov * 0.05):
            financial_rows.append({
                "venue_id": venue.venue_id, "venue_name": venue.name,
                "group": "addition", "category": name, "amount": amount,
            })
        for name, amount in _weighted_amounts(rng, _DEDUCTIONS, gov * 0.24):
            financial_rows.append({
                "venue_id": venue.venue_id, "venue_name": venue.name,
                "group": "deduction", "category": name, "amount": amount,
            })
        for name, amount in _weighted_amounts(rng, _COURIER_FEES, gov * 0.11):
            financial_rows.append({
                "venue_id": venue.venue_id, "venue_name": venue.name,
                "group": "courier_fee", "category": name, "amount": amount,
            })

    # Monthly picker export: month-to-date, picker orders only.
    month_start = period.end.replace(day=1)
    picker_mask = (
        orders_df["used_picker"]
        & (orders_df["order_datetime"].dt.date >= month_start)
        & (orders_df["order_datetime"].dt.date <= period.end)
    )
    for _, row in orders_df[picker_mask].iterrows():
        monthly_rows.append({
            "venue_name": row["venue_name"],
            "purchase_id": row["purchase_id"],
            "dynamic_time_delivered": row["delivered_datetime"],
            "order_number": row["order_number"],
            "rating_of_goods": row["rating"],
            "goods_items_full_amount": row["basket_value"],
        })

    return {
        "orders": orders_df,
        "offline": pd.DataFrame(offline_rows, columns=schema.OFFLINE_COLUMNS),
        "financials": pd.DataFrame(financial_rows, columns=schema.FINANCIALS_COLUMNS),
        "picker_usage": pd.DataFrame(picker_rows, columns=schema.PICKER_USAGE_COLUMNS),
        "monthly_picker": pd.DataFrame(monthly_rows, columns=schema.MONTHLY_PICKER_COLUMNS),
    }


def write_sample(config: Config) -> Path:
    frames = generate(config)
    out = config.data_dir
    out.mkdir(parents=True, exist_ok=True)
    for name, df in frames.items():
        df.to_csv(out / f"{name}.csv", index=False)
    return out
