"""MCP Server implementation for WebScraper.

Exposes web scraping functionality as MCP tools for AI agent integration.
Uses stdio transport for Cursor integration.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from mcp_webscraper.config import get_settings
from mcp_webscraper.jobs import JobManager
from mcp_webscraper.models.schemas import ScrapeRequest, InputType, JobStatus, ScrapeResult
from mcp_webscraper.core import WebScraper

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create MCP server
mcp = FastMCP("WebScraper")


class ScrapeUrlResult(BaseModel):
    """Structured output for scrape_url tool."""
    job_id: str = Field(description="Unique job identifier")
    status: str = Field(description="Job completion status")
    url: str = Field(description="URL that was scraped")
    data_count: int = Field(description="Number of data items extracted")
    extraction_method: str = Field(description="Method used (static/dynamic)")
    processing_time: float = Field(description="Processing time in seconds")
    data: List[Dict[str, Any]] = Field(description="Extracted data items")


class BatchScrapeResult(BaseModel):
    """Structured output for scrape_batch tool."""
    job_id: str = Field(description="Unique job identifier") 
    status: str = Field(description="Job completion status")
    total_urls: int = Field(description="Total number of URLs processed")
    successful_urls: int = Field(description="Number of successfully scraped URLs")
    total_items: int = Field(description="Total data items extracted")
    processing_time: float = Field(description="Total processing time in seconds")
    results: List[Dict[str, Any]] = Field(description="Combined extracted data")


class ValidationResult(BaseModel):
    """Structured output for validate_selectors tool."""
    url: str = Field(description="URL that was tested")
    selectors_tested: int = Field(description="Number of selectors tested")
    valid_selectors: List[str] = Field(description="Selectors that found elements")
    invalid_selectors: List[str] = Field(description="Selectors that found no elements")
    sample_matches: Dict[str, List[str]] = Field(description="Sample text from valid selectors")


# Global job manager for MCP tools
_job_manager: Optional[JobManager] = None


async def get_job_manager() -> JobManager:
    """Get or create the global job manager."""
    global _job_manager
    if _job_manager is None:
        settings = get_settings()
        _job_manager = JobManager(**settings.get_job_manager_config())
        await _job_manager.start_workers()
    return _job_manager


@mcp.tool()
async def scrape_url(
    url: str,
    custom_selectors: Optional[Dict[str, str]] = None,
    force_dynamic: bool = False,
) -> ScrapeUrlResult:
    """
    Scrape a single URL and extract structured data.
    
    Args:
        url: The URL to scrape
        custom_selectors: Optional CSS selectors for custom extraction (e.g., {"title": "h1", "price": ".price"})
        force_dynamic: Force use of JavaScript rendering (Playwright) instead of static scraping
        
    Returns:
        Structured scraping results with extracted data
    """
    import time
    start_time = time.time()
    
    logger.info(f"MCP tool scrape_url called: {url}")
    
    # Create scrape request
    request = ScrapeRequest(
        input_type=InputType.URL,
        target=url,
        custom_selectors=custom_selectors,
        force_dynamic=force_dynamic,
    )
    
    # Get job manager and submit job
    job_manager = await get_job_manager()
    job_id = await job_manager.submit_job(request)
    
    # Wait for completion (polling)
    while True:
        status = job_manager.get_job_status(job_id)
        if status and status.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            break
        await asyncio.sleep(0.5)
    
    processing_time = time.time() - start_time
    
    if status.status == JobStatus.FAILED:
        raise RuntimeError(f"Scraping failed: {status.progress}")
    
    # Get result file
    result_file = await job_manager.get_job_result(job_id)
    if not result_file:
        raise RuntimeError("Result file not found")
    
    # Load and return structured result
    with open(result_file, 'r') as f:
        result_data = json.load(f)
    
    return ScrapeUrlResult(
        job_id=job_id,
        status=status.status.value,
        url=url,
        data_count=len(result_data.get('data', [])),
        extraction_method=result_data.get('extraction_method', 'unknown'),
        processing_time=processing_time,
        data=result_data.get('data', [])
    )


@mcp.tool()
async def scrape_batch(
    urls: List[str],
    custom_selectors: Optional[Dict[str, str]] = None,
    force_dynamic: bool = False,
) -> BatchScrapeResult:
    """
    Scrape multiple URLs and return combined results.
    
    Args:
        urls: List of URLs to scrape
        custom_selectors: Optional CSS selectors for custom extraction
        force_dynamic: Force use of JavaScript rendering for all URLs
        
    Returns:
        Combined scraping results from all URLs
    """
    import time
    import tempfile
    import os
    
    start_time = time.time()
    
    logger.info(f"MCP tool scrape_batch called with {len(urls)} URLs")
    
    # Create temporary file with URLs
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"urls": [{"url": url} for url in urls]}, f)
        temp_file = f.name
    
    try:
        # Create scrape request
        request = ScrapeRequest(
            input_type=InputType.FILE,
            target=temp_file,
            custom_selectors=custom_selectors,
            force_dynamic=force_dynamic,
        )
        
        # Get job manager and submit job
        job_manager = await get_job_manager()
        job_id = await job_manager.submit_job(request)
        
        # Wait for completion
        while True:
            status = job_manager.get_job_status(job_id)
            if status and status.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            await asyncio.sleep(0.5)
        
        processing_time = time.time() - start_time
        
        if status.status == JobStatus.FAILED:
            raise RuntimeError(f"Batch scraping failed: {status.progress}")
        
        # Get result file
        result_file = await job_manager.get_job_result(job_id)
        if not result_file:
            raise RuntimeError("Result file not found")
        
        # Load and return structured result
        with open(result_file, 'r') as f:
            result_data = json.load(f)
        
        return BatchScrapeResult(
            job_id=job_id,
            status=status.status.value,
            total_urls=len(urls),
            successful_urls=result_data.get('metadata', {}).get('urls_processed', 0),
            total_items=len(result_data.get('data', [])),
            processing_time=processing_time,
            results=result_data.get('data', [])
        )
        
    finally:
        # Clean up temporary file
        if os.path.exists(temp_file):
            os.unlink(temp_file)


@mcp.tool()
async def validate_selectors(
    url: str,
    selectors: Dict[str, str],
) -> ValidationResult:
    """
    Test CSS selectors against a URL to validate they find elements.
    
    Args:
        url: The URL to test selectors against
        selectors: Dictionary of selector names to CSS selector strings
        
    Returns:
        Validation results showing which selectors work and sample matches
    """
    logger.info(f"MCP tool validate_selectors called: {url}")
    
    # Create scraper with minimal config for testing
    settings = get_settings()
    scraper_config = settings.get_scraper_config()
    
    async with WebScraper(**scraper_config) as scraper:
        # Get page content
        result = await scraper.scrape_url(url, custom_selectors=selectors)
        
        valid_selectors = []
        invalid_selectors = []
        sample_matches = {}
        
        # Check which selectors found data
        for data_item in result.data:
            for key, value in data_item.metadata.items():
                if key in selectors and value:
                    if key not in valid_selectors:
                        valid_selectors.append(key)
                        # Store sample match
                        sample_text = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        if key not in sample_matches:
                            sample_matches[key] = []
                        sample_matches[key].append(sample_text)
        
        # Find selectors that didn't match
        for selector_name in selectors.keys():
            if selector_name not in valid_selectors:
                invalid_selectors.append(selector_name)
        
        return ValidationResult(
            url=url,
            selectors_tested=len(selectors),
            valid_selectors=valid_selectors,
            invalid_selectors=invalid_selectors,
            sample_matches=sample_matches
        )


@mcp.resource("config://webscraper")
def get_webscraper_config() -> str:
    """Get the current WebScraper configuration."""
    settings = get_settings()
    config = {
        "server": settings.get_server_config(),
        "scraper": settings.get_scraper_config(),
        "job_manager": settings.get_job_manager_config(),
    }
    return json.dumps(config, indent=2)


@mcp.resource("status://jobs")
def get_jobs_status() -> str:
    """Get current job queue and processing status."""
    if _job_manager:
        stats = _job_manager.get_queue_stats()
        recent_jobs = _job_manager.list_jobs(limit=10)
        
        return json.dumps({
            "queue_stats": stats,
            "recent_jobs": [
                {
                    "job_id": job.job_id,
                    "status": job.status.value,
                    "created_at": job.created_at.isoformat(),
                    "source_url": job.source_url,
                    "progress": job.progress,
                }
                for job in recent_jobs
            ]
        }, indent=2)
    
    return json.dumps({"status": "Job manager not initialized"}, indent=2)


# Lifecycle management
async def cleanup():
    """Clean up resources on shutdown."""
    global _job_manager
    if _job_manager:
        await _job_manager.stop_workers()
        _job_manager = None


if __name__ == "__main__":
    # Run the MCP server with stdio transport
    mcp.run() 