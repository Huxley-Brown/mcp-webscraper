# MCP WebScraper

A local web scraping service with dynamic page support, designed as an MCP (Model Context Protocol) server for AI agents.

## Features

- **Static & Dynamic Content**: Handles both regular HTML and JavaScript-heavy pages
- **MCP-Compatible**: REST API designed for AI agent integration
- **Command Line Interface**: Direct CLI usage for batch operations
- **Non-blocking**: Asynchronous job processing with status tracking
- **Local-only**: No external dependencies or cloud services required
- **Configurable**: Resource limits, anti-scraping measures, and output formats

## Architecture

- **FastAPI** REST server with async job processing
- **HTTPX** for efficient HTTP requests with HTTP/2 support
- **Playwright** for JavaScript-heavy pages (headless Chromium)
- **BeautifulSoup + lxml** for robust HTML parsing
- **Typer** for the command-line interface
- **AsyncIO** for concurrent scraping operations

## Installation

### Requirements

- Python 3.9 or higher
- ~200MB disk space for Playwright browsers

### Setup

1. **Clone and install**:
   ```bash
   git clone <repository-url>
   cd webscraper
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```

2. **Install Playwright browsers**:
   ```bash
   python -m playwright install chromium
   ```

## Usage

### CLI Interface

**Single URL**:
```bash
mcp-scraper scrape --url https://quotes.toscrape.com/
```

**Batch from file**:
```bash
mcp-scraper scrape --list-file inputs/urls.json --output-dir ./results
```

**Input file formats**:

JSON:
```json
[
  {"url": "https://quotes.toscrape.com/"},
  {"url": "https://httpbin.org/html"}
]
```

CSV:
```csv
url
https://quotes.toscrape.com/
https://httpbin.org/html
```

### REST API

**Start the server**:
```bash
uvicorn mcp_webscraper.api.main:app --reload
```

**Submit a job**:
```bash
curl -X POST "http://localhost:8000/scrape" \
     -H "Content-Type: application/json" \
     -d '{
           "input_type": "url",
           "target": "https://quotes.toscrape.com/",
           "output_dir": "./scrapes_out"
         }'
```

**Check status**:
```bash
curl "http://localhost:8000/status/{job_id}"
```

**Get results**:
```bash
curl "http://localhost:8000/results/{job_id}"
```

### API Endpoints

- `POST /scrape` - Submit scraping job
- `GET /status/{job_id}` - Check job status  
- `GET /results/{job_id}` - Download results
- `GET /jobs` - List recent jobs
- `GET /docs` - Interactive API documentation

## Output Format

Results are saved as JSON files with the structure:

```json
{
  "job_id": "9b5328c8",
  "source_url": "https://quotes.toscrape.com/",
  "scrape_timestamp": "2025-01-20T11:14:23Z",
  "status": "completed",
  "extraction_method": "static|dynamic",
  "data": [
    {
      "quote": "The world as we have created it...",
      "author": "Albert Einstein",
      "tags": ["change", "deep-thoughts", "thinking", "world"]
    }
  ]
}
```

## Configuration

### Environment Variables

Create a `.env` file:

```env
# Server settings
HOST=0.0.0.0
PORT=8000
OUTPUT_DIR=./scrapes_out

# Resource limits
MAX_CONCURRENT_JOBS=5
MAX_PLAYWRIGHT_INSTANCES=3
MAX_QUEUE_SIZE=100

# Anti-scraping
USER_AGENT_ROTATION=true
RESPECT_ROBOTS_TXT=true
REQUEST_DELAY=1.0
```

### Command Line Options

```bash
mcp-scraper scrape --help
```

## Development

### Install development dependencies:
```bash
pip install -e ".[dev]"
```

### Run tests:
```bash
pytest
```

### Code formatting:
```bash
black src/
isort src/
```

### Type checking:
```bash
mypy src/
```

## Project Structure

```
src/mcp_webscraper/
├── __init__.py
├── cli.py              # Command-line interface
├── api/                # FastAPI REST endpoints
├── core/               # Core scraping logic
├── jobs/               # Job queue and workers  
└── models/             # Pydantic data models
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

**Note**: This tool is designed for ethical web scraping. Always respect robots.txt, rate limits, and website terms of service. 