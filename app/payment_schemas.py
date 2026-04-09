from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime
from app.payment_models import PaymentProvider, PaymentStatus, SubscriptionTier


class PlatformUserUpsertRequest(BaseModel):
    email: EmailStr
    full_name: str
    company_name: str
    phone: str
    country: Optional[str] = None
    preferred_payment_provider: PaymentProvider = PaymentProvider.CARD


class PlatformUserRegisterRequest(PlatformUserUpsertRequest):
    password: str
    confirm_password: str


class PlatformUserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformUserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    company_name: str
    phone: str
    country: Optional[str]
    is_active: bool
    preferred_payment_provider: PaymentProvider
    trial_started_at: datetime
    trial_ends_at: datetime
    total_scrapes: int
    last_scrape_at: Optional[datetime]
    last_login: Optional[datetime]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PlatformAuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: PlatformUserResponse


class AccessStatusResponse(BaseModel):
    email: EmailStr
    can_scrape: bool
    trial_active: bool
    trial_days_left: int
    requires_subscription: bool
    recommended_tier: str
    has_active_subscription: bool
    subscription_tier: Optional[str] = None
    preferred_payment_provider: Optional[PaymentProvider] = None


class UserSubscriptionSnapshotResponse(BaseModel):
    id: int
    tier: SubscriptionTier
    is_active: bool
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    provider: Optional[PaymentProvider] = None


class UserActivitySummaryResponse(BaseModel):
    total_scrapes: int
    last_scrape_at: Optional[datetime]
    member_since: datetime


class UserDashboardResponse(BaseModel):
    profile: PlatformUserResponse
    access: AccessStatusResponse
    current_subscription: Optional[UserSubscriptionSnapshotResponse] = None
    recent_payments: list["PaymentResponse"]
    subscription_history: list["SubscriptionResponse"]
    activity: UserActivitySummaryResponse


class UserSubscriptionCancelRequest(BaseModel):
    email: EmailStr


class CreateSubscriptionCheckoutRequest(BaseModel):
    email: EmailStr
    tier: SubscriptionTier = SubscriptionTier.PRO
    provider: PaymentProvider = PaymentProvider.CARD
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CreateCheckoutSessionRequest(BaseModel):
    email: EmailStr
    amount: float
    description: Optional[str] = "Scrape credit purchase"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class CheckoutSessionResponse(BaseModel):
    session_id: str
    url: str


class PaymentResponse(BaseModel):
    id: int
    user_email: str
    amount: float
    currency: str
    status: PaymentStatus
    description: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class ScrapeCreditResponse(BaseModel):
    id: int
    payment_id: int
    credits: int
    used: int
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class SubscriptionResponse(BaseModel):
    id: int
    user_email: str
    tier: SubscriptionTier
    is_active: bool
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PricingPlan(BaseModel):
    name: str
    tier: str
    price: float
    billing_period: str
    scrape_credits: int
    max_results_per_scrape: int
    features: list[str]
    popular: bool = False


class CreditPurchaseRequest(BaseModel):
    email: EmailStr
    credits: int


class WebhookPayload(BaseModel):
    event_type: str
    data: Dict[str, Any]