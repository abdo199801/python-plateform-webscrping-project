import os
import stripe
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from urllib import error, parse, request as urlrequest
from sqlalchemy.orm import Session

from app.payment_models import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PlatformUser,
    ScrapeCredit,
    Subscription,
    SubscriptionTier,
)
from app.payment_schemas import (
    CreateCheckoutSessionRequest,
    CreateSubscriptionCheckoutRequest,
    CreditPurchaseRequest,
    PlatformUserUpsertRequest,
)

# Configure Stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_placeholder")
TRIAL_DURATION_DAYS = 15
SCRAPE_ALLOWED_TIERS = {SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE}
DEFAULT_MAX_RESULTS_PER_SCRAPE = 1000
ENTERPRISE_MAX_RESULTS_PER_SCRAPE = 1000

# Pricing configuration
PRICING_PLANS = [
    {
        "name": "Free Trial",
        "tier": "free",
        "price": 0,
        "billing_period": "15 days",
        "scrape_credits": 999,
        "max_results_per_scrape": DEFAULT_MAX_RESULTS_PER_SCRAPE,
        "features": [
            "Unlimited scrapes for 15 days",
            "Collect business contacts",
            "Live lead dashboard",
            "No card required to start"
        ],
        "popular": False
    },
    {
        "name": "Professional",
        "tier": "pro",
        "price": 79,
        "billing_period": "monthly",
        "scrape_credits": 999,
        "max_results_per_scrape": DEFAULT_MAX_RESULTS_PER_SCRAPE,
        "features": [
            "Unlimited scrapes after trial",
            "1000 results per scrape",
            "All export formats",
            "Priority support",
            "Card or PayPal checkout",
            "Lead intelligence dashboard"
        ],
        "popular": True
    },
    {
        "name": "Enterprise",
        "tier": "enterprise",
        "price": 199,
        "billing_period": "monthly",
        "scrape_credits": 999,
        "max_results_per_scrape": ENTERPRISE_MAX_RESULTS_PER_SCRAPE,
        "features": [
            "Unlimited scrapes after trial",
            "1000 results per scrape",
            "All export formats",
            "24/7 Priority support",
            "Unlimited business storage",
            "Full API access",
            "Advanced filtering",
            "Custom integrations",
            "Dedicated account manager"
        ],
        "popular": False
    }
]

# Credit packages for one-time purchases
CREDIT_PACKAGES = [
    {"credits": 5, "price": 15, "bonus": 0},
    {"credits": 10, "price": 25, "bonus": 2},
    {"credits": 25, "price": 50, "bonus": 5},
    {"credits": 50, "price": 90, "bonus": 15},
    {"credits": 100, "price": 150, "bonus": 30},
]


def utc_now() -> datetime:
    return datetime.utcnow()


def normalize_utc_naive(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def get_frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:8000").strip().rstrip("/")


def get_paypal_api_base() -> str:
    environment = os.getenv("PAYPAL_ENVIRONMENT", "sandbox").strip().lower()
    if environment == "live":
        return "https://api-m.paypal.com"
    return "https://api-m.sandbox.paypal.com"


def get_paypal_access_token() -> str:
    client_id = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ValueError("PayPal is not configured yet. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET.")

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    token_request = urlrequest.Request(
        url=f"{get_paypal_api_base()}/v1/oauth2/token",
        data=body,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlrequest.urlopen(token_request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"PayPal token request failed: {detail}") from exc
    except error.URLError as exc:
        raise ValueError(f"PayPal connection failed: {exc.reason}") from exc

    access_token = payload.get("access_token")
    if not access_token:
        raise ValueError("PayPal token response did not include an access token.")

    return access_token


def paypal_api_request(path: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
    access_token = get_paypal_access_token()
    request_data = json.dumps(payload).encode("utf-8") if payload is not None else None
    paypal_request = urlrequest.Request(
        url=f"{get_paypal_api_base()}{path}",
        data=request_data,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )

    try:
        with urlrequest.urlopen(paypal_request, timeout=30) as response:
            raw_payload = response.read().decode("utf-8")
            return json.loads(raw_payload) if raw_payload else {}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"PayPal API request failed: {detail}") from exc
    except error.URLError as exc:
        raise ValueError(f"PayPal connection failed: {exc.reason}") from exc


def get_pricing_plan_by_tier(tier: SubscriptionTier) -> Optional[Dict[str, Any]]:
    return next((plan for plan in PRICING_PLANS if plan["tier"] == tier.value), None)


def get_pricing_plans() -> List[Dict[str, Any]]:
    """Get all available pricing plans."""
    return PRICING_PLANS


def get_credit_packages() -> List[Dict[str, Any]]:
    """Get all available credit packages."""
    return CREDIT_PACKAGES


def get_platform_user(db: Session, email: str) -> Optional[PlatformUser]:
    return db.query(PlatformUser).filter(PlatformUser.email == email).first()


def upsert_platform_user(db: Session, payload: PlatformUserUpsertRequest) -> PlatformUser:
    user = get_platform_user(db, payload.email)
    now = utc_now()

    if user is None:
        user = PlatformUser(
            email=payload.email,
            full_name=payload.full_name.strip(),
            company_name=payload.company_name.strip(),
            phone=payload.phone.strip(),
            country=(payload.country or "").strip() or None,
            preferred_payment_provider=payload.preferred_payment_provider,
            trial_started_at=now,
            trial_ends_at=now + timedelta(days=TRIAL_DURATION_DAYS),
        )
        db.add(user)
    else:
        user.full_name = payload.full_name.strip()
        user.company_name = payload.company_name.strip()
        user.phone = payload.phone.strip()
        user.country = (payload.country or "").strip() or None
        user.preferred_payment_provider = payload.preferred_payment_provider

    db.commit()
    db.refresh(user)
    return user


def mark_user_scrape(db: Session, email: str) -> Optional[PlatformUser]:
    user = get_platform_user(db, email)
    if user is None:
        return None

    user.total_scrapes += 1
    user.last_scrape_at = utc_now()
    db.commit()
    db.refresh(user)
    return user


def has_eligible_subscription(subscription: Optional[Subscription]) -> bool:
    if subscription is None or not subscription.is_active:
        return False
    if subscription.tier not in SCRAPE_ALLOWED_TIERS:
        return False
    current_period_end = normalize_utc_naive(subscription.current_period_end)
    if current_period_end and current_period_end < utc_now():
        return False
    return True


def get_user_access_state(db: Session, email: str) -> Dict[str, Any]:
    user = get_platform_user(db, email)
    if user is None:
        return {
            "email": email,
            "can_scrape": False,
            "trial_active": False,
            "trial_days_left": 0,
            "requires_subscription": False,
            "recommended_tier": "pro",
            "has_active_subscription": False,
            "subscription_tier": None,
            "preferred_payment_provider": None,
        }

    now = utc_now()
    trial_ends_at = normalize_utc_naive(user.trial_ends_at) or now
    trial_active = trial_ends_at >= now
    trial_days_left = max(0, (trial_ends_at.date() - now.date()).days)
    subscription = get_user_subscription(db, email)
    subscription_active = has_eligible_subscription(subscription)

    return {
        "email": email,
        "can_scrape": trial_active or subscription_active,
        "trial_active": trial_active,
        "trial_days_left": trial_days_left,
        "requires_subscription": not trial_active and not subscription_active,
        "recommended_tier": "pro",
        "has_active_subscription": subscription_active,
        "subscription_tier": subscription.tier.value if subscription_active and subscription else None,
        "preferred_payment_provider": user.preferred_payment_provider,
    }


def get_credit_price(credits: int) -> Optional[float]:
    """Get the price for a specific number of credits."""
    for package in CREDIT_PACKAGES:
        if package["credits"] == credits:
            return package["price"]
    return None


def create_checkout_session(
    db: Session,
    request: CreateCheckoutSessionRequest
) -> Dict[str, str]:
    """Create a Stripe checkout session."""
    try:
        # Create pending payment record
        payment = Payment(
            user_email=request.email,
            amount=request.amount,
            currency="usd",
            status=PaymentStatus.PENDING,
            description=request.description
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        # Create Stripe checkout session
        success_url = request.success_url or f"{os.getenv('FRONTEND_URL', 'http://localhost:8000')}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or f"{os.getenv('FRONTEND_URL', 'http://localhost:8000')}/payment/cancel"

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": request.description or "Scrape Credits",
                        },
                        "unit_amount": int(request.amount * 100),  # Convert to cents
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=request.email,
            metadata={
                "payment_id": str(payment.id),
                "user_email": request.email
            }
        )

        # Update payment with Stripe session ID
        payment.stripe_checkout_session_id = session.id
        db.commit()

        return {
            "session_id": session.id,
            "url": session.url
        }
    except Exception as e:
        db.rollback()
        raise e


def create_subscription_checkout_session(
    db: Session,
    request: CreateSubscriptionCheckoutRequest,
) -> Dict[str, str]:
    """Create a subscription checkout session for card or PayPal."""
    try:
        email = request.email
        tier = request.tier.value

        # Find the plan
        plan = get_pricing_plan_by_tier(request.tier)
        if not plan or plan["price"] == 0:
            raise ValueError(f"Invalid subscription tier: {tier}")
        if request.tier not in SCRAPE_ALLOWED_TIERS:
            raise ValueError("Only Professional or Enterprise plans unlock scraping after the trial.")

        # Create pending subscription record
        subscription = Subscription(
            user_email=email,
            tier=request.tier,
            is_active=False
        )
        db.add(subscription)
        db.commit()
        db.refresh(subscription)

        success_url = request.success_url or f"{get_frontend_url()}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or f"{get_frontend_url()}/subscription/cancel"

        user = get_platform_user(db, email)
        if user:
            user.preferred_payment_provider = request.provider
            db.commit()

        if request.provider == PaymentProvider.PAYPAL:
            raise ValueError("Use the PayPal button to create and capture a PayPal order.")

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"{plan['name']} Subscription",
                        },
                        "recurring": {
                            "interval": "month"
                        },
                        "unit_amount": int(plan["price"] * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            customer_email=email,
            metadata={
                "subscription_id": str(subscription.id),
                "user_email": email,
                "tier": tier
            }
        )

        subscription.stripe_subscription_id = session.subscription_id if session.subscription_id else None
        subscription.stripe_customer_id = session.customer if session.customer else None
        db.commit()

        return {
            "session_id": session.id,
            "url": session.url,
            "provider": request.provider.value,
            "requires_manual_activation": "false",
        }
    except Exception as e:
        db.rollback()
        raise e


def create_paypal_subscription_order(
    db: Session,
    request: CreateSubscriptionCheckoutRequest,
) -> Dict[str, Any]:
    if request.provider != PaymentProvider.PAYPAL:
        raise ValueError("PayPal order creation requires provider=paypal.")

    plan = get_pricing_plan_by_tier(request.tier)
    if not plan or plan["price"] == 0:
        raise ValueError(f"Invalid subscription tier: {request.tier.value}")
    if request.tier not in SCRAPE_ALLOWED_TIERS:
        raise ValueError("Only Professional or Enterprise plans unlock scraping after the trial.")

    user = get_platform_user(db, request.email)
    if user is None:
        raise ValueError("Please save the company profile before starting PayPal checkout.")

    user.preferred_payment_provider = PaymentProvider.PAYPAL

    subscription = Subscription(
        user_email=request.email,
        tier=request.tier,
        is_active=False,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    payment = Payment(
        user_email=request.email,
        amount=plan["price"],
        currency="USD",
        status=PaymentStatus.PENDING,
        description=f"{plan['name']} subscription via PayPal",
        payment_metadata={
            "tier": request.tier.value,
            "provider": PaymentProvider.PAYPAL.value,
            "subscription_id": subscription.id,
        },
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    frontend_url = get_frontend_url()
    order_payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": f"subscription-{subscription.id}",
                "description": f"{plan['name']} monthly subscription",
                "custom_id": str(subscription.id),
                "amount": {
                    "currency_code": "USD",
                    "value": f"{plan['price']:.2f}",
                },
            }
        ],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "landing_page": "LOGIN",
                    "user_action": "PAY_NOW",
                    "return_url": f"{frontend_url}/subscription/success",
                    "cancel_url": f"{frontend_url}/subscription/cancel",
                }
            }
        },
    }

    try:
        order = paypal_api_request("/v2/checkout/orders", method="POST", payload=order_payload)
    except Exception:
        db.delete(payment)
        db.delete(subscription)
        db.commit()
        raise

    order_id = order.get("id")
    if not order_id:
        db.delete(payment)
        db.delete(subscription)
        db.commit()
        raise ValueError("PayPal did not return an order id.")

    subscription.stripe_subscription_id = f"paypal-order-{order_id}"
    payment.stripe_checkout_session_id = order_id
    payment.payment_metadata = {
        **(payment.payment_metadata or {}),
        "paypal_order_id": order_id,
    }
    db.commit()

    return {
        "id": order_id,
        "subscription_id": subscription.id,
        "plan": plan["name"],
        "provider": PaymentProvider.PAYPAL.value,
    }


def capture_paypal_subscription_order(db: Session, order_id: str) -> Dict[str, Any]:
    if not order_id:
        raise ValueError("PayPal order id is required.")

    order = paypal_api_request(f"/v2/checkout/orders/{order_id}/capture", method="POST", payload={})
    status = order.get("status")
    if status != "COMPLETED":
        raise ValueError(f"PayPal capture returned status {status or 'unknown'}.")

    subscription = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == f"paypal-order-{order_id}"
    ).order_by(Subscription.created_at.desc()).first()
    if subscription is None:
        raise ValueError("Subscription record not found for this PayPal order.")

    payment = db.query(Payment).filter(Payment.stripe_checkout_session_id == order_id).order_by(Payment.created_at.desc()).first()

    capture_id = None
    purchase_units = order.get("purchase_units") or []
    if purchase_units:
        payments = purchase_units[0].get("payments") or {}
        captures = payments.get("captures") or []
        if captures:
            capture_id = captures[0].get("id")

    subscription.is_active = True
    subscription.cancel_at_period_end = False
    subscription.current_period_start = utc_now()
    subscription.current_period_end = utc_now() + timedelta(days=30)
    subscription.stripe_customer_id = order.get("payer", {}).get("payer_id")
    subscription.stripe_subscription_id = f"paypal-capture-{capture_id or order_id}"

    if payment is not None:
        payment.status = PaymentStatus.COMPLETED
        payment.completed_at = utc_now()
        payment.stripe_payment_intent_id = capture_id
        payment.payment_metadata = {
            **(payment.payment_metadata or {}),
            "paypal_order_status": status,
            "paypal_capture_id": capture_id,
        }

    db.commit()
    db.refresh(subscription)

    return order


def handle_webhook_event(event_type: str, data: Dict[str, Any]) -> Optional[Payment]:
    """Handle Stripe webhook events."""
    from app.database import SessionLocal
    db = SessionLocal()
    
    try:
        if event_type == "checkout.session.completed":
            session = data["object"]
            payment_id = session.get("metadata", {}).get("payment_id")
            subscription_id = session.get("metadata", {}).get("subscription_id")
            
            if payment_id:
                payment = db.query(Payment).filter(Payment.id == int(payment_id)).first()
                if payment:
                    payment.status = PaymentStatus.COMPLETED
                    payment.stripe_payment_intent_id = session.get("payment_intent")
                    payment.completed_at = utc_now()
                    
                    # Grant scrape credits
                    amount = session["amount_total"] / 100  # Convert from cents
                    credits = calculate_credits_from_amount(amount)
                    
                    scrape_credit = ScrapeCredit(
                        payment_id=payment.id,
                        credits=credits,
                        expires_at=utc_now() + timedelta(days=365)
                    )
                    db.add(scrape_credit)
                    db.commit()
                    return payment

            if subscription_id:
                subscription = db.query(Subscription).filter(Subscription.id == int(subscription_id)).first()
                if subscription:
                    subscription.is_active = True
                    subscription.current_period_start = utc_now()
                    subscription.current_period_end = utc_now() + timedelta(days=30)
                    subscription.stripe_customer_id = session.get("customer")
                    subscription.stripe_subscription_id = session.get("subscription")
                    db.commit()

        elif event_type == "customer.subscription.created":
            subscription_data = data["object"]
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_data.get("id")
            ).first()
            if subscription:
                subscription.is_active = subscription_data.get("status") == "active"
                db.commit()

        elif event_type == "customer.subscription.updated":
            subscription_data = data["object"]
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_data.get("id")
            ).first()
            if subscription:
                subscription.is_active = subscription_data.get("status") == "active"
                db.commit()

        elif event_type == "customer.subscription.deleted":
            subscription_data = data["object"]
            subscription = db.query(Subscription).filter(
                Subscription.stripe_subscription_id == subscription_data.get("id")
            ).first()
            if subscription:
                subscription.is_active = False
                subscription.current_period_end = utc_now()
                db.commit()

    except Exception as e:
        db.rollback()
        print(f"Error handling webhook: {e}")
    finally:
        db.close()
    
    return None


def calculate_credits_from_amount(amount: float) -> int:
    """Calculate the number of scrape credits based on payment amount."""
    # Find the best matching package
    best_credits = 0
    for package in CREDIT_PACKAGES:
        if package["price"] <= amount:
            total_credits = package["credits"] + package["bonus"]
            if total_credits > best_credits:
                best_credits = total_credits
    
    # If no package matches, give 1 credit per $3
    if best_credits == 0:
        best_credits = max(1, int(amount / 3))
    
    return best_credits


def get_user_credits(db: Session, email: str) -> int:
    """Get available scrape credits for a user."""
    credits = db.query(ScrapeCredit).filter(
        ScrapeCredit.payment.has(Payment.user_email == email),
        ScrapeCredit.is_active == True,
        (ScrapeCredit.expires_at.is_(None) | ScrapeCredit.expires_at > utc_now())
    ).all()
    
    total_available = sum(credit.credits - credit.used for credit in credits)
    return max(0, total_available)


def use_credit(db: Session, email: str) -> bool:
    """Use one scrape credit. Returns True if successful."""
    credits = db.query(ScrapeCredit).filter(
        ScrapeCredit.payment.has(Payment.user_email == email),
        ScrapeCredit.is_active == True,
        ScrapeCredit.used < ScrapeCredit.credits,
        (ScrapeCredit.expires_at.is_(None) | ScrapeCredit.expires_at > utc_now())
    ).order_by(ScrapeCredit.created_at.desc()).first()
    
    if credits:
        credits.used += 1
        if credits.used >= credits.credits:
            credits.is_active = False
        db.commit()
        return True
    return False


def refund_credit(db: Session, email: str) -> bool:
    """Restore one previously consumed scrape credit after a failed run."""
    credit = db.query(ScrapeCredit).filter(
        ScrapeCredit.payment.has(Payment.user_email == email),
        ScrapeCredit.used > 0,
    ).order_by(ScrapeCredit.created_at.desc()).first()

    if not credit:
        return False

    credit.used -= 1
    if credit.used < credit.credits:
        credit.is_active = True

    db.commit()
    return True


def get_user_subscription(db: Session, email: str) -> Optional[Subscription]:
    """Get the active subscription for a user."""
    return db.query(Subscription).filter(
        Subscription.user_email == email,
    ).order_by(Subscription.created_at.desc()).first()


def get_max_results_for_tier(tier: SubscriptionTier) -> int:
    """Get the maximum results per scrape for a subscription tier."""
    plan = next((p for p in PRICING_PLANS if p["tier"] == tier.value), None)
    if plan:
        return plan["max_results_per_scrape"]
    return DEFAULT_MAX_RESULTS_PER_SCRAPE


def activate_subscription_for_user(
    db: Session,
    email: str,
    tier: SubscriptionTier = SubscriptionTier.PRO,
    duration_days: int = 30,
) -> Subscription:
    subscription = get_user_subscription(db, email)
    if subscription is None:
        subscription = Subscription(user_email=email, tier=tier)
        db.add(subscription)

    subscription.tier = tier
    subscription.is_active = True
    subscription.current_period_start = utc_now()
    subscription.current_period_end = utc_now() + timedelta(days=max(1, duration_days))
    subscription.stripe_subscription_id = subscription.stripe_subscription_id or f"manual-admin-{email}"
    db.commit()
    db.refresh(subscription)
    return subscription


def deactivate_subscription_for_user(db: Session, email: str) -> Optional[Subscription]:
    subscription = get_user_subscription(db, email)
    if subscription is None:
        return None

    subscription.is_active = False
    subscription.current_period_end = utc_now()
    db.commit()
    db.refresh(subscription)
    return subscription


def get_user_dashboard(db: Session, email: str) -> Dict[str, Any]:
    user = get_platform_user(db, email)
    if user is None:
        raise ValueError("User profile not found")

    subscription = get_user_subscription(db, email)
    payments = (
        db.query(Payment)
        .filter(Payment.user_email == email)
        .order_by(Payment.created_at.desc())
        .limit(5)
        .all()
    )
    subscriptions = (
        db.query(Subscription)
        .filter(Subscription.user_email == email)
        .order_by(Subscription.created_at.desc())
        .limit(5)
        .all()
    )

    subscription_snapshot = None
    if subscription is not None:
        subscription_snapshot = {
            "id": subscription.id,
            "tier": subscription.tier,
            "is_active": subscription.is_active,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "cancel_at_period_end": subscription.cancel_at_period_end,
            "provider": user.preferred_payment_provider,
        }

    return {
        "profile": user,
        "access": get_user_access_state(db, email),
        "current_subscription": subscription_snapshot,
        "recent_payments": payments,
        "subscription_history": subscriptions,
        "activity": {
            "total_scrapes": user.total_scrapes,
            "last_scrape_at": user.last_scrape_at,
            "member_since": user.created_at,
        },
    }


def cancel_subscription_for_user(db: Session, email: str) -> Optional[Subscription]:
    subscription = get_user_subscription(db, email)
    if subscription is None:
        return None

    now = utc_now()
    stripe_subscription_id = (subscription.stripe_subscription_id or "").strip()
    managed_by_stripe = (
        stripe_subscription_id
        and not stripe_subscription_id.startswith("manual-admin-")
        and not stripe_subscription_id.startswith("paypal-pending-")
        and not stripe_subscription_id.startswith("paypal-order-")
        and not stripe_subscription_id.startswith("paypal-capture-")
        and not stripe.api_key.endswith("placeholder")
    )

    if managed_by_stripe:
        stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)

    subscription.cancel_at_period_end = True
    current_period_end = normalize_utc_naive(subscription.current_period_end)
    if not current_period_end or current_period_end <= now:
        subscription.is_active = False
        subscription.current_period_end = now

    db.commit()
    db.refresh(subscription)
    return subscription