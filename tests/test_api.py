"""Tests for FastAPI endpoints."""

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from src.mcp_webscraper.api.main import app
from src.mcp_webscraper.models.schemas import JobStatus


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestAPIEndpoints:
    """Test FastAPI endpoint functionality."""
    
    def test_root_endpoint(self, client):
        """Test root endpoint returns correct information."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "MCP WebScraper"
        assert data["version"] == "0.1.0"
        assert data["status"] == "running"
        assert "environment" in data
    
    def test_config_endpoint(self, client):
        """Test configuration endpoint."""
        response = client.get("/config")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check that all major config sections are present
        required_sections = [
            "server", "resources", "scraping", 
            "circuit_breaker", "logging", "monitoring"
        ]
        for section in required_sections:
            assert section in data
        
        # Check some specific values
        assert data["server"]["host"] == "0.0.0.0"
        assert data["server"]["port"] == 8000
        assert data["resources"]["max_concurrent_jobs"] >= 1
        assert data["scraping"]["respect_robots_txt"] is True
    
    def test_stats_endpoint(self, client):
        """Test basic stats endpoint."""
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        required_keys = [
            "queued_jobs", "active_jobs", "total_jobs",
            "active_playwright_instances", "max_concurrent_jobs",
            "max_playwright_instances"
        ]
        
        for key in required_keys:
            assert key in data
            assert isinstance(data[key], int)
    
    def test_detailed_stats_endpoint(self, client):
        """Test detailed stats endpoint."""
        response = client.get("/stats/detailed")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "queue_stats" in data
        assert "scraping_stats" in data
        assert "error_patterns" in data
        assert "timestamp" in data
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] in ["healthy", "degraded"]
        assert "timestamp" in data
        assert "queue_size" in data
        assert "active_jobs" in data
    
    @patch('src.mcp_webscraper.api.main.job_manager')
    def test_scrape_endpoint_success(self, mock_job_manager, client):
        """Test successful job submission."""
        # Mock job manager
        mock_job_manager.submit_job = AsyncMock(return_value="test-job-123")
        
        request_data = {
            "input_type": "url",
            "target": "https://example.com",
            "output_dir": "./test_output"
        }
        
        response = client.post("/scrape", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "job_id" in data
        assert data["status"] == "queued"
        assert "message" in data
    
    def test_scrape_endpoint_validation(self, client):
        """Test request validation on scrape endpoint."""
        # Missing required fields
        response = client.post("/scrape", json={})
        assert response.status_code == 422
        
        # Invalid input_type
        invalid_request = {
            "input_type": "invalid",
            "target": "https://example.com"
        }
        response = client.post("/scrape", json=invalid_request)
        assert response.status_code == 422
    
    @patch('src.mcp_webscraper.api.main.job_manager')
    def test_job_status_endpoint(self, mock_job_manager, client):
        """Test job status retrieval."""
        from datetime import datetime
        from src.mcp_webscraper.models.schemas import JobStatusResponse
        
        # Mock job status
        mock_status = JobStatusResponse(
            job_id="test-job-123",
            status=JobStatus.COMPLETED,
            created_at=datetime.utcnow(),
            source_url="https://example.com",
            progress="Completed with 5 items"
        )
        mock_job_manager.get_job_status.return_value = mock_status
        
        response = client.get("/status/test-job-123")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "completed"
        assert data["source_url"] == "https://example.com"
    
    @patch('src.mcp_webscraper.api.main.job_manager')
    def test_job_status_not_found(self, mock_job_manager, client):
        """Test job status for non-existent job."""
        mock_job_manager.get_job_status.return_value = None
        
        response = client.get("/status/nonexistent-job")
        
        assert response.status_code == 404
        data = response.json()
        assert "Job nonexistent-job not found" in data["detail"]
    
    @patch('src.mcp_webscraper.api.main.job_manager')
    def test_list_jobs_endpoint(self, mock_job_manager, client):
        """Test jobs listing endpoint."""
        from src.mcp_webscraper.models.schemas import JobListResponse
        
        mock_response = JobListResponse(jobs=[], total=0)
        mock_job_manager.list_jobs.return_value = []
        mock_job_manager.jobs = {}
        
        response = client.get("/jobs")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "jobs" in data
        assert "total" in data
        assert isinstance(data["jobs"], list)
        assert isinstance(data["total"], int)
    
    def test_jobs_limit_parameter(self, client):
        """Test jobs endpoint with limit parameter."""
        response = client.get("/jobs?limit=10")
        assert response.status_code == 200
        
        # Test maximum limit
        response = client.get("/jobs?limit=200")
        assert response.status_code == 200
        # Should be capped at 100
    
    @patch('src.mcp_webscraper.api.main.job_manager')
    def test_cancel_job_endpoint(self, mock_job_manager, client):
        """Test job cancellation."""
        from datetime import datetime
        from src.mcp_webscraper.models.schemas import JobStatusResponse
        
        # Mock running job
        mock_status = JobStatusResponse(
            job_id="test-job-123",
            status=JobStatus.RUNNING,
            created_at=datetime.utcnow(),
            source_url="https://example.com"
        )
        mock_job_manager.get_job_status.return_value = mock_status
        
        response = client.delete("/jobs/test-job-123")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["job_id"] == "test-job-123"
        assert "cancelled" in data["message"].lower()
    
    @patch('src.mcp_webscraper.api.main.job_manager')
    def test_cancel_completed_job(self, mock_job_manager, client):
        """Test cancelling already completed job."""
        from datetime import datetime
        from src.mcp_webscraper.models.schemas import JobStatusResponse
        
        # Mock completed job
        mock_status = JobStatusResponse(
            job_id="test-job-123",
            status=JobStatus.COMPLETED,
            created_at=datetime.utcnow(),
            source_url="https://example.com"
        )
        mock_job_manager.get_job_status.return_value = mock_status
        
        response = client.delete("/jobs/test-job-123")
        
        assert response.status_code == 400
        data = response.json()
        assert "cannot be cancelled" in data["message"]


@pytest.mark.integration
class TestAPIIntegration:
    """Integration tests for complete API workflows."""
    
    def test_complete_scraping_workflow(self, client):
        """Test complete workflow from job submission to result retrieval."""
        # This would require actual job processing
        # In a real test environment, you might use a test database
        # and mock external HTTP calls
        pass
    
    def test_error_handling_in_api(self, client):
        """Test API error handling for various scenarios."""
        # Test file not found
        response = client.post("/scrape", json={
            "input_type": "file",
            "target": "/nonexistent/file.json"
        })
        # Should handle file not found gracefully
        
        # Test invalid URL format
        response = client.post("/scrape", json={
            "input_type": "url",
            "target": "not-a-valid-url"
        })
        # Should validate URL format


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 