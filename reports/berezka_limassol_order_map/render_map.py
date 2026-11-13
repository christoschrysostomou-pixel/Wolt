#!/usr/bin/env python3
"""Render a shareable Limassol HTML map for Berezka Cuisine.

Always plots kitchen locations from venues.json. If an aggregated CSV of
order areas is present (from Snowflake or Looker), overlays demand as
circles sized by order count — never street addresses.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Berezka Cuisine — Limassol order geography</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    :root { --ink: #1f2328; --muted: #5b6169; --line: #d8dce2; --bg: #f6f5f1; --card: #fff; --accent: #134f5c; }
    * { box-sizing: border-box; }
    body { margin: 0; font: 14px/1.45 "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink); background: var(--bg); }
    header { padding: 20px 24px 8px; max-width: 1100px; margin: 0 auto; }
    h1 { font-size: 22px; margin: 0 0 6px; font-weight: 650; }
    .sub { color: var(--muted); max-width: 720px; }
    .banner { max-width: 1100px; margin: 8px auto 0; padding: 10px 14px; background: #fff8e3; border: 1px solid #ead9a0; }
    .wrap { display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; max-width: 1100px; margin: 16px auto 32px; padding: 0 24px; }
    @media (max-width: 860px) { .wrap { grid-template-columns: 1fr; } }
    #map { height: 560px; border: 1px solid var(--line); background: #e8e4db; }
    aside { background: var(--card); border: 1px solid var(--line); padding: 14px 16px; }
    h2 { font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid var(--line); vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    td.num { text-align: right; font-variant-numeric: tabular-nums; }
    .legend { display: flex; gap: 12px; align-items: center; font-size: 12px; color: var(--muted); margin-top: 8px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    footer { max-width: 1100px; margin: 0 auto 28px; padding: 0 24px; color: var(--muted); font-size: 12px; }
  </style>
</head>
<body>
  <header>
    <h1>Berezka Cuisine — Limassol customer geography</h1>
    <p class="sub">Approximate picture of where Wolt customers are, for advertising planning. Areas with fewer than 5 orders are omitted.</p>
  </header>
  __BANNER__
  <div class="wrap">
    <div>
      <div id="map"></div>
      <div class="legend">
        <span><span class="dot" style="background:#134f5c"></span> Kitchen</span>
        <span><span class="dot" style="background:#c45c26"></span> Order density (aggregated)</span>
      </div>
    </div>
    <aside>
      <h2>Highest-demand areas</h2>
      __TABLE__
    </aside>
  </div>
  <footer>
    Source: __SOURCE__. Times in Asia/Nicosia. Kitchen pins from public Wolt / berezka.cy listings.
    Do not treat kitchen locations as customer demand.
  </footer>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const venues = __VENUES__;
    const areas = __AREAS__;
    const map = L.map("map").setView([34.685, 33.04], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 16
    }).addTo(map);

    const maxOrders = Math.max(0, ...areas.map(a => a.orders || 0));
    areas.forEach(a => {
      if (a.lat == null || a.lng == null) return;
      const radius = 180 + (maxOrders ? (a.orders / maxOrders) * 620 : 0);
      L.circle([a.lat, a.lng], {
        radius,
        color: "#c45c26",
        weight: 1,
        fillColor: "#c45c26",
        fillOpacity: 0.22
      }).bindPopup(
        `<strong>${a.area_name}</strong><br>${a.orders} orders` +
        (a.share_pct != null ? ` (${a.share_pct}% of mapped)` : "")
      ).addTo(map);
    });

    venues.forEach(v => {
      L.circleMarker([v.lat, v.lng], {
        radius: 7,
        color: "#134f5c",
        weight: 2,
        fillColor: "#fff",
        fillOpacity: 1
      }).bindPopup(
        `<strong>${v.name}</strong><br>${v.area}<br>${v.address}`
      ).addTo(map);
    });
  </script>
</body>
</html>
"""


def load_venues(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["venues"]


def load_areas(csv_path: Path | None) -> list[dict]:
    if csv_path is None or not csv_path.exists():
        return []
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            orders = raw.get("orders") or raw.get("ORDERS") or "0"
            lat = raw.get("lat") or raw.get("LAT") or ""
            lng = raw.get("lng") or raw.get("LNG") or raw.get("lon") or ""
            share = raw.get("share_pct") or raw.get("SHARE_PCT") or ""
            rows.append(
                {
                    "area_name": raw.get("area_name") or raw.get("AREA_NAME") or "Unknown",
                    "lat": float(lat) if lat else None,
                    "lng": float(lng) if lng else None,
                    "orders": int(float(orders)),
                    "share_pct": float(share) if share else None,
                    "gov_local": raw.get("gov_local") or raw.get("gov_eur") or "",
                }
            )
    rows.sort(key=lambda r: r["orders"], reverse=True)
    return rows


def table_html(areas: list[dict]) -> str:
    if not areas:
        return (
            "<p>No aggregated order areas yet. Run the Snowflake extractor "
            "or pass a Looker CSV.</p>"
        )
    body = []
    for row in areas[:12]:
        share = f"{row['share_pct']:.1f}%" if row.get("share_pct") is not None else "—"
        body.append(
            "<tr>"
            f"<td>{row['area_name']}</td>"
            f"<td class='num'>{row['orders']:,}</td>"
            f"<td class='num'>{share}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Area</th><th class='num'>Orders</th>"
        "<th class='num'>Share</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def banner_html(areas: list[dict]) -> str:
    if areas:
        return ""
    return (
        '<div class="banner"><strong>Order heatmap not loaded.</strong> '
        "This view shows kitchen locations only. Complete Snowflake SSO locally "
        "or drop a Looker area CSV, then re-run <code>render_map.py</code>.</div>"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venues", type=Path, default=HERE / "venues.json")
    parser.add_argument("--csv", type=Path, default=HERE / "output" / "areas.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "output" / "berezka_limassol_order_map.html",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    venues = load_venues(args.venues)
    areas = load_areas(args.csv if args.csv.exists() else None)
    source = (
        f"Wolt Snowflake, last extract; {len(areas)} areas (≥5 orders)"
        if areas
        else "public kitchen listings only"
    )
    html = (
        HTML.replace("__VENUES__", json.dumps(venues))
        .replace("__AREAS__", json.dumps(areas))
        .replace("__TABLE__", table_html(areas))
        .replace("__BANNER__", banner_html(areas))
        .replace("__SOURCE__", source)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"wrote {args.output} ({len(venues)} kitchens, {len(areas)} areas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
