"""Core scraping functionality and utilities."""

from .detector import JavaScriptDetector
from .scraper import WebScraper

__all__ = [
    "JavaScriptDetector",
    "WebScraper",
] 