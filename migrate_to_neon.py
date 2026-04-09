#!/usr/bin/env python3
import argparse
import os
from typing import Iterable

from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.admin_models import AdminAction, AdminRule, AdminUser
from app.database import Base
from app.models import Business, ScrapeRun
from app.payment_models import Payment, PlatformUser, ScrapeCredit, Subscription


load_dotenv()


SOURCE_MODELS = [
    ScrapeRun,
    Business,
    PlatformUser,
    Payment,
    ScrapeCredit,
    Subscription,
    AdminUser,
    AdminAction,
    AdminRule,
]

DELETE_ORDER = [
    AdminAction,
    AdminRule,
    AdminUser,
    ScrapeCredit,
    Payment,
    Subscription,
    PlatformUser,
    Business,
    ScrapeRun,
]


def build_engine(database_url: str):
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    return create_engine(database_url, connect_args=connect_args)


def get_database_urls(args: argparse.Namespace) -> tuple[str, str]:
    source_url = args.source_url or os.getenv("SOURCE_DATABASE_URL") or "sqlite:///./googlemaps.db"
    target_url = args.target_url or os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL")

    if not target_url:
        raise ValueError("Target database URL is required. Set NEON_DATABASE_URL or pass --target-url.")

    return source_url, target_url


def model_to_mapping(instance, columns: Iterable) -> dict:
    return {column.name: getattr(instance, column.name) for column in columns}


def count_rows(session: Session, model) -> int:
    return int(session.execute(select(model).count()).scalar_one())


def truncate_target(session: Session) -> None:
    for model in DELETE_ORDER:
        session.execute(delete(model))
    session.commit()


def copy_table(source_session: Session, target_session: Session, model) -> int:
    rows = source_session.execute(select(model)).scalars().all()
    if not rows:
        return 0

    mappings = [model_to_mapping(row, model.__table__.columns) for row in rows]
    target_session.bulk_insert_mappings(model, mappings)
    target_session.commit()
    return len(mappings)


def verify_connection(session: Session, label: str) -> None:
    session.execute(text("SELECT 1"))
    print(f"{label} connection OK")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate MapsScraper data from SQLite to Neon/PostgreSQL")
    parser.add_argument("--source-url", help="Source database URL. Defaults to SOURCE_DATABASE_URL or local SQLite file.")
    parser.add_argument("--target-url", help="Target Neon/PostgreSQL database URL. Defaults to NEON_DATABASE_URL or DATABASE_URL.")
    parser.add_argument("--truncate-target", action="store_true", help="Delete target data before copying rows.")
    parser.add_argument("--allow-nonempty-target", action="store_true", help="Allow migration into a target that already has rows.")
    args = parser.parse_args()

    try:
        source_url, target_url = get_database_urls(args)
    except ValueError as exc:
        print(str(exc))
        return 1

    print(f"Source DB: {source_url}")
    print(f"Target DB: {target_url}")

    source_engine = build_engine(source_url)
    target_engine = build_engine(target_url)
    SourceSession = sessionmaker(bind=source_engine)
    TargetSession = sessionmaker(bind=target_engine)

    Base.metadata.create_all(bind=target_engine)

    source_session = SourceSession()
    target_session = TargetSession()
    try:
        verify_connection(source_session, "Source")
        verify_connection(target_session, "Target")

        source_scrapes = source_session.query(ScrapeRun).count()
        source_businesses = source_session.query(Business).count()
        print(f"Source rows: {source_scrapes} scrape runs, {source_businesses} businesses")

        target_has_data = any(target_session.query(model).first() is not None for model in SOURCE_MODELS)
        if target_has_data and not args.allow_nonempty_target and not args.truncate_target:
            print("Target database already contains data. Re-run with --truncate-target or --allow-nonempty-target.")
            return 1

        if args.truncate_target:
            print("Truncating target tables before migration...")
            truncate_target(target_session)

        print("Starting migration...")
        for model in SOURCE_MODELS:
            copied = copy_table(source_session, target_session, model)
            print(f"Copied {copied} rows into {model.__tablename__}")

        print("Migration completed successfully.")
        return 0
    finally:
        source_session.close()
        target_session.close()


if __name__ == "__main__":
    raise SystemExit(main())