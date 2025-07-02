"""Core scraping functionality and utilities."""

from .anti_scraping import AntiScrapingManager, UserAgentRotator, RobotsTxtChecker, RateLimiter
from .detector import JavaScriptDetector
from .error_handling import (
    ErrorHandler,
    ScrapingError,
    NetworkError,
    HTTPError,
    RateLimitError,
    JavaScriptError,
    ErrorSeverity,
    ErrorCategory,
)
from .scraper import WebScraper

__all__ = [
    # Main scraper
    "WebScraper",
    "JavaScriptDetector",
    
    # Anti-scraping
    "AntiScrapingManager",
    "UserAgentRotator", 
    "RobotsTxtChecker",
    "RateLimiter",
    
    # Error handling
    "ErrorHandler",
    "ScrapingError",
    "NetworkError",
    "HTTPError", 
    "RateLimitError",
    "JavaScriptError",
    "ErrorSeverity",
    "ErrorCategory",
] 