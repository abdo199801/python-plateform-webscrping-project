from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.payment_models import PaymentProvider


# ==================== Admin User Schemas ====================

class AdminUserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None


class AdminUserCreate(AdminUserBase):
    password: str
    is_superuser: bool = False
    # Permissions
    can_manage_users: bool = True
    can_view_scrapes: bool = True
    can_run_scrapes: bool = True
    can_manage_payments: bool = False
    can_view_analytics: bool = True
    can_manage_admins: bool = False


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    can_manage_users: Optional[bool] = None
    can_view_scrapes: Optional[bool] = None
    can_run_scrapes: Optional[bool] = None
    can_manage_payments: Optional[bool] = None
    can_view_analytics: Optional[bool] = None
    can_manage_admins: Optional[bool] = None


class AdminUserResponse(AdminUserBase):
    id: int
    is_superuser: bool
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    can_manage_users: bool
    can_view_scrapes: bool
    can_run_scrapes: bool
    can_manage_payments: bool
    can_view_analytics: bool
    can_manage_admins: bool

    class Config:
        from_attributes = True


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str
    admin: AdminUserResponse


# ==================== Admin Action Schemas ====================

class AdminActionBase(BaseModel):
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    details: Optional[str] = None


class AdminActionCreate(AdminActionBase):
    admin_email: str
    ip_address: Optional[str] = None


class AdminActionResponse(AdminActionBase):
    id: int
    admin_email: str
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Admin Rule Schemas ====================

class AdminRuleBase(BaseModel):
    rule_name: str
    rule_type: str
    description: Optional[str] = None
    config: Optional[dict] = None


class AdminRuleCreate(AdminRuleBase):
    pass


class AdminRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[dict] = None
    description: Optional[str] = None


class AdminRuleResponse(AdminRuleBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ==================== Dashboard Stats Schema ====================

class DashboardStats(BaseModel):
    total_scrapes: int
    total_businesses: int
    total_users: int
    total_revenue: float
    active_subscriptions: int
    recent_scrapes: int  # Last 7 days
    credits_sold: int


class SystemHealth(BaseModel):
    database_status: str
    stripe_status: str
    uptime_hours: float
    last_scrape: Optional[datetime] = None
    queue_status: str = "idle"


class PlatformUserAdminResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    company_name: str
    phone: str
    country: Optional[str] = None
    preferred_payment_provider: PaymentProvider
    trial_started_at: datetime
    trial_ends_at: datetime
    trial_active: bool
    trial_days_left: int
    total_scrapes: int
    last_scrape_at: Optional[datetime] = None
    has_active_subscription: bool
    subscription_tier: Optional[str] = None
    created_at: datetime
    notes: Optional[str] = None


class PlatformUserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    preferred_payment_provider: Optional[PaymentProvider] = None
    trial_ends_at: Optional[datetime] = None
    notes: Optional[str] = None
    activate_pro_subscription: bool = False
    deactivate_subscription: bool = False
    subscription_days: int = 30