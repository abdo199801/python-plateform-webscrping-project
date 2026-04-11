from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.database import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String(255), nullable=False, index=True)
    location = Column(String(255), nullable=True, index=True)
    radius = Column(String(50), nullable=False, default="10000")
    max_results = Column(Integer, nullable=False, default=500)
    headless = Column(Boolean, nullable=False, default=False)
    processed_results = Column(Integer, nullable=False, default=0)
    total_results = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="completed", index=True)
    progress_message = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    businesses = relationship(
        "Business",
        back_populates="scrape_run",
        cascade="all, delete-orphan",
        order_by="Business.id.desc()",
    )


class Business(Base):
    __tablename__ = "businesses"

    id = Column(Integer, primary_key=True, index=True)
    scrape_run_id = Column(Integer, ForeignKey("scrape_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    address = Column(Text, nullable=True)
    phone = Column(String(100), nullable=True)
    website = Column(String(255), nullable=True)
    rating = Column(Float, nullable=False, default=0.0)
    reviews_count = Column(Integer, nullable=False, default=0)
    category = Column(String(255), nullable=True, index=True)
    business_hours = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    latitude = Column(String(50), nullable=True)
    longitude = Column(String(50), nullable=True)
    place_id = Column(String(255), nullable=True, index=True)
    source_url = Column(Text, nullable=True)
    scraped_date = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True, index=True)
    city = Column(String(100), nullable=True, index=True)
    street = Column(String(255), nullable=True)
    postal_code = Column(String(50), nullable=True)
    state_province = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    social_media = Column(Text, nullable=True)
    extraction_sources = Column(Text, nullable=True)
    ai_place_summary = Column(Text, nullable=True)
    ai_current_hours = Column(Text, nullable=True)
    ai_popular_times = Column(Text, nullable=True)
    ai_review_highlights = Column(Text, nullable=True)
    ai_grounding_sources = Column(Text, nullable=True)
    ai_enrichment_status = Column(String(50), nullable=True)
    ai_enriched_at = Column(DateTime(timezone=True), nullable=True)
    dedupe_status = Column(String(50), nullable=True, index=True)
    duplicate_of_business_id = Column(Integer, nullable=True, index=True)
    dedupe_confidence = Column(Float, nullable=True)
    dedupe_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scrape_run = relationship("ScrapeRun", back_populates="businesses")
