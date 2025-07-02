## Project Bootstrap & Environment

- [ ] Create Git repository & `.python-version`
  - **How**: `git init && echo "3.9" > .python-version`
  - **Why**: Ensures team uses consistent interpreter.

- [ ] Set up Python virtual environment
  - **How**: `python -m venv .venv && source .venv/bin/activate`
  - **Why**: Isolates dependencies, preventing version conflicts.

- [ ] Define `pyproject.toml` / `requirements.txt`
  - **How**: Include `fastapi`, `uvicorn[standard]`, `httpx`, `playwright`, `beautifulsoup4`, `lxml`, `typer`, `tenacity`, `python-dotenv`.
  - **Why**: Centralises dependency management; reproducible builds.

- [ ] Install Playwright browsers
  - **How**: `python -m playwright install chromium`
  - **Why**: Required runtime for JavaScript rendering.

---

## Core Scraper Library (`scraper/`)

- [ ] Implement async `fetch_static(url)`  
  - **How**: Use `httpx.AsyncClient.get()` with 10 s timeout.  
  - **Why**: Handles 80 % of pages w/out browser overhead.

- [ ] Implement async `fetch_dynamic(url)`  
  - **How**:  
    - Launch headless Chromium in a Playwright context.  
    - `page.goto(url, wait_until='networkidle', timeout=30_000)`  
    - Extract `page.content()` before closing browser.  
  - **Why**: Renders JS; `networkidle` ensures scripts finished.

- [ ] Build `detect_js_need(html)` heuristic  
  - **How**: Look for `<script src=...\.js>` plus empty `<div id="root">`.  
  - **Why**: Auto-route static vs dynamic.

- [ ] Implement `parse_quotes(html)` demo parser  
  - **How**: BeautifulSoup CSS selectors `.quote .text`, `.author`, `.tag`.  
  - **Why**: Proves end-to-end pipeline; template for new sites.

- [ ] Design `ResultSchema` (`pydantic.BaseModel`)  
  - **Fields**: `job_id`, `source_url`, `timestamp`, `status`, `data: list[dict]`.  
  - **Why**: Enforces consistency; enables auto-docs.

---

## Job Queue & Concurrency

- [ ] Create `Job` dataclass (uuid, target, status, started_at, finished_at)
  - **Why**: Single source of truth for metadata.

- [ ] Implement `asyncio.Queue` instance at module scope
  - **How**: `job_queue = asyncio.Queue(maxsize=N)`  
  - **Why**: Producer–consumer separation.

- [ ] Spawn worker task(s) on startup
  - **How**: `asyncio.create_task(worker_loop())` inside FastAPI startup event.
  - **Why**: Starts background processing without blocking API thread.

- [ ] Inside `worker_loop`
  - [ ] Pull job, update status → “running”.
  - [ ] Call scraper (`fetch_*` then `parse_*`).
  - [ ] Persist JSON to `<OUTPUT_DIR>/<job_id>.json`.
  - [ ] Update status → “completed” or “failed”; log exception.
  - **Supporting context**: Non-blocking ensures API stays responsive.

---

## REST API (FastAPI)

- [ ] Define `ScrapeRequest` & `ScrapeResponse` Pydantic models
  - **Why**: Strong input validation; OpenAPI docs auto-generate.

- [ ] Implement `POST /scrape`
  - **How**:  
    - Validate `input_type` (`url`/`file`).  
    - Generate `job_id`, push to `job_queue`.  
    - Return `{job_id, status: queued}`.
  - **Warnings**: Reject paths outside project root to prevent directory traversal.

- [ ] Implement `GET /status/{job_id}`
  - **How**: Lookup in job table; 404 if absent.
  - **Why**: Enables polling by downstream agent.

- [ ] Implement `GET /results/{job_id}`
  - **How**: Stream `FileResponse` if exists; 404 otherwise.
  - **Why**: Allows download once job is finished.

- [ ] Implement `GET /jobs`
  - **How**: Return list of last N job summaries.
  - **Why**: Simple dashboard for operators.

- [ ] Add Swagger & ReDoc docs auto-exposed
  - **How**: Provided by FastAPI at `/docs`.
  - **Why**: Human + AI discoverability.

---

## CLI (`mcp_scraper.py`)

- [ ] Scaffold Typer application
  - **Commands**: `scrape`, `version`.
  - **Options**: `--url`, `--list-file`, `--output-dir`.
  - **Why**: Mirrors API for local batch usage.

- [ ] For `scrape` command
  - [ ] Validate mutually exclusive `--url` vs `--list-file`.
  - [ ] If URL: call API `POST /scrape`.
  - [ ] If file: upload via API or iterate locally.
  - **Supporting theory**: Keeps a single execution path; DRY.

---

## Error Handling & Resilience

- [ ] Wrap fetch calls with `tenacity.retry`
  - **Params**: `wait=wait_exponential(multiplier=1, min=1, max=10)`, `stop=stop_after_attempt(5)`.
  - **Why**: Mitigates transient network errors.

- [ ] Capture `asyncio.TimeoutError`, `httpx.RequestError`, Playwright `TimeoutError`
  - **How**: Update job status → “failed”, log details.
  - **Warning**: Do **not** expose stack traces via API (security).

---

## Anti-Scraping & Politeness

- [ ] Rotate `User-Agent` header
  - **How**: Load list from `user_agents.txt`, choose per request.
  - **Why**: Reduces fingerprinting.

- [ ] Implement robots.txt check
  - **How**: Use `aiorobotstxt` to parse; skip disallowed paths.
  - **Why**: Ethical & reduces bans.

- [ ] Throttle per-domain concurrency
  - **How**: `asyncio.Semaphore(max_per_domain)`.
  - **Why**: Prevents overwhelming target hosts.

---

## Testing

- [ ] Unit-test parsers with pytest
  - **Why**: Prevent schema regressions.

- [ ] Integration test end-to-end on `<EXAMPLE_URL>`
  - **How**: Spin up FastAPI with `TestClient`; assert JSON shape.
  - **Why**: Ensures pipeline integrity.

---

## Documentation & Dev UX

- [ ] Write `README.md`
  - Sections: Installation, CLI usage, API docs link, sample input files.

- [ ] Create sample `inputs/urls.json` & `inputs/urls.csv`
  - **Why**: Quick start for users and CI.

- [ ] Add Makefile tasks (`make dev`, `make test`, `make run`)
  - **Why**: Simplifies common workflows.

---

## Packaging & Deployment

- [ ] Add `pyproject.toml` with Poetry metadata (optional)
  - **Why**: Enables `poetry install` and version pinning.

- [ ] Build Dockerfile (local optional)
  - **How**:  
    ```
    FROM python:3.9-slim  
    RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx ...  
    CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
    ```
  - **Why**: Encapsulates dependencies; reproducible across machines.

---

## Security & Maintenance

- [ ] Run dependency vulnerability scan (`pip-audit`)
  - **Why**: Catch known CVEs.

- [ ] Configure log rotation (10 MB, 7 files)
  - **How**: `logging.handlers.RotatingFileHandler`.
  - **Why**: Prevents disk exhaustion.

---

## Future Enhancements (Icebox)

- [ ] Swap in Redis + Celery for distributed queues.
- [ ] Add proxy pool management for heavy scraping.
- [ ] Implement custom browser-fingerprint obfuscation plugin.
- [ ] Real-time WebSocket progress stream in API.