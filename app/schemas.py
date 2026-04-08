from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ScrapeRequest(BaseModel):
    keyword: str = Field(min_length=1, max_length=255)
    email: EmailStr
    location: str = Field(default="", max_length=255)
    radius: str = Field(default="10000", max_length=50)
    max_results: int = Field(default=25, ge=1, le=500)
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
    created_at: datetime


class ScrapeRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword: str
    location: Optional[str] = None
    radius: str
    max_results: int
    headless: bool
    total_results: int
    status: str
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
