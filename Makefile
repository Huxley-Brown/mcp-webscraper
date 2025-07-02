.PHONY: help install install-dev setup test lint format type-check clean run

help:		## Show this help
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:	## Install package
	pip install -e .

install-dev:	## Install with development dependencies  
	pip install -e ".[dev]"

setup:		## Complete setup (install + browsers)
	pip install -e ".[dev]"
	python -m playwright install chromium

test:		## Run tests
	pytest

lint:		## Run linting
	flake8 src/

format:		## Format code
	black src/
	isort src/

type-check:	## Run type checking
	mypy src/

clean:		## Clean build artifacts
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

run:		## Run the API server
	uvicorn mcp_webscraper.api.main:app --reload

run-cli:	## Show CLI help
	mcp-scraper --help 