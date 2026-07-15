"""PDF report assembly.

Builds a multi-page PDF:

* Page 1  – merchant-wide preview (KPI cards + headline charts).
* Then    – one section of pages per venue covering Purchases, Wolt+,
            Operations, Quality, Additions & Deductions and Picker.
* Appendix – merchant-wide Monthly Picker Metrics table.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from . import charts, metrics
from .config import Config
from .loader import ReportData

WOLT_BLUE = colors.HexColor("#00C2E8")
WOLT_DARK = colors.HexColor("#032E3F")
WOLT_NAVY = colors.HexColor("#00688B")
GOOD = colors.HexColor("#2BB673")
WARN = colors.HexColor("#F5A623")
BAD = colors.HexColor("#E5484D")
LIGHT = colors.HexColor("#F2F6F8")
GREY = colors.HexColor("#8A9BA8")


class ReportBuilder:
    def __init__(self, config: Config, data: ReportData, sample: bool = True):
        self.config = config
        self.data = data
        self.sample = sample
        self.cur = config.currency_symbol
        self._styles()

    # ------------------------------------------------------------------ styles
    def _styles(self) -> None:
        ss = getSampleStyleSheet()
        self.h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=WOLT_DARK,
                                 fontSize=26, leading=30, spaceAfter=2)
        self.h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=colors.white,
                                 fontSize=13, leading=16, leftIndent=4)
        self.h3 = ParagraphStyle("h3", parent=ss["Heading3"], textColor=WOLT_NAVY,
                                 fontSize=11, leading=13, spaceBefore=6, spaceAfter=2)
        self.body = ParagraphStyle("body", parent=ss["Normal"], textColor=WOLT_DARK,
                                   fontSize=9, leading=12)
        self.small = ParagraphStyle("small", parent=ss["Normal"], textColor=GREY,
                                    fontSize=7.5, leading=9)
        self.cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=8, leading=10)
        self.cell_center = ParagraphStyle("cellc", parent=self.cell, alignment=TA_CENTER)
        self.kpi_num = ParagraphStyle("kpinum", parent=ss["Normal"], fontSize=17,
                                     leading=19, textColor=WOLT_DARK, alignment=TA_CENTER,
                                     fontName="Helvetica-Bold")
        self.kpi_lbl = ParagraphStyle("kpilbl", parent=ss["Normal"], fontSize=7.5,
                                     leading=9, textColor=GREY, alignment=TA_CENTER)

    # -------------------------------------------------------------- doc set-up
    def build(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc = BaseDocTemplate(
            str(output_path), pagesize=A4,
            leftMargin=1.4 * cm, rightMargin=1.4 * cm,
            topMargin=2.4 * cm, bottomMargin=1.4 * cm,
            title=f"{self.config.merchant_name} Weekly Report {self.config.period.label}",
            author="Wolt Merchant Analytics",
        )
        frame = Frame(doc.leftMargin, doc.bottomMargin,
                      doc.width, doc.height, id="main")
        doc.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=self._cover_header),
            PageTemplate(id="content", frames=[frame], onPage=self._content_header),
        ])

        story: list = []
        story += self._cover_page()
        story.append(NextPageTemplate("content"))
        story.append(PageBreak())

        for i, venue in enumerate(self.config.venues):
            story += self._venue_pages(venue)
            if i < len(self.config.venues) - 1:
                story.append(PageBreak())

        story.append(PageBreak())
        story += self._monthly_picker_appendix()

        doc.build(story)
        return output_path

    # ---------------------------------------------------------- headers/footers
    def _base_footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        footer = f"{self.config.merchant_name}  ·  Wolt Weekly Report  ·  {self.config.period.label}"
        if self.sample:
            footer += "  ·  SAMPLE DATA (not real figures)"
        canvas.drawString(1.4 * cm, 0.9 * cm, footer)
        canvas.drawRightString(A4[0] - 1.4 * cm, 0.9 * cm, f"Page {doc.page}")
        canvas.restoreState()

    def _cover_header(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(WOLT_DARK)
        canvas.rect(0, A4[1] - 1.4 * cm, A4[0], 1.4 * cm, fill=1, stroke=0)
        canvas.setFillColor(WOLT_BLUE)
        canvas.rect(0, A4[1] - 1.5 * cm, A4[0], 0.1 * cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.white)
        canvas.drawString(1.4 * cm, A4[1] - 0.95 * cm, "wolt")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(A4[0] - 1.4 * cm, A4[1] - 0.95 * cm, "Merchant Weekly Report")
        canvas.restoreState()
        self._base_footer(canvas, doc)

    def _content_header(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(WOLT_DARK)
        canvas.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, fill=1, stroke=0)
        canvas.setFillColor(WOLT_BLUE)
        canvas.rect(0, A4[1] - 1.2 * cm, A4[0], 0.08 * cm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(colors.white)
        canvas.drawString(1.4 * cm, A4[1] - 0.78 * cm, self.config.merchant_name)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(A4[0] - 1.4 * cm, A4[1] - 0.78 * cm,
                               f"Week {self.config.period.iso_week}  ·  {self.config.period.label}")
        canvas.restoreState()
        self._base_footer(canvas, doc)

    # ------------------------------------------------------------- helpers
    def _img(self, png_buf, width_cm=8.4):
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(png_buf)
        iw, ih = ir.getSize()
        w = width_cm * cm
        h = w * ih / iw
        png_buf.seek(0)
        return Image(png_buf, width=w, height=h)

    def _charts_row(self, buffers, width_cm=8.4, gap=0.4):
        imgs = [self._img(b, width_cm) for b in buffers]
        if len(imgs) == 1:
            return imgs[0]
        t = Table([imgs], colWidths=[width_cm * cm + gap * cm] * len(imgs))
        t.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    def _section_banner(self, title, color=WOLT_NAVY):
        t = Table([[Paragraph(title, self.h2)]], colWidths=[self.doc_width()])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    def doc_width(self):
        return A4[0] - 2.8 * cm

    def _kpi_cards(self, items, per_row=5):
        """items: list of (value_str, label, color)."""
        cells = []
        for value, label, color in items:
            inner = Table([
                [Paragraph(value, ParagraphStyle("k", parent=self.kpi_num, textColor=color))],
                [Paragraph(label, self.kpi_lbl)],
            ], colWidths=[self.doc_width() / per_row - 0.2 * cm])
            inner.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DCE5EA")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            cells.append(inner)

        rows = [cells[i:i + per_row] for i in range(0, len(cells), per_row)]
        for r in rows:
            while len(r) < per_row:
                r.append("")
        t = Table(rows, colWidths=[self.doc_width() / per_row] * per_row)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    def _table(self, df: pd.DataFrame, headers, fmts, col_widths=None, align_right=True):
        head = [Paragraph(f"<b>{h}</b>", self.cell) for h in headers]
        data = [head]
        for _, row in df.iterrows():
            line = []
            for col, fmt in fmts:
                val = row[col] if col in row else ""
                try:
                    txt = fmt(val)
                except Exception:
                    txt = str(val)
                line.append(Paragraph(txt, self.cell))
            data.append(line)
        t = Table(data, colWidths=col_widths, repeatRows=1)
        style = [
            ("BACKGROUND", (0, 0), (-1, 0), WOLT_DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DCE5EA")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if align_right:
            style.append(("ALIGN", (1, 1), (-1, -1), "RIGHT"))
        t.setStyle(TableStyle(style))
        return t

    # --------------------------------------------------------------- cover page
    def _cover_page(self):
        cfg = self.config
        k = metrics.kpis(self.data.orders)
        story: list = [Spacer(1, 0.3 * cm)]

        title = Paragraph(f"{cfg.merchant_name}", self.h1)
        subtitle = Paragraph(
            f"Weekly Performance Report &nbsp;·&nbsp; Week {cfg.period.iso_week} "
            f"&nbsp;·&nbsp; {cfg.period.label}", self.body)
        story += [title, subtitle, Spacer(1, 0.15 * cm)]
        story.append(Paragraph(
            f"Merchant overview across {len(cfg.venues)} venues. "
            f"Page 1 summarises the whole merchant; the following pages break "
            f"down each venue individually.", self.small))
        if self.sample:
            story.append(Paragraph(
                "<b>Note:</b> figures below are synthetic sample data generated "
                "for demonstration (live warehouse connection was unavailable). "
                "Point <i>data_source</i> at Snowflake in config.yaml for real numbers.",
                ParagraphStyle("warn", parent=self.small, textColor=BAD)))
        story.append(Spacer(1, 0.3 * cm))

        t = cfg.targets
        cards = [
            (f"{k['orders']:,}", "Total Orders", WOLT_DARK),
            (f"{self.cur}{k['gov']:,.0f}", "Group Gross Value", WOLT_DARK),
            (f"{self.cur}{k['avg_basket']:.2f}", "Avg Basket Value", WOLT_DARK),
            (f"{k['wolt_plus_orders']:,}", "Wolt+ Orders", WOLT_BLUE),
            (f"{k['wolt_plus_new_users']:,}", "Wolt+ New Users", WOLT_BLUE),
            (f"{k['pofr_pct']:.1f}%", "POFR (Group)", self._c(k['pofr_pct'], t.get('pofr_pct', 98))),
            (f"{k['punctuality_pct']:.1f}%", "Punctuality", self._c(k['punctuality_pct'], t.get('punctuality_pct', 95))),
            (f"{k['rejection_pct']:.1f}%", "Rejections", self._c(k['rejection_pct'], t.get('rejection_pct', 2), lower=True)),
            (f"{k['avg_delivery_min']:.0f} min", "Avg Delivery", self._c(k['avg_delivery_min'], t.get('avg_delivery_min', 35), lower=True)),
            (self._rating_str(k['avg_rating']), "Avg Rating", self._c(k['avg_rating'], t.get('rating', 4.7))),
        ]
        story.append(self._kpi_cards(cards, per_row=5))
        story.append(Spacer(1, 0.35 * cm))

        # Charts: orders per venue, GOV per venue.
        opv = metrics.orders_per_venue(self.data.orders)
        gpv = metrics.gov_per_venue(self.data.orders)
        story.append(self._charts_row([
            charts.hbar(opv, "Orders per Venue", fmt="{:.0f}", color=charts.WOLT_BLUE),
            charts.hbar(gpv, f"Gross Value per Venue ({self.cur})",
                        fmt="{:,.0f}", color=charts.WOLT_NAVY),
        ]))
        story.append(Spacer(1, 0.2 * cm))

        # Orders per day (merchant) + orders per hour (merchant).
        opd = metrics.orders_per_day(self.data.orders)
        opd.index = [d.strftime("%a %d") for d in opd.index]
        oph = metrics.orders_per_hour(self.data.orders)
        story.append(self._charts_row([
            charts.line(opd, "Orders per Day (Group)", color=charts.WOLT_NAVY),
            charts.vbar(oph, "Orders per Hour (Group)", color=charts.WOLT_BLUE),
        ]))
        story.append(Spacer(1, 0.2 * cm))

        # Lost sales overview + per-store rating.
        ls = metrics.lost_sales_breakdown(self.data.orders)
        qbv = metrics.quality_by_venue(self.data.orders, self.data.offline)
        story.append(self._charts_row([
            charts.lost_sales_combo(ls, "Lost Sales by Reason (Group)", currency=self.cur),
            charts.hbar(qbv["avg_rating"].sort_values(ascending=False),
                        "Rating per Store", fmt="{:.2f}", color=charts.ACCENT,
                        target=t.get("rating", 4.7), lower_is_better=False),
        ]))
        return story

    # ------------------------------------------------------------- venue pages
    def _venue_pages(self, venue):
        vd = self.data.for_venue(venue.venue_id)
        cfg = self.config
        t = cfg.targets
        story: list = []
        story.append(Paragraph(venue.name, self.h1))
        story.append(Paragraph(
            f"Venue breakdown &nbsp;·&nbsp; {cfg.period.label}", self.small))
        story.append(Spacer(1, 0.2 * cm))

        if vd.orders.empty:
            story.append(Paragraph("No orders for this venue in the selected week.", self.body))
            return story

        k = metrics.kpis(vd.orders)
        cards = [
            (f"{k['orders']:,}", "Orders", WOLT_DARK),
            (f"{self.cur}{k['gov']:,.0f}", "Gross Value", WOLT_DARK),
            (f"{self.cur}{k['avg_basket']:.2f}", "Avg Basket", WOLT_DARK),
            (f"{k['wolt_plus_orders']:,}", "Wolt+ Orders", WOLT_BLUE),
            (f"{k['wolt_plus_new_users']:,}", "Wolt+ New Users", WOLT_BLUE),
            (f"{k['pofr_pct']:.1f}%", "POFR", self._c(k['pofr_pct'], t.get('pofr_pct', 98))),
            (f"{k['punctuality_pct']:.1f}%", "Punctuality", self._c(k['punctuality_pct'], t.get('punctuality_pct', 95))),
            (f"{k['rejection_pct']:.1f}%", "Rejections", self._c(k['rejection_pct'], t.get('rejection_pct', 2), lower=True)),
            (f"{k['avg_delivery_min']:.0f} min", "Avg Delivery", self._c(k['avg_delivery_min'], t.get('avg_delivery_min', 35), lower=True)),
            (self._rating_str(k['avg_rating']), "Avg Rating", self._c(k['avg_rating'], t.get('rating', 4.7))),
        ]
        story.append(self._kpi_cards(cards, per_row=5))
        story.append(Spacer(1, 0.25 * cm))

        # --- Purchases ---
        story.append(self._section_banner("Purchases"))
        story.append(Spacer(1, 0.15 * cm))
        oph = metrics.orders_per_hour(vd.orders)
        opd = metrics.orders_per_day(vd.orders)
        opd.index = [d.strftime("%a %d") for d in opd.index]
        story.append(self._charts_row([
            charts.vbar(oph, "Orders per Hour", color=charts.WOLT_BLUE),
            charts.line(opd, "Orders per Day", color=charts.WOLT_NAVY),
        ]))
        story.append(Spacer(1, 0.15 * cm))

        # --- Wolt+ ---
        story.append(self._section_banner("Wolt+"))
        story.append(Spacer(1, 0.15 * cm))
        wp = pd.Series({
            "W+ Orders": k["wolt_plus_orders"],
            "Non W+ Orders": k["orders"] - k["wolt_plus_orders"],
        })
        wp_new = pd.Series({
            "New W+ Users": k["wolt_plus_new_users"],
            "Returning W+": max(k["wolt_plus_orders"] - k["wolt_plus_new_users"], 0),
        })
        story.append(self._charts_row([
            charts.donut(wp, "Wolt+ vs Non-Wolt+ Orders", fmt="{:.0f}"),
            charts.donut(wp_new, "Wolt+ New vs Returning", fmt="{:.0f}"),
        ]))
        story.append(Spacer(1, 0.15 * cm))

        # --- Operations ---
        story.append(self._section_banner("Operations"))
        story.append(Spacer(1, 0.15 * cm))
        ops_series = pd.Series({
            "POFR %": k["pofr_pct"],
            "Punctuality %": k["punctuality_pct"],
            "Ops Perf.": k["ops_performance"],
            "Late Orders %": k["late_orders_pct"],
            "Substitution %": k["substitution_pct"],
            "Unfulfilled %": k["unfulfilled_pct"],
        })
        times_series = pd.Series({
            "Delivery": k["avg_delivery_min"],
            "Prep": k["avg_prep_min"],
            "Marker Ready": k["avg_marker_ready_min"],
        })
        story.append(self._charts_row([
            charts.hbar(ops_series, "Operational Rates (%)", fmt="{:.1f}", color=charts.WOLT_NAVY),
            charts.hbar(times_series, "Avg Times (minutes)", fmt="{:.1f}", color=charts.WOLT_BLUE),
        ]))
        story.append(Spacer(1, 0.15 * cm))

        # --- Quality ---
        story.append(self._section_banner("Quality"))
        story.append(Spacer(1, 0.15 * cm))
        qbv = metrics.quality_by_venue(vd.orders, vd.offline)
        qseries = pd.Series({
            "Rejections %": float(qbv["rejection_pct"].iloc[0]) if not qbv.empty else 0.0,
            "Offline %": float(qbv["offline_pct"].iloc[0]) if not qbv.empty else 0.0,
        })
        offline_hours = float(qbv["offline_hours"].iloc[0]) if not qbv.empty else 0.0
        ls = metrics.lost_sales_breakdown(vd.orders)
        story.append(self._charts_row([
            charts.lost_sales_combo(ls, "Lost Sales by Reason", currency=self.cur),
            charts.donut(metrics.rejection_reasons(vd.orders) if not metrics.rejection_reasons(vd.orders).empty
                         else pd.Series({"No rejections": 1}),
                         "Rejection Reasons", fmt="{:.0f}"),
        ]))
        story.append(Spacer(1, 0.1 * cm))
        quality_cards = [
            (f"{qseries['Rejections %']:.1f}%", "Rejections %",
             self._c(qseries['Rejections %'], t.get('rejection_pct', 2), lower=True)),
            (self._rating_str(k['avg_rating']), "Rating per Store",
             self._c(k['avg_rating'], t.get('rating', 4.7))),
            (f"{qseries['Offline %']:.2f}%", "Offline % (New)",
             self._c(qseries['Offline %'], t.get('offline_pct', 1), lower=True)),
            (f"{offline_hours:.1f} h", "Offline Hours (New)", WOLT_DARK),
            (f"{self.cur}{ls['lost_eur'].sum():,.0f}", "Lost Sales GOV", BAD),
        ]
        story.append(self._kpi_cards(quality_cards, per_row=5))
        story.append(Spacer(1, 0.15 * cm))

        # --- Additions & Deductions ---
        story.append(self._section_banner("Additions & Deductions"))
        story.append(Spacer(1, 0.15 * cm))
        add = metrics.financial_breakdown(vd.financials, "addition")
        ded = metrics.financial_breakdown(vd.financials, "deduction")
        cf = metrics.financial_breakdown(vd.financials, "courier_fee")
        story.append(self._charts_row([
            charts.donut(add, f"Addition Breakdown ({self.cur})", fmt="{:,.0f}", value_suffix=""),
            charts.donut(ded, f"Deduction Breakdown ({self.cur})", fmt="{:,.0f}"),
        ]))
        story.append(Spacer(1, 0.1 * cm))
        story.append(self._charts_row([charts.donut(cf, f"Courier Fee Breakdown ({self.cur})", fmt="{:,.0f}")],
                                      width_cm=9.0))
        story.append(Spacer(1, 0.15 * cm))

        # --- Picker ---
        story.append(self._section_banner("Picker"))
        story.append(Spacer(1, 0.15 * cm))
        pu = metrics.picker_usage_by_venue(vd.picker_usage)
        usage_pct = float(pu["picker_usage_pct"].iloc[0]) if not pu.empty else 0.0
        picked = int(pu["orders_picked"].iloc[0]) if not pu.empty else 0
        total = int(pu["orders_total"].iloc[0]) if not pu.empty else 0
        picker_cards = [
            (f"{usage_pct:.1f}%", "Picker Usage per Store", WOLT_BLUE),
            (f"{picked:,}", "Orders via Picker", WOLT_DARK),
            (f"{total:,}", "Total Orders", WOLT_DARK),
        ]
        story.append(self._kpi_cards(picker_cards, per_row=5))

        # Per-venue monthly picker sample rows.
        mp = metrics.monthly_picker_table(vd.monthly_picker, limit=8)
        if not mp.empty:
            story.append(Spacer(1, 0.15 * cm))
            story.append(Paragraph("Monthly Picker Metrics (most recent, month-to-date)", self.h3))
            story.append(self._monthly_picker_flowable(mp))

        return story

    # ------------------------------------------------ monthly picker appendix
    def _monthly_picker_flowable(self, mp: pd.DataFrame):
        headers = ["Venue Name", "Purchase ID", "Delivered", "Order Number",
                   "Rating of Goods", f"Goods Items ({self.cur})"]
        fmts = [
            ("venue_name", lambda v: str(v)),
            ("purchase_id", lambda v: str(v)),
            ("dynamic_time_delivered", lambda v: pd.to_datetime(v).strftime("%Y-%m-%d %H:%M")),
            ("order_number", lambda v: str(v)),
            ("rating_of_goods", lambda v: "—" if pd.isna(v) else f"{float(v):.1f}"),
            ("goods_items_full_amount", lambda v: f"{self.cur}{float(v):,.2f}"),
        ]
        col_widths = [3.2 * cm, 2.6 * cm, 3.0 * cm, 3.4 * cm, 2.4 * cm, 3.0 * cm]
        return self._table(mp, headers, fmts, col_widths=col_widths, align_right=False)

    def _monthly_picker_appendix(self):
        story: list = [
            Paragraph("Monthly Picker Metrics", self.h1),
            Paragraph(
                f"Order-level export for all venues, month-to-date "
                f"({self.config.period.end.replace(day=1):%d %b %Y} – {self.config.period.end:%d %b %Y}). "
                f"Picker-fulfilled orders only.", self.small),
            Spacer(1, 0.25 * cm),
        ]
        mp = metrics.monthly_picker_table(self.data.monthly_picker, limit=45)
        if mp.empty:
            story.append(Paragraph("No picker orders in the current month.", self.body))
            return story
        total = len(self.data.monthly_picker)
        story.append(self._monthly_picker_flowable(mp))
        story.append(Spacer(1, 0.15 * cm))
        story.append(Paragraph(
            f"Showing {len(mp)} of {total:,} picker orders month-to-date. "
            f"Full dataset is available in data/monthly_picker.csv.", self.small))
        return story


    # ------------------------------------------------------------- utilities
    def _c(self, value, target, lower=False):
        if value != value:  # NaN
            return GREY
        if lower:
            if value <= target:
                return GOOD
            if value <= target * 1.5:
                return WARN
            return BAD
        if value >= target:
            return GOOD
        if value >= target * 0.9:
            return WARN
        return BAD

    def _rating_str(self, rating):
        return "—" if rating != rating else f"{rating:.2f}"
