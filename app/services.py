from __future__ import annotations

import importlib.util
import logging
import multiprocessing
import os
import threading
import time
from pathlib import Path
from queue import Empty
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRAPER_PATH = ROOT_DIR / "googlemaps.py"
SCRAPE_JOB_TIMEOUT_SECONDS = max(60, int(os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS", "900")))
SCRAPE_WORKER_LOCK = threading.Lock()
logger = logging.getLogger(__name__)

# Module cache for lazy loading
_scraper_module_cache: Optional[Any] = None
_UniversalGoogleMapsScraper_cache: Optional[Any] = None


def _scrape_worker(payload: Dict[str, Any], result_queue) -> None:
    try:
        def report_progress(processed_results: int, message: str) -> None:
            result_queue.put(
                {
                    "type": "progress",
                    "processed_results": processed_results,
                    "progress_message": message,
                }
            )

        results = run_scrape(payload, progress_callback=report_progress)
        result_queue.put({"type": "complete", "ok": True, "results": results})
    except Exception as exc:
        result_queue.put({"type": "complete", "ok": False, "error": str(exc)})


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


def run_scrape(payload: Dict[str, Any], progress_callback=None) -> List[Dict[str, Any]]:
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
        progress_callback=progress_callback,
    )

    if payload.get("save_files") and results:
        filename = scraper.generate_filename(payload["keyword"], payload["location"]) + ".xlsx"
        scraper.save_to_excel(results, filename)

    return results


def run_scrape_with_timeout(payload: Dict[str, Any], on_progress=None) -> List[Dict[str, Any]]:
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue()
    process = context.Process(target=_scrape_worker, args=(payload, result_queue))
    process.start()
    deadline = time.monotonic() + SCRAPE_JOB_TIMEOUT_SECONDS
    final_result: Optional[Dict[str, Any]] = None

    try:
        while True:
            if time.monotonic() >= deadline:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
                    if process.is_alive():
                        process.kill()
                        process.join(timeout=5)
                raise TimeoutError(
                    f"Scrape exceeded the {SCRAPE_JOB_TIMEOUT_SECONDS // 60} minute limit and was stopped. "
                    "This usually means the hosted browser could not load Google Maps reliably."
                )

            process.join(timeout=1)

            while True:
                try:
                    event = result_queue.get_nowait()
                except Empty:
                    break

                if event.get("type") == "progress":
                    if on_progress:
                        on_progress(event.get("processed_results", 0), event.get("progress_message") or "")
                    continue

                if event.get("type") == "complete":
                    final_result = event

            if final_result is not None and not process.is_alive():
                break

            if not process.is_alive() and final_result is None:
                break
    finally:
        result_queue.close()

    if final_result is None:
        exit_code = process.exitcode
        raise RuntimeError(
            f"Scraper worker exited before returning data (exit code {exit_code})."
        )

    if not final_result.get("ok"):
        raise RuntimeError(final_result.get("error") or "Scrape worker failed without an error message.")

    return final_result.get("results") or []


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


def create_scrape_run(db: Session, payload: Dict[str, Any], status: str = "queued") -> models.ScrapeRun:
    run = models.ScrapeRun(
        keyword=payload["keyword"],
        location=payload["location"],
        radius=payload["radius"],
        max_results=payload["max_results"],
        headless=payload["headless"],
        processed_results=0,
        total_results=0,
        status=status,
        progress_message="Queued for scraping...",
        error_message=None,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_scrape_run_status(db: Session, run_id: int, status: str, error_message: Optional[str] = None) -> None:
    run = db.query(models.ScrapeRun).filter(models.ScrapeRun.id == run_id).first()
    if run is None:
        return

    run.status = status
    if status == "queued":
        run.progress_message = "Queued for scraping..."
    elif status == "running" and not run.progress_message:
        run.progress_message = "Preparing Google Maps session..."
    elif status == "completed":
        run.progress_message = "Scrape completed."
    elif status == "failed":
        run.progress_message = "Scrape failed."
    run.error_message = error_message if status == "failed" else None
    db.commit()


def update_scrape_run_progress(db: Session, run_id: int, processed_results: int, progress_message: Optional[str] = None) -> None:
    run = db.query(models.ScrapeRun).filter(models.ScrapeRun.id == run_id).first()
    if run is None:
        return

    run.processed_results = max(0, min(processed_results, run.max_results or processed_results))
    if progress_message:
        run.progress_message = progress_message[:500]
    db.commit()


def complete_scrape_run(db: Session, run_id: int, results: List[Dict[str, Any]]) -> models.ScrapeRun:
    run = db.query(models.ScrapeRun).filter(models.ScrapeRun.id == run_id).first()
    if run is None:
        raise ValueError(f"Scrape run {run_id} not found")

    run.status = "completed"
    run.processed_results = len(results)
    run.total_results = len(results)
    run.progress_message = "Scrape completed."
    run.error_message = None

    for raw_business in results:
        normalized = {key: raw_business.get(key) for key in BUSINESS_FIELDS}
        normalized["name"] = normalized.get("name") or "Unknown"
        business = models.Business(scrape_run_id=run.id, **normalized)
        db.add(business)

    db.commit()
    db.refresh(run)
    return run


def fail_scrape_run(db: Session, run_id: int, error_message: Optional[str] = None) -> None:
    run = db.query(models.ScrapeRun).filter(models.ScrapeRun.id == run_id).first()
    if run is None:
        return

    run.status = "failed"
    run.progress_message = "Scrape failed."
    run.error_message = error_message[:1000] if error_message else "The scrape worker stopped before completing the run."
    db.commit()


def process_scrape_run(run_id: int, payload: Dict[str, Any], user_email: str) -> None:
    db = SessionLocal()
    try:
        with SCRAPE_WORKER_LOCK:
            update_scrape_run_status(db, run_id, "running")
            update_scrape_run_progress(db, run_id, 0, "Preparing Google Maps session...")
            results = run_scrape_with_timeout(
                payload,
                on_progress=lambda processed, message: update_scrape_run_progress(db, run_id, processed, message),
            )
            complete_scrape_run(db, run_id, results)

            from app.payment_service import mark_user_scrape

            mark_user_scrape(db, user_email)
    except Exception as exc:
        db.rollback()
        logger.exception("Scrape run %s failed", run_id)
        fail_scrape_run(db, run_id, str(exc))
    finally:
        db.close()