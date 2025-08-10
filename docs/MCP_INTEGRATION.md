# MCP WebScraper Integration Guide

## Overview

This document provides complete examples for integrating the MCP WebScraper with AI agents using the Model Context Protocol (MCP). The webscraper exposes three main tools (`scrape_url`, `scrape_batch`, `validate_selectors`) and configuration resources through both HTTP transport and stdio transport.

## Table of Contents

1. [MCP Server Setup](#mcp-server-setup)
2. [MCP Tools Overview](#mcp-tools-overview)
3. [Python MCP Client Integration](#python-mcp-client-integration)
4. [Cursor Integration](#cursor-integration)
5. [REST API Integration](#rest-api-integration)
6. [CLI Integration](#cli-integration)
7. [Error Handling](#error-handling)
8. [Best Practices](#best-practices)

---

## MCP Server Setup

### 1. Start the MCP Server

The MCP WebScraper can be accessed through multiple transports:

#### HTTP Transport (Recommended for AI Agents)

```bash
# Start the FastAPI server with mounted MCP endpoint
uvicorn src.mcp_webscraper.api.main:app --host 0.0.0.0 --port 8000

# Or use the Makefile
make run
```

The MCP server is mounted at `/mcp` and provides streamable HTTP transport.

#### Stdio Transport (For Cursor Integration)

```bash
# Run MCP server directly with stdio transport
python -m src.mcp_webscraper.mcp_server
```

### 2. Verify MCP Server

```bash
# Test the HTTP endpoint
curl http://localhost:8000/mcp/info

# Check available tools
curl http://localhost:8000/mcp/tools
```

---

## MCP Tools Overview

### Available Tools

| Tool | Description | Input | Output |
|------|-------------|-------|--------|
| `scrape_url` | Scrape a single URL | url, custom_selectors, force_dynamic | Structured data with metadata |
| `scrape_batch` | Scrape multiple URLs | urls[], custom_selectors, force_dynamic | Combined results from all URLs |
| `validate_selectors` | Test CSS selectors | url, selectors{} | Validation results with samples |

### Available Resources

| Resource | Description |
|----------|-------------|
| `config://webscraper` | Current webscraper configuration |
| `status://jobs` | Active jobs status information |

---

## Python MCP Client Integration

### Basic MCP Client Setup

```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def webscraper_mcp_client():
    """Connect to webscraper MCP server and use tools."""
    
    # Connect to the MCP server via HTTP
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()
            
            # List available tools
            tools_response = await session.list_tools()
            print("Available tools:")
            for tool in tools_response.tools:
                print(f"  - {tool.name}: {tool.description}")
            
            # List available resources
            resources_response = await session.list_resources()
            print("\nAvailable resources:")
            for resource in resources_response.resources:
                print(f"  - {resource.uri}")
            
            return session

# Run the client
asyncio.run(webscraper_mcp_client())
```

### Using the scrape_url Tool

```python
async def scrape_single_url():
    """Example of using the scrape_url MCP tool."""
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Simple URL scraping
            result = await session.call_tool(
                "scrape_url",
                arguments={
                    "url": "https://quotes.toscrape.com/",
                }
            )
            
            print(f"Scraped {result.content[0].json['data_count']} items")
            print(f"Processing time: {result.content[0].json['processing_time']:.2f}s")
            
            # Advanced scraping with custom selectors
            result = await session.call_tool(
                "scrape_url",
                arguments={
                    "url": "https://news.ycombinator.com/",
                    "custom_selectors": {
                        "container": ".athing",
                        "title": ".titleline > a",
                        "score": ".score"
                    }
                }
            )
            
            # Access structured data
            scraped_data = result.content[0].json
            print(f"Extraction method: {scraped_data['extraction_method']}")
            
            for item in scraped_data['data'][:3]:  # Show first 3 items
                print(f"Title: {item.get('metadata', {}).get('title', 'N/A')}")

asyncio.run(scrape_single_url())
```

### Using the scrape_batch Tool

```python
async def scrape_multiple_urls():
    """Example of using the scrape_batch MCP tool."""
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Batch scraping
            urls = [
                "https://quotes.toscrape.com/page/1/",
                "https://quotes.toscrape.com/page/2/",
                "https://quotes.toscrape.com/page/3/"
            ]
            
            result = await session.call_tool(
                "scrape_batch",
                arguments={
                    "urls": urls,
                    "custom_selectors": {
                        "container": ".quote",
                        "text": ".text",
                        "author": ".author"
                    }
                }
            )
            
            # Access batch results
            batch_data = result.content[0].json
            print(f"Processed {batch_data['total_urls']} URLs")
            print(f"Successfully scraped {batch_data['successful_urls']} URLs")
            print(f"Total items extracted: {batch_data['total_items']}")
            
            # Process combined results
            for item in batch_data['results'][:5]:  # Show first 5 items
                quote = item.get('metadata', {}).get('text', '')
                author = item.get('metadata', {}).get('author', '')
                print(f"'{quote}' - {author}")

asyncio.run(scrape_multiple_urls())
```

### Using the validate_selectors Tool

```python
async def validate_css_selectors():
    """Example of using the validate_selectors MCP tool."""
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Test selectors before scraping
            selectors_to_test = {
                "title": "h1, .title, .headline",
                "price": ".price, .cost, .amount",
                "rating": ".rating, .stars",
                "description": ".description, .summary"
            }
            
            result = await session.call_tool(
                "validate_selectors",
                arguments={
                    "url": "https://example-ecommerce.com/product/123",
                    "selectors": selectors_to_test
                }
            )
            
            # Check validation results
            validation_data = result.content[0].json
            print(f"Tested {validation_data['selectors_tested']} selectors")
            print(f"Valid selectors: {validation_data['valid_selectors']}")
            print(f"Invalid selectors: {validation_data['invalid_selectors']}")
            
            # Show sample matches
            for selector, samples in validation_data['sample_matches'].items():
                print(f"\n{selector} found:")
                for sample in samples[:2]:  # Show first 2 samples
                    print(f"  - {sample}")

asyncio.run(validate_css_selectors())
```

### Using MCP Resources

```python
async def read_webscraper_resources():
    """Example of reading MCP resources."""
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Read configuration resource
            config_content, mime_type = await session.read_resource("config://webscraper")
            print("Webscraper Configuration:")
            print(config_content)
            
            # Read jobs status resource
            status_content, mime_type = await session.read_resource("status://jobs")
            print("\nJobs Status:")
            print(status_content)

asyncio.run(read_webscraper_resources())
```

---

## Cursor Integration

### Setup for Cursor IDE

**Important**: Do NOT run the MCP server command in your terminal. Configure it in Cursor so Cursor can manage the server automatically.

1. Project config (recommended) — create `.cursor/mcp.json` in your project root:

```json
{
  "servers": {
    "webscraper": {
      "command": "/absolute/path/to/webscraper/.venv/bin/python",
      "args": ["-m", "mcp_webscraper.mcp_server"]
    }
  }
}
```

2. Alternative (from source tree) — if you prefer running the module from `src`:

```json
{
  "servers": {
    "webscraper": {
      "command": "python",
      "args": ["-m", "src.mcp_webscraper.mcp_server"],
      "cwd": "/absolute/path/to/your/webscraper/project"
    }
  }
}
```

**Key Points:**
- Prefer the project-level config to avoid global path drift.
- When using the installed package form (`mcp_webscraper.mcp_server`), ensure your venv has `pip install -e .` run.
- Cursor will automatically start/stop the server as needed.

2. **Restart Cursor** to load the MCP server configuration.

3. **Verify the connection** - You should see the webscraper available in Cursor's MCP servers list.

4. **Use in Cursor chat**:

```
@webscraper scrape_url url="https://quotes.toscrape.com/" custom_selectors='{"container": ".quote", "text": ".text", "author": ".author"}'
```

### Example Cursor Workflows

```
# Scrape a news website
@webscraper scrape_url url="https://news.ycombinator.com/" custom_selectors='{"container": ".athing", "title": ".titleline > a"}'

# Validate selectors before scraping
@webscraper validate_selectors url="https://example.com/" selectors='{"title": "h1", "price": ".price"}'

# Batch scrape multiple pages
@webscraper scrape_batch urls='["https://quotes.toscrape.com/page/1/", "https://quotes.toscrape.com/page/2/"]'

### Troubleshooting after moving directories

- Recreate your virtual environment and reinstall dependencies:
  ```bash
  rm -rf .venv && python -m venv .venv
  . .venv/bin/activate
  pip install -e .
  python -m playwright install chromium
  ```
- Ensure your project-level `.cursor/mcp.json` points to the new absolute path of `.venv/bin/python`.
- Avoid setting `PYTHONPATH` to old paths in global `~/.cursor/mcp.json`; prefer the project config.
```

---

## REST API Integration

### Using the REST API Endpoints

```python
import requests
import time

def rest_api_scraping():
    """Example using the REST API directly."""
    
    # Submit scraping job
    response = requests.post("http://localhost:8000/scrape", json={
        "input_type": "url",
        "target": "https://quotes.toscrape.com/",
        "custom_selectors": {
            "container": ".quote",
            "text": ".text",
            "author": ".author"
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
            return results
        elif status_data["status"] == "failed":
            print(f"Job failed: {status_data.get('error', 'Unknown error')}")
            break
        
        time.sleep(2)

# Run the example
results = rest_api_scraping()
```

---

## CLI Integration

### Single URL Processing

```bash
# Basic scraping
python -m src.mcp_webscraper.cli scrape --url "https://quotes.toscrape.com/"

# With custom selectors
python -m src.mcp_webscraper.cli scrape \
  --url "https://news.ycombinator.com/" \
  --selectors '{"container": ".athing", "title": ".titleline > a"}'

# Force dynamic rendering
python -m src.mcp_webscraper.cli scrape \
  --url "https://spa-example.com/" \
  --force-dynamic
```

### Batch Processing

```bash
# Create URL list file
cat > urls.json << EOF
{
  "urls": [
    "https://quotes.toscrape.com/page/1/",
    "https://quotes.toscrape.com/page/2/"
  ]
}
EOF

# Process batch
python -m src.mcp_webscraper.cli scrape --list-file urls.json
```

### Selector Validation

```bash
# Validate selectors
python -m src.mcp_webscraper.cli validate \
  --url "https://news.ycombinator.com/" \
  --selectors '{"title": ".titleline > a", "score": ".score"}'
```

---

## Error Handling

### MCP Client Error Handling

```python
from mcp.shared.exceptions import McpError

async def robust_mcp_client():
    """MCP client with comprehensive error handling."""
    
    try:
        async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Call tool with error handling
                try:
                    result = await session.call_tool(
                        "scrape_url",
                        arguments={"url": "https://invalid-url"}
                    )
                    return result
                    
                except McpError as e:
                    print(f"MCP error: {e}")
                    return None
                    
    except ConnectionError:
        print("Could not connect to MCP server")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None
```

### Circuit Breaker for MCP Calls

```python
import time
from typing import Optional

class MCPCircuitBreaker:
    """Circuit breaker for MCP tool calls."""
    
    def __init__(self, failure_threshold=3, recovery_timeout=60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call_tool(self, session, tool_name, arguments):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await session.call_tool(tool_name, arguments)
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
async def scrape_with_circuit_breaker():
    breaker = MCPCircuitBreaker()
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            try:
                result = await breaker.call_tool(
                    session, 
                    "scrape_url", 
                    {"url": "https://example.com"}
                )
                return result
            except Exception as e:
                print(f"Scraping failed: {e}")
                return None
```

---

## Best Practices

### 1. Resource Management

```python
async def managed_mcp_session():
    """Properly managed MCP session with cleanup."""
    
    session = None
    try:
        async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Your MCP operations here
                result = await session.call_tool("scrape_url", {"url": "https://example.com"})
                return result
                
    except Exception as e:
        print(f"Error in MCP session: {e}")
        return None
    finally:
        # Cleanup is handled by context managers
        pass
```

### 2. Batch Processing with Rate Limiting

```python
import asyncio

async def rate_limited_batch_scraping(urls, delay=2.0):
    """Scrape URLs with rate limiting using MCP tools."""
    
    results = []
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            for url in urls:
                try:
                    result = await session.call_tool(
                        "scrape_url",
                        arguments={"url": url}
                    )
                    results.append(result)
                    
                    # Rate limiting delay
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    print(f"Failed to scrape {url}: {e}")
                    continue
    
    return results
```

### 3. Selector Development Workflow

```python
async def develop_selectors(url, potential_selectors):
    """Iteratively develop and test CSS selectors."""
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # First, validate potential selectors
            validation_result = await session.call_tool(
                "validate_selectors",
                arguments={
                    "url": url,
                    "selectors": potential_selectors
                }
            )
            
            validation_data = validation_result.content[0].json
            valid_selectors = {
                k: v for k, v in potential_selectors.items() 
                if k in validation_data['valid_selectors']
            }
            
            print(f"Valid selectors: {list(valid_selectors.keys())}")
            
            # If we have valid selectors, test scraping
            if valid_selectors:
                scrape_result = await session.call_tool(
                    "scrape_url",
                    arguments={
                        "url": url,
                        "custom_selectors": valid_selectors
                    }
                )
                
                scrape_data = scrape_result.content[0].json
                print(f"Scraped {scrape_data['data_count']} items")
                
                return valid_selectors, scrape_data
            
            return None, None

# Example usage
potential_selectors = {
    "title": "h1, .title, .headline",
    "price": ".price, .cost",
    "description": ".desc, .summary"
}

asyncio.run(develop_selectors("https://example.com", potential_selectors))
```

### 4. Configuration Management

```python
async def get_webscraper_config():
    """Retrieve and display webscraper configuration via MCP."""
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Read configuration resource
            config_content, mime_type = await session.read_resource("config://webscraper")
            
            print("Current WebScraper Configuration:")
            print(config_content)
            
            # Read jobs status
            status_content, mime_type = await session.read_resource("status://jobs")
            
            print("\nCurrent Jobs Status:")
            print(status_content)

asyncio.run(get_webscraper_config())
```

---

## Real-World Integration Examples

### AI Content Aggregator

```python
async def ai_content_aggregator():
    """AI agent that aggregates content from multiple sources."""
    
    sources = [
        {
            "name": "Hacker News",
            "url": "https://news.ycombinator.com/",
            "selectors": {
                "container": ".athing",
                "title": ".titleline > a",
                "score": ".score"
            }
        },
        {
            "name": "Quotes",
            "url": "https://quotes.toscrape.com/",
            "selectors": {
                "container": ".quote",
                "text": ".text",
                "author": ".author"
            }
        }
    ]
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            aggregated_content = []
            
            for source in sources:
                try:
                    result = await session.call_tool(
                        "scrape_url",
                        arguments={
                            "url": source["url"],
                            "custom_selectors": source["selectors"]
                        }
                    )
                    
                    scrape_data = result.content[0].json
                    
                    # Process and categorize content
                    for item in scrape_data['data']:
                        aggregated_content.append({
                            "source": source["name"],
                            "url": source["url"],
                            "data": item,
                            "extraction_method": scrape_data["extraction_method"]
                        })
                        
                except Exception as e:
                    print(f"Failed to scrape {source['name']}: {e}")
                    continue
            
            print(f"Aggregated {len(aggregated_content)} items from {len(sources)} sources")
            return aggregated_content

# Run the aggregator
content = asyncio.run(ai_content_aggregator())
```

### Dynamic E-commerce Monitor

```python
async def ecommerce_price_monitor():
    """Monitor product prices across multiple e-commerce sites."""
    
    products = [
        {
            "name": "Gaming Laptop",
            "urls": [
                "https://store1.com/gaming-laptop",
                "https://store2.com/gaming-laptop",
            ],
            "selectors": {
                "container": ".product",
                "price": ".price, .cost",
                "availability": ".stock, .availability"
            }
        }
    ]
    
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            monitoring_results = []
            
            for product in products:
                product_data = {"name": product["name"], "stores": []}
                
                # Use batch scraping for efficiency
                result = await session.call_tool(
                    "scrape_batch",
                    arguments={
                        "urls": product["urls"],
                        "custom_selectors": product["selectors"]
                    }
                )
                
                batch_data = result.content[0].json
                
                # Process results for each store
                for i, url in enumerate(product["urls"]):
                    store_items = [
                        item for item in batch_data['results'] 
                        if item.get('url') == url
                    ]
                    
                    if store_items:
                        price_info = store_items[0].get('metadata', {})
                        product_data["stores"].append({
                            "url": url,
                            "price": price_info.get('price'),
                            "availability": price_info.get('availability')
                        })
                
                monitoring_results.append(product_data)
            
            return monitoring_results

# Run the monitor
prices = asyncio.run(ecommerce_price_monitor())
```

This comprehensive guide provides everything needed to integrate the MCP WebScraper with AI agents, from basic setup to advanced real-world applications. The examples demonstrate both the MCP protocol integration and traditional REST API usage patterns. 