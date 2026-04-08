from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import ScrapeRun


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
        rows.append(
            {
                "Name": business.name,
                "Category": business.category or "",
                "Phone": business.phone or "",
                "Email": business.email or "",
                "Website": business.website or "",
                "City": business.city or "",
                "Country": business.country or "",
                "Address": business.address or "",
                "Rating": business.rating,
                "Reviews": business.reviews_count,
                "Description": business.description or "",
            }
        )
    return pd.DataFrame(rows)


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


def export_run_file(run: ScrapeRun, file_format: str) -> Path:
    exporters = {
        "xlsx": export_run_to_excel,
        "csv": export_run_to_csv,
        "pdf": export_run_to_pdf,
    }
    if file_format not in exporters:
        raise ValueError(f"Unsupported export format: {file_format}")
    return exporters[file_format](run)