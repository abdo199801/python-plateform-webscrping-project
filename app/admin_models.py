from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class AdminUser(Base):
    """Admin user model for managing admin access."""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_superuser = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Admin permissions/rules
    can_manage_users = Column(Boolean, default=True)
    can_view_scrapes = Column(Boolean, default=True)
    can_run_scrapes = Column(Boolean, default=True)
    can_manage_payments = Column(Boolean, default=False)
    can_view_analytics = Column(Boolean, default=True)
    can_manage_admins = Column(Boolean, default=False)  # Only superusers


class AdminAction(Base):
    """Audit log for admin actions."""
    __tablename__ = "admin_actions"

    id = Column(Integer, primary_key=True, index=True)
    admin_email = Column(String(255), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)  # login, logout, create, update, delete, etc.
    resource_type = Column(String(50), nullable=True)  # user, scrape, payment, etc.
    resource_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AdminRule(Base):
    """Configurable admin rules and restrictions."""
    __tablename__ = "admin_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(100), unique=True, nullable=False, index=True)
    rule_type = Column(String(50), nullable=False)  # rate_limit, access_control, scrape_limit, etc.
    is_active = Column(Boolean, default=True)
    config = Column(Text, nullable=True)  # JSON configuration
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)