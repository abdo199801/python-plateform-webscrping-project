import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, inspect, or_, text
from starlette.concurrency import run_in_threadpool

from app.admin_models import AdminUser
from app.auth_service import (
    authenticate_platform_user,
    create_user_token,
    get_admin_by_email,
    get_platform_user_by_email,
    hash_password,
    register_platform_user,
    update_platform_user_last_login,
    verify_user_token,
)
from app.database import Base, SessionLocal, engine, get_db
from app.export_service import export_run_file
from app.models import Business, ScrapeRun
from app.lead_models import LeadRecord
from app.schemas import (
    BusinessResponse,
    InsightBucket,
    InsightOverviewResponse,
    InsightRecentRun,
    LeadRecordResponse,
    LeadRecordUpsertRequest,
    LeadSummaryResponse,
    PaginatedBusinessesResponse,
    PaginatedScrapeRunsResponse,
    PaginationMetaResponse,
    SavedSearchCreateRequest,
    SavedSearchResponse,
    ScrapeRequest,
    ScrapeRunResponse,
    ScrapeSummaryResponse,
)
from app.services import create_scrape_run, update_scrape_run_progress
from app.tasks import dispatch_scrape_run, get_task_queue_backend
from app.payment_models import Payment, PaymentStatus, ScrapeCredit, Subscription
from app.payment_schemas import (
    AccessStatusResponse,
    CreateCheckoutSessionRequest,
    CreateSubscriptionCheckoutRequest,
    CreditPurchaseRequest,
    PlatformAuthResponse,
    PlatformUserLoginRequest,
    PlatformUserRegisterRequest,
    PlatformUserResponse,
    PlatformUserUpsertRequest,
    UserDashboardResponse,
    UserSubscriptionCancelRequest,
    UserSubscriptionSnapshotResponse,
)
from app.payment_service import (
    cancel_subscription_for_user,
    capture_paypal_subscription_order,
    get_platform_user,
    get_pricing_plans,
    get_credit_packages,
    create_checkout_session,
    create_paypal_subscription_order,
    create_subscription_checkout_session,
    DEFAULT_MAX_RESULTS_PER_SCRAPE,
    get_user_dashboard,
    get_max_results_for_tier,
    get_user_access_state,
    get_user_subscription,
    handle_webhook_event,
    get_user_credits,
    mark_user_scrape,
    refund_credit,
    upsert_platform_user,
    use_credit,
)
from app.admin_routes import router as admin_router
from app.lead_service import (
    create_saved_search,
    delete_saved_search,
    get_lead_map,
    get_lead_summary,
    list_saved_searches,
    serialize_business_with_lead,
    serialize_lead_record,
    serialize_saved_search,
    upsert_lead_record,
)

user_security = HTTPBearer(auto_error=False)


def get_runtime_config() -> dict[str, str]:
    return {
        "apiBaseUrl": os.getenv("API_BASE_URL", "").strip().rstrip("/"),
        "frontendUrl": os.getenv("FRONTEND_URL", "").strip().rstrip("/"),
        "googleMapsEmbedApiKey": os.getenv("GOOGLE_MAPS_EMBED_API_KEY", "").strip(),
    }


def get_allowed_origins() -> list[str]:
    origins: list[str] = []
    configured_origins = os.getenv("ALLOWED_ORIGINS", "")
    frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    local_defaults = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    def add_origin(value: str) -> None:
        cleaned = value.strip().rstrip("/")
        if cleaned and cleaned not in origins:
            origins.append(cleaned)

    if configured_origins:
        for origin in configured_origins.split(","):
            add_origin(origin)

    if frontend_url:
        add_origin(frontend_url)

    for origin in local_defaults:
        add_origin(origin)

    if "*" in origins:
        return ["*"]

    return origins


def bootstrap_admin_user() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    if not admin_email or not admin_password:
        return

    full_name = os.getenv("ADMIN_FULL_NAME", "Platform Administrator").strip() or "Platform Administrator"
    is_superuser = os.getenv("ADMIN_IS_SUPERUSER", "true").strip().lower() not in {"0", "false", "no"}

    db = SessionLocal()
    try:
        existing_admin = get_admin_by_email(db, admin_email)
        if existing_admin:
            return

        admin = AdminUser(
            email=admin_email,
            hashed_password=hash_password(admin_password),
            full_name=full_name,
            is_superuser=is_superuser,
            is_active=True,
            can_manage_users=True,
            can_view_scrapes=True,
            can_run_scrapes=True,
            can_manage_payments=is_superuser,
            can_view_analytics=True,
            can_manage_admins=is_superuser,
        )
        db.add(admin)
        db.commit()
        print(f"Bootstrapped admin user: {admin_email}")
    except Exception as exc:
        db.rollback()
        print(f"Admin bootstrap error: {exc}")
    finally:
        db.close()


def ensure_platform_user_auth_columns() -> None:
    inspector = inspect(engine)
    if "platform_users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("platform_users")}
    statements: list[str] = []

    if "hashed_password" not in existing_columns:
        statements.append("ALTER TABLE platform_users ADD COLUMN hashed_password VARCHAR(255)")
    if "is_active" not in existing_columns:
        statements.append("ALTER TABLE platform_users ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
    if "last_login" not in existing_columns:
        statements.append("ALTER TABLE platform_users ADD COLUMN last_login TIMESTAMP")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if "is_active" not in existing_columns:
            connection.execute(text("UPDATE platform_users SET is_active = TRUE WHERE is_active IS NULL"))


def ensure_scrape_run_columns() -> None:
    inspector = inspect(engine)
    if "scrape_runs" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("scrape_runs")}
    statements: list[str] = []

    if "processed_results" not in existing_columns:
        statements.append("ALTER TABLE scrape_runs ADD COLUMN processed_results INTEGER DEFAULT 0")
    if "progress_message" not in existing_columns:
        statements.append("ALTER TABLE scrape_runs ADD COLUMN progress_message TEXT")
    if "error_message" not in existing_columns:
        statements.append("ALTER TABLE scrape_runs ADD COLUMN error_message TEXT")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if "processed_results" not in existing_columns:
            connection.execute(text("UPDATE scrape_runs SET processed_results = COALESCE(total_results, 0) WHERE processed_results IS NULL"))


def _normalize_run_datetime(value):
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def recover_abandoned_scrape_runs() -> None:
    stale_after_seconds = max(
        300,
        int(os.getenv("SCRAPE_JOB_STALE_SECONDS", str(int(os.getenv("SCRAPE_JOB_TIMEOUT_SECONDS", "900")) + 300))),
    )
    stale_before = datetime.utcnow() - timedelta(seconds=stale_after_seconds)

    db = SessionLocal()
    try:
        stale_runs = (
            db.query(ScrapeRun)
            .filter(ScrapeRun.status.in_(["queued", "running"]))
            .all()
        )

        updated = False
        for run in stale_runs:
            created_at = _normalize_run_datetime(run.created_at)
            if created_at and created_at <= stale_before:
                run.status = "failed"
                run.error_message = "The scrape job timed out or the worker restarted before it finished."
                updated = True

        if updated:
            db.commit()
        else:
            db.rollback()
    except Exception as exc:
        db.rollback()
        print(f"Scrape recovery error: {exc}")
    finally:
        db.close()


def get_current_platform_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(user_security),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_user_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_platform_user_by_email(db, email)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_platform_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(user_security),
    db: Session = Depends(get_db),
):
    if not credentials:
        return None

    payload = verify_user_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_platform_user_by_email(db, email)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_current_user_email(current_user, email: str) -> None:
    if current_user.email != email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only access your own account data")


def require_current_user_email_if_authenticated(current_user, email: str) -> None:
    if current_user is None:
        return
    require_current_user_email(current_user, email)


ALLOWED_ORIGINS = get_allowed_origins()
ALLOW_CREDENTIALS = ALLOWED_ORIGINS != ["*"]

app = FastAPI(title="Google Maps Scraper Fullstack API", version="2.0.0")

# Include admin routes
app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.on_event("startup")
def startup():
    import traceback
    try:
        Base.metadata.create_all(bind=engine)
        ensure_platform_user_auth_columns()
        ensure_scrape_run_columns()
        # Test the connection
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()
        bootstrap_admin_user()
        recover_abandoned_scrape_runs()
        app.state.db_ready = True
        print("Database initialized successfully!")
    except Exception as e:
        app.state.db_ready = False
        print(f"Database initialization error: {e}")
        print(traceback.format_exc())


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.head("/", include_in_schema=False)
def index_head():
    return Response(status_code=200)


@app.get("/admin", include_in_schema=False)
def admin_dashboard():
    """Admin dashboard page."""
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/admin/login", include_in_schema=False)
def admin_login_page():
    """Dedicated admin login entry point."""
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/config.js", include_in_schema=False)
def frontend_config():
    config_script = "window.APP_CONFIG = Object.freeze(" + json.dumps(get_runtime_config()) + ");"
    return Response(content=config_script, media_type="application/javascript")


# Mount static files after defining routes to avoid catching /admin
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "database_ready": getattr(app.state, "db_ready", False),
        "queue_backend": get_task_queue_backend(),
        "enable_celery": os.getenv("ENABLE_CELERY", "").strip().lower(),
        "playwright_browsers_path": os.getenv("PLAYWRIGHT_BROWSERS_PATH", "").strip() or "<unset>",
    }


@app.head("/api/health", include_in_schema=False)
def health_check_head():
    return Response(status_code=200)


@app.post("/api/scrapes", response_model=ScrapeSummaryResponse)
async def create_scrape(
    payload: ScrapeRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, payload.email)
    data = payload.model_dump()
    user = get_platform_user(db, payload.email)
    if user is None:
        raise HTTPException(
            status_code=400,
            detail="Please submit your company information before launching a scrape.",
        )

    access_state = get_user_access_state(db, payload.email)
    active_subscription = get_user_subscription(db, payload.email)
    billing_mode = "subscription" if access_state["has_active_subscription"] else "trial"

    if not access_state["can_scrape"]:
        raise HTTPException(
            status_code=402,
            detail="Your 15-day trial has ended. Subscribe to Professional or Enterprise to keep scraping.",
        )

    max_results_allowed = DEFAULT_MAX_RESULTS_PER_SCRAPE
    limit_label = "trial"
    if access_state["has_active_subscription"] and active_subscription:
        max_results_allowed = get_max_results_for_tier(active_subscription.tier)
        limit_label = active_subscription.tier.value

    if payload.max_results > max_results_allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Your {limit_label} plan allows up to {max_results_allowed} results per scrape. "
                "Upgrade to a higher plan to scrape more."
            ),
        )

    run = create_scrape_run(db, data, status="queued")
    queue_backend = dispatch_scrape_run(background_tasks, run.id, data, payload.email)
    if queue_backend == "celery":
        update_scrape_run_progress(db, run.id, 0, "Queued in Redis worker...")
    queued_run = (
        db.query(ScrapeRun)
        .options(joinedload(ScrapeRun.businesses))
        .filter(ScrapeRun.id == run.id)
        .first()
    )
    return {
        "run": queued_run,
        "results": [],
        "remaining_credits": access_state["trial_days_left"],
        "billing_mode": billing_mode,
    }


def build_pagination(page: int, page_size: int, total: int) -> PaginationMetaResponse:
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return PaginationMetaResponse(page=page, page_size=page_size, total=total, total_pages=total_pages)


def build_business_query(
    db: Session,
    current_user,
    email: Optional[str] = None,
    search: Optional[str] = None,
    city: Optional[str] = None,
    country: Optional[str] = None,
    category: Optional[str] = None,
    lead_status: Optional[str] = None,
    tag: Optional[str] = None,
    saved_only: bool = False,
):
    query = db.query(Business).order_by(Business.created_at.desc())

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Business.name.ilike(pattern),
                Business.address.ilike(pattern),
                Business.website.ilike(pattern),
                Business.city.ilike(pattern),
                Business.country.ilike(pattern),
                Business.category.ilike(pattern),
            )
        )

    if city:
        query = query.filter(Business.city.ilike(f"%{city}%"))
    if country:
        query = query.filter(Business.country.ilike(f"%{country}%"))
    if category:
        query = query.filter(Business.category.ilike(f"%{category}%"))
    if email:
        require_current_user_email_if_authenticated(current_user, email)
        query = query.outerjoin(
            LeadRecord,
            and_(LeadRecord.business_id == Business.id, LeadRecord.user_email == email),
        )
        if lead_status:
            query = query.filter(LeadRecord.status == lead_status.strip().lower())
        if tag:
            query = query.filter(LeadRecord.tags.ilike(f"%{tag}%"))
        if saved_only:
            query = query.filter(LeadRecord.id.is_not(None), LeadRecord.is_archived == False)
    elif lead_status or tag or saved_only:
        raise HTTPException(status_code=400, detail="email is required when filtering lead pipeline data")

    return query


@app.get("/api/scrapes", response_model=list[ScrapeRunResponse] | PaginatedScrapeRunsResponse)
def list_scrape_runs(
    db: Session = Depends(get_db),
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=6, ge=1, le=50),
):
    query = (
        db.query(ScrapeRun)
        .options(joinedload(ScrapeRun.businesses))
        .order_by(ScrapeRun.created_at.desc())
    )

    if page is None:
        return query.all()

    total = query.count()
    offset = (page - 1) * page_size
    runs = query.offset(offset).limit(page_size).all()
    return {"items": runs, "pagination": build_pagination(page, page_size, total)}


@app.get("/api/businesses", response_model=list[BusinessResponse] | PaginatedBusinessesResponse)
def list_businesses(
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_platform_user),
    email: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    lead_status: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    saved_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    query = build_business_query(
        db,
        current_user,
        email=email,
        search=search,
        city=city,
        country=country,
        category=category,
        lead_status=lead_status,
        tag=tag,
        saved_only=saved_only,
    )

    if page is None:
        items = query.limit(limit).all()
        if not email:
            return items
        lead_map = get_lead_map(db, email, [item.id for item in items])
        return [serialize_business_with_lead(item, lead_map.get(item.id)) for item in items]

    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    if not email:
        return {"items": items, "pagination": build_pagination(page, page_size, total)}

    lead_map = get_lead_map(db, email, [item.id for item in items])
    serialized_items = [serialize_business_with_lead(item, lead_map.get(item.id)) for item in items]
    return {"items": serialized_items, "pagination": build_pagination(page, page_size, total)}


@app.get("/api/businesses/exports/{file_format}")
def download_businesses_export(
    file_format: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_platform_user),
    email: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    lead_status: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    saved_only: bool = Query(default=False),
):
    query = build_business_query(
        db,
        current_user,
        email=email,
        search=search,
        city=city,
        country=country,
        category=category,
        lead_status=lead_status,
        tag=tag,
        saved_only=saved_only,
    )
    businesses = query.all()

    if not businesses:
        raise HTTPException(status_code=404, detail="No businesses match the current filters")

    label_parts = ["all_businesses"]
    if search:
        label_parts.append(search)
    if city:
        label_parts.append(city)
    if country:
        label_parts.append(country)
    if category:
        label_parts.append(category)

    try:
        from app.export_service import export_businesses_file

        export_path = export_businesses_file(businesses, file_format.lower(), "_".join(label_parts))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "pdf": "application/pdf",
    }
    return FileResponse(export_path, filename=export_path.name, media_type=media_types[file_format.lower()])


@app.get("/api/businesses/{business_id}")
def get_business(business_id: int, db: Session = Depends(get_db)):
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


@app.post("/api/leads", response_model=LeadRecordResponse)
def save_lead_record(
    payload: LeadRecordUpsertRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, payload.email)
    try:
        record = upsert_lead_record(
            db,
            payload.email,
            payload.business_id,
            payload.status,
            payload.tags,
            payload.notes,
            payload.is_archived,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return serialize_lead_record(record)


@app.get("/api/leads/summary/{email}", response_model=LeadSummaryResponse)
def get_lead_pipeline_summary(email: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    require_current_user_email_if_authenticated(current_user, email)
    return get_lead_summary(db, email)


@app.get("/api/saved-searches/{email}", response_model=list[SavedSearchResponse])
def get_user_saved_searches(email: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    require_current_user_email_if_authenticated(current_user, email)
    searches = list_saved_searches(db, email)
    return [serialize_saved_search(saved_search) for saved_search in searches]


@app.post("/api/saved-searches", response_model=SavedSearchResponse)
def create_user_saved_search(
    payload: SavedSearchCreateRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, payload.email)
    saved_search = create_saved_search(
        db,
        payload.email,
        payload.name,
        payload.search_query,
        payload.city,
        payload.country,
        payload.category,
        payload.lead_status,
        payload.tag,
        payload.saved_only,
        payload.alert_enabled,
    )
    return serialize_saved_search(saved_search)


@app.delete("/api/saved-searches/{search_id}")
def remove_user_saved_search(
    search_id: int,
    email: str = Query(...),
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, email)
    try:
        delete_saved_search(db, email, search_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "id": search_id}


@app.get("/api/scrapes/{run_id}/exports/{file_format}")
def download_scrape_export(run_id: int, file_format: str, db: Session = Depends(get_db)):
    run = (
        db.query(ScrapeRun)
        .options(joinedload(ScrapeRun.businesses))
        .filter(ScrapeRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Scrape run not found")

    try:
        export_path = export_run_file(run, file_format.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_types = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "pdf": "application/pdf",
    }
    return FileResponse(export_path, filename=export_path.name, media_type=media_types[file_format.lower()])


@app.get("/api/insights/overview", response_model=InsightOverviewResponse)
def insights_overview(db: Session = Depends(get_db)):
    total_runs = db.query(func.count(ScrapeRun.id)).scalar() or 0
    total_businesses = db.query(func.count(Business.id)).scalar() or 0
    completed_runs = (
        db.query(func.count(ScrapeRun.id))
        .filter(ScrapeRun.status == "completed")
        .scalar()
        or 0
    )
    average_rating = db.query(func.avg(Business.rating)).scalar() or 0

    contactable_businesses = (
        db.query(func.count(Business.id))
        .filter(
            or_(
                func.length(func.trim(func.coalesce(Business.phone, ""))) > 0,
                func.length(func.trim(func.coalesce(Business.website, ""))) > 0,
                func.length(func.trim(func.coalesce(Business.email, ""))) > 0,
            )
        )
        .scalar()
        or 0
    )

    top_categories_query = (
        db.query(Business.category, func.count(Business.id))
        .filter(Business.category.isnot(None), Business.category != "")
        .group_by(Business.category)
        .order_by(func.count(Business.id).desc(), Business.category.asc())
        .limit(5)
        .all()
    )
    top_cities_query = (
        db.query(Business.city, func.count(Business.id))
        .filter(Business.city.isnot(None), Business.city != "")
        .group_by(Business.city)
        .order_by(func.count(Business.id).desc(), Business.city.asc())
        .limit(5)
        .all()
    )
    recent_runs_query = (
        db.query(ScrapeRun)
        .order_by(ScrapeRun.created_at.desc())
        .limit(5)
        .all()
    )

    success_rate = round((completed_runs / total_runs) * 100, 1) if total_runs else 0.0

    return InsightOverviewResponse(
        total_runs=total_runs,
        total_businesses=total_businesses,
        success_rate=success_rate,
        average_rating=round(float(average_rating), 2),
        contactable_businesses=contactable_businesses,
        top_categories=[
            InsightBucket(label=label, count=count)
            for label, count in top_categories_query
        ],
        top_cities=[
            InsightBucket(label=label, count=count)
            for label, count in top_cities_query
        ],
        recent_runs=[
            InsightRecentRun(
                id=run.id,
                keyword=run.keyword,
                location=run.location,
                total_results=run.total_results,
                status=run.status,
                created_at=run.created_at,
            )
            for run in recent_runs_query
        ],
    )


@app.post("/api/auth/register", response_model=PlatformAuthResponse)
def register_user_account(payload: PlatformUserRegisterRequest, db: Session = Depends(get_db)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Password confirmation does not match")

    try:
        user = register_platform_user(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            company_name=payload.company_name,
            phone=payload.phone,
            country=payload.country,
            preferred_payment_provider=payload.preferred_payment_provider,
        )
        update_platform_user_last_login(db, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    access_token = create_user_token({"sub": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@app.post("/api/auth/login", response_model=PlatformAuthResponse)
def login_user_account(payload: PlatformUserLoginRequest, db: Session = Depends(get_db)):
    user = authenticate_platform_user(db, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    update_platform_user_last_login(db, user)
    access_token = create_user_token({"sub": user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
    }


@app.get("/api/auth/me", response_model=PlatformUserResponse)
def get_authenticated_user(current_user=Depends(get_current_platform_user)):
    return current_user


@app.post("/api/users/onboard", response_model=PlatformUserResponse)
def onboard_user(
    payload: PlatformUserUpsertRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, payload.email)
    return upsert_platform_user(db, payload)


@app.put("/api/users/profile", response_model=PlatformUserResponse)
def update_user_profile(
    payload: PlatformUserUpsertRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, payload.email)
    return upsert_platform_user(db, payload)


@app.get("/api/users/access/{email}", response_model=AccessStatusResponse)
def get_user_access(email: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    require_current_user_email_if_authenticated(current_user, email)
    return get_user_access_state(db, email)


@app.get("/api/users/dashboard/{email}", response_model=UserDashboardResponse)
def get_user_dashboard_view(email: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    require_current_user_email_if_authenticated(current_user, email)
    try:
        return get_user_dashboard(db, email)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/users/subscription/cancel", response_model=UserSubscriptionSnapshotResponse)
def cancel_user_subscription(
    request: UserSubscriptionCancelRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    require_current_user_email_if_authenticated(current_user, request.email)
    try:
        subscription = cancel_subscription_for_user(db, request.email)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if subscription is None:
        raise HTTPException(status_code=404, detail="No subscription found for this user")

    user = get_platform_user(db, request.email)
    return {
        "id": subscription.id,
        "tier": subscription.tier,
        "is_active": subscription.is_active,
        "current_period_start": subscription.current_period_start,
        "current_period_end": subscription.current_period_end,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "provider": user.preferred_payment_provider if user else None,
    }


# ==================== PAYMENT ROUTES ====================

@app.get("/api/pricing")
def get_pricing():
    """Get all available pricing plans and credit packages."""
    return {
        "plans": get_pricing_plans(),
        "credit_packages": get_credit_packages()
    }


@app.get("/api/payment/config")
def get_payment_config():
    return {
        "publishable_key": "",
        "payments_enabled": False,
        "paypal_enabled": False,
        "paypal_client_id": "",
        "paypal_currency": "USD",
        "paypal_environment": "sandbox",
        "paypal_sdk_base": "",
        "trial_days": 15,
    }


@app.post("/api/payment/create-checkout-session")
def create_payment_session(
    request: CreateCheckoutSessionRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db)
):
    raise HTTPException(status_code=503, detail="Checkout is currently unavailable.")


@app.post("/api/subscription/create-checkout-session")
def create_subscription_session(
    request: CreateSubscriptionCheckoutRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db)
):
    raise HTTPException(status_code=503, detail="Checkout is currently unavailable.")


@app.post("/api/paypal/orders")
def create_paypal_order(
    request: CreateSubscriptionCheckoutRequest,
    current_user=Depends(get_optional_platform_user),
    db: Session = Depends(get_db),
):
    raise HTTPException(status_code=503, detail="Checkout is currently unavailable.")


@app.post("/api/paypal/orders/{order_id}/capture")
def capture_paypal_order(order_id: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    raise HTTPException(status_code=503, detail="Checkout is currently unavailable.")


@app.post("/api/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    raise HTTPException(status_code=503, detail="Checkout is currently unavailable.")


@app.get("/api/user/credits/{email}")
def get_credits(email: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    """Get available credits for a user."""
    require_current_user_email_if_authenticated(current_user, email)
    credits = get_user_credits(db, email)
    return {"email": email, "available_credits": credits}


@app.post("/api/user/credits/use")
def consume_credit(email: str, current_user=Depends(get_optional_platform_user), db: Session = Depends(get_db)):
    """Use one scrape credit."""
    require_current_user_email_if_authenticated(current_user, email)
    success = use_credit(db, email)
    if success:
        remaining = get_user_credits(db, email)
        return {"success": True, "remaining_credits": remaining}
    else:
        raise HTTPException(
            status_code=402,
            detail="No available credits. Please purchase more credits or subscribe."
        )


@app.get("/api/payment/success")
def payment_success(session_id: str):
    """Payment success page redirect."""
    return {"status": "success", "session_id": session_id}


@app.get("/api/payment/cancel")
def payment_cancel():
    """Payment cancelled."""
    return {"status": "cancelled", "message": "Payment was cancelled"}
