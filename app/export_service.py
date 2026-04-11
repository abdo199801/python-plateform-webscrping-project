from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Business, ScrapeRun


EXPORT_DIR = Path(__file__).resolve().parent.parent / "results" / "exports"


def ensure_export_dir() -> Path:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


def build_export_basename(run: ScrapeRun) -> str:
    keyword = "_".join((run.keyword or "scrape").lower().split()[:3])
    location = "_".join(((run.location or "worldwide").lower()).split()[:3])
    timestamp = run.created_at.strftime("%Y%m%d_%H%M%S") if run.created_at else "latest"
    return f"run_{run.id}_{keyword}_{location}_{timestamp}"


def businesses_to_dataframe(run: ScrapeRun) -> pd.DataFrame:
    rows: list[dict] = []
    for business in run.businesses:
        rows.append(_serialize_business_row(business))
    return pd.DataFrame(rows)


def _serialize_business_row(business: Business) -> dict:
    return {
        "Name": business.name,
        "Category": business.category or "",
        "Phone": business.phone or "",
        "Email": business.email or "",
        "Website": business.website or "",
        "City": business.city or "",
        "Country": business.country or "",
        "Address": business.address or "",
        "Extraction Sources": business.extraction_sources or "",
        "AI Place Summary": business.ai_place_summary or "",
        "AI Current Hours": business.ai_current_hours or "",
        "AI Popular Times": business.ai_popular_times or "",
        "AI Review Highlights": business.ai_review_highlights or "",
        "AI Enrichment Status": business.ai_enrichment_status or "",
        "Dedupe Status": business.dedupe_status or "",
        "Duplicate Of": business.duplicate_of_business_id or "",
        "Dedupe Confidence": business.dedupe_confidence or "",
        "Rating": business.rating,
        "Reviews": business.reviews_count,
        "Description": business.description or "",
    }


def exportable_businesses_to_dataframe(businesses: Iterable[Business]) -> pd.DataFrame:
    rows: list[dict] = []
    for business in businesses:
        rows.append(
            _serialize_business_row(business)
        )
    return pd.DataFrame(rows)


def build_business_export_basename(label: str) -> str:
    safe_label = "_".join((label or "businesses").lower().split()[:6]) or "businesses"
    timestamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{safe_label}_{timestamp}"


def export_run_to_excel(run: ScrapeRun) -> Path:
    export_dir = ensure_export_dir()
    path = export_dir / f"{build_export_basename(run)}.xlsx"
    businesses_to_dataframe(run).to_excel(path, index=False)
    return path


def export_run_to_csv(run: ScrapeRun) -> Path:
    export_dir = ensure_export_dir()
    path = export_dir / f"{build_export_basename(run)}.csv"
    businesses_to_dataframe(run).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_run_to_pdf(run: ScrapeRun) -> Path:
    export_dir = ensure_export_dir()
    path = export_dir / f"{build_export_basename(run)}.pdf"
    dataframe = businesses_to_dataframe(run)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()

    content: list = [
        Paragraph(f"MapsScraper Export: {run.keyword}", styles["Title"]),
        Paragraph(f"Location: {run.location or 'Worldwide'}", styles["Normal"]),
        Paragraph(f"Results: {run.total_results} | Browser mode: {'Headless' if run.headless else 'Visible'}", styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data: list[list[str]] = [["Name", "Category", "Phone", "Website", "City", "Country", "Rating"]]
    for _, row in dataframe.iterrows():
        table_data.append(
            [
                str(row.get("Name", ""))[:40],
                str(row.get("Category", ""))[:24],
                str(row.get("Phone", ""))[:22],
                str(row.get("Website", ""))[:32],
                str(row.get("City", ""))[:18],
                str(row.get("Country", ""))[:18],
                str(row.get("Rating", "")),
            ]
        )

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10241f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9d9d9")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f1e8")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    content.append(table)
    doc.build(content)
    return path


def export_businesses_to_excel(businesses: Iterable[Business], label: str = "businesses") -> Path:
    export_dir = ensure_export_dir()
    path = export_dir / f"{build_business_export_basename(label)}.xlsx"
    exportable_businesses_to_dataframe(businesses).to_excel(path, index=False)
    return path


def export_businesses_to_csv(businesses: Iterable[Business], label: str = "businesses") -> Path:
    export_dir = ensure_export_dir()
    path = export_dir / f"{build_business_export_basename(label)}.csv"
    exportable_businesses_to_dataframe(businesses).to_csv(path, index=False, encoding="utf-8-sig")
    return path


def export_businesses_to_pdf(businesses: Iterable[Business], label: str = "businesses") -> Path:
    export_dir = ensure_export_dir()
    path = export_dir / f"{build_business_export_basename(label)}.pdf"
    dataframe = exportable_businesses_to_dataframe(businesses)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()

    content: list = [
        Paragraph(f"MapsScraper Export: {label}", styles["Title"]),
        Paragraph(f"Businesses exported: {len(dataframe.index)}", styles["Normal"]),
        Spacer(1, 12),
    ]

    table_data: list[list[str]] = [["Name", "Category", "Phone", "Website", "City", "Country", "Rating"]]
    for _, row in dataframe.iterrows():
        table_data.append(
            [
                str(row.get("Name", ""))[:40],
                str(row.get("Category", ""))[:24],
                str(row.get("Phone", ""))[:22],
                str(row.get("Website", ""))[:32],
                str(row.get("City", ""))[:18],
                str(row.get("Country", ""))[:18],
                str(row.get("Rating", "")),
            ]
        )

    table = Table(table_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10241f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d9d9d9")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f1e8")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    content.append(table)
    doc.build(content)
    return path


def export_run_file(run: ScrapeRun, file_format: str) -> Path:
    exporters = {
        "xlsx": export_run_to_excel,
        "csv": export_run_to_csv,
        "pdf": export_run_to_pdf,
    }
    if file_format not in exporters:
        raise ValueError(f"Unsupported export format: {file_format}")
    return exporters[file_format](run)


def export_businesses_file(businesses: Iterable[Business], file_format: str, label: str = "businesses") -> Path:
    exporters = {
        "xlsx": export_businesses_to_excel,
        "csv": export_businesses_to_csv,
        "pdf": export_businesses_to_pdf,
    }
    if file_format not in exporters:
        raise ValueError(f"Unsupported export format: {file_format}")
    return exporters[file_format](businesses, label)