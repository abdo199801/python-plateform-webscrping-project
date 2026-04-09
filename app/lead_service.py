import json
from typing import Dict, Iterable, Optional

from sqlalchemy.orm import Session

from app.lead_models import LeadRecord, SavedSearch
from app.models import Business


ALLOWED_LEAD_STATUSES = {"new", "contacted", "qualified", "proposal", "won", "lost"}


def normalize_lead_status(value: Optional[str]) -> str:
    candidate = (value or "new").strip().lower()
    if candidate not in ALLOWED_LEAD_STATUSES:
        raise ValueError(f"Invalid lead status: {candidate}")
    return candidate


def normalize_tags(tags: Optional[list[str]]) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for raw_tag in tags:
        tag = (raw_tag or "").strip()
        lowered = tag.lower()
        if not tag or lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(tag)
    return normalized[:12]


def parse_tags(raw_tags: Optional[str]) -> list[str]:
    if not raw_tags:
        return []
    try:
        loaded = json.loads(raw_tags)
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return normalize_tags([str(item) for item in loaded])


def encode_tags(tags: Optional[list[str]]) -> str:
    return json.dumps(normalize_tags(tags), ensure_ascii=True)


def get_lead_map(db: Session, user_email: str, business_ids: Iterable[int]) -> Dict[int, LeadRecord]:
    ids = list(dict.fromkeys(int(business_id) for business_id in business_ids))
    if not ids:
        return {}

    records = (
        db.query(LeadRecord)
        .filter(LeadRecord.user_email == user_email, LeadRecord.business_id.in_(ids))
        .all()
    )
    return {record.business_id: record for record in records}


def serialize_lead_record(record: LeadRecord) -> dict:
    return {
        "id": record.id,
        "user_email": record.user_email,
        "business_id": record.business_id,
        "status": record.status,
        "tags": parse_tags(record.tags),
        "notes": record.notes or "",
        "is_archived": record.is_archived,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def serialize_business_with_lead(business: Business, record: Optional[LeadRecord]) -> dict:
    return {
        "id": business.id,
        "scrape_run_id": business.scrape_run_id,
        "name": business.name,
        "address": business.address,
        "phone": business.phone,
        "website": business.website,
        "rating": business.rating,
        "reviews_count": business.reviews_count,
        "category": business.category,
        "business_hours": business.business_hours,
        "description": business.description,
        "latitude": business.latitude,
        "longitude": business.longitude,
        "place_id": business.place_id,
        "source_url": business.source_url,
        "scraped_date": business.scraped_date,
        "country": business.country,
        "city": business.city,
        "street": business.street,
        "postal_code": business.postal_code,
        "state_province": business.state_province,
        "email": business.email,
        "social_media": business.social_media,
        "created_at": business.created_at,
        "lead_id": record.id if record else None,
        "lead_status": record.status if record else None,
        "lead_tags": parse_tags(record.tags) if record else [],
        "lead_notes": record.notes if record else "",
        "lead_updated_at": record.updated_at if record else None,
        "lead_archived": record.is_archived if record else False,
    }


def upsert_lead_record(
    db: Session,
    user_email: str,
    business_id: int,
    status: Optional[str],
    tags: Optional[list[str]],
    notes: Optional[str],
    is_archived: bool,
) -> LeadRecord:
    business = db.query(Business).filter(Business.id == business_id).first()
    if business is None:
        raise ValueError("Business not found")

    record = (
        db.query(LeadRecord)
        .filter(LeadRecord.user_email == user_email, LeadRecord.business_id == business_id)
        .first()
    )
    if record is None:
        record = LeadRecord(user_email=user_email, business_id=business_id)
        db.add(record)

    record.status = normalize_lead_status(status)
    record.tags = encode_tags(tags)
    record.notes = (notes or "").strip()[:2000]
    record.is_archived = is_archived
    db.commit()
    db.refresh(record)
    return record


def get_lead_summary(db: Session, user_email: str) -> dict:
    records = db.query(LeadRecord).filter(LeadRecord.user_email == user_email).all()
    counts = {status: 0 for status in sorted(ALLOWED_LEAD_STATUSES)}
    archived = 0
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
        if record.is_archived:
            archived += 1

    return {
        "total": len(records),
        "active": max(0, len(records) - archived),
        "archived": archived,
        "counts": counts,
    }


def list_saved_searches(db: Session, user_email: str) -> list[SavedSearch]:
    return (
        db.query(SavedSearch)
        .filter(SavedSearch.user_email == user_email)
        .order_by(SavedSearch.created_at.desc())
        .all()
    )


def create_saved_search(
    db: Session,
    user_email: str,
    name: str,
    search_query: Optional[str],
    city: Optional[str],
    country: Optional[str],
    category: Optional[str],
    lead_status: Optional[str],
    tag: Optional[str],
    saved_only: bool,
    alert_enabled: bool,
) -> SavedSearch:
    saved_search = SavedSearch(
        user_email=user_email,
        name=name.strip(),
        search_query=(search_query or "").strip() or None,
        city=(city or "").strip() or None,
        country=(country or "").strip() or None,
        category=(category or "").strip() or None,
        lead_status=(lead_status or "").strip().lower() or None,
        tag=(tag or "").strip() or None,
        saved_only=saved_only,
        alert_enabled=alert_enabled,
    )
    db.add(saved_search)
    db.commit()
    db.refresh(saved_search)
    return saved_search


def delete_saved_search(db: Session, user_email: str, search_id: int) -> None:
    saved_search = (
        db.query(SavedSearch)
        .filter(SavedSearch.id == search_id, SavedSearch.user_email == user_email)
        .first()
    )
    if saved_search is None:
        raise ValueError("Saved search not found")

    db.delete(saved_search)
    db.commit()


def serialize_saved_search(saved_search: SavedSearch) -> dict:
    return {
        "id": saved_search.id,
        "user_email": saved_search.user_email,
        "name": saved_search.name,
        "search_query": saved_search.search_query,
        "city": saved_search.city,
        "country": saved_search.country,
        "category": saved_search.category,
        "lead_status": saved_search.lead_status,
        "tag": saved_search.tag,
        "saved_only": saved_search.saved_only,
        "alert_enabled": saved_search.alert_enabled,
        "created_at": saved_search.created_at,
    }
