from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ScrapeRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=255)
    email: EmailStr
    location: str = Field(default="", max_length=255)
    radius: str = Field(default="10000", max_length=50)
    max_results: int = Field(default=1000, ge=1, le=1000)
    headless: bool = False
    save_files: bool = False


class BusinessResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scrape_run_id: int
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    rating: float
    reviews_count: int
    category: Optional[str] = None
    business_hours: Optional[str] = None
    description: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    place_id: Optional[str] = None
    source_url: Optional[str] = None
    scraped_date: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    postal_code: Optional[str] = None
    state_province: Optional[str] = None
    email: Optional[str] = None
    social_media: Optional[str] = None
    extraction_sources: Optional[str] = None
    created_at: datetime
    lead_id: Optional[int] = None
    lead_status: Optional[str] = None
    lead_tags: List[str] = Field(default_factory=list)
    lead_notes: str = ""
    lead_updated_at: Optional[datetime] = None
    lead_archived: bool = False


class ScrapeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    location: Optional[str] = None
    radius: str
    max_results: int
    headless: bool
    processed_results: int = 0
    total_results: int
    status: str
    progress_message: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    businesses: List[BusinessResponse] = []


class ScrapeSummaryResponse(BaseModel):
    run: ScrapeRunResponse
    results: List[BusinessResponse]
    remaining_credits: int
    billing_mode: str


class PaginationMetaResponse(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PaginatedScrapeRunsResponse(BaseModel):
    items: List[ScrapeRunResponse]
    pagination: PaginationMetaResponse


class PaginatedBusinessesResponse(BaseModel):
    items: List[BusinessResponse]
    pagination: PaginationMetaResponse


class InsightBucket(BaseModel):
    label: str
    count: int


class InsightRecentRun(BaseModel):
    id: int
    keyword: str
    location: Optional[str] = None
    total_results: int
    status: str
    created_at: datetime


class InsightOverviewResponse(BaseModel):
    total_runs: int
    total_businesses: int
    success_rate: float
    average_rating: float
    contactable_businesses: int
    top_categories: List[InsightBucket]
    top_cities: List[InsightBucket]
    recent_runs: List[InsightRecentRun]


class LeadRecordUpsertRequest(BaseModel):
    email: EmailStr
    business_id: int
    status: str = Field(default="new", min_length=1, max_length=50)
    tags: List[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)
    is_archived: bool = False


class LeadRecordResponse(BaseModel):
    id: int
    user_email: EmailStr
    business_id: int
    status: str
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class LeadSummaryResponse(BaseModel):
    total: int
    active: int
    archived: int
    counts: dict[str, int]


class SavedSearchCreateRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    search_query: Optional[str] = Field(default=None, max_length=255)
    city: Optional[str] = Field(default=None, max_length=100)
    country: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    lead_status: Optional[str] = Field(default=None, max_length=50)
    tag: Optional[str] = Field(default=None, max_length=100)
    saved_only: bool = False
    alert_enabled: bool = True


class SavedSearchResponse(BaseModel):
    id: int
    user_email: EmailStr
    name: str
    search_query: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    category: Optional[str] = None
    lead_status: Optional[str] = None
    tag: Optional[str] = None
    saved_only: bool
    alert_enabled: bool
    created_at: datetime
