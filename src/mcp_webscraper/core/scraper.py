"""Core web scraping functionality with static and dynamic content support."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from ..models.schemas import ExtractionMethod, ScrapedData, ScrapeResult
from .detector import JavaScriptDetector

logger = logging.getLogger(__name__)


class WebScraper:
    """Main web scraping class with static and dynamic content support."""
    
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: Optional[str] = None,
        respect_robots: bool = True,
        request_delay: float = 1.0,
    ):
        """
        Initialize the web scraper.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            user_agent: Custom user agent string
            respect_robots: Whether to check robots.txt
            request_delay: Delay between requests in seconds
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.respect_robots = respect_robots
        
        # Default user agent
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        # Initialize components
        self.js_detector = JavaScriptDetector()
        self._browser: Optional[Browser] = None
        
        # Configure HTTPX client
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )
    
    async def scrape_url(
        self,
        url: str,
        force_dynamic: bool = False,
        custom_selectors: Optional[Dict[str, str]] = None,
    ) -> ScrapeResult:
        """
        Scrape a single URL with automatic static/dynamic detection.
        
        Args:
            url: URL to scrape
            force_dynamic: Force use of Playwright regardless of detection
            custom_selectors: Custom CSS selectors for extraction
            
        Returns:
            Complete scrape result with extracted data
        """
        job_id = self._generate_job_id()
        start_time = datetime.utcnow()
        
        logger.info(f"Starting scrape job {job_id} for URL: {url}")
        
        try:
            # Determine scraping method
            if force_dynamic:
                method = ExtractionMethod.DYNAMIC
                logger.info(f"Job {job_id}: Using dynamic rendering (forced)")
            else:
                # Try static first to determine if JS is needed
                try:
                    html = await self._fetch_static(url)
                    detection = self.js_detector.detect_javascript_need(html, url)
                    
                    if detection['needs_javascript']:
                        method = ExtractionMethod.DYNAMIC
                        logger.info(
                            f"Job {job_id}: Switching to dynamic rendering "
                            f"(confidence: {detection['confidence']:.2f})"
                        )
                        # Re-fetch with dynamic rendering
                        html = await self._fetch_dynamic(url)
                    else:
                        method = ExtractionMethod.STATIC
                        logger.info(f"Job {job_id}: Using static scraping")
                        
                except Exception as e:
                    logger.warning(f"Job {job_id}: Static fetch failed, trying dynamic: {e}")
                    method = ExtractionMethod.DYNAMIC
                    html = await self._fetch_dynamic(url)
            
            # Extract data from HTML
            data = await self._extract_data(html, url, custom_selectors)
            
            # Create result
            result = ScrapeResult(
                job_id=job_id,
                source_url=url,
                scrape_timestamp=start_time,
                status="completed",
                extraction_method=method,
                data=data,
                metadata={
                    "processing_time_seconds": (datetime.utcnow() - start_time).total_seconds(),
                    "data_items_count": len(data),
                    "html_size_bytes": len(html),
                }
            )
            
            logger.info(f"Job {job_id}: Completed successfully with {len(data)} items")
            return result
            
        except Exception as e:
            logger.error(f"Job {job_id}: Failed with error: {e}")
            return ScrapeResult(
                job_id=job_id,
                source_url=url,
                scrape_timestamp=start_time,
                status="failed",
                extraction_method=method if 'method' in locals() else ExtractionMethod.STATIC,
                data=[],
                error_message=str(e),
                metadata={
                    "processing_time_seconds": (datetime.utcnow() - start_time).total_seconds(),
                }
            )
    
    async def _fetch_static(self, url: str) -> str:
        """Fetch page content using HTTPX (static content)."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        ):
            with attempt:
                logger.debug(f"Fetching static content from: {url}")
                
                # Add delay for politeness
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)
                
                response = await self.http_client.get(url)
                response.raise_for_status()
                
                return response.text
    
    async def _fetch_dynamic(self, url: str) -> str:
        """Fetch page content using Playwright (dynamic content)."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        ):
            with attempt:
                logger.debug(f"Fetching dynamic content from: {url}")
                
                # Initialize browser if needed
                if not self._browser:
                    await self._init_browser()
                
                # Create new page
                page = await self._browser.new_page()
                
                try:
                    # Configure page
                    await page.set_extra_http_headers({"User-Agent": self.user_agent})
                    
                    # Navigate to URL with network idle wait
                    await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=self.timeout * 1000,  # Convert to milliseconds
                    )
                    
                    # Wait a bit more for any lazy-loaded content
                    await page.wait_for_timeout(2000)
                    
                    # Get rendered HTML
                    html = await page.content()
                    
                    return html
                    
                finally:
                    await page.close()
    
    async def _extract_data(
        self,
        html: str,
        url: str,
        custom_selectors: Optional[Dict[str, str]] = None,
    ) -> List[ScrapedData]:
        """Extract structured data from HTML."""
        soup = BeautifulSoup(html, 'lxml')
        data = []
        
        if custom_selectors:
            # Use custom selectors if provided
            data = await self._extract_with_selectors(soup, url, custom_selectors)
        else:
            # Use generic extraction strategies
            data = await self._generic_extraction(soup, url)
        
        return data
    
    async def _extract_with_selectors(
        self,
        soup: BeautifulSoup,
        url: str,
        selectors: Dict[str, str],
    ) -> List[ScrapedData]:
        """Extract data using custom CSS selectors."""
        data = []
        
        # If selectors provided, assume they define a repeating pattern
        # Example: {"container": ".quote", "text": ".text", "author": ".author"}
        
        container_selector = selectors.get("container")
        if not container_selector:
            # If no container, treat as single item extraction
            item_data = {}
            for field, selector in selectors.items():
                elements = soup.select(selector)
                if elements:
                    if len(elements) == 1:
                        item_data[field] = elements[0].get_text(strip=True)
                    else:
                        item_data[field] = [el.get_text(strip=True) for el in elements]
            
            if item_data:
                data.append(ScrapedData(metadata=item_data))
        else:
            # Container-based extraction (multiple items)
            containers = soup.select(container_selector)
            
            for container in containers:
                item_data = {}
                for field, selector in selectors.items():
                    if field == "container":
                        continue
                    
                    elements = container.select(selector)
                    if elements:
                        if len(elements) == 1:
                            item_data[field] = elements[0].get_text(strip=True)
                        else:
                            item_data[field] = [el.get_text(strip=True) for el in elements]
                
                if item_data:
                    data.append(ScrapedData(metadata=item_data))
        
        return data
    
    async def _generic_extraction(self, soup: BeautifulSoup, url: str) -> List[ScrapedData]:
        """Generic data extraction when no custom selectors provided."""
        data = []
        
        # Strategy 1: Look for common article/content patterns
        article_selectors = [
            "article",
            ".post", ".entry", ".content",
            ".article", ".story",
            "[role='main'] > div",
            "main > div",
        ]
        
        articles_found = False
        for selector in article_selectors:
            articles = soup.select(selector)
            if articles:
                for article in articles:
                    title_elem = article.find(['h1', 'h2', 'h3', '.title', '.headline'])
                    text_elem = article.find(['p', '.text', '.content', '.body'])
                    
                    if title_elem or text_elem:
                        data.append(ScrapedData(
                            title=title_elem.get_text(strip=True) if title_elem else None,
                            text=text_elem.get_text(strip=True) if text_elem else None,
                            url=url,
                        ))
                        articles_found = True
                
                if articles_found:
                    break
        
        # Strategy 2: Look for list items if no articles found
        if not articles_found:
            list_selectors = [
                "li",
                ".item", ".entry",
                ".quote", ".post-summary",
            ]
            
            for selector in list_selectors:
                items = soup.select(selector)
                if len(items) > 1:  # Multiple items suggest a list
                    for item in items[:20]:  # Limit to first 20 items
                        text = item.get_text(strip=True)
                        if len(text) > 10:  # Skip very short items
                            data.append(ScrapedData(
                                text=text,
                                url=url,
                            ))
                    break
        
        # Strategy 3: Fallback to main content if nothing else found
        if not data:
            main_content = soup.find(['main', '#main', '.main', '#content', '.content'])
            if main_content:
                paragraphs = main_content.find_all('p')
                for p in paragraphs[:10]:  # Limit to first 10 paragraphs
                    text = p.get_text(strip=True)
                    if len(text) > 20:  # Only substantial paragraphs
                        data.append(ScrapedData(
                            text=text,
                            url=url,
                        ))
        
        # If still no data, extract page title at minimum
        if not data:
            title_elem = soup.find('title')
            if title_elem:
                data.append(ScrapedData(
                    title=title_elem.get_text(strip=True),
                    url=url,
                ))
        
        return data
    
    async def _init_browser(self) -> None:
        """Initialize Playwright browser."""
        logger.debug("Initializing Playwright browser")
        playwright = await async_playwright().start()
        self._browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-features=TranslateUI',
                '--disable-extensions',
                '--disable-default-apps',
            ]
        )
    
    def _generate_job_id(self) -> str:
        """Generate a unique job ID."""
        import uuid
        return uuid.uuid4().hex[:8]
    
    async def close(self) -> None:
        """Clean up resources."""
        if self.http_client:
            await self.http_client.aclose()
        
        if self._browser:
            await self._browser.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close() 