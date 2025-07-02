# Testing Guide

## Overview

This guide covers the comprehensive testing strategy for the MCP WebScraper, including unit tests, integration tests, and real-world validation.

## Test Structure

```
tests/
├── __init__.py              # Test package
├── test_core.py            # Core scraping functionality
├── test_api.py             # FastAPI endpoints
├── test_config.py          # Configuration management
├── test_jobs.py            # Job manager and queue
├── test_anti_scraping.py   # Anti-scraping features
├── test_error_handling.py  # Error handling and retries
└── integration/            # Integration tests
    ├── test_end_to_end.py  # Complete workflows
    └── test_real_sites.py  # Real website testing
```

## Running Tests

### Quick Start

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run with coverage
pytest --cov=src/mcp_webscraper --cov-report=html

# Run specific test categories
pytest -m "not integration"      # Skip integration tests
pytest -m "not external"        # Skip external dependency tests
pytest tests/test_core.py        # Run specific test file
```

### Test Configuration

The project uses `pytest.ini` for configuration:

```ini
[tool:pytest]
addopts = -ra -q --strict-markers
testpaths = tests
markers =
    integration: integration tests
    slow: slow tests
    external: tests requiring external services
```

## Test Categories

### 1. Unit Tests

#### Core Functionality (`test_core.py`)

```bash
# Test JavaScript detection
pytest tests/test_core.py::TestJavaScriptDetector -v

# Test scraper functionality  
pytest tests/test_core.py::TestWebScraper -v

# Test error handling
pytest tests/test_core.py::TestErrorHandler -v
```

**Key Test Scenarios:**
- JavaScript need detection (React, Vue, Angular, AJAX)
- Static vs dynamic scraping decisions
- CSS selector extraction
- Error handling and retries
- Circuit breaker functionality

#### API Tests (`test_api.py`)

```bash
# Test all API endpoints
pytest tests/test_api.py -v

# Test specific endpoint
pytest tests/test_api.py::TestAPIEndpoints::test_scrape_endpoint_success -v
```

**Coverage Areas:**
- Request validation
- Job submission and tracking
- Status monitoring
- Error responses
- Rate limiting
- Authentication (if enabled)

#### Configuration Tests (`test_config.py`)

```bash
# Test configuration system
pytest tests/test_config.py -v
```

**Testing Areas:**
- Default values
- Environment variable overrides
- Validation rules
- Settings caching
- Production mode detection

### 2. Integration Tests

#### End-to-End Workflows

```bash
# Run integration tests
pytest tests/integration/ -v

# Skip if external services unavailable
pytest -m "not external"
```

#### Real Website Testing

```python
# Example integration test
@pytest.mark.integration
@pytest.mark.external
async def test_real_website_scraping():
    """Test against actual websites."""
    scraper = WebScraper(request_delay=2.0)  # Be polite
    
    test_cases = [
        {
            "url": "https://quotes.toscrape.com/",
            "expected_items": lambda x: x > 5,
            "selector_test": ".quote"
        },
        {
            "url": "https://httpbin.org/html",
            "expected_items": lambda x: x >= 1,
            "selector_test": "h1"
        }
    ]
    
    for case in test_cases:
        try:
            result = await scraper.scrape_url(case["url"])
            assert case["expected_items"](len(result.data))
            print(f"✓ {case['url']}: {len(result.data)} items")
        except Exception as e:
            pytest.skip(f"External site not accessible: {e}")
    
    await scraper.close()
```

### 3. Performance Tests

#### Load Testing

```python
import asyncio
import time

@pytest.mark.slow
async def test_concurrent_scraping():
    """Test concurrent job processing."""
    start_time = time.time()
    
    # Submit multiple jobs concurrently
    tasks = []
    for i in range(10):
        task = scraper.scrape_url(f"https://httpbin.org/delay/1")
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    # Should complete faster than sequential execution
    assert elapsed < 15  # Should be much faster than 10 seconds
    assert all(r.status == "completed" for r in results)
```

#### Memory Usage Testing

```python
import psutil
import os

def test_memory_usage():
    """Test memory usage doesn't grow excessively."""
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss
    
    # Perform memory-intensive operations
    for _ in range(100):
        # Simulate scraping operations
        html = "<html>" + "x" * 10000 + "</html>"
        detector = JavaScriptDetector()
        detector.detect_javascript_need(html)
    
    final_memory = process.memory_info().rss
    memory_growth = final_memory - initial_memory
    
    # Memory growth should be reasonable (< 50MB)
    assert memory_growth < 50 * 1024 * 1024
```

## Mock Testing

### HTTP Mocking

```python
import httpx
from unittest.mock import AsyncMock, patch

@patch('httpx.AsyncClient.get')
async def test_static_scraping_with_mock(mock_get):
    """Test static scraping with mocked HTTP responses."""
    
    # Mock successful response
    mock_response = AsyncMock()
    mock_response.text = """
    <html>
        <body>
            <div class="quote">
                <span class="text">"Test quote"</span>
                <span class="author">Test Author</span>
            </div>
        </body>
    </html>
    """
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response
    
    scraper = WebScraper()
    result = await scraper.scrape_url("https://example.com")
    
    assert result.status == "completed"
    assert len(result.data) > 0
    
    await scraper.close()
```

### Playwright Mocking

```python
from unittest.mock import AsyncMock, patch

@patch('playwright.async_api.async_playwright')
async def test_dynamic_scraping_with_mock(mock_playwright):
    """Test dynamic scraping with mocked Playwright."""
    
    # Set up mock playwright chain
    mock_browser = AsyncMock()
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    
    mock_playwright.return_value.__aenter__.return_value.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page
    mock_page.content.return_value = "<html><body>Dynamic content</body></html>"
    
    scraper = WebScraper()
    result = await scraper._fetch_dynamic("https://example.com")
    
    assert "Dynamic content" in result
    
    # Verify Playwright methods were called
    mock_page.goto.assert_called_once()
    mock_page.wait_for_load_state.assert_called()
    
    await scraper.close()
```

## Test Data and Fixtures

### Test HTML Samples

```python
# tests/fixtures/html_samples.py
STATIC_HTML = """
<html>
    <head><title>Static Page</title></head>
    <body>
        <h1>Welcome</h1>
        <div class="content">
            <p>This is static content.</p>
        </div>
    </body>
</html>
"""

REACT_SPA_HTML = """
<html>
    <head>
        <script src="react.min.js"></script>
        <script src="react-dom.min.js"></script>
    </head>
    <body>
        <div id="root"></div>
        <script>
            ReactDOM.render(
                React.createElement('div', null, 'Hello React'),
                document.getElementById('root')
            );
        </script>
    </body>
</html>
"""

QUOTES_PAGE_HTML = """
<html>
    <body>
        <div class="quote">
            <span class="text">"The world as we have created it is a process of our thinking."</span>
            <small class="author">Albert Einstein</small>
            <div class="tags">
                <a class="tag">change</a>
                <a class="tag">deep-thoughts</a>
            </div>
        </div>
        <div class="quote">
            <span class="text">"It is our choices that show what we truly are."</span>
            <small class="author">J.K. Rowling</small>
            <div class="tags">
                <a class="tag">abilities</a>
                <a class="tag">choices</a>
            </div>
        </div>
    </body>
</html>
"""
```

### Configuration Fixtures

```python
# tests/conftest.py
import pytest
import tempfile
import os
from src.mcp_webscraper.config.settings import AppSettings

@pytest.fixture
def test_config():
    """Provide test configuration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config = AppSettings(
            output_dir=temp_dir,
            max_concurrent_jobs=2,
            max_playwright_instances=1,
            request_delay=0.1,  # Faster for testing
            debug=True,
            log_level="DEBUG"
        )
        yield config

@pytest.fixture
def test_output_dir():
    """Provide temporary output directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def sample_urls():
    """Provide sample URLs for testing."""
    return [
        "https://quotes.toscrape.com/page/1/",
        "https://quotes.toscrape.com/page/2/",
        "https://httpbin.org/html"
    ]
```

## Continuous Integration

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.9, 3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -e .
        pip install pytest pytest-asyncio pytest-cov
        playwright install chromium
    
    - name: Run unit tests
      run: |
        pytest tests/ -m "not integration" --cov=src/mcp_webscraper
    
    - name: Run integration tests
      run: |
        pytest tests/ -m "integration and not external" --cov=src/mcp_webscraper --cov-append
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Test Best Practices

### 1. Test Organization

```python
class TestWebScraperCore:
    """Group related tests in classes."""
    
    def setup_method(self):
        """Setup before each test method."""
        self.scraper = WebScraper()
    
    def teardown_method(self):
        """Cleanup after each test method."""
        asyncio.run(self.scraper.close())
    
    async def test_basic_functionality(self):
        """Test basic scraper functionality."""
        pass
    
    async def test_error_conditions(self):
        """Test error handling."""
        pass
```

### 2. Async Testing

```python
# Use pytest-asyncio for async tests
@pytest.mark.asyncio
async def test_async_function():
    """Test async functionality properly."""
    result = await some_async_function()
    assert result is not None

# Or use the class decorator
@pytest_asyncio.async_test
class TestAsyncClass:
    async def test_method(self):
        """Test method."""
        pass
```

### 3. Parametrized Testing

```python
@pytest.mark.parametrize("url,expected_js", [
    ("https://static-site.com", False),
    ("https://spa-app.com", True),
    ("https://mixed-content.com", True),
])
def test_js_detection(url, expected_js):
    """Test JS detection with multiple URLs."""
    # Mock the HTML content based on URL
    # Test detection logic
    pass
```

### 4. Failure Analysis

```python
def test_with_detailed_failure_info():
    """Provide detailed failure information."""
    try:
        result = scraper.process_data(test_data)
        assert result.success
        assert len(result.items) > 0
    except AssertionError:
        print(f"Test data: {test_data}")
        print(f"Result: {result}")
        print(f"Available methods: {dir(result)}")
        raise
```

## Manual Testing

### API Testing with curl

```bash
# Test basic scraping
curl -X POST "http://localhost:8000/scrape" \
  -H "Content-Type: application/json" \
  -d '{"input_type": "url", "target": "https://quotes.toscrape.com/"}'

# Test with custom selectors
curl -X POST "http://localhost:8000/scrape" \
  -H "Content-Type: application/json" \
  -d '{
    "input_type": "url",
    "target": "https://news.ycombinator.com/",
    "custom_selectors": {
      "container": ".athing",
      "title": ".titleline > a",
      "score": ".score"
    }
  }'

# Monitor job status
JOB_ID="your-job-id-here"
curl "http://localhost:8000/status/$JOB_ID"

# Get results
curl "http://localhost:8000/results/$JOB_ID"
```

### CLI Testing

```bash
# Test CLI with various options
python -m src.mcp_webscraper.cli scrape --url "https://quotes.toscrape.com/" --verbose

# Test file processing
echo '{"urls": ["https://quotes.toscrape.com/"]}' > test_urls.json
python -m src.mcp_webscraper.cli scrape --list-file test_urls.json

# Test error conditions
python -m src.mcp_webscraper.cli scrape --url "invalid-url"
python -m src.mcp_webscraper.cli scrape --list-file "nonexistent.json"
```

## Performance Benchmarking

```python
import time
import statistics

async def benchmark_scraping_speed():
    """Benchmark scraping performance."""
    urls = ["https://httpbin.org/html"] * 10
    times = []
    
    for url in urls:
        start = time.time()
        result = await scraper.scrape_url(url)
        end = time.time()
        times.append(end - start)
    
    print(f"Average time: {statistics.mean(times):.2f}s")
    print(f"Median time: {statistics.median(times):.2f}s")
    print(f"Min time: {min(times):.2f}s")
    print(f"Max time: {max(times):.2f}s")
```

This comprehensive testing guide ensures the MCP WebScraper is thoroughly validated across all functionality and use cases. 