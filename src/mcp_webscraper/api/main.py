"""FastAPI main application with MCP-compatible REST endpoints."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from ..jobs import JobManager
from ..models.schemas import (
    ErrorResponse,
    JobListResponse,
    JobStatus,
    JobStatusResponse,
    ScrapeRequest,
    ScrapeResponse,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global job manager instance
job_manager: JobManager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    global job_manager
    
    # Startup
    logger.info("Starting MCP WebScraper API...")
    
    # Initialize job manager with configurable limits
    job_manager = JobManager(
        max_concurrent_jobs=5,
        max_playwright_instances=3,
        max_queue_size=100,
        output_dir="./scrapes_out"
    )
    
    # Start background workers
    await job_manager.start_workers()
    
    logger.info("MCP WebScraper API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down MCP WebScraper API...")
    
    if job_manager:
        await job_manager.stop_workers()
    
    logger.info("MCP WebScraper API shut down complete")


# Create FastAPI app
app = FastAPI(
    title="MCP WebScraper",
    description="Local web scraping service with dynamic page support for AI agents",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint - API information."""
    return {
        "name": "MCP WebScraper",
        "version": "0.1.0",
        "description": "Local web scraping service with dynamic page support",
        "docs": "/docs",
        "status": "running"
    }


@app.post("/scrape", response_model=ScrapeResponse)
async def submit_scrape_job(request: ScrapeRequest):
    """
    Submit a new web scraping job.
    
    The job will be processed asynchronously in the background.
    Use the returned job_id to check status and retrieve results.
    """
    try:
        # Validate input
        if request.input_type.value == "file":
            file_path = Path(request.target)
            if not file_path.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Input file not found: {request.target}"
                )
            
            # Security check - prevent directory traversal
            try:
                file_path.resolve().relative_to(Path.cwd().resolve())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="File path outside project directory not allowed"
                )
        
        # Submit job to queue
        job_id = await job_manager.submit_job(request)
        
        return ScrapeResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            message=f"Job {job_id} submitted successfully and queued for processing"
        )
        
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get the current status of a scraping job.
    
    Returns detailed information about job progress, timestamps, and current state.
    """
    job = job_manager.get_job_status(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    return job


@app.get("/results/{job_id}")
async def get_job_results(job_id: str):
    """
    Download the results of a completed scraping job.
    
    Returns the JSON result file if the job is completed successfully.
    """
    # Check if job exists and is completed
    job = job_manager.get_job_status(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    if job.status != JobStatus.COMPLETED:
        return JSONResponse(
            status_code=400,
            content={
                "error": "job_not_completed",
                "message": f"Job {job_id} is not completed (status: {job.status.value})",
                "current_status": job.status.value,
                "progress": job.progress
            }
        )
    
    # Get result file
    result_file = await job_manager.get_job_result(job_id)
    
    if not result_file or not result_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Result file for job {job_id} not found"
        )
    
    return FileResponse(
        path=result_file,
        media_type="application/json",
        filename=f"scrape_result_{job_id}.json"
    )


@app.get("/jobs", response_model=JobListResponse)
async def list_jobs(limit: int = 50):
    """
    List recent scraping jobs with their current status.
    
    Returns jobs ordered by creation time (most recent first).
    """
    if limit > 100:
        limit = 100  # Cap the limit for performance
    
    jobs = job_manager.list_jobs(limit=limit)
    
    return JobListResponse(
        jobs=jobs,
        total=len(job_manager.jobs)
    )


@app.get("/stats", response_model=Dict[str, Any])
async def get_queue_stats():
    """
    Get current queue and resource statistics.
    
    Useful for monitoring system load and capacity.
    """
    return job_manager.get_queue_stats()


@app.get("/stats/detailed")
async def get_detailed_stats():
    """
    Get detailed scraping statistics including error rates and anti-scraping metrics.
    
    Provides comprehensive insight into system performance and error patterns.
    """
    basic_stats = job_manager.get_queue_stats()
    
    # Try to get scraping stats from a sample worker
    # Note: This is a simplified approach - in production you might want
    # to aggregate stats across all workers
    detailed_stats = {
        "queue_stats": basic_stats,
        "scraping_stats": {},  # Would be populated with actual worker stats
        "error_patterns": {},  # Error analysis
        "timestamp": str(datetime.utcnow()),
    }
    
    return detailed_stats


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancel a queued or running job.
    
    Note: Jobs that are already processing may not stop immediately.
    """
    job = job_manager.get_job_status(job_id)
    
    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} not found"
        )
    
    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        return JSONResponse(
            status_code=400,
            content={
                "error": "job_not_cancellable",
                "message": f"Job {job_id} cannot be cancelled (status: {job.status.value})",
                "current_status": job.status.value
            }
        )
    
    # Update job status
    job.status = JobStatus.CANCELLED
    job.progress = "Cancelled by user"
    
    return {
        "message": f"Job {job_id} has been cancelled",
        "job_id": job_id,
        "status": job.status.value
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    
    Returns system status and basic metrics.
    """
    stats = job_manager.get_queue_stats()
    
    # Determine health status
    is_healthy = (
        stats["active_jobs"] < stats["max_concurrent_jobs"] and
        stats["queued_jobs"] < 50  # Alert if queue is getting full
    )
    
    return {
        "status": "healthy" if is_healthy else "degraded",
        "timestamp": str(datetime.utcnow()),
        "queue_size": stats["queued_jobs"],
        "active_jobs": stats["active_jobs"],
        "total_jobs": stats["total_jobs"],
        "uptime": "running"  # Could track actual uptime
    }


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": "The requested resource was not found",
            "path": str(request.url.path)
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Custom 500 handler."""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An internal server error occurred",
            "details": "Check server logs for more information"
        }
    )


# Import datetime for health check
from datetime import datetime 