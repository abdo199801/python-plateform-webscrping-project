import json
import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, text
from starlette.concurrency import run_in_threadpool

from app.admin_models import AdminUser
from app.auth_service import get_admin_by_email, hash_password
from app.database import Base, SessionLocal, engine, get_db
from app.export_service import export_run_file
from app.models import Business, ScrapeRun
from app.schemas import (
    BusinessResponse,
    InsightBucket,
    InsightOverviewResponse,
    InsightRecentRun,
    PaginatedBusinessesResponse,
    PaginatedScrapeRunsResponse,
    PaginationMetaResponse,
    ScrapeRequest,
    ScrapeRunResponse,
    ScrapeSummaryResponse,
)
from app.services import persist_scrape, run_scrape
from app.payment_models import Payment, PaymentStatus, ScrapeCredit, Subscription
from app.payment_schemas import (
    AccessStatusResponse,
    CreateCheckoutSessionRequest,
    CreateSubscriptionCheckoutRequest,
    CreditPurchaseRequest,
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

import stripe


def get_runtime_config() -> dict[str, str]:
    return {
        "apiBaseUrl": os.getenv("API_BASE_URL", "").strip().rstrip("/"),
        "frontendUrl": os.getenv("FRONTEND_URL", "").strip().rstrip("/"),
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
        # Test the connection
        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()
        bootstrap_admin_user()
        app.state.db_ready = True
        print("Database initialized successfully!")
    except Exception as e:
        app.state.db_ready = False
        print(f"Database initialization error: {e}")
        print(traceback.format_exc())


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


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
    return {"status": "ok", "database_ready": getattr(app.state, "db_ready", False)}


@app.post("/api/scrapes", response_model=ScrapeSummaryResponse)
async def create_scrape(payload: ScrapeRequest, db: Session = Depends(get_db)):
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

    if access_state["has_active_subscription"] and active_subscription:
        max_results_allowed = get_max_results_for_tier(active_subscription.tier)
        if payload.max_results > max_results_allowed:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your {active_subscription.tier.value} plan allows up to "
                    f"{max_results_allowed} results per scrape."
                ),
            )

    try:
        results = await run_in_threadpool(run_scrape, data)
        run = persist_scrape(db, data, results)
        mark_user_scrape(db, payload.email)
        hydrated_run = (
            db.query(ScrapeRun)
            .options(joinedload(ScrapeRun.businesses))
            .filter(ScrapeRun.id == run.id)
            .first()
        )
        return {
            "run": hydrated_run,
            "results": hydrated_run.businesses,
            "remaining_credits": access_state["trial_days_left"],
            "billing_mode": billing_mode,
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def build_pagination(page: int, page_size: int, total: int) -> PaginationMetaResponse:
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    return PaginationMetaResponse(page=page, page_size=page_size, total=total, total_pages=total_pages)


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
    city: Optional[str] = Query(default=None),
    country: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    page: Optional[int] = Query(default=None, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
):
    query = db.query(Business).order_by(Business.created_at.desc())

    if city:
        query = query.filter(Business.city.ilike(f"%{city}%"))
    if country:
        query = query.filter(Business.country.ilike(f"%{country}%"))
    if category:
        query = query.filter(Business.category.ilike(f"%{category}%"))

    if page is None:
        return query.limit(limit).all()

    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    return {"items": items, "pagination": build_pagination(page, page_size, total)}


@app.get("/api/businesses/{business_id}")
def get_business(business_id: int, db: Session = Depends(get_db)):
    business = db.query(Business).filter(Business.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


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


@app.post("/api/users/onboard", response_model=PlatformUserResponse)
def onboard_user(payload: PlatformUserUpsertRequest, db: Session = Depends(get_db)):
    return upsert_platform_user(db, payload)


@app.put("/api/users/profile", response_model=PlatformUserResponse)
def update_user_profile(payload: PlatformUserUpsertRequest, db: Session = Depends(get_db)):
    return upsert_platform_user(db, payload)


@app.get("/api/users/access/{email}", response_model=AccessStatusResponse)
def get_user_access(email: str, db: Session = Depends(get_db)):
    return get_user_access_state(db, email)


@app.get("/api/users/dashboard/{email}", response_model=UserDashboardResponse)
def get_user_dashboard_view(email: str, db: Session = Depends(get_db)):
    try:
        return get_user_dashboard(db, email)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/users/subscription/cancel", response_model=UserSubscriptionSnapshotResponse)
def cancel_user_subscription(request: UserSubscriptionCancelRequest, db: Session = Depends(get_db)):
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
    publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    paypal_client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    paypal_client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    paypal_currency = os.getenv("PAYPAL_CURRENCY", "USD").strip() or "USD"
    paypal_environment = os.getenv("PAYPAL_ENVIRONMENT", "sandbox").strip() or "sandbox"
    return {
        "publishable_key": publishable_key,
        "payments_enabled": bool(publishable_key and not publishable_key.endswith("placeholder")),
        "paypal_enabled": bool(paypal_client_id and paypal_client_secret),
        "paypal_client_id": paypal_client_id,
        "paypal_currency": paypal_currency,
        "paypal_environment": paypal_environment,
        "paypal_sdk_base": "https://www.paypal.com/sdk/js",
        "trial_days": 15,
    }


@app.post("/api/payment/create-checkout-session")
def create_payment_session(
    request: CreateCheckoutSessionRequest,
    db: Session = Depends(get_db)
):
    """Create a Stripe checkout session for purchasing credits."""
    try:
        result = create_checkout_session(db, request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payment error: {str(e)}")


@app.post("/api/subscription/create-checkout-session")
def create_subscription_session(
    request: CreateSubscriptionCheckoutRequest,
    db: Session = Depends(get_db)
):
    """Create a subscription checkout session."""
    try:
        result = create_subscription_checkout_session(db, request)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Subscription error: {str(e)}")


@app.post("/api/paypal/orders")
def create_paypal_order(
    request: CreateSubscriptionCheckoutRequest,
    db: Session = Depends(get_db),
):
    try:
        return create_paypal_subscription_order(db, request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal order error: {str(e)}")


@app.post("/api/paypal/orders/{order_id}/capture")
def capture_paypal_order(order_id: str, db: Session = Depends(get_db)):
    try:
        return capture_paypal_subscription_order(db, order_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PayPal capture error: {str(e)}")


@app.post("/api/webhook", include_in_schema=False)
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Handle the event
    handle_webhook_event(event["type"], event["data"])
    
    return JSONResponse(content={"received": True}, status_code=200)


@app.get("/api/user/credits/{email}")
def get_credits(email: str, db: Session = Depends(get_db)):
    """Get available credits for a user."""
    credits = get_user_credits(db, email)
    return {"email": email, "available_credits": credits}


@app.post("/api/user/credits/use")
def consume_credit(email: str, db: Session = Depends(get_db)):
    """Use one scrape credit."""
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
