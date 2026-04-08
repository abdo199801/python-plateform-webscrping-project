# Re-export all functions from auth_service for backward compatibility
from app.auth_service import (
    hash_password,
    verify_password,
    create_admin_token,
    verify_admin_token,
    create_admin_user,
    get_admin_by_email,
    get_admin_by_id,
    authenticate_admin,
    update_admin_last_login,
    list_admin_users,
    deactivate_admin_user,
)

# Additional admin service functions that are not in auth_service
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.admin_models import AdminAction, AdminRule, AdminUser
from app.admin_schemas import AdminRuleCreate, AdminRuleUpdate
from app.models import ScrapeRun, Business
from app.payment_models import Payment, PaymentStatus, PlatformUser, Subscription, ScrapeCredit, SubscriptionTier
from app.payment_service import (
    activate_subscription_for_user,
    deactivate_subscription_for_user,
    get_user_access_state,
    upsert_platform_user,
)
from app.payment_schemas import PlatformUserUpsertRequest


def update_admin_user(db: Session, admin: AdminUser, update_data) -> AdminUser:
    """Update an admin user."""
    update_dict = update_data.model_dump(exclude_unset=True)
    
    if "password" in update_dict and update_dict["password"]:
        update_dict["hashed_password"] = hash_password(update_dict.pop("password"))
    
    for field, value in update_dict.items():
        setattr(admin, field, value)
    
    db.commit()
    db.refresh(admin)
    return admin


# ==================== Admin Action Logging ====================

def log_admin_action(
    db: Session,
    admin_email: str,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None
) -> AdminAction:
    """Log an admin action for audit purposes."""
    db_action = AdminAction(
        admin_email=admin_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(db_action)
    db.commit()
    db.refresh(db_action)
    return db_action


def get_admin_actions(db: Session, admin_email: Optional[str] = None, limit: int = 100) -> list:
    """Get admin action logs."""
    query = db.query(AdminAction).order_by(AdminAction.created_at.desc())
    if admin_email:
        query = query.filter(AdminAction.admin_email == admin_email)
    return query.limit(limit).all()


# ==================== Admin Rules Management ====================

def create_admin_rule(db: Session, rule_data: AdminRuleCreate) -> AdminRule:
    """Create a new admin rule."""
    import json
    config_json = json.dumps(rule_data.config) if rule_data.config else None
    db_rule = AdminRule(
        rule_name=rule_data.rule_name,
        rule_type=rule_data.rule_type,
        config=config_json,
        description=rule_data.description,
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


def get_admin_rule(db: Session, rule_id: int) -> Optional[AdminRule]:
    """Get admin rule by ID."""
    return db.query(AdminRule).filter(AdminRule.id == rule_id).first()


def get_admin_rule_by_name(db: Session, rule_name: str) -> Optional[AdminRule]:
    """Get admin rule by name."""
    return db.query(AdminRule).filter(AdminRule.rule_name == rule_name).first()


def list_admin_rules(db: Session, rule_type: Optional[str] = None) -> list:
    """List all admin rules."""
    query = db.query(AdminRule)
    if rule_type:
        query = query.filter(AdminRule.rule_type == rule_type)
    return query.all()


def update_admin_rule(db: Session, rule: AdminRule, update_data: AdminRuleUpdate) -> AdminRule:
    """Update an admin rule."""
    update_dict = update_data.model_dump(exclude_unset=True)
    
    if "config" in update_dict and update_dict["config"] is not None:
        import json
        update_dict["config"] = json.dumps(update_dict["config"])
    
    for field, value in update_dict.items():
        setattr(rule, field, value)
    
    db.commit()
    db.refresh(rule)
    return rule


def delete_admin_rule(db: Session, rule: AdminRule) -> bool:
    """Delete an admin rule."""
    db.delete(rule)
    db.commit()
    return True


# ==================== Dashboard Statistics ====================

def get_dashboard_stats(db: Session) -> dict:
    """Get dashboard statistics."""
    total_scrapes = db.query(ScrapeRun).count()
    total_businesses = db.query(Business).count()
    unique_user_emails = db.query(PlatformUser).count()
    total_revenue = db.query(func.sum(Payment.amount)).filter(Payment.status == PaymentStatus.COMPLETED).scalar() or 0.0
    active_subscriptions = db.query(Subscription).filter(Subscription.is_active == True).count()
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_scrapes = db.query(ScrapeRun).filter(ScrapeRun.created_at >= seven_days_ago).count()
    credits_sold = db.query(func.sum(ScrapeCredit.credits)).filter(ScrapeCredit.is_active == True).scalar() or 0
    
    return {
        "total_scrapes": total_scrapes,
        "total_businesses": total_businesses,
        "total_users": unique_user_emails,
        "total_revenue": round(total_revenue, 2),
        "active_subscriptions": active_subscriptions,
        "recent_scrapes": recent_scrapes,
        "credits_sold": credits_sold,
    }


def get_system_health(db: Session) -> dict:
    """Get system health status."""
    import os
    
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception:
        db_status = "unhealthy"
    
    stripe_key = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_status = "configured" if stripe_key and not stripe_key.startswith("sk_test_placeholder") else "not_configured"
    
    last_scrape = db.query(ScrapeRun).order_by(ScrapeRun.created_at.desc()).first()
    last_scrape_time = last_scrape.created_at if last_scrape else None
    
    return {
        "database_status": db_status,
        "stripe_status": stripe_status,
        "uptime_hours": 0.0,
        "last_scrape": last_scrape_time,
        "queue_status": "idle",
    }


def get_recent_payments(db: Session, limit: int = 20) -> list:
    """Get recent payments for admin dashboard."""
    return db.query(Payment).order_by(Payment.created_at.desc()).limit(limit).all()


def get_active_subscriptions_list(db: Session, limit: int = 50) -> list:
    """Get active subscriptions for admin dashboard."""
    return db.query(Subscription).filter(Subscription.is_active == True).order_by(Subscription.created_at.desc()).limit(limit).all()


def list_platform_users(db: Session, limit: int = 200) -> list[dict]:
    users = db.query(PlatformUser).order_by(PlatformUser.created_at.desc()).limit(limit).all()
    return [serialize_platform_user(db, user) for user in users]


def get_platform_user_by_id(db: Session, user_id: int) -> Optional[PlatformUser]:
    return db.query(PlatformUser).filter(PlatformUser.id == user_id).first()


def serialize_platform_user(db: Session, user: PlatformUser) -> dict:
    access = get_user_access_state(db, user.email)
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "company_name": user.company_name,
        "phone": user.phone,
        "country": user.country,
        "preferred_payment_provider": user.preferred_payment_provider,
        "trial_started_at": user.trial_started_at,
        "trial_ends_at": user.trial_ends_at,
        "trial_active": access["trial_active"],
        "trial_days_left": access["trial_days_left"],
        "total_scrapes": user.total_scrapes,
        "last_scrape_at": user.last_scrape_at,
        "has_active_subscription": access["has_active_subscription"],
        "subscription_tier": access["subscription_tier"],
        "created_at": user.created_at,
        "notes": user.notes,
    }


def create_platform_user(db: Session, payload: PlatformUserUpsertRequest) -> dict:
    if db.query(PlatformUser).filter(PlatformUser.email == payload.email).first():
        raise ValueError("Customer with this email already exists")
    user = upsert_platform_user(db, payload)
    return serialize_platform_user(db, user)


def delete_platform_user(db: Session, user: PlatformUser) -> None:
    db.delete(user)
    db.commit()


def update_platform_user(db: Session, user: PlatformUser, update_data) -> dict:
    data = update_data.model_dump(exclude_unset=True)
    activate_pro_subscription = data.pop("activate_pro_subscription", False)
    deactivate_subscription = data.pop("deactivate_subscription", False)
    subscription_days = data.pop("subscription_days", 30)

    for field, value in data.items():
        setattr(user, field, value)

    db.commit()

    if activate_pro_subscription:
        activate_subscription_for_user(db, user.email, SubscriptionTier.PRO, subscription_days)
    if deactivate_subscription:
        deactivate_subscription_for_user(db, user.email)

    db.refresh(user)
    return serialize_platform_user(db, user)