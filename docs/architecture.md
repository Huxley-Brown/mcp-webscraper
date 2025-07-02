## Project Title  
**Local “MCP” Web-Scraping Service with Dynamic-Page Support**

## Purpose & Objectives  
Build a **locally-run service** that can scrape both static HTML *and* JavaScript-heavy pages, expose its functionality through an MCP-style REST API, and allow command-line usage. It must run entirely on the developer’s hardware, queue jobs non-blockingly, return structured JSON, and be modular enough for downstream AI agents to orchestrate.

---

## 1 Technical Architecture  

### 1.1 Hardware / Software Stack  
| Layer | Technology | Rationale |
|-------|------------|-----------|
| OS & Hardware | Developer’s workstation / VM (Linux, macOS, Windows) | All tooling is cross-platform and local-only. |
| Language Runtime | **Python 3.9+** | Rich scraping & async ecosystem; compatible with AI tooling. |
| API Server | **FastAPI** (on Uvicorn) | ASGI, async-first, auto-generated OpenAPI docs. |
| CLI | **Typer** (Click-based) | Minimal boilerplate & rich help. |
| HTTP Client | **HTTPX (AsyncClient)** | HTTP/2, timeouts, connection pooling. |
| JS Renderer | **Playwright** | Multi-browser, async, faster & more modern than Selenium. |
| HTML Parser | **BeautifulSoup + lxml** | Robust parsing of malformed HTML. |
| Job Store | In-memory dict → **SQLite (optional)** | Quick prototyping; easy upgrade to file DB. |
| Output Store | Local filesystem (JSON per job) | Zero external dependency; AI-readable. |
| Concurrency | **asyncio + task queue** | Non-blocking I/O at scale. |
| Logging | Python `logging`, rotating file handler | Troubleshooting & audit. |

### 1.2 Major Components & Interactions  

1. **Interface Layer**  
   * *CLI*: validates flags (`--url` / `--list-file`) and posts jobs to API or runs inline.  
   * *REST API*: FastAPI endpoints `/scrape`, `/status/{id}`, `/results/{id}`, `/jobs`.

2. **Job Manager / Queue**  
   * Generates UUID job-IDs.  
   * Stores metadata (`status`, timestamps).  
   * Pushes jobs onto an `asyncio.Queue`.

3. **Worker Pool**  
   * Asynchronous coroutine or process per job.  
   * **Fetch stage**  
     * Tries HTTPX first; if JS detected (or forced) switches to Playwright.  
   * **Parse stage**  
     * Extracts user-defined selectors into structured JSON.  
   * **Persist stage**  
     * Writes `<OUTPUT_DIR>/<job_id>.json`, updates status.

4. **Result Store**  
   * Simple JSON files, one per job.  
   * Optional extra assets (HTML snapshot, screenshots) in sub-folder.

5. **Monitoring & Logging**  
   * Standard log plus optional Prometheus exporter for metrics.

**Data-flow (text diagram)**  

Client (CLI / REST) → Job Queue → Worker → Result JSON
↑ ↓
Status API ← Job Metadata ← Logger/DB


---

## 2 Key Goals, Constraints & Trade-Offs  

| Goal / Constraint | Design Choice | Trade-Offs |
|-------------------|--------------|------------|
| **Local-only** execution | All libs pure-Python + Playwright browsers installed locally | Heavier initial setup (≈ 200 MB). |
| **Dynamic page** support | Use Playwright headless Chromium | More CPU/RAM per job vs. pure HTTP. |
| **High concurrency** | `asyncio` coroutines & HTTP/2 | Needs careful resource limits to avoid DoS. |
| **Non-blocking API** | Background tasks / worker queue | Requires persistent job store for crash safety. |
| **Polite scraping** | Robots.txt check, rate-limit, UA rotation | Slightly slower but reduces blocks. |
| **AI-friendly output** | Stable JSON schema | Limits flexibility of site-specific schemas. |

---

## 3 Theoretical Context  

* **AsyncIO Event-Loop Model** – single-thread M:N task multiplexing; ideal for I/O bound work.  
* **Producer–Consumer Pattern** – queue mediates fast producers (API requests) and slower consumers (scrapers).  
* **HTTP/2 Multiplexing** – enabled in HTTPX for fewer TCP connections and head-of-line blocking prevention.  
* **Robots Exclusion Protocol** – scraper optionally parses `/robots.txt` and honours `Crawl-delay`.  
* **Exponential Back-off Retries** – via `tenacity` to mitigate transient 5xx network faults.  
* **Headless Browser Stealth** – Playwright context options reduce automation fingerprints.  

---

## 4 Key Assumptions / Dependencies  

* Python 3.9+ is pre-installed and developer can install OS-level Playwright browsers (`playwright install`).  
* Target sites are legally scrapable and do not strictly prohibit automated access.  
* Network bandwidth and CPU resources suffice for the planned concurrency level.  
* No external task broker (Redis, RabbitMQ) is required, but upgrading is architecturally straightforward.  