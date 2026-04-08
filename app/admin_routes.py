from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import json

from app.database import get_db
from app.admin_schemas import (
    AdminLoginRequest,
    AdminLoginResponse,
    PlatformUserAdminResponse,
    PlatformUserAdminUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserResponse,
    AdminRuleCreate,
    AdminRuleUpdate,
    AdminRuleResponse,
    DashboardStats,
    SystemHealth,
)
from app.admin_service import (
    authenticate_admin,
    create_admin_user,
    create_platform_user,
    delete_platform_user,
    get_admin_by_email,
    get_admin_by_id,
    update_admin_user,
    list_admin_users,
    deactivate_admin_user,
    create_admin_token,
    verify_admin_token,
    log_admin_action,
    get_admin_actions,
    create_admin_rule,
    get_admin_rule,
    get_admin_rule_by_name,
    list_admin_rules,
    update_admin_rule,
    delete_admin_rule,
    get_dashboard_stats,
    get_system_health,
    get_recent_payments,
    get_active_subscriptions_list,
    get_platform_user_by_id,
    list_platform_users,
    serialize_platform_user,
    update_platform_user,
    update_admin_last_login,
)
from app.payment_schemas import PlatformUserUpsertRequest

router = APIRouter(prefix="/api/admin", tags=["admin"])
security = HTTPBearer(auto_error=False)


# ==================== Authentication Dependency ====================

async def get_current_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> AdminUserResponse:
    """Get current authenticated admin user."""
    if not credentials:
        # Try getting token from cookies
        token = request.cookies.get("admin_token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        token = credentials.credentials

    payload = verify_admin_token(token)
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

    admin = get_admin_by_email(db, email)
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AdminUserResponse.model_validate(admin)


def require_permission(permission: str):
    """Dependency factory to check specific admin permissions."""
    async def permission_checker(
        current_admin: AdminUserResponse = Depends(get_current_admin)
    ) -> AdminUserResponse:
        if not getattr(current_admin, permission, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: requires {permission}",
            )
        return current_admin
    return permission_checker


# ==================== Auth Routes ====================

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    request: Request,
    login_data: AdminLoginRequest,
    db: Session = Depends(get_db)
):
    """Admin login endpoint."""
    admin = authenticate_admin(db, login_data.email, login_data.password)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Update last login
    update_admin_last_login(db, admin)

    # Create JWT token
    access_token = create_admin_token(
        data={"sub": admin.email},
        expires_delta=timedelta(hours=24)
    )

    # Log the login action
    client_ip = request.client.host if request.client else None
    log_admin_action(
        db=db,
        admin_email=admin.email,
        action="login",
        ip_address=client_ip,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "admin": AdminUserResponse.model_validate(admin),
    }


@router.post("/logout")
async def admin_logout(
    request: Request,
    current_admin: AdminUserResponse = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Admin logout endpoint."""
    client_ip = request.client.host if request.client else None
    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="logout",
        ip_address=client_ip,
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=AdminUserResponse)
async def get_current_admin_info(
    current_admin: AdminUserResponse = Depends(get_current_admin)
):
    """Get current admin user info."""
    return current_admin


# ==================== Dashboard Routes ====================

@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_statistics(
    current_admin: AdminUserResponse = Depends(require_permission("can_view_analytics")),
    db: Session = Depends(get_db)
):
    """Get dashboard statistics."""
    stats = get_dashboard_stats(db)
    return stats


@router.get("/dashboard/health", response_model=SystemHealth)
async def get_system_health_status(
    current_admin: AdminUserResponse = Depends(require_permission("can_view_analytics")),
    db: Session = Depends(get_db)
):
    """Get system health status."""
    health = get_system_health(db)
    return health


@router.get("/dashboard/recent-payments")
async def get_dashboard_recent_payments(
    limit: int = 20,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_payments")),
    db: Session = Depends(get_db)
):
    """Get recent payments for dashboard."""
    payments = get_recent_payments(db, limit)
    return payments


@router.get("/dashboard/active-subscriptions")
async def get_dashboard_subscriptions(
    limit: int = 50,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_payments")),
    db: Session = Depends(get_db)
):
    """Get active subscriptions for dashboard."""
    subscriptions = get_active_subscriptions_list(db, limit)
    return subscriptions


@router.get("/customers", response_model=list[PlatformUserAdminResponse])
async def get_customers(
    limit: int = 200,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db)
):
    """List platform customers and their access state."""
    return list_platform_users(db, limit)


@router.post("/customers", response_model=PlatformUserAdminResponse)
async def create_customer(
    customer_data: PlatformUserUpsertRequest,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db)
):
    """Create a platform customer manually from the admin area."""
    try:
        customer = create_platform_user(db, customer_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="create_customer",
        resource_type="platform_user",
        resource_id=customer["id"],
        details=f"Created customer {customer['email']}",
    )
    return customer


@router.get("/customers/{customer_id}", response_model=PlatformUserAdminResponse)
async def get_customer(
    customer_id: int,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db)
):
    """Get one platform customer."""
    customer = get_platform_user_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )
    return serialize_platform_user(db, customer)


@router.put("/customers/{customer_id}", response_model=PlatformUserAdminResponse)
async def update_customer(
    customer_id: int,
    update_data: PlatformUserAdminUpdate,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db)
):
    """Update trial and subscription access for a platform customer."""
    customer = get_platform_user_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    updated = update_platform_user(db, customer, update_data)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="update_customer",
        resource_type="platform_user",
        resource_id=customer_id,
        details=f"Updated customer access for {customer.email}",
    )

    return updated


@router.delete("/customers/{customer_id}")
async def delete_customer(
    customer_id: int,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_users")),
    db: Session = Depends(get_db)
):
    """Delete a platform customer."""
    customer = get_platform_user_by_id(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    customer_email = customer.email
    delete_platform_user(db, customer)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="delete_customer",
        resource_type="platform_user",
        resource_id=customer_id,
        details=f"Deleted customer {customer_email}",
    )
    return {"message": "Customer deleted"}


# ==================== Admin User Management Routes ====================

@router.post("/users", response_model=AdminUserResponse)
async def create_new_admin(
    admin_data: AdminUserCreate,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Create a new admin user (requires can_manage_admins permission)."""
    # Check if email already exists
    existing = get_admin_by_email(db, admin_data.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin with this email already exists",
        )

    admin = create_admin_user(db, admin_data)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="create_admin",
        resource_type="admin_user",
        resource_id=admin.id,
        details=f"Created admin user: {admin.email}",
    )

    return admin


@router.get("/users", response_model=list[AdminUserResponse])
async def list_all_admins(
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """List all admin users."""
    admins = list_admin_users(db)
    return admins


@router.get("/users/{admin_id}", response_model=AdminUserResponse)
async def get_admin_details(
    admin_id: int,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Get admin user details."""
    admin = get_admin_by_id(db, admin_id)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found",
        )
    return admin


@router.put("/users/{admin_id}", response_model=AdminUserResponse)
async def update_admin_details(
    admin_id: int,
    update_data: AdminUserUpdate,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Update admin user details."""
    admin = get_admin_by_id(db, admin_id)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found",
        )

    # Prevent self-deactivation
    if admin_id == current_admin.id and update_data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    admin = update_admin_user(db, admin, update_data)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="update_admin",
        resource_type="admin_user",
        resource_id=admin_id,
        details=f"Updated admin user: {admin.email}",
    )

    return admin


@router.delete("/users/{admin_id}")
async def deactivate_admin(
    admin_id: int,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Deactivate an admin user."""
    admin = get_admin_by_id(db, admin_id)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin user not found",
        )

    # Prevent self-deactivation
    if admin_id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate yourself",
        )

    deactivate_admin_user(db, admin)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="deactivate_admin",
        resource_type="admin_user",
        resource_id=admin_id,
        details=f"Deactivated admin user: {admin.email}",
    )

    return {"message": "Admin user deactivated"}


# ==================== Admin Rules Routes ====================

@router.post("/rules", response_model=AdminRuleResponse)
async def create_rule(
    rule_data: AdminRuleCreate,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Create a new admin rule."""
    # Check if rule name already exists
    existing = get_admin_rule_by_name(db, rule_data.rule_name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rule with this name already exists",
        )

    rule = create_admin_rule(db, rule_data)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="create_rule",
        resource_type="admin_rule",
        resource_id=rule.id,
        details=f"Created rule: {rule.rule_name}",
    )

    return rule


@router.get("/rules", response_model=list[AdminRuleResponse])
async def list_rules(
    rule_type: Optional[str] = None,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """List all admin rules."""
    rules = list_admin_rules(db, rule_type)
    return rules


@router.get("/rules/{rule_id}", response_model=AdminRuleResponse)
async def get_rule(
    rule_id: int,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Get admin rule details."""
    rule = get_admin_rule(db, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    return rule


@router.put("/rules/{rule_id}", response_model=AdminRuleResponse)
async def update_rule(
    rule_id: int,
    update_data: AdminRuleUpdate,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Update an admin rule."""
    rule = get_admin_rule(db, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    rule = update_admin_rule(db, rule, update_data)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="update_rule",
        resource_type="admin_rule",
        resource_id=rule_id,
        details=f"Updated rule: {rule.rule_name}",
    )

    return rule


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: int,
    current_admin: AdminUserResponse = Depends(require_permission("can_manage_admins")),
    db: Session = Depends(get_db)
):
    """Delete an admin rule."""
    rule = get_admin_rule(db, rule_id)
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )

    delete_admin_rule(db, rule)

    log_admin_action(
        db=db,
        admin_email=current_admin.email,
        action="delete_rule",
        resource_type="admin_rule",
        resource_id=rule_id,
        details=f"Deleted rule: {rule.rule_name}",
    )

    return {"message": "Rule deleted"}


# ==================== Audit Log Routes ====================

@router.get("/audit-logs")
async def get_audit_logs(
    limit: int = 100,
    current_admin: AdminUserResponse = Depends(require_permission("can_view_analytics")),
    db: Session = Depends(get_db)
):
    """Get admin action audit logs."""
    logs = get_admin_actions(db, limit=limit)
    return logs