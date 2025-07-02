"""Job queue management and worker coordination."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
import uuid

from ..core import WebScraper
from ..models.schemas import JobStatus, JobStatusResponse, ScrapeRequest, ScrapeResult

logger = logging.getLogger(__name__)


class JobManager:
    """Manages job queue, workers, and resource limits."""
    
    def __init__(
        self,
        max_concurrent_jobs: int = 5,
        max_playwright_instances: int = 3,
        max_queue_size: int = 100,
        output_dir: str = "./scrapes_out",
    ):
        """
        Initialize the job manager.
        
        Args:
            max_concurrent_jobs: Maximum number of concurrent scraping jobs
            max_playwright_instances: Maximum Playwright browser instances
            max_queue_size: Maximum queue size before rejecting new jobs
            output_dir: Default output directory for results
        """
        self.max_concurrent_jobs = max_concurrent_jobs
        self.max_playwright_instances = max_playwright_instances
        self.max_queue_size = max_queue_size
        self.output_dir = Path(output_dir)
        
        # Create output directory
        self.output_dir.mkdir(exist_ok=True)
        
        # Job storage and tracking
        self.jobs: Dict[str, JobStatusResponse] = {}
        self.job_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        
        # Resource tracking
        self.active_jobs: Set[str] = set()
        self.active_playwright_instances = 0
        self._playwright_semaphore = asyncio.Semaphore(max_playwright_instances)
        self._job_semaphore = asyncio.Semaphore(max_concurrent_jobs)
        
        # Worker management
        self._workers: List[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._running = False
        
        logger.info(
            f"JobManager initialized: max_jobs={max_concurrent_jobs}, "
            f"max_playwright={max_playwright_instances}, queue_size={max_queue_size}"
        )
    
    async def start_workers(self, num_workers: Optional[int] = None) -> None:
        """Start background worker tasks."""
        if self._running:
            logger.warning("Workers already running")
            return
        
        num_workers = num_workers or min(self.max_concurrent_jobs, 3)
        self._running = True
        
        logger.info(f"Starting {num_workers} worker tasks")
        
        for i in range(num_workers):
            worker_task = asyncio.create_task(
                self._worker_loop(f"worker-{i}"),
                name=f"scraper-worker-{i}"
            )
            self._workers.append(worker_task)
    
    async def stop_workers(self) -> None:
        """Stop all worker tasks gracefully."""
        if not self._running:
            return
        
        logger.info("Stopping workers...")
        self._running = False
        self._shutdown_event.set()
        
        # Cancel all workers
        for worker in self._workers:
            worker.cancel()
        
        # Wait for workers to finish
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        
        self._workers.clear()
        logger.info("All workers stopped")
    
    async def submit_job(self, request: ScrapeRequest) -> str:
        """
        Submit a new scraping job.
        
        Args:
            request: Scrape request parameters
            
        Returns:
            Job ID for tracking
            
        Raises:
            asyncio.QueueFull: If queue is at capacity
        """
        job_id = self._generate_job_id()
        
        # Create job metadata
        job_info = JobStatusResponse(
            job_id=job_id,
            status=JobStatus.QUEUED,
            created_at=datetime.utcnow(),
            source_url=request.target if request.input_type.value == "url" else None,
            progress="Waiting in queue"
        )
        
        # Store job metadata
        self.jobs[job_id] = job_info
        
        # Add to queue (this can raise QueueFull)
        await self.job_queue.put((job_id, request))
        
        logger.info(f"Job {job_id} submitted to queue")
        return job_id
    
    def get_job_status(self, job_id: str) -> Optional[JobStatusResponse]:
        """Get current status of a job."""
        return self.jobs.get(job_id)
    
    def list_jobs(self, limit: int = 50) -> List[JobStatusResponse]:
        """List recent jobs, most recent first."""
        sorted_jobs = sorted(
            self.jobs.values(),
            key=lambda j: j.created_at,
            reverse=True
        )
        return sorted_jobs[:limit]
    
    async def get_job_result(self, job_id: str) -> Optional[Path]:
        """Get the result file path for a completed job."""
        job = self.jobs.get(job_id)
        if not job or job.status != JobStatus.COMPLETED:
            return None
        
        result_file = self.output_dir / f"{job_id}.json"
        return result_file if result_file.exists() else None
    
    def get_queue_stats(self) -> Dict[str, int]:
        """Get current queue and resource statistics."""
        return {
            "queued_jobs": self.job_queue.qsize(),
            "active_jobs": len(self.active_jobs),
            "total_jobs": len(self.jobs),
            "active_playwright_instances": self.active_playwright_instances,
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_playwright_instances": self.max_playwright_instances,
        }
    
    async def _worker_loop(self, worker_name: str) -> None:
        """Main worker loop that processes jobs from the queue."""
        logger.info(f"{worker_name} started")
        
        try:
            while self._running and not self._shutdown_event.is_set():
                try:
                    # Wait for a job with timeout to allow shutdown checks
                    job_id, request = await asyncio.wait_for(
                        self.job_queue.get(), timeout=1.0
                    )
                    
                    # Process the job
                    await self._process_job(job_id, request, worker_name)
                    
                    # Mark task as done
                    self.job_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # Normal timeout, continue loop
                    continue
                    
                except Exception as e:
                    logger.error(f"{worker_name} error: {e}")
                    
        except asyncio.CancelledError:
            logger.info(f"{worker_name} cancelled")
        except Exception as e:
            logger.error(f"{worker_name} unexpected error: {e}")
        finally:
            logger.info(f"{worker_name} stopped")
    
    async def _process_job(self, job_id: str, request: ScrapeRequest, worker_name: str) -> None:
        """Process a single scraping job."""
        job = self.jobs.get(job_id)
        if not job:
            logger.error(f"Job {job_id} not found in metadata")
            return
        
        logger.info(f"{worker_name} processing job {job_id}")
        
        # Acquire job semaphore
        async with self._job_semaphore:
            try:
                # Update job status
                job.status = JobStatus.RUNNING
                job.started_at = datetime.utcnow()
                job.progress = "Processing..."
                self.active_jobs.add(job_id)
                
                # Determine if we need Playwright
                needs_playwright = request.force_dynamic
                
                # Acquire Playwright semaphore if needed
                if needs_playwright:
                    async with self._playwright_semaphore:
                        self.active_playwright_instances += 1
                        try:
                            result = await self._execute_scrape(job_id, request)
                        finally:
                            self.active_playwright_instances -= 1
                else:
                    result = await self._execute_scrape(job_id, request)
                
                # Save result
                await self._save_result(job_id, result, request.output_dir)
                
                # Update job status
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()
                job.progress = f"Completed with {len(result.data)} items"
                
                logger.info(f"Job {job_id} completed successfully")
                
            except Exception as e:
                logger.error(f"Job {job_id} failed: {e}")
                
                # Update job status
                job.status = JobStatus.FAILED
                job.completed_at = datetime.utcnow()
                job.progress = f"Failed: {str(e)}"
                
            finally:
                self.active_jobs.discard(job_id)
    
    async def _execute_scrape(self, job_id: str, request: ScrapeRequest) -> ScrapeResult:
        """Execute the actual scraping operation."""
        # Configure scraper
        scraper_config = {
            "timeout": 30,
            "max_retries": 3,
            "request_delay": 1.0,
        }
        
        async with WebScraper(**scraper_config) as scraper:
            if request.input_type.value == "url":
                # Single URL scraping
                result = await scraper.scrape_url(
                    url=request.target,
                    force_dynamic=request.force_dynamic,
                    custom_selectors=request.custom_selectors,
                )
                # Override job_id to match our tracking
                result.job_id = job_id
                return result
                
            elif request.input_type.value == "file":
                # Multi-URL scraping from file
                return await self._scrape_from_file(
                    job_id, request.target, scraper, request
                )
            
            else:
                raise ValueError(f"Unsupported input type: {request.input_type}")
    
    async def _scrape_from_file(
        self, 
        job_id: str, 
        file_path: str, 
        scraper: WebScraper, 
        request: ScrapeRequest
    ) -> ScrapeResult:
        """Scrape multiple URLs from a file."""
        import json
        import csv
        
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"Input file not found: {file_path}")
        
        # Read URLs from file
        urls = []
        if file_path.endswith('.json'):
            with open(file_path_obj, 'r') as f:
                data = json.load(f)
                urls = [item.get('url') for item in data if item.get('url')]
        elif file_path.endswith('.csv'):
            with open(file_path_obj, 'r') as f:
                reader = csv.DictReader(f)
                urls = [row.get('url') for row in reader if row.get('url')]
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
        
        if not urls:
            raise ValueError(f"No URLs found in file: {file_path}")
        
        logger.info(f"Job {job_id}: Scraping {len(urls)} URLs from file")
        
        # Scrape all URLs
        all_data = []
        for i, url in enumerate(urls):
            try:
                # Update progress
                job = self.jobs.get(job_id)
                if job:
                    job.progress = f"Processing URL {i+1}/{len(urls)}: {url}"
                
                result = await scraper.scrape_url(
                    url=url,
                    force_dynamic=request.force_dynamic,
                    custom_selectors=request.custom_selectors,
                )
                all_data.extend(result.data)
                
            except Exception as e:
                logger.warning(f"Job {job_id}: Failed to scrape {url}: {e}")
                continue
        
        # Create combined result
        return ScrapeResult(
            job_id=job_id,
            source_url=f"file://{file_path}",
            scrape_timestamp=datetime.utcnow(),
            status=JobStatus.COMPLETED,
            extraction_method="static",  # Will be updated based on actual methods used
            data=all_data,
            metadata={
                "urls_processed": len(urls),
                "data_items_count": len(all_data),
                "source_file": file_path,
            }
        )
    
    async def _save_result(self, job_id: str, result: ScrapeResult, output_dir: Optional[str]) -> None:
        """Save scraping result to JSON file."""
        if output_dir:
            save_dir = Path(output_dir)
        else:
            save_dir = self.output_dir
        
        save_dir.mkdir(exist_ok=True)
        output_file = save_dir / f"{job_id}.json"
        
        # Convert to dict for JSON serialization
        result_dict = result.model_dump(mode='json')
        
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Job {job_id}: Result saved to {output_file}")
    
    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        return uuid.uuid4().hex[:8]
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_workers()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop_workers() 