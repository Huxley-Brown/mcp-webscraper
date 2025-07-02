# MCP WebScraper Integration Guide

## Overview

This document provides complete examples for integrating the MCP WebScraper with AI agents and Model Context Protocol (MCP) environments.

## Table of Contents

1. [Quick Start](#quick-start)
2. [API Integration](#api-integration)
3. [CLI Integration](#cli-integration)
4. [Python SDK Examples](#python-sdk-examples)
5. [Error Handling](#error-handling)
6. [Best Practices](#best-practices)

---

## Quick Start

### 1. Start the Service

```bash
# Start the API server
uvicorn src.mcp_webscraper.api.main:app --host 0.0.0.0 --port 8000

# Or use the Makefile
make run
```

### 2. Test Basic Functionality

```bash
# Test with a simple URL
curl -X POST "http://localhost:8000/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "input_type": "url",
    "target": "https://quotes.toscrape.com/"
  }'
```

---

## API Integration

### Basic URL Scraping

```python
import requests
import json
import time

# Submit scraping job
response = requests.post("http://localhost:8000/scrape", json={
    "input_type": "url",
    "target": "https://news.ycombinator.com/",
    "custom_selectors": {
        "container": ".athing",
        "title": ".titleline > a",
        "score": ".score"
    }
})

job_data = response.json()
job_id = job_data["job_id"]

# Poll for completion
while True:
    status_response = requests.get(f"http://localhost:8000/status/{job_id}")
    status_data = status_response.json()
    
    if status_data["status"] == "completed":
        # Get results
        results_response = requests.get(f"http://localhost:8000/results/{job_id}")
        results = results_response.json()
        
        print(f"Scraped {len(results['data'])} items")
        for item in results['data'][:3]:  # Show first 3
            print(f"- {item['text'][:100]}...")
        break
    elif status_data["status"] == "failed":
        print(f"Job failed: {status_data.get('error', 'Unknown error')}")
        break
    else:
        print(f"Status: {status_data['status']}")
        time.sleep(2)
```

### Batch File Processing

```python
# Create a URL list file
urls = [
    "https://quotes.toscrape.com/page/1/",
    "https://quotes.toscrape.com/page/2/",
    "https://quotes.toscrape.com/page/3/"
]

with open("batch_urls.json", "w") as f:
    json.dump({"urls": urls}, f)

# Submit batch job
response = requests.post("http://localhost:8000/scrape", json={
    "input_type": "file",
    "target": "batch_urls.json"
})

# Monitor multiple jobs (each URL gets its own job)
# Process results as they complete
```

### Custom Selector Patterns

```python
# E-commerce product scraping
ecommerce_selectors = {
    "container": ".product-item",
    "title": ".product-title",
    "price": ".price",
    "rating": ".rating",
    "availability": ".stock-status"
}

# News article scraping
news_selectors = {
    "container": "article",
    "headline": "h1, h2.headline",
    "author": ".author, .byline",
    "date": ".date, time",
    "content": ".article-body, .content"
}

# Social media scraping
social_selectors = {
    "container": ".post",
    "content": ".post-content",
    "author": ".author-name",
    "timestamp": ".timestamp",
    "likes": ".like-count"
}
```

---

## CLI Integration

### Single URL Processing

```bash
# Basic scraping
python -m src.mcp_webscraper.cli scrape --url "https://example.com"

# With output directory
python -m src.mcp_webscraper.cli scrape \
  --url "https://example.com" \
  --output-dir ./my_results

# Verbose output
python -m src.mcp_webscraper.cli scrape \
  --url "https://example.com" \
  --verbose
```

### Batch File Processing

```bash
# Create URL list
echo "https://quotes.toscrape.com/page/1/" > urls.txt
echo "https://quotes.toscrape.com/page/2/" >> urls.txt

# Process file
python -m src.mcp_webscraper.cli scrape --list-file urls.txt

# JSON format
cat > urls.json << EOF
{
  "urls": [
    "https://quotes.toscrape.com/page/1/",
    "https://quotes.toscrape.com/page/2/"
  ]
}
EOF

python -m src.mcp_webscraper.cli scrape --list-file urls.json
```

---

## Python SDK Examples

### Using the Core Scraper Directly

```python
import asyncio
from src.mcp_webscraper.core import WebScraper

async def scrape_example():
    scraper = WebScraper(
        timeout=30,
        max_retries=3,
        request_delay=1.0,
        user_agent_rotation=True
    )
    
    try:
        # Simple scraping
        result = await scraper.scrape_url("https://quotes.toscrape.com/")
        print(f"Scraped {len(result.data)} items")
        
        # Custom selectors
        custom_selectors = {
            "container": ".quote",
            "text": ".text",
            "author": ".author"
        }
        
        result = await scraper.scrape_url(
            "https://quotes.toscrape.com/",
            custom_selectors=custom_selectors
        )
        
        for item in result.data:
            print(f"Quote: {item.metadata.get('text', '')}")
            print(f"Author: {item.metadata.get('author', '')}")
            print("---")
            
    finally:
        await scraper.close()

# Run the example
asyncio.run(scrape_example())
```

### Job Manager Integration

```python
import asyncio
from src.mcp_webscraper.jobs.manager import JobManager
from src.mcp_webscraper.config.settings import get_settings

async def job_manager_example():
    settings = get_settings()
    job_manager = JobManager(
        **settings.get_job_manager_config()
    )
    
    try:
        # Start the job manager
        await job_manager.start()
        
        # Submit a job
        job_id = await job_manager.submit_job(
            input_type="url",
            target="https://quotes.toscrape.com/"
        )
        
        print(f"Submitted job: {job_id}")
        
        # Monitor job progress
        while True:
            status = job_manager.get_job_status(job_id)
            if not status:
                print("Job not found")
                break
                
            print(f"Status: {status.status}")
            
            if status.status in ["completed", "failed"]:
                break
                
            await asyncio.sleep(1)
            
    finally:
        await job_manager.stop()

asyncio.run(job_manager_example())
```

---

## Error Handling

### Handling API Errors

```python
import requests

def safe_scrape(url, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.post("http://localhost:8000/scrape", 
                json={"input_type": "url", "target": url},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.ConnectionError:
            print(f"Connection error (attempt {attempt + 1})")
            if attempt == max_retries - 1:
                raise
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 422:
                print(f"Validation error: {e.response.json()}")
                return None  # Don't retry validation errors
            raise
            
        except requests.exceptions.Timeout:
            print(f"Timeout (attempt {attempt + 1})")
            if attempt == max_retries - 1:
                raise
```

### Circuit Breaker Pattern

```python
import requests
import time

class SimpleCircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
    
    def on_success(self):
        self.failure_count = 0
        self.state = "CLOSED"
    
    def on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

# Usage
breaker = SimpleCircuitBreaker()

def scrape_with_breaker(url):
    def _scrape():
        response = requests.post("http://localhost:8000/scrape", 
            json={"input_type": "url", "target": url})
        response.raise_for_status()
        return response.json()
    
    return breaker.call(_scrape)
```

---

## Best Practices

### 1. Resource Management

```python
# Always use context managers or ensure cleanup
async def managed_scraping():
    scraper = WebScraper()
    try:
        result = await scraper.scrape_url("https://example.com")
        return result
    finally:
        await scraper.close()

# Or use async context manager
async def context_scraping():
    async with WebScraper() as scraper:
        result = await scraper.scrape_url("https://example.com")
        return result
```

### 2. Rate Limiting

```python
import asyncio
from asyncio import Semaphore

# Limit concurrent requests
semaphore = Semaphore(3)  # Max 3 concurrent requests

async def rate_limited_scrape(url):
    async with semaphore:
        # Your scraping logic here
        await asyncio.sleep(1)  # Politeness delay
        return await scraper.scrape_url(url)
```

### 3. Monitoring and Logging

```python
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def monitor_job(job_id):
    while True:
        try:
            response = requests.get(f"http://localhost:8000/status/{job_id}")
            status = response.json()
            
            logger.info(f"Job {job_id}: {status['status']}")
            
            if status['status'] in ['completed', 'failed']:
                break
                
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Error monitoring job {job_id}: {e}")
            break
```

### 4. Configuration Management

```python
import os
from src.mcp_webscraper.config.settings import get_settings

# Environment-specific configuration
os.environ['MAX_CONCURRENT_JOBS'] = '10'
os.environ['REQUEST_DELAY'] = '2.0'
os.environ['LOG_LEVEL'] = 'DEBUG'

settings = get_settings()
print(f"Max jobs: {settings.max_concurrent_jobs}")
print(f"Request delay: {settings.request_delay}s")
```

### 5. Custom Selector Development

```python
# Test selectors before production use
def test_selectors(html_content, selectors):
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    containers = soup.select(selectors.get('container', 'body'))
    print(f"Found {len(containers)} containers")
    
    for i, container in enumerate(containers[:3]):
        print(f"\nContainer {i + 1}:")
        for key, selector in selectors.items():
            if key != 'container':
                elements = container.select(selector)
                values = [elem.get_text(strip=True) for elem in elements]
                print(f"  {key}: {values}")
```

---

## Real-World Examples

### News Aggregation

```python
# Scrape multiple news sources
news_sources = [
    {
        "url": "https://news.ycombinator.com/",
        "selectors": {
            "container": ".athing",
            "title": ".titleline > a",
            "score": ".score"
        }
    },
    {
        "url": "https://www.reddit.com/r/programming/",
        "selectors": {
            "container": "[data-testid='post-container']",
            "title": "h3",
            "score": "[data-testid='vote-arrows'] button"
        }
    }
]

async def aggregate_news():
    all_articles = []
    
    for source in news_sources:
        try:
            result = await scraper.scrape_url(
                source["url"],
                custom_selectors=source["selectors"]
            )
            all_articles.extend(result.data)
        except Exception as e:
            print(f"Failed to scrape {source['url']}: {e}")
    
    return all_articles
```

### E-commerce Price Monitoring

```python
# Monitor product prices across sites
products = [
    {
        "name": "Gaming Laptop",
        "urls": [
            "https://store1.com/laptop-xyz",
            "https://store2.com/laptop-xyz",
            "https://store3.com/laptop-xyz"
        ],
        "price_selector": ".price, .cost, .amount"
    }
]

async def monitor_prices():
    for product in products:
        prices = []
        for url in product["urls"]:
            try:
                result = await scraper.scrape_url(
                    url,
                    custom_selectors={
                        "container": "body",
                        "price": product["price_selector"]
                    }
                )
                # Extract price logic here
                prices.append(result)
            except Exception as e:
                print(f"Failed to get price from {url}: {e}")
        
        # Compare prices and alert if needed
```

This guide provides comprehensive examples for integrating the MCP WebScraper into various AI agent workflows and applications. 