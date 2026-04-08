#!/usr/bin/env python3
"""
Admin User Creation Script for MapsScraper Pro

This script creates the initial admin user for the admin dashboard.
Run this script once to set up your admin account.

Usage:
    python create_admin.py

Or with custom credentials:
    python create_admin.py --email admin@example.com --password yourpassword

Default credentials (if not provided):
    Email: admin@admin.com
    Password: admin123
"""

import argparse
import sys
import os

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.database import Base, engine, get_db
from app.admin_models import AdminUser
from app.auth_service import hash_password, get_admin_by_email


def create_initial_admin(
    email: str = "admin@admin.com",
    password: str = "admin123",
    full_name: str = "Super Admin",
    is_superuser: bool = True
):
    """Create the initial admin user."""
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Get database session
    db = next(get_db())
    
    try:
        # Check if admin already exists
        existing_admin = get_admin_by_email(db, email)
        if existing_admin:
            print(f"Admin user '{email}' already exists!")
            print(f"  ID: {existing_admin.id}")
            print(f"  Superuser: {existing_admin.is_superuser}")
            print(f"  Active: {existing_admin.is_active}")
            return existing_admin
        
        # Create new admin user
        hashed_password = hash_password(password)
        admin = AdminUser(
            email=email,
            hashed_password=hashed_password,
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
        db.refresh(admin)
        
        print("=" * 50)
        print("✅ Admin user created successfully!")
        print("=" * 50)
        print(f"  Email: {email}")
        print(f"  Password: {password}")
        print(f"  Full Name: {full_name}")
        print(f"  Superuser: {is_superuser}")
        print("=" * 50)
        print(f"\n🌐 Admin Dashboard URL: http://localhost:8000/admin")
        print("\n⚠️  IMPORTANT: Please change the default password after first login!")
        
        return admin
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creating admin user: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Create admin user for MapsScraper Pro")
    parser.add_argument("--email", default="admin@admin.com", help="Admin email address")
    parser.add_argument("--password", default="admin123", help="Admin password")
    parser.add_argument("--name", default="Super Admin", help="Admin full name")
    parser.add_argument("--superuser", action="store_true", default=True, help="Make admin a superuser")
    
    args = parser.parse_args()
    
    print("🔧 Setting up admin user for MapsScraper Pro...")
    print(f"   Database: {os.getenv('DATABASE_URL', 'sqlite:///./googlemaps.db')}")
    print()
    
    create_initial_admin(
        email=args.email,
        password=args.password,
        full_name=args.name,
        is_superuser=args.superuser
    )


if __name__ == "__main__":
    main()