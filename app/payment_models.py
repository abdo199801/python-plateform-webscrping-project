from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, ForeignKey, Enum as SQLEnum, JSON, func
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class SubscriptionTier(str, enum.Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PaymentProvider(str, enum.Enum):
    CARD = "card"
    PAYPAL = "paypal"


class PlatformUser(Base):
    __tablename__ = "platform_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    company_name = Column(String(255), nullable=False)
    phone = Column(String(100), nullable=False)
    country = Column(String(100), nullable=True)
    preferred_payment_provider = Column(
        SQLEnum(PaymentProvider),
        nullable=False,
        default=PaymentProvider.CARD,
    )
    trial_started_at = Column(DateTime(timezone=True), nullable=False)
    trial_ends_at = Column(DateTime(timezone=True), nullable=False)
    total_scrapes = Column(Integer, nullable=False, default=0)
    last_scrape_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    status = Column(SQLEnum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_checkout_session_id = Column(String(255), unique=True, nullable=True)
    description = Column(Text, nullable=True)
    payment_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    scrape_credits = relationship(
        "ScrapeCredit",
        back_populates="payment",
        cascade="all, delete-orphan",
    )


class ScrapeCredit(Base):
    __tablename__ = "scrape_credits"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    credits = Column(Integer, nullable=False, default=1)
    used = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    payment = relationship("Payment", back_populates="scrape_credits")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    tier = Column(SQLEnum(SubscriptionTier), nullable=False, default=SubscriptionTier.FREE)
    stripe_subscription_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=False)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
