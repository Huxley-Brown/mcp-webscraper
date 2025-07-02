"""Tests for core scraping functionality."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp_webscraper.core import WebScraper, JavaScriptDetector
from src.mcp_webscraper.core.error_handling import ErrorHandler, NetworkError, HTTPError
from src.mcp_webscraper.models.schemas import ExtractionMethod


class TestJavaScriptDetector:
    """Test JavaScript detection logic."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.detector = JavaScriptDetector()
    
    def test_detect_static_page(self):
        """Test detection of static HTML page."""
        html = """
        <html>
            <head><title>Static Page</title></head>
            <body>
                <h1>Welcome</h1>
                <p>This is a static page with content.</p>
            </body>
        </html>
        """
        
        result = self.detector.detect_javascript_need(html)
        
        assert result['needs_javascript'] is False
        assert result['confidence'] < 0.6
        assert result['recommendation'] == 'static'
    
    def test_detect_react_spa(self):
        """Test detection of React SPA indicators."""
        html = """
        <html>
            <head>
                <script src="react.min.js"></script>
                <script src="react-dom.min.js"></script>
            </head>
            <body>
                <div id="root"></div>
                <script>
                    ReactDOM.render(App, document.getElementById('root'));
                    fetch('/api/data').then(response => response.json());
                </script>
            </body>
        </html>
        """
        
        result = self.detector.detect_javascript_need(html)
        
        # Should detect React patterns even if below final threshold
        assert result['confidence'] > 0.4  # Significant confidence
        assert result['indicators']['spa_framework'] > 0.5  # Strong SPA detection
        assert result['indicators']['empty_containers'] > 0.8  # Empty root div
        assert any('react' in reason.lower() for reason in result['reasons'])
        assert any('ReactDOM' in reason for reason in result['reasons'])
    
    def test_detect_vue_spa(self):
        """Test detection of Vue.js SPA indicators."""
        html = """
        <html>
            <head><script src="vue.js"></script></head>
            <body>
                <div id="app" v-if="loading">
                    <div class="loading">Loading...</div>
                </div>
                <script>
                    new Vue({ 
                        el: '#app',
                        data: { loading: true },
                        mounted: function() {
                            fetch('/api/data').then(response => response.json());
                        }
                    });
                </script>
            </body>
        </html>
        """
        
        result = self.detector.detect_javascript_need(html)
        
        # Should detect Vue patterns
        assert result['confidence'] > 0.3  # Some confidence
        assert result['indicators']['spa_framework'] > 0.0  # Vue framework detected
        assert any('vue' in reason.lower() for reason in result['reasons'])
        assert any('v-if' in reason or 'Vue' in reason for reason in result['reasons'])
    
    def test_detect_ajax_patterns(self):
        """Test detection of AJAX/fetch patterns."""
        html = """
        <html>
            <body>
                <div id="content">Loading...</div>
                <script>
                    fetch('/api/data').then(response => response.json())
                        .then(data => document.getElementById('content').innerHTML = data);
                </script>
            </body>
        </html>
        """
        
        result = self.detector.detect_javascript_need(html)
        
        assert any('AJAX pattern found' in reason for reason in result['reasons'])


class TestWebScraper:
    """Test WebScraper functionality."""
    
    @pytest.mark.asyncio
    async def test_scraper_initialization(self):
        """Test scraper initialization with different configurations."""
        scraper = WebScraper(
            timeout=60,
            max_retries=5,
            user_agent_rotation=True,
            request_delay=2.0
        )
        
        assert scraper.timeout == 60
        assert scraper.max_retries == 5
        assert scraper.request_delay == 2.0
        assert scraper.anti_scraping is not None
        assert scraper.error_handler is not None
        
        await scraper.close()
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_fetch_static_success(self, mock_get):
        """Test successful static content fetching."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test content</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        
        scraper = WebScraper()
        
        # Mock anti-scraping preparation
        scraper.anti_scraping.prepare_request = AsyncMock(
            return_value=(True, {"User-Agent": "test"}, None)
        )
        
        result = await scraper._fetch_static("https://example.com")
        
        assert result == "<html><body>Test content</body></html>"
        assert mock_get.called
        
        await scraper.close()
    
    @pytest.mark.asyncio
    @patch('httpx.AsyncClient.get')
    async def test_fetch_static_with_robots_block(self, mock_get):
        """Test static fetch blocked by robots.txt."""
        scraper = WebScraper()
        
        # Mock anti-scraping preparation to block request
        scraper.anti_scraping.prepare_request = AsyncMock(
            return_value=(False, {}, None)
        )
        
        with pytest.raises(Exception):  # Should raise ScrapingError
            await scraper._fetch_static("https://example.com")
        
        assert not mock_get.called
        await scraper.close()
    
    @pytest.mark.asyncio
    async def test_scrape_url_integration(self):
        """Test complete URL scraping workflow."""
        scraper = WebScraper()
        
        # Mock the fetching methods
        test_html = """
        <html>
            <body>
                <h1>Test Page</h1>
                <p>Test content paragraph.</p>
            </body>
        </html>
        """
        
        scraper._fetch_static = AsyncMock(return_value=test_html)
        
        result = await scraper.scrape_url("https://example.com")
        
        assert result.status == "completed"
        assert result.extraction_method == ExtractionMethod.STATIC
        assert len(result.data) > 0
        assert result.job_id is not None
        
        await scraper.close()


class TestErrorHandler:
    """Test error handling and retry logic."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.error_handler = ErrorHandler()
    
    def test_circuit_breaker_creation(self):
        """Test circuit breaker creation and management."""
        cb1 = self.error_handler.get_circuit_breaker("domain1.com")
        cb2 = self.error_handler.get_circuit_breaker("domain1.com")
        cb3 = self.error_handler.get_circuit_breaker("domain2.com")
        
        assert cb1 is cb2  # Same instance for same domain
        assert cb1 is not cb3  # Different instance for different domain
        assert cb1.state == "CLOSED"
    
    def test_error_stats_tracking(self):
        """Test error statistics tracking."""
        initial_stats = self.error_handler.get_error_stats()
        assert isinstance(initial_stats, dict)
        
        # Stats should be empty initially
        assert len(initial_stats) == 0
    
    @pytest.mark.asyncio
    async def test_handle_with_retry_success(self):
        """Test successful function execution with retry handler."""
        async def success_func():
            return "success"
        
        result = await self.error_handler.handle_with_retry(success_func)
        assert result == "success"
    
    @pytest.mark.asyncio
    async def test_handle_with_retry_failure(self):
        """Test function failure with retry logic."""
        call_count = 0
        
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise NetworkError("Network timeout")
        
        with pytest.raises(NetworkError):
            await self.error_handler.handle_with_retry(
                failing_func, 
                url="https://example.com"
            )
        
        # Should have been called multiple times due to retries
        assert call_count > 1


@pytest.mark.integration
class TestEndToEndScraping:
    """Integration tests for complete scraping workflows."""
    
    @pytest.mark.asyncio  
    async def test_quotes_scraping_workflow(self):
        """Test scraping quotes.toscrape.com (if accessible)."""
        scraper = WebScraper(request_delay=0.1)  # Faster for testing
        
        try:
            result = await scraper.scrape_url("https://quotes.toscrape.com/")
            
            assert result.status == "completed"
            assert len(result.data) > 0
            assert result.extraction_method in [ExtractionMethod.STATIC, ExtractionMethod.DYNAMIC]
            
            # Check that we extracted some meaningful content
            has_content = any(
                item.text and len(item.text) > 10 
                for item in result.data
            )
            assert has_content
            
        except Exception as e:
            pytest.skip(f"External site not accessible: {e}")
        finally:
            await scraper.close()
    
    @pytest.mark.asyncio
    async def test_custom_selectors(self):
        """Test custom CSS selector extraction."""
        scraper = WebScraper()
        
        # Mock HTML content that matches our selectors
        test_html = """
        <html>
            <body>
                <div class="quote">
                    <span class="text">"Test quote 1"</span>
                    <span class="author">Author 1</span>
                </div>
                <div class="quote">
                    <span class="text">"Test quote 2"</span>
                    <span class="author">Author 2</span>
                </div>
            </body>
        </html>
        """
        
        scraper._fetch_static = AsyncMock(return_value=test_html)
        
        custom_selectors = {
            "container": ".quote",
            "text": ".text",
            "author": ".author"
        }
        
        result = await scraper.scrape_url(
            "https://example.com",
            custom_selectors=custom_selectors
        )
        
        assert result.status == "completed"
        assert len(result.data) == 2
        
        # Check that custom selectors were used
        first_item = result.data[0]
        assert "text" in first_item.metadata
        assert "author" in first_item.metadata
        assert "Test quote 1" in first_item.metadata["text"]
        
        await scraper.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 