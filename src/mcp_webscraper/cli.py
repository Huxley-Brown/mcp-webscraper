"""Command-line interface for MCP WebScraper."""

import asyncio
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .core import WebScraper
from .models.schemas import ScrapeRequest, InputType

# Configure rich console for better output
console = Console()
app = typer.Typer(
    name="mcp-scraper",
    help="MCP WebScraper - Local web scraping service with dynamic page support",
    no_args_is_help=True,
)

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors by default
    format='%(levelname)s: %(message)s'
)


@app.command()
def scrape(
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="Single URL to scrape"
    ),
    list_file: Optional[str] = typer.Option(
        None,
        "--list-file",
        "-f",
        help="File containing URLs to scrape (JSON or CSV format)"
    ),
    output_dir: str = typer.Option(
        "./scrapes_out",
        "--output-dir",
        "-o",
        help="Output directory for results"
    ),
    force_dynamic: bool = typer.Option(
        False,
        "--force-dynamic",
        "-d",
        help="Force use of Playwright for JavaScript rendering"
    ),
    custom_selectors: Optional[str] = typer.Option(
        None,
        "--selectors",
        "-s",
        help="Custom CSS selectors as JSON string"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging"
    ),
    timeout: int = typer.Option(
        30,
        "--timeout",
        "-t",
        help="Request timeout in seconds"
    ),
    delay: float = typer.Option(
        1.0,
        "--delay",
        help="Delay between requests in seconds"
    ),
):
    """
    Scrape websites and extract structured data.
    
    Examples:
        mcp-scraper scrape --url https://quotes.toscrape.com/
        mcp-scraper scrape --list-file urls.json --output-dir results/
        mcp-scraper scrape --url https://example.com --force-dynamic --verbose
    """
    # Configure logging level
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger("src.mcp_webscraper").setLevel(logging.INFO)
    
    # Validate input
    if not url and not list_file:
        console.print("[red]Error: Either --url or --list-file must be provided[/red]")
        raise typer.Exit(1)
    
    if url and list_file:
        console.print("[red]Error: Cannot specify both --url and --list-file[/red]")
        raise typer.Exit(1)
    
    # Parse custom selectors if provided
    selectors_dict = None
    if custom_selectors:
        try:
            selectors_dict = json.loads(custom_selectors)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing selectors JSON: {e}[/red]")
            raise typer.Exit(1)
    
    # Run the scraping
    try:
        asyncio.run(_run_scrape(
            url=url,
            list_file=list_file,
            output_dir=output_dir,
            force_dynamic=force_dynamic,
            custom_selectors=selectors_dict,
            timeout=timeout,
            delay=delay,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Scraping cancelled by user[/yellow]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    from . import __version__
    console.print(f"MCP WebScraper version {__version__}")


@app.command()
def validate(
    file: str = typer.Argument(..., help="Input file to validate (JSON or CSV)")
):
    """
    Validate input file format and show preview.
    
    Examples:
        mcp-scraper validate urls.json
        mcp-scraper validate urls.csv
    """
    try:
        file_path = Path(file)
        if not file_path.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        
        urls = _load_urls_from_file(str(file_path))
        
        console.print(f"[green]✓ File validation successful[/green]")
        console.print(f"Format: {file_path.suffix.upper()}")
        console.print(f"URLs found: {len(urls)}")
        
        # Show preview
        if urls:
            console.print("\n[bold]Preview (first 5 URLs):[/bold]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("#", style="dim", width=4)
            table.add_column("URL")
            
            for i, url in enumerate(urls[:5], 1):
                table.add_row(str(i), url)
            
            console.print(table)
            
            if len(urls) > 5:
                console.print(f"[dim]... and {len(urls) - 5} more URLs[/dim]")
        
    except Exception as e:
        console.print(f"[red]Validation failed: {e}[/red]")
        raise typer.Exit(1)


async def _run_scrape(
    url: Optional[str],
    list_file: Optional[str],
    output_dir: str,
    force_dynamic: bool,
    custom_selectors: Optional[dict],
    timeout: int,
    delay: float,
):
    """Run the scraping operation."""
    
    # Determine input type and targets
    if url:
        targets = [url]
        input_type = "url"
        source_desc = f"URL: {url}"
    else:
        targets = _load_urls_from_file(list_file)
        input_type = "file"
        source_desc = f"File: {list_file} ({len(targets)} URLs)"
    
    console.print(f"[bold blue]MCP WebScraper[/bold blue]")
    console.print(f"Source: {source_desc}")
    console.print(f"Output: {output_dir}")
    console.print(f"Method: {'Dynamic (Playwright)' if force_dynamic else 'Auto-detect'}")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Configure scraper
    scraper_config = {
        "timeout": timeout,
        "max_retries": 3,
        "request_delay": delay,
    }
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=False,
    ) as progress:
        
        # Add progress task
        task = progress.add_task("Initializing...", total=len(targets))
        
        async with WebScraper(**scraper_config) as scraper:
            all_results = []
            
            for i, target_url in enumerate(targets, 1):
                progress.update(task, description=f"Scraping {i}/{len(targets)}: {target_url}")
                
                try:
                    result = await scraper.scrape_url(
                        url=target_url,
                        force_dynamic=force_dynamic,
                        custom_selectors=custom_selectors,
                    )
                    
                    all_results.append(result)
                    
                    # Save individual result
                    result_file = output_path / f"{result.job_id}.json"
                    _save_result(result, result_file)
                    
                    console.print(
                        f"[green]✓[/green] {target_url} → {len(result.data)} items "
                        f"({result.extraction_method.value})"
                    )
                    
                    progress.advance(task)
                    
                except Exception as e:
                    console.print(f"[red]✗[/red] {target_url} → Error: {e}")
                    progress.advance(task)
                    continue
        
        progress.update(task, description="Completed")
    
    # Summary
    successful = [r for r in all_results if r.status == "completed"]
    total_items = sum(len(r.data) for r in successful)
    
    console.print(f"\n[bold green]Scraping Complete![/bold green]")
    console.print(f"Successfully scraped: {len(successful)}/{len(targets)} URLs")
    console.print(f"Total data items: {total_items}")
    console.print(f"Results saved to: {output_path}")
    
    # Show extraction methods used
    methods = {}
    for result in successful:
        method = result.extraction_method.value
        methods[method] = methods.get(method, 0) + 1
    
    if methods:
        console.print("\nExtraction methods used:")
        for method, count in methods.items():
            console.print(f"  {method}: {count} URLs")


def _load_urls_from_file(file_path: str) -> list[str]:
    """Load URLs from JSON or CSV file."""
    file_path_obj = Path(file_path)
    
    if not file_path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    urls = []
    
    if file_path.endswith('.json'):
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'url' in item:
                            urls.append(item['url'])
                        elif isinstance(item, str):
                            urls.append(item)
                else:
                    raise ValueError("JSON file must contain a list")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {e}")
    
    elif file_path.endswith('.csv'):
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            try:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'url' in row and row['url']:
                        urls.append(row['url'].strip())
            except Exception as e:
                raise ValueError(f"Error reading CSV file: {e}")
    
    else:
        raise ValueError(f"Unsupported file format. Use .json or .csv files.")
    
    if not urls:
        raise ValueError(f"No valid URLs found in file: {file_path}")
    
    return urls


def _save_result(result, output_file: Path):
    """Save scraping result to JSON file."""
    result_dict = result.model_dump(mode='json')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)


def main() -> None:
    """Main CLI entry point."""
    app()


if __name__ == "__main__":
    main() 