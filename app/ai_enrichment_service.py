from __future__ import annotations

import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models


logger = logging.getLogger(__name__)


def _clean_text(value: Optional[str]) -> str:
    return " ".join((value or "").split())


def _normalize_phone(value: Optional[str]) -> str:
    return "".join(character for character in (value or "") if character.isdigit())


def _similarity(left: Optional[str], right: Optional[str]) -> float:
    left_clean = _clean_text(left).lower()
    right_clean = _clean_text(right).lower()
    if not left_clean or not right_clean:
        return 0.0
    return SequenceMatcher(None, left_clean, right_clean).ratio()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _split_hours(raw_hours: Optional[str]) -> list[str]:
    if not raw_hours:
        return []
    hours = []
    for chunk in str(raw_hours).replace(";", "\n").splitlines():
        normalized = _clean_text(chunk)
        if normalized:
            hours.append(normalized)
    return hours


def _build_local_summary(business: models.Business) -> str:
    parts: list[str] = []
    if business.category:
        parts.append(_clean_text(business.category))
    if business.address:
        parts.append(f"located at {_clean_text(business.address)}")
    elif business.city or business.country:
        location = ", ".join(part for part in [_clean_text(business.city), _clean_text(business.country)] if part)
        if location:
            parts.append(f"located in {location}")
    if business.rating:
        rating_text = f"rated {float(business.rating):.1f}/5"
        if business.reviews_count:
            rating_text += f" from {int(business.reviews_count)} reviews"
        parts.append(rating_text)
    contact_bits = []
    if business.phone:
        contact_bits.append("phone")
    if business.website:
        contact_bits.append("website")
    if business.email:
        contact_bits.append("email")
    if contact_bits:
        parts.append("contact available via " + ", ".join(contact_bits))
    if business.description:
        description = _clean_text(business.description)
        if description:
            parts.append(description[:180])
    return ". ".join(parts[:4])[:500]


def _build_review_highlights(business: models.Business) -> list[str]:
    highlights: list[str] = []
    if business.rating and business.reviews_count:
        highlights.append(f"Rating {float(business.rating):.1f}/5 across {int(business.reviews_count)} reviews.")
    elif business.rating:
        highlights.append(f"Rating {float(business.rating):.1f}/5.")
    if business.description:
        description = _clean_text(business.description)
        if description:
            highlights.append(description[:160])
    return highlights[:3]


def _dedupe_signal_score(primary: models.Business, candidate: models.Business) -> tuple[float, str]:
    place_match = bool(primary.place_id and candidate.place_id and primary.place_id == candidate.place_id)
    website_match = bool(primary.website and candidate.website and _clean_text(primary.website).lower() == _clean_text(candidate.website).lower())
    phone_match = bool(_normalize_phone(primary.phone) and _normalize_phone(primary.phone) == _normalize_phone(candidate.phone))
    name_similarity = _similarity(primary.name, candidate.name)
    address_similarity = _similarity(primary.address, candidate.address)

    if place_match:
        return 0.99, "Matched on identical Google place ID."
    if website_match and phone_match and name_similarity >= 0.8:
        return 0.96, "Matched on website, phone, and similar business name."
    if phone_match and name_similarity >= 0.85 and address_similarity >= 0.65:
        return 0.94, "Matched on phone with similar name and address."
    if website_match and name_similarity >= 0.9 and address_similarity >= 0.8:
        return 0.92, "Matched on website with highly similar name and address."
    if name_similarity >= 0.92 and address_similarity >= 0.85:
        return 0.9, "High fuzzy similarity on business name and address."
    if name_similarity >= 0.84 and (address_similarity >= 0.7 or phone_match or website_match):
        return 0.83, "Possible duplicate based on fuzzy similarity."
    return 0.0, ""


def _field_completeness_score(business: models.Business) -> float:
    filled_fields = [
        business.address,
        business.phone,
        business.website,
        business.email,
        business.social_media,
        business.city,
        business.country,
        business.description,
        business.ai_place_summary,
        business.ai_current_hours,
        business.ai_review_highlights,
    ]
    return sum(1 for value in filled_fields if value) + float(business.reviews_count or 0) / 100.0


def _merge_business_data(canonical: models.Business, duplicate: models.Business) -> None:
    merge_fields = [
        "address",
        "phone",
        "website",
        "category",
        "business_hours",
        "description",
        "latitude",
        "longitude",
        "place_id",
        "source_url",
        "country",
        "city",
        "street",
        "postal_code",
        "state_province",
        "email",
        "social_media",
        "extraction_sources",
        "ai_place_summary",
        "ai_current_hours",
        "ai_popular_times",
        "ai_review_highlights",
        "ai_grounding_sources",
        "ai_enrichment_status",
    ]
    for field_name in merge_fields:
        current_value = getattr(canonical, field_name)
        duplicate_value = getattr(duplicate, field_name)
        if not current_value and duplicate_value:
            setattr(canonical, field_name, duplicate_value)

    canonical.rating = max(float(canonical.rating or 0.0), float(duplicate.rating or 0.0))
    canonical.reviews_count = max(int(canonical.reviews_count or 0), int(duplicate.reviews_count or 0))


def enrich_businesses_locally(db: Session, run_id: int) -> None:
    businesses = (
        db.query(models.Business)
        .filter(models.Business.scrape_run_id == run_id)
        .order_by(models.Business.id.asc())
        .all()
    )
    if not businesses:
        return

    for business in businesses:
        business.ai_place_summary = _build_local_summary(business) or None
        current_hours = _split_hours(business.business_hours)
        review_highlights = _build_review_highlights(business)
        business.ai_current_hours = _json_dumps(current_hours) if current_hours else None
        business.ai_popular_times = _json_dumps([])
        business.ai_review_highlights = _json_dumps(review_highlights) if review_highlights else None
        business.ai_grounding_sources = _json_dumps(["local_scrape_fields"])
        business.ai_enrichment_status = "local"
        business.ai_enriched_at = datetime.utcnow()

    db.commit()


def smart_dedupe_businesses(db: Session, run_id: int) -> None:
    run = db.query(models.ScrapeRun).filter(models.ScrapeRun.id == run_id).first()
    businesses = (
        db.query(models.Business)
        .filter(models.Business.scrape_run_id == run_id)
        .order_by(models.Business.id.asc())
        .all()
    )
    if not businesses:
        return

    for business in businesses:
        if not business.dedupe_status:
            business.dedupe_status = "unique"
        business.duplicate_of_business_id = None
        business.dedupe_confidence = None
        business.dedupe_notes = None

    merged_ids: set[int] = set()

    for index, business in enumerate(businesses):
        if business.id in merged_ids:
            continue
        for candidate_index in range(index + 1, len(businesses)):
            candidate = businesses[candidate_index]
            if candidate.id in merged_ids:
                continue

            auto_merge = False
            flag_review = False
            confidence, reason = _dedupe_signal_score(business, candidate)

            if confidence >= 0.9:
                auto_merge = True
            elif confidence >= 0.83:
                flag_review = True

            if not auto_merge and not flag_review:
                continue

            canonical = business
            duplicate = candidate
            if _field_completeness_score(candidate) > _field_completeness_score(business):
                canonical = candidate
                duplicate = business

            if auto_merge:
                _merge_business_data(canonical, duplicate)
                canonical.dedupe_status = "canonical"
                canonical.dedupe_confidence = max(float(canonical.dedupe_confidence or 0.0), confidence)
                canonical.dedupe_notes = reason
                duplicate.dedupe_status = "merged"
                duplicate.duplicate_of_business_id = canonical.id
                duplicate.dedupe_confidence = confidence
                duplicate.dedupe_notes = reason
                merged_ids.add(duplicate.id)
            elif flag_review:
                if canonical.dedupe_status == "unique":
                    canonical.dedupe_status = "flagged"
                canonical.dedupe_confidence = max(float(canonical.dedupe_confidence or 0.0), confidence)
                canonical.dedupe_notes = reason
                duplicate.dedupe_status = "flagged"
                duplicate.duplicate_of_business_id = canonical.id
                duplicate.dedupe_confidence = confidence
                duplicate.dedupe_notes = reason

    if run is not None:
        unique_count = sum(1 for business in businesses if business.dedupe_status != "merged")
        run.total_results = unique_count
        run.processed_results = unique_count

    db.commit()


def run_post_scrape_intelligence(db: Session, run_id: int) -> None:
    try:
        enrich_businesses_locally(db, run_id)
    except Exception:
        logger.exception("Local enrichment failed for run %s", run_id)

    try:
        smart_dedupe_businesses(db, run_id)
    except Exception:
        logger.exception("Local smart deduplication failed for run %s", run_id)