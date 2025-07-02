"""
MCP WebScraper - Local web scraping service with dynamic page support.

A locally-run service that can scrape both static HTML and JavaScript-heavy pages,
expose its functionality through an MCP-style REST API, and allow command-line usage.
"""

__version__ = "0.1.0"

# Make configuration easily accessible
from .config import get_settings

__all__ = ["get_settings"] 