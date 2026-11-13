#!/usr/bin/env python3
"""Render a shareable Limassol HTML map for Berezka Cuisine.

Always plots official Cyprus postal-code areas (greater Limassol) and the
seven kitchen pins. If an aggregated CSV of orders is present — or later
dropped onto the page — it choropleths those areas and ranks them.
Never plots street addresses.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEOJSON_PATH = HERE / "data" / "limassol_postcodes.geojson"

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Berezka Cuisine — Limassol customer geography</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    :root { --ink:#1f2328; --muted:#5b6169; --line:#d8dce2; --bg:#f4f1ea; --card:#fff; --accent:#134f5c; --heat:#c45c26; }
    * { box-sizing: border-box; }
    body { margin:0; font:14px/1.45 "Helvetica Neue", Helvetica, Arial, sans-serif; color:var(--ink); background:var(--bg); }
    header { padding:20px 24px 8px; max-width:1180px; margin:0 auto; }
    h1 { font-size:22px; margin:0 0 6px; font-weight:650; }
    .sub { color:var(--muted); max-width:760px; }
    .banner { max-width:1180px; margin:10px auto 0; padding:12px 14px; background:#fff8e3; border:1px solid #ead9a0; }
    .banner.ok { background:#eef6f2; border-color:#c5ddd2; }
    .wrap { display:grid; grid-template-columns:1.55fr 1fr; gap:16px; max-width:1180px; margin:16px auto 28px; padding:0 24px; }
    @media (max-width: 920px) { .wrap { grid-template-columns:1fr; } }
    #map { height:620px; border:1px solid var(--line); background:#e7e2d6; }
    aside { background:var(--card); border:1px solid var(--line); padding:14px 16px; }
    h2 { font-size:12px; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); margin:0 0 10px; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { text-align:left; padding:6px 4px; border-bottom:1px solid var(--line); vertical-align:top; }
    th { color:var(--muted); font-weight:600; }
    td.num { text-align:right; font-variant-numeric:tabular-nums; }
    .legend { display:flex; flex-wrap:wrap; gap:10px 14px; align-items:center; font-size:12px; color:var(--muted); margin-top:8px; }
    .swatch { width:12px; height:12px; display:inline-block; border:1px solid var(--line); }
    .drop { border:1px dashed #c9b99a; background:#fffdf7; padding:10px 12px; margin-bottom:12px; }
    .drop input { display:block; margin-top:6px; }
    .muted { color:var(--muted); font-size:12px; }
    .row { display:flex; gap:8px; flex-wrap:wrap; margin:8px 0 12px; }
    button { font:inherit; padding:6px 10px; border:1px solid var(--line); background:#fff; cursor:pointer; }
    button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
    footer { max-width:1180px; margin:0 auto 28px; padding:0 24px; color:var(--muted); font-size:12px; }
    code { font-size:12px; background:#eee; padding:1px 4px; }
    tr.active td { background:#fff3e8; }
  </style>
</head>
<body>
  <header>
    <h1>Berezka Cuisine — Limassol customer geography</h1>
    <p class="sub">Approximate picture of <strong>where Wolt customers are</strong>, by postal area, for advertising planning. Kitchen pins are where food is cooked, not demand. Areas with fewer than 5 orders are omitted.</p>
  </header>
  <div id="statusBanner" class="banner"></div>
  <div class="wrap">
    <div>
      <div id="map"></div>
      <div class="legend" id="legend"></div>
    </div>
    <aside>
      <div class="drop" id="drop">
        <strong>Load order geography</strong>
        <p class="muted" style="margin:6px 0 0">Drop a Looker / Snowflake CSV here. Needed columns: a postal code or lat/lng, plus an order count (or one row per order). Do not include street addresses.</p>
        <input id="file" type="file" accept=".csv,text/csv" />
      </div>
      <div class="row">
        <button type="button" id="grainPostal">By postal code</button>
        <button type="button" id="grainCommunity">By municipality</button>
        <button type="button" id="toggleKitchens">Hide kitchens</button>
      </div>
      <h2>Highest-demand areas</h2>
      <div id="tableWrap"></div>
      <p class="muted" id="scopeLine"></p>
    </aside>
  </div>
  <footer>
    Customer areas: Department of Lands and Surveys Cyprus postal-code polygons (greater Limassol).
    Kitchens: public Wolt / berezka.cy listings. Source of order counts: <span id="sourceLabel"></span>.
    Times in Asia/Nicosia. This page never stores raw addresses.
  </footer>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/h3-js@4.2.1/dist/h3-js.umd.js"></script>
  <script>
    const MIN_ORDERS = 5;
    const venues = __VENUES__;
    const geojson = __GEOJSON__;
    const bakedAreas = __AREAS__;
    const bakedSource = __SOURCE__;

    const ALIASES = {
      "3090": "Erimi",
      "3051": "Omonia / Zakaki",
      "3036": "Old Port / Marina",
      "3020": "Katholiki",
      "3165": "Neapolis",
      "4048": "Potamos Germasogeias",
      "4532": "Agios Tychonas tourist area",
      "4521": "Agios Tychon"
    };

    function enrich(rows) {
      const total = rows.reduce((s, r) => s + (r.orders || 0), 0) || 1;
      return rows.map(r => {
        const postal = String(r.postal_code || "").replace(/\.0$/, "");
        const p = postal ? postalProps(postal) : null;
        const community = r.community || (p && p.community) || "";
        const named = r.area_name && r.area_name !== "Unknown" ? r.area_name : "";
        return {
          key: postal || r.key || r.area_name,
          postal_code: postal,
          h3: r.h3 || "",
          lat: r.lat != null ? r.lat : (p && p.lat),
          lng: r.lng != null ? r.lng : (p && p.lng),
          orders: r.orders || 0,
          gov: r.gov || 0,
          community,
          area_name: named || areaLabel(postal, community),
          share_pct: r.share_pct != null ? Number(r.share_pct) : Math.round(1000 * (r.orders || 0) / total) / 10
        };
      }).sort((a, b) => b.orders - a.orders);
    }

    const state = {
      grain: "postal",
      showKitchens: true,
      rows: [],
      source: bakedSource
    };

    const map = L.map("map").setView([34.685, 33.04], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 16
    }).addTo(map);

    const kitchenLayer = L.layerGroup().addTo(map);
    venues.forEach(v => {
      L.circleMarker([v.lat, v.lng], {
        radius: 8,
        color: "#134f5c",
        weight: 2,
        fillColor: "#fff",
        fillOpacity: 1
      }).bindPopup(`<strong>${esc(v.name)}</strong><br>${esc(v.area)}<br>${esc(v.address)}<br><em>Kitchen, not customer demand</em>`)
        .addTo(kitchenLayer);
    });

    let areaLayer = null;
    let extraLayer = L.layerGroup().addTo(map);

    function esc(s) {
      return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    function normKey(s) {
      return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
    }

    function pick(row, names) {
      const mapKeys = {};
      Object.keys(row).forEach(k => { mapKeys[normKey(k)] = k; });
      for (const n of names) {
        const k = mapKeys[normKey(n)];
        if (k && row[k] !== undefined && row[k] !== "") return row[k];
      }
      return "";
    }

    function parseCsv(text) {
      const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(l => l.trim());
      if (!lines.length) return [];
      const split = line => {
        const out = []; let cur = ""; let q = false;
        for (let i = 0; i < line.length; i++) {
          const ch = line[i];
          if (ch === '"') { q = !q; continue; }
          if (ch === "," && !q) { out.push(cur); cur = ""; continue; }
          cur += ch;
        }
        out.push(cur);
        return out.map(s => s.trim());
      };
      let headerIdx = 0;
      for (let i = 0; i < Math.min(lines.length, 8); i++) {
        const n = normKey(lines[i]);
        if (n.includes("postal") || n.includes("lat") || n.includes("order") || n.includes("area") || n.includes("h3")) {
          headerIdx = i; break;
        }
      }
      const headers = split(lines[headerIdx]);
      const rows = [];
      for (let i = headerIdx + 1; i < lines.length; i++) {
        const cells = split(lines[i]);
        if (!cells.some(c => c)) continue;
        const row = {};
        headers.forEach((h, j) => { row[h] = cells[j] || ""; });
        rows.push(row);
      }
      return rows;
    }

    function looksH3(s) {
      return /^[0-9a-f]{15}$/i.test(String(s || "").trim());
    }

    function pointInRing(lng, lat, ring) {
      let inside = false;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const xi = ring[i][0], yi = ring[i][1];
        const xj = ring[j][0], yj = ring[j][1];
        const intersect = ((yi > lat) !== (yj > lat)) &&
          (lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi);
        if (intersect) inside = !inside;
      }
      return inside;
    }

    function pointInFeature(lng, lat, feature) {
      const g = feature.geometry;
      if (!g) return false;
      const polys = g.type === "Polygon" ? [g.coordinates] : (g.type === "MultiPolygon" ? g.coordinates : []);
      return polys.some(poly => pointInRing(lng, lat, poly[0] || []));
    }

    function findPostal(lng, lat) {
      if (lng == null || lat == null || Number.isNaN(lng) || Number.isNaN(lat)) return null;
      const hit = geojson.features.find(f => pointInFeature(lng, lat, f));
      return hit ? hit.properties.postal_code : null;
    }

    function postalProps(code) {
      const f = geojson.features.find(x => x.properties.postal_code === String(code));
      return f ? f.properties : null;
    }

    function areaLabel(code, community) {
      const alias = ALIASES[String(code)];
      if (alias) return `${alias} (${code})`;
      if (community && community.toLowerCase() !== "lemesos") return `${community} (${code})`;
      return `Limassol ${code}`;
    }

    function toNumber(v) {
      if (v === "" || v == null) return null;
      const n = Number(String(v).replace(/,/g, ""));
      return Number.isFinite(n) ? n : null;
    }

    function normalizeRows(raw) {
      const hasOrdersCol = raw.some(r => pick(r, ["orders", "order_count", "purchases", "count of purchases", "number of orders"]));
      const agg = new Map();
      raw.forEach(r => {
        const ordersCol = toNumber(pick(r, ["orders", "order_count", "purchases", "count of purchases", "number of orders"]));
        const qty = hasOrdersCol ? (ordersCol || 0) : 1;
        if (qty <= 0) return;
        let postal = String(pick(r, ["postal_code", "postcode", "zip", "delivery_postal_code", "customer_postal_code", "postal"])).replace(/\.0$/, "");
        const lat = toNumber(pick(r, ["lat", "latitude", "delivery_lat", "customer_lat"]));
        const lng = toNumber(pick(r, ["lng", "lon", "longitude", "delivery_lng", "customer_lng"]));
        const areaName = pick(r, ["area_name", "area", "neighbourhood", "neighborhood", "district", "h3", "h3_index"]);
        const gov = toNumber(pick(r, ["gov_eur", "gov_local", "gov", "goods_items_full_amount"]));
        if (!postal && /^\d{4}$/.test(String(areaName).trim())) postal = String(areaName).trim();
        if (!postal && lat != null && lng != null) postal = findPostal(lng, lat) || "";
        const h3id = looksH3(areaName) ? String(areaName).trim() : "";
        const key = postal || (h3id ? `h3:${h3id}` : "") || (lat != null && lng != null ? `pt:${lat.toFixed(3)},${lng.toFixed(3)}` : "");
        if (!key) return;
        const cur = agg.get(key) || {
          key, postal_code: postal, h3: h3id, lat, lng,
          orders: 0, gov: 0, area_name: "", community: ""
        };
        cur.orders += qty;
        if (gov) cur.gov += gov;
        if (postal) {
          const p = postalProps(postal);
          if (p) {
            cur.community = p.community;
            cur.lat = p.lat;
            cur.lng = p.lng;
            cur.area_name = areaLabel(postal, p.community);
          } else {
            cur.area_name = areaLabel(postal, "");
          }
        } else if (h3id) {
          cur.area_name = `H3 ${h3id.slice(0, 8)}…`;
        } else {
          cur.area_name = areaName || key;
        }
        agg.set(key, cur);
      });
      const rows = [...agg.values()].filter(r => r.orders >= MIN_ORDERS);
      const total = rows.reduce((s, r) => s + r.orders, 0) || 1;
      rows.forEach(r => { r.share_pct = Math.round(1000 * r.orders / total) / 10; });
      rows.sort((a, b) => b.orders - a.orders);
      return rows;
    }

    function rolled(rows) {
      if (state.grain === "postal") return rows;
      const m = new Map();
      rows.forEach(r => {
        const name = r.community || r.area_name || "Unknown";
        const cur = m.get(name) || { key: name, area_name: name, community: name, postal_code: "", orders: 0, gov: 0, lat: r.lat, lng: r.lng };
        cur.orders += r.orders;
        cur.gov += r.gov || 0;
        m.set(name, cur);
      });
      const out = [...m.values()];
      const total = out.reduce((s, r) => s + r.orders, 0) || 1;
      out.forEach(r => { r.share_pct = Math.round(1000 * r.orders / total) / 10; });
      out.sort((a, b) => b.orders - a.orders);
      return out;
    }

    function colorFor(orders, max) {
      if (!orders) return "#cfc6b6";
      const t = Math.sqrt(orders / max);
      const stops = ["#f7e3d4", "#e8b48a", "#d67b45", "#c45c26", "#8a3514"];
      const i = Math.min(stops.length - 1, Math.floor(t * (stops.length - 1)));
      return stops[i];
    }

    function render() {
      const rows = rolled(state.rows);
      const byPostal = new Map(state.rows.map(r => [String(r.postal_code), r]));
      const max = Math.max(0, ...state.rows.map(r => r.orders || 0));
      if (areaLayer) map.removeLayer(areaLayer);
      extraLayer.clearLayers();
      areaLayer = L.geoJSON(geojson, {
        style: f => {
          const rec = byPostal.get(String(f.properties.postal_code));
          const orders = rec ? rec.orders : 0;
          return {
            color: orders ? "#8a5a3a" : "#6e6a62",
            weight: orders ? 1 : 1.1,
            fillColor: colorFor(orders, max || 1),
            fillOpacity: orders ? 0.78 : 0.32
          };
        },
        onEachFeature: (f, layer) => {
          const rec = byPostal.get(String(f.properties.postal_code));
          const label = areaLabel(f.properties.postal_code, f.properties.community);
          const body = rec
            ? `<strong>${esc(label)}</strong><br>${rec.orders.toLocaleString()} orders${rec.share_pct != null ? ` (${rec.share_pct}% of mapped)` : ""}`
            : `<strong>${esc(label)}</strong><br>No mapped orders (≥ ${MIN_ORDERS})`;
          layer.bindPopup(body);
        }
      }).addTo(map);

      state.rows.forEach(r => {
        if (r.postal_code && byPostal.has(String(r.postal_code))) return;
        if (r.h3 && window.h3) {
          try {
            const bound = h3.cellToBoundary(r.h3).map(([lat, lng]) => [lat, lng]);
            L.polygon(bound, { color: "#c45c26", weight: 1, fillOpacity: 0.35 })
              .bindPopup(`<strong>${esc(r.area_name)}</strong><br>${r.orders} orders`)
              .addTo(extraLayer);
            return;
          } catch (e) {}
        }
        if (r.lat != null && r.lng != null) {
          L.circle([r.lat, r.lng], {
            radius: 180 + (max ? (r.orders / max) * 620 : 0),
            color: "#c45c26", weight: 1, fillColor: "#c45c26", fillOpacity: 0.22
          }).bindPopup(`<strong>${esc(r.area_name)}</strong><br>${r.orders} orders`).addTo(extraLayer);
        }
      });

      kitchenLayer[state.showKitchens ? "addTo" : "removeFrom"](map);

      const banner = document.getElementById("statusBanner");
      if (!state.rows.length) {
        banner.className = "banner";
        banner.innerHTML = "<strong>Order heatmap is not loaded yet.</strong> The polygons are official Limassol postal areas with no customer counts. Export Looker <code>core / f_purchases</code> for Berezka in Limassol (last 12 months, delivery postal code or lat/lng — not street address) and drop the CSV on the right.";
      } else {
        banner.className = "banner ok";
        banner.innerHTML = `<strong>${state.rows.length} areas</strong> with at least ${MIN_ORDERS} delivered orders. Darker orange = more orders. Kitchen pins remain a separate layer.`;
      }

      const top = rows.slice(0, 15);
      if (!top.length) {
        document.getElementById("tableWrap").innerHTML = "<p>No aggregated order areas yet.</p>";
      } else {
        document.getElementById("tableWrap").innerHTML =
          "<table><thead><tr><th>Area</th><th class='num'>Orders</th><th class='num'>Share</th></tr></thead><tbody>" +
          top.map((r, i) => `<tr${i===0?" class='active'":""}><td>${esc(r.area_name)}</td><td class="num">${r.orders.toLocaleString()}</td><td class="num">${r.share_pct == null ? "—" : Number(r.share_pct).toFixed(1) + "%"}</td></tr>`).join("") +
          "</tbody></table>";
      }

      const total = state.rows.reduce((s, r) => s + r.orders, 0);
      document.getElementById("scopeLine").textContent = total
        ? `${total.toLocaleString()} mapped orders across ${state.rows.length} areas (≥ ${MIN_ORDERS} each). Grain: ${state.grain === "postal" ? "postal code" : "municipality / community"}.`
        : "Waiting for an area-level order export.";
      document.getElementById("sourceLabel").textContent = state.source;
      document.getElementById("legend").innerHTML =
        '<span><span class="swatch" style="background:#fff;border-color:#134f5c"></span> Kitchen</span>' +
        '<span><span class="swatch" style="background:#cfc6b6"></span> No mapped orders</span>' +
        '<span><span class="swatch" style="background:#e8b48a"></span> Lower demand</span>' +
        '<span><span class="swatch" style="background:#8a3514"></span> Highest demand</span>';
    }

    function ingestCsv(text, label) {
      const raw = parseCsv(text);
      state.rows = normalizeRows(raw);
      state.source = label || "CSV dropped in the browser";
      render();
    }

    const fileInput = document.getElementById("file");
    fileInput.addEventListener("change", e => {
      const f = e.target.files && e.target.files[0];
      if (!f) return;
      f.text().then(t => ingestCsv(t, f.name));
    });
    const drop = document.getElementById("drop");
    drop.addEventListener("dragover", e => { e.preventDefault(); });
    drop.addEventListener("drop", e => {
      e.preventDefault();
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (!f) return;
      f.text().then(t => ingestCsv(t, f.name));
    });
    document.getElementById("grainPostal").onclick = () => { state.grain = "postal"; render(); };
    document.getElementById("grainCommunity").onclick = () => { state.grain = "community"; render(); };
    document.getElementById("toggleKitchens").onclick = ev => {
      state.showKitchens = !state.showKitchens;
      ev.target.textContent = state.showKitchens ? "Hide kitchens" : "Show kitchens";
      render();
    };

    state.rows = enrich(bakedAreas.slice());
    render();
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
            postal = raw.get("postal_code") or raw.get("POSTAL_CODE") or ""
            rows.append(
                {
                    "area_name": raw.get("area_name") or raw.get("AREA_NAME") or "Unknown",
                    "postal_code": postal,
                    "lat": float(lat) if lat else None,
                    "lng": float(lng) if lng else None,
                    "orders": int(float(orders)),
                    "share_pct": float(share) if share else None,
                    "community": raw.get("community") or "",
                    "h3": raw.get("h3") or "",
                }
            )
    rows.sort(key=lambda r: r["orders"], reverse=True)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venues", type=Path, default=HERE / "venues.json")
    parser.add_argument("--geojson", type=Path, default=GEOJSON_PATH)
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
    geojson = json.loads(args.geojson.read_text(encoding="utf-8"))
    areas = load_areas(args.csv if args.csv.exists() else None)
    source = (
        f"Wolt Snowflake / Looker extract; {len(areas)} areas (≥5 orders)"
        if areas
        else "waiting for Looker or Snowflake CSV"
    )
    html = (
        HTML.replace("__VENUES__", json.dumps(venues))
        .replace("__GEOJSON__", json.dumps(geojson, separators=(",", ":")))
        .replace("__AREAS__", json.dumps(areas))
        .replace("__SOURCE__", json.dumps(source))
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"wrote {args.output} ({len(venues)} kitchens, {len(geojson['features'])} postal areas, {len(areas)} order areas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
