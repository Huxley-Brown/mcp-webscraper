"""Pydantic models for MCP WebScraper data structures."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    """Job execution status."""
    QUEUED = "queued"
    RUNNING = "running" 
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExtractionMethod(str, Enum):
    """Method used for content extraction."""
    STATIC = "static"  # HTTPX + BeautifulSoup
    DYNAMIC = "dynamic"  # Playwright + BeautifulSoup


class InputType(str, Enum):
    """Type of input for scraping jobs."""
    URL = "url"
    FILE = "file"


class ScrapedData(BaseModel):
    """Individual scraped data item."""
    # Flexible structure to accommodate different sites
    text: Optional[str] = Field(None, description="Main text content")
    title: Optional[str] = Field(None, description="Title or heading")
    url: Optional[HttpUrl] = Field(None, description="Associated URL")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional site-specific data")
    
    class Config:
        """Pydantic configuration."""
        extra = "allow"  # Allow additional fields for site-specific data


class ScrapeResult(BaseModel):
    """Complete scraping result schema."""
    job_id: str = Field(..., description="Unique job identifier")
    source_url: HttpUrl = Field(..., description="Original URL scraped")
    scrape_timestamp: datetime = Field(..., description="When scraping was performed")
    status: JobStatus = Field(..., description="Final job status")
    extraction_method: ExtractionMethod = Field(..., description="Method used for extraction")
    data: List[ScrapedData] = Field(default_factory=list, description="Extracted data items")
    error_message: Optional[str] = Field(None, description="Error details if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Job-level metadata")


class ScrapeRequest(BaseModel):
    """API request to start a scraping job."""
    input_type: InputType = Field(..., description="Type of input (url or file)")
    target: str = Field(..., description="URL or file path to scrape")
    output_dir: Optional[str] = Field("./scrapes_out", description="Output directory for results")
    force_dynamic: Optional[bool] = Field(False, description="Force use of Playwright for JS rendering")
    custom_selectors: Optional[Dict[str, str]] = Field(None, description="CSS selectors for extraction")


class ScrapeResponse(BaseModel):
    """API response after job submission."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Initial job status")
    message: str = Field(..., description="Human-readable status message")


class JobStatusResponse(BaseModel):
    """Job status query response."""
    job_id: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Current job status")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    source_url: Optional[str] = Field(None, description="Target URL being scraped")
    progress: Optional[str] = Field(None, description="Human-readable progress info")


class JobListResponse(BaseModel):
    """Response for listing recent jobs."""
    jobs: List[JobStatusResponse] = Field(..., description="List of recent jobs")
    total: int = Field(..., description="Total number of jobs")


class ErrorResponse(BaseModel):
    """Standardized error response for API."""
    error: str = Field(..., description="Error type/code")
    message: str = Field(..., description="Human-readable error message") 
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")
    job_id: Optional[str] = Field(None, description="Associated job ID if applicable") 