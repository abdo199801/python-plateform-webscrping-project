import os
import stripe
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
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

# Pricing configuration
PRICING_PLANS = [
    {
        "name": "Free Trial",
        "tier": "free",
        "price": 0,
        "billing_period": "15 days",
        "scrape_credits": 999,
        "max_results_per_scrape": 100,
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
        "max_results_per_scrape": 100,
        "features": [
            "Unlimited scrapes after trial",
            "100 results per scrape",
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
        "max_results_per_scrape": 500,
        "features": [
            "Unlimited scrapes after trial",
            "500 results per scrape",
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
    now = datetime.utcnow()

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
    user.last_scrape_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def has_eligible_subscription(subscription: Optional[Subscription]) -> bool:
    if subscription is None or not subscription.is_active:
        return False
    if subscription.tier not in SCRAPE_ALLOWED_TIERS:
        return False
    if subscription.current_period_end and subscription.current_period_end < datetime.utcnow():
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

    now = datetime.utcnow()
    trial_active = user.trial_ends_at >= now
    trial_days_left = max(0, (user.trial_ends_at.date() - now.date()).days)
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
        plan = next((p for p in PRICING_PLANS if p["tier"] == tier), None)
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

        success_url = request.success_url or f"{os.getenv('FRONTEND_URL', 'http://localhost:8000')}/subscription/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = request.cancel_url or f"{os.getenv('FRONTEND_URL', 'http://localhost:8000')}/subscription/cancel"

        user = get_platform_user(db, email)
        if user:
            user.preferred_payment_provider = request.provider
            db.commit()

        if request.provider == PaymentProvider.PAYPAL:
            paypal_url = os.getenv("PAYPAL_SUBSCRIPTION_URL", "").strip()
            if not paypal_url:
                raise ValueError("PayPal checkout is not configured yet. Add PAYPAL_SUBSCRIPTION_URL to enable it.")

            subscription.stripe_subscription_id = f"paypal-pending-{subscription.id}"
            db.commit()
            return {
                "session_id": f"paypal-pending-{subscription.id}",
                "url": paypal_url,
                "provider": request.provider.value,
                "requires_manual_activation": "true",
            }

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
                    payment.completed_at = datetime.utcnow()
                    
                    # Grant scrape credits
                    amount = session["amount_total"] / 100  # Convert from cents
                    credits = calculate_credits_from_amount(amount)
                    
                    scrape_credit = ScrapeCredit(
                        payment_id=payment.id,
                        credits=credits,
                        expires_at=datetime.utcnow() + timedelta(days=365)
                    )
                    db.add(scrape_credit)
                    db.commit()
                    return payment

            if subscription_id:
                subscription = db.query(Subscription).filter(Subscription.id == int(subscription_id)).first()
                if subscription:
                    subscription.is_active = True
                    subscription.current_period_start = datetime.utcnow()
                    subscription.current_period_end = datetime.utcnow() + timedelta(days=30)
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
                subscription.current_period_end = datetime.utcnow()
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
        (ScrapeCredit.expires_at.is_(None) | ScrapeCredit.expires_at > datetime.utcnow())
    ).all()
    
    total_available = sum(credit.credits - credit.used for credit in credits)
    return max(0, total_available)


def use_credit(db: Session, email: str) -> bool:
    """Use one scrape credit. Returns True if successful."""
    credits = db.query(ScrapeCredit).filter(
        ScrapeCredit.payment.has(Payment.user_email == email),
        ScrapeCredit.is_active == True,
        ScrapeCredit.used < ScrapeCredit.credits,
        (ScrapeCredit.expires_at.is_(None) | ScrapeCredit.expires_at > datetime.utcnow())
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
    return 25  # Default for free tier


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
    subscription.current_period_start = datetime.utcnow()
    subscription.current_period_end = datetime.utcnow() + timedelta(days=max(1, duration_days))
    subscription.stripe_subscription_id = subscription.stripe_subscription_id or f"manual-admin-{email}"
    db.commit()
    db.refresh(subscription)
    return subscription


def deactivate_subscription_for_user(db: Session, email: str) -> Optional[Subscription]:
    subscription = get_user_subscription(db, email)
    if subscription is None:
        return None

    subscription.is_active = False
    subscription.current_period_end = datetime.utcnow()
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

    now = datetime.utcnow()
    stripe_subscription_id = (subscription.stripe_subscription_id or "").strip()
    managed_by_stripe = (
        stripe_subscription_id
        and not stripe_subscription_id.startswith("manual-admin-")
        and not stripe_subscription_id.startswith("paypal-pending-")
        and not stripe.api_key.endswith("placeholder")
    )

    if managed_by_stripe:
        stripe.Subscription.modify(stripe_subscription_id, cancel_at_period_end=True)

    subscription.cancel_at_period_end = True
    if not subscription.current_period_end or subscription.current_period_end <= now:
        subscription.is_active = False
        subscription.current_period_end = now

    db.commit()
    db.refresh(subscription)
    return subscription