"""Tests for configuration management."""

import os
import pytest
from unittest.mock import patch
from pydantic import ValidationError

from src.mcp_webscraper.config.settings import AppSettings, get_settings


class TestAppSettings:
    """Test application settings and validation."""
    
    def test_default_settings(self):
        """Test default configuration values."""
        settings = AppSettings()
        
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.max_concurrent_jobs == 5
        assert settings.max_playwright_instances == 3
        assert settings.request_delay == 1.0
        assert settings.respect_robots_txt is True
        assert settings.user_agent_rotation is True
        assert settings.log_level == "INFO"
        assert settings.debug is False
    
    def test_environment_override(self):
        """Test environment variable overrides."""
        with patch.dict(os.environ, {
            'HOST': '127.0.0.1',
            'PORT': '9000',
            'MAX_CONCURRENT_JOBS': '10',
            'REQUEST_DELAY': '2.5',
            'LOG_LEVEL': 'DEBUG'
        }):
            settings = AppSettings()
            
            assert settings.host == "127.0.0.1"
            assert settings.port == 9000
            assert settings.max_concurrent_jobs == 10
            assert settings.request_delay == 2.5
            assert settings.log_level == "DEBUG"
    
    def test_validation_errors(self):
        """Test configuration validation."""
        # Test invalid concurrent jobs
        with patch.dict(os.environ, {'MAX_CONCURRENT_JOBS': '0'}):
            with pytest.raises(ValidationError):
                AppSettings()
        
        with patch.dict(os.environ, {'MAX_CONCURRENT_JOBS': '150'}):
            with pytest.raises(ValidationError):
                AppSettings()
        
        # Test invalid log level
        with patch.dict(os.environ, {'LOG_LEVEL': 'INVALID'}):
            with pytest.raises(ValidationError):
                AppSettings()
        
        # Test invalid request delay
        with patch.dict(os.environ, {'REQUEST_DELAY': '-1.0'}):
            with pytest.raises(ValidationError):
                AppSettings()
    
    def test_cors_origins_parsing(self):
        """Test CORS origins parsing."""
        # Single origin
        with patch.dict(os.environ, {'CORS_ORIGINS': 'https://example.com'}):
            settings = AppSettings()
            assert settings.get_cors_origins() == ['https://example.com']
        
        # Multiple origins
        with patch.dict(os.environ, {'CORS_ORIGINS': 'https://app.com,https://api.com'}):
            settings = AppSettings()
            origins = settings.get_cors_origins()
            assert 'https://app.com' in origins
            assert 'https://api.com' in origins
        
        # Wildcard
        with patch.dict(os.environ, {'CORS_ORIGINS': '*'}):
            settings = AppSettings()
            assert settings.get_cors_origins() == ['*']
    
    def test_custom_user_agents_parsing(self):
        """Test custom user agents parsing."""
        user_agents = "Mozilla/5.0 (Windows)...||Mozilla/5.0 (Macintosh)..."
        
        with patch.dict(os.environ, {'CUSTOM_USER_AGENTS': user_agents}):
            settings = AppSettings()
            parsed = settings.get_custom_user_agents()
            
            assert len(parsed) == 2
            assert "Mozilla/5.0 (Windows)..." in parsed
            assert "Mozilla/5.0 (Macintosh)..." in parsed
    
    def test_production_detection(self):
        """Test production mode detection."""
        # Development mode
        settings = AppSettings(debug=True, log_level="DEBUG")
        assert settings.is_production() is False
        
        # Production mode
        settings = AppSettings(debug=False, log_level="WARNING")
        assert settings.is_production() is True
        
        settings = AppSettings(debug=False, log_level="ERROR")
        assert settings.is_production() is True
    
    def test_config_generators(self):
        """Test configuration dict generators."""
        settings = AppSettings()
        
        # Test scraper config
        scraper_config = settings.get_scraper_config()
        required_keys = [
            'timeout', 'max_retries', 'respect_robots', 
            'request_delay', 'user_agent_rotation', 
            'max_concurrent_per_domain'
        ]
        for key in required_keys:
            assert key in scraper_config
        
        # Test job manager config
        job_config = settings.get_job_manager_config()
        required_keys = [
            'max_concurrent_jobs', 'max_playwright_instances',
            'max_queue_size', 'output_dir'
        ]
        for key in required_keys:
            assert key in job_config
        
        # Test anti-scraping config
        anti_scraping_config = settings.get_anti_scraping_config()
        required_keys = [
            'respect_robots_txt', 'user_agent_rotation',
            'default_delay', 'max_concurrent_per_domain'
        ]
        for key in required_keys:
            assert key in anti_scraping_config
    
    def test_log_file_path(self):
        """Test log file path handling."""
        # No log file
        settings = AppSettings()
        assert settings.get_log_file_path() is None
        
        # With log file
        with patch.dict(os.environ, {'LOG_FILE': 'logs/app.log'}):
            settings = AppSettings()
            log_path = settings.get_log_file_path()
            assert log_path is not None
            assert str(log_path) == 'logs/app.log'


class TestSettingsCache:
    """Test settings caching functionality."""
    
    def test_settings_caching(self):
        """Test that get_settings() returns cached instance."""
        # Clear any existing cache
        get_settings.cache_clear()
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should be the same instance due to caching
        assert settings1 is settings2
    
    def test_cache_with_environment_changes(self):
        """Test cache behavior with environment changes."""
        get_settings.cache_clear()
        
        # Get initial settings
        settings1 = get_settings()
        initial_port = settings1.port
        
        # Change environment (cache won't reflect this)
        with patch.dict(os.environ, {'PORT': '9999'}):
            settings2 = get_settings()
            # Should still be cached value
            assert settings2.port == initial_port
        
        # Clear cache and try again
        get_settings.cache_clear()
        with patch.dict(os.environ, {'PORT': '9999'}):
            settings3 = get_settings()
            assert settings3.port == 9999


class TestConfigValidation:
    """Test configuration validation rules."""
    
    def test_resource_limits_validation(self):
        """Test resource limit validation."""
        # Valid ranges
        settings = AppSettings(
            max_concurrent_jobs=10,
            max_playwright_instances=5,
            request_delay=0.5
        )
        assert settings.max_concurrent_jobs == 10
        assert settings.max_playwright_instances == 5
        assert settings.request_delay == 0.5
        
        # Invalid Playwright instances (too high)
        with pytest.raises(ValidationError):
            AppSettings(max_playwright_instances=25)
        
        # Invalid request delay (too high)
        with pytest.raises(ValidationError):
            AppSettings(request_delay=120.0)
    
    def test_output_directory_creation(self):
        """Test output directory creation during validation."""
        import tempfile
        import shutil
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "test_output")
            
            # Directory shouldn't exist initially
            assert not os.path.exists(output_path)
            
            # Creating settings should create the directory
            settings = AppSettings(output_dir=output_path)
            assert os.path.exists(output_path)
            assert os.path.isdir(output_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 