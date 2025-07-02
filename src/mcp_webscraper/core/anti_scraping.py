"""Anti-scraping countermeasures and politeness utilities."""

import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)


class UserAgentRotator:
    """Manages rotation of user agent strings to reduce fingerprinting."""
    
    DEFAULT_USER_AGENTS = [
        # Chrome on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        
        # Chrome on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        
        # Firefox on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
        
        # Firefox on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        
        # Safari on macOS
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        
        # Edge on Windows
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    ]
    
    def __init__(self, user_agents: Optional[List[str]] = None):
        """Initialize with custom or default user agents."""
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS
        self._current_index = 0
    
    def get_random(self) -> str:
        """Get a random user agent."""
        return random.choice(self.user_agents)
    
    def get_next(self) -> str:
        """Get the next user agent in rotation."""
        user_agent = self.user_agents[self._current_index]
        self._current_index = (self._current_index + 1) % len(self.user_agents)
        return user_agent
    
    def add_user_agent(self, user_agent: str) -> None:
        """Add a custom user agent to the rotation."""
        if user_agent not in self.user_agents:
            self.user_agents.append(user_agent)


class RobotsTxtChecker:
    """Checks robots.txt files and respects crawl delays."""
    
    def __init__(self, user_agent: str = "*"):
        """Initialize robots.txt checker."""
        self.user_agent = user_agent
        self._cache: Dict[str, tuple] = {}  # domain -> (RobotFileParser, timestamp)
        self._cache_ttl = 3600  # 1 hour cache
    
    async def can_fetch(self, url: str, http_client: httpx.AsyncClient) -> tuple[bool, Optional[float]]:
        """
        Check if URL can be fetched according to robots.txt.
        
        Returns:
            tuple: (can_fetch: bool, crawl_delay: Optional[float])
        """
        try:
            parsed_url = urlparse(url)
            domain = f"{parsed_url.scheme}://{parsed_url.netloc}"
            
            # Check cache
            if domain in self._cache:
                rp, timestamp = self._cache[domain]
                if time.time() - timestamp < self._cache_ttl:
                    can_fetch = rp.can_fetch(self.user_agent, url)
                    crawl_delay = rp.crawl_delay(self.user_agent)
                    return can_fetch, crawl_delay
            
            # Fetch robots.txt
            robots_url = urljoin(domain, "/robots.txt")
            
            try:
                response = await http_client.get(robots_url, timeout=10.0)
                if response.status_code == 200:
                    rp = RobotFileParser()
                    rp.read_string(response.text)
                    
                    # Cache the result
                    self._cache[domain] = (rp, time.time())
                    
                    can_fetch = rp.can_fetch(self.user_agent, url)
                    crawl_delay = rp.crawl_delay(self.user_agent)
                    
                    logger.debug(f"Robots.txt for {domain}: can_fetch={can_fetch}, crawl_delay={crawl_delay}")
                    return can_fetch, crawl_delay
                else:
                    # If robots.txt doesn't exist or is inaccessible, assume allowed
                    logger.debug(f"No robots.txt found for {domain} (status: {response.status_code})")
                    return True, None
                    
            except Exception as e:
                logger.warning(f"Error fetching robots.txt for {domain}: {e}")
                # If we can't fetch robots.txt, assume allowed
                return True, None
                
        except Exception as e:
            logger.error(f"Error parsing URL {url}: {e}")
            return True, None


class RateLimiter:
    """Implements rate limiting per domain to avoid overwhelming servers."""
    
    def __init__(self, default_delay: float = 1.0, max_concurrent_per_domain: int = 2):
        """
        Initialize rate limiter.
        
        Args:
            default_delay: Default delay between requests to same domain (seconds)
            max_concurrent_per_domain: Max concurrent requests per domain
        """
        self.default_delay = default_delay
        self.max_concurrent_per_domain = max_concurrent_per_domain
        
        # Track last request time per domain
        self._last_request: Dict[str, float] = {}
        
        # Semaphores per domain for concurrency control
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        
        # Lock for managing semaphores
        self._semaphore_lock = asyncio.Lock()
    
    async def wait_if_needed(self, url: str, custom_delay: Optional[float] = None) -> None:
        """
        Wait if needed to respect rate limits.
        
        Args:
            url: Target URL
            custom_delay: Custom delay (e.g. from robots.txt crawl-delay)
        """
        domain = self._extract_domain(url)
        delay = custom_delay if custom_delay is not None else self.default_delay
        
        # Get or create semaphore for this domain
        async with self._semaphore_lock:
            if domain not in self._domain_semaphores:
                self._domain_semaphores[domain] = asyncio.Semaphore(self.max_concurrent_per_domain)
        
        # Acquire semaphore for concurrency control
        semaphore = self._domain_semaphores[domain]
        await semaphore.acquire()
        
        try:
            # Check if we need to wait based on last request time
            if domain in self._last_request and delay > 0:
                elapsed = time.time() - self._last_request[domain]
                if elapsed < delay:
                    wait_time = delay - elapsed
                    logger.debug(f"Rate limiting: waiting {wait_time:.2f}s for {domain}")
                    await asyncio.sleep(wait_time)
            
            # Update last request time
            self._last_request[domain] = time.time()
            
        finally:
            # Always release the semaphore
            semaphore.release()
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return url


class AntiScrapingManager:
    """Coordinates all anti-scraping countermeasures."""
    
    def __init__(
        self,
        respect_robots_txt: bool = True,
        user_agent_rotation: bool = True,
        default_delay: float = 1.0,
        max_concurrent_per_domain: int = 2,
        custom_user_agents: Optional[List[str]] = None,
    ):
        """
        Initialize anti-scraping manager.
        
        Args:
            respect_robots_txt: Whether to check and respect robots.txt
            user_agent_rotation: Whether to rotate user agents
            default_delay: Default delay between requests (seconds)
            max_concurrent_per_domain: Max concurrent requests per domain
            custom_user_agents: Custom user agent list
        """
        self.respect_robots_txt = respect_robots_txt
        self.user_agent_rotation = user_agent_rotation
        
        # Initialize components
        self.user_agent_rotator = UserAgentRotator(custom_user_agents)
        self.robots_checker = RobotsTxtChecker()
        self.rate_limiter = RateLimiter(
            default_delay=default_delay,
            max_concurrent_per_domain=max_concurrent_per_domain
        )
        
        # Stats tracking
        self.stats = {
            "requests_blocked_by_robots": 0,
            "requests_delayed": 0,
            "total_requests": 0,
        }
    
    async def prepare_request(
        self, 
        url: str, 
        http_client: httpx.AsyncClient
    ) -> tuple[bool, Dict[str, str], Optional[float]]:
        """
        Prepare a request with anti-scraping measures.
        
        Args:
            url: Target URL
            http_client: HTTP client for robots.txt checking
            
        Returns:
            tuple: (should_proceed: bool, headers: dict, delay: Optional[float])
        """
        self.stats["total_requests"] += 1
        
        # Check robots.txt if enabled
        crawl_delay = None
        if self.respect_robots_txt:
            can_fetch, crawl_delay = await self.robots_checker.can_fetch(url, http_client)
            if not can_fetch:
                self.stats["requests_blocked_by_robots"] += 1
                logger.warning(f"Request blocked by robots.txt: {url}")
                return False, {}, None
        
        # Prepare headers with user agent rotation
        headers = {}
        if self.user_agent_rotation:
            user_agent = self.user_agent_rotator.get_random()
            headers["User-Agent"] = user_agent
            logger.debug(f"Using User-Agent: {user_agent}")
        
        # Apply rate limiting
        await self.rate_limiter.wait_if_needed(url, crawl_delay)
        if crawl_delay and crawl_delay > 0:
            self.stats["requests_delayed"] += 1
        
        return True, headers, crawl_delay
    
    def get_stats(self) -> Dict[str, int]:
        """Get anti-scraping statistics."""
        return self.stats.copy()
    
    def get_current_user_agent(self) -> str:
        """Get current user agent."""
        return self.user_agent_rotator.get_random() 