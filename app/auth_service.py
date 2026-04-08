from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.admin_models import AdminUser
from app.admin_schemas import AdminUserCreate
import bcrypt


# ==================== Password Hashing ====================

def hash_password(password: str) -> str:
    """Hash a password using bcrypt directly."""
    password_bytes = password.encode('utf-8')[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8')[:72],
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False


# ==================== JWT Token Management ====================

def create_admin_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT token for admin authentication."""
    from jose import jwt
    
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    
    to_encode.update({"exp": expire})
    
    import os
    SECRET_KEY = os.getenv("ADMIN_JWT_SECRET", "admin-secret-key-change-in-production")
    ALGORITHM = "HS256"
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_admin_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    from jose import jwt, JWTError
    
    import os
    SECRET_KEY = os.getenv("ADMIN_JWT_SECRET", "admin-secret-key-change-in-production")
    ALGORITHM = "HS256"
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ==================== Admin User Management ====================

def create_admin_user(db: Session, admin_data: AdminUserCreate) -> AdminUser:
    """Create a new admin user."""
    hashed_pw = hash_password(admin_data.password)
    db_admin = AdminUser(
        email=admin_data.email,
        hashed_password=hashed_pw,
        full_name=admin_data.full_name,
        is_superuser=admin_data.is_superuser,
        can_manage_users=admin_data.can_manage_users,
        can_view_scrapes=admin_data.can_view_scrapes,
        can_run_scrapes=admin_data.can_run_scrapes,
        can_manage_payments=admin_data.can_manage_payments,
        can_view_analytics=admin_data.can_view_analytics,
        can_manage_admins=admin_data.can_manage_admins,
    )
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)
    return db_admin


def get_admin_by_email(db: Session, email: str) -> Optional[AdminUser]:
    """Get admin user by email."""
    return db.query(AdminUser).filter(AdminUser.email == email).first()


def get_admin_by_id(db: Session, admin_id: int) -> Optional[AdminUser]:
    """Get admin user by ID."""
    return db.query(AdminUser).filter(AdminUser.id == admin_id).first()


def authenticate_admin(db: Session, email: str, password: str) -> Optional[AdminUser]:
    """Authenticate an admin user."""
    admin = get_admin_by_email(db, email)
    if not admin:
        return None
    if not verify_password(password, admin.hashed_password):
        return None
    if not admin.is_active:
        return None
    return admin


def update_admin_last_login(db: Session, admin: AdminUser) -> AdminUser:
    """Update admin's last login timestamp."""
    admin.last_login = datetime.utcnow()
    db.commit()
    db.refresh(admin)
    return admin


def list_admin_users(db: Session, skip: int = 0, limit: int = 100) -> list:
    """List all admin users."""
    return db.query(AdminUser).offset(skip).limit(limit).all()


def deactivate_admin_user(db: Session, admin: AdminUser) -> AdminUser:
    """Deactivate an admin user."""
    admin.is_active = False
    db.commit()
    db.refresh(admin)
    return admin
