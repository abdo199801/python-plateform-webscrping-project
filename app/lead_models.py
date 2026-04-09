from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func

from app.database import Base


class LeadRecord(Base):
    __tablename__ = "lead_records"
    __table_args__ = (
        UniqueConstraint("user_email", "business_id", name="uq_lead_records_user_business"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="new", index=True)
    tags = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    search_query = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    lead_status = Column(String(50), nullable=True)
    tag = Column(String(100), nullable=True)
    saved_only = Column(Boolean, nullable=False, default=False)
    alert_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
