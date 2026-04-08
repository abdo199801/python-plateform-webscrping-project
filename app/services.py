from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app import models


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRAPER_PATH = ROOT_DIR / "googlemaps.py"

# Module cache for lazy loading
_scraper_module_cache: Optional[Any] = None
_UniversalGoogleMapsScraper_cache: Optional[Any] = None


def _load_scraper_module():
    """Lazily load the scraper module only when needed."""
    global _scraper_module_cache, _UniversalGoogleMapsScraper_cache
    
    if _scraper_module_cache is not None:
        return _scraper_module_cache
    
    spec = importlib.util.spec_from_file_location("local_googlemaps_scraper", SCRAPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load scraper module from {SCRAPER_PATH}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    _scraper_module_cache = module
    _UniversalGoogleMapsScraper_cache = module.UniversalGoogleMapsScraper
    
    return module


def get_scraper_class():
    """Get the UniversalGoogleMapsScraper class with lazy loading."""
    if _UniversalGoogleMapsScraper_cache is not None:
        return _UniversalGoogleMapsScraper_cache
    _load_scraper_module()
    return _UniversalGoogleMapsScraper_cache


BUSINESS_FIELDS = {
    "name",
    "address",
    "phone",
    "website",
    "rating",
    "reviews_count",
    "category",
    "business_hours",
    "description",
    "latitude",
    "longitude",
    "place_id",
    "source_url",
    "scraped_date",
    "country",
    "city",
    "street",
    "postal_code",
    "state_province",
    "email",
    "social_media",
}


def run_scrape(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run the scraper with lazy module loading."""
    try:
        ScraperClass = get_scraper_class()
    except Exception as e:
        raise RuntimeError(
            "Unable to initialize the scraper. Verify Chrome and the scraper dependencies are installed."
        ) from e
    
    scraper = ScraperClass(
        headless=payload["headless"],
        max_results=payload["max_results"],
        delay_between_requests=1.5,
    )
    results = scraper.scrape(
        keyword=payload["keyword"],
        location=payload["location"],
        radius=payload["radius"],
        max_results=payload["max_results"],
    )

    if payload.get("save_files") and results:
        filename = scraper.generate_filename(payload["keyword"], payload["location"]) + ".xlsx"
        scraper.save_to_excel(results, filename)

    return results


def persist_scrape(
    db: Session,
    payload: Dict[str, Any],
    results: List[Dict[str, Any]],
) -> models.ScrapeRun:
    run = models.ScrapeRun(
        keyword=payload["keyword"],
        location=payload["location"],
        radius=payload["radius"],
        max_results=payload["max_results"],
        headless=payload["headless"],
        total_results=len(results),
        status="completed",
    )
    db.add(run)
    db.flush()

    for raw_business in results:
        normalized = {key: raw_business.get(key) for key in BUSINESS_FIELDS}
        normalized["name"] = normalized.get("name") or "Unknown"
        business = models.Business(scrape_run_id=run.id, **normalized)
        db.add(business)

    db.commit()
    db.refresh(run)
    return run