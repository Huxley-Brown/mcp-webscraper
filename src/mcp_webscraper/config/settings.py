"""Application settings and configuration management."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, validator
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings


class AppSettings(BaseSettings):
    """Application configuration settings."""
    
    # Server Configuration
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    reload: bool = Field(default=False, env="RELOAD")
    
    # Output Configuration
    output_dir: str = Field(default="./scrapes_out", env="OUTPUT_DIR")
    
    # Resource Limits
    max_concurrent_jobs: int = Field(default=5, env="MAX_CONCURRENT_JOBS")
    max_playwright_instances: int = Field(default=3, env="MAX_PLAYWRIGHT_INSTANCES")
    max_queue_size: int = Field(default=100, env="MAX_QUEUE_SIZE")
    max_concurrent_per_domain: int = Field(default=2, env="MAX_CONCURRENT_PER_DOMAIN")
    
    # Request Configuration
    default_timeout: int = Field(default=30, env="DEFAULT_TIMEOUT")
    max_retries: int = Field(default=3, env="MAX_RETRIES")
    request_delay: float = Field(default=1.0, env="REQUEST_DELAY")
    
    # Anti-scraping Configuration
    respect_robots_txt: bool = Field(default=True, env="RESPECT_ROBOTS_TXT")
    user_agent_rotation: bool = Field(default=True, env="USER_AGENT_ROTATION")
    custom_user_agents: Optional[str] = Field(default=None, env="CUSTOM_USER_AGENTS")
    
    # Circuit Breaker Configuration
    circuit_breaker_failure_threshold: int = Field(default=5, env="CIRCUIT_BREAKER_FAILURE_THRESHOLD")
    circuit_breaker_recovery_timeout: float = Field(default=60.0, env="CIRCUIT_BREAKER_RECOVERY_TIMEOUT")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(default=None, env="LOG_FILE")
    log_rotation_size: str = Field(default="10MB", env="LOG_ROTATION_SIZE")
    log_retention_count: int = Field(default=7, env="LOG_RETENTION_COUNT")
    
    # Development Configuration
    debug: bool = Field(default=False, env="DEBUG")
    enable_cors: bool = Field(default=True, env="ENABLE_CORS")
    cors_origins: str = Field(default="*", env="CORS_ORIGINS")
    
    # Security Configuration
    api_key: Optional[str] = Field(default=None, env="API_KEY")
    enable_rate_limiting: bool = Field(default=False, env="ENABLE_RATE_LIMITING")
    rate_limit_requests: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    rate_limit_window: int = Field(default=3600, env="RATE_LIMIT_WINDOW")  # seconds
    
    # Performance Configuration
    enable_compression: bool = Field(default=True, env="ENABLE_COMPRESSION")
    cache_ttl: int = Field(default=3600, env="CACHE_TTL")  # seconds
    
    # Monitoring Configuration
    enable_metrics: bool = Field(default=True, env="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, env="METRICS_PORT")
    health_check_interval: int = Field(default=30, env="HEALTH_CHECK_INTERVAL")  # seconds
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @validator("output_dir")
    def validate_output_dir(cls, v):
        """Ensure output directory exists."""
        Path(v).mkdir(parents=True, exist_ok=True)
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper
    
    @validator("cors_origins")
    def validate_cors_origins(cls, v):
        """Parse CORS origins."""
        if v == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",") if origin.strip()]
    
    @validator("custom_user_agents")
    def validate_custom_user_agents(cls, v):
        """Parse custom user agents."""
        if not v:
            return None
        return [ua.strip() for ua in v.split("||") if ua.strip()]
    
    @validator("max_concurrent_jobs")
    def validate_max_concurrent_jobs(cls, v):
        """Validate concurrent job limit."""
        if v < 1:
            raise ValueError("max_concurrent_jobs must be at least 1")
        if v > 100:
            raise ValueError("max_concurrent_jobs should not exceed 100")
        return v
    
    @validator("max_playwright_instances")
    def validate_max_playwright_instances(cls, v):
        """Validate Playwright instance limit."""
        if v < 1:
            raise ValueError("max_playwright_instances must be at least 1")
        if v > 20:
            raise ValueError("max_playwright_instances should not exceed 20")
        return v
    
    @validator("request_delay")
    def validate_request_delay(cls, v):
        """Validate request delay."""
        if v < 0:
            raise ValueError("request_delay cannot be negative")
        if v > 60:
            raise ValueError("request_delay should not exceed 60 seconds")
        return v
    
    def get_cors_origins(self) -> List[str]:
        """Get CORS origins as a list."""
        if isinstance(self.cors_origins, list):
            return self.cors_origins
        return [self.cors_origins]
    
    def get_custom_user_agents(self) -> Optional[List[str]]:
        """Get custom user agents as a list."""
        return self.custom_user_agents
    
    def get_log_file_path(self) -> Optional[Path]:
        """Get log file path."""
        if not self.log_file:
            return None
        return Path(self.log_file)
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug and self.log_level in ["WARNING", "ERROR"]
    
    def get_scraper_config(self) -> dict:
        """Get configuration dict for WebScraper initialization."""
        return {
            "timeout": self.default_timeout,
            "max_retries": self.max_retries,
            "respect_robots": self.respect_robots_txt,
            "request_delay": self.request_delay,
            "user_agent_rotation": self.user_agent_rotation,
            "max_concurrent_per_domain": self.max_concurrent_per_domain,
            "custom_user_agents": self.get_custom_user_agents(),
        }
    
    def get_job_manager_config(self) -> dict:
        """Get configuration dict for JobManager initialization."""
        return {
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_playwright_instances": self.max_playwright_instances,
            "max_queue_size": self.max_queue_size,
            "output_dir": self.output_dir,
        }
    
    def get_anti_scraping_config(self) -> dict:
        """Get configuration dict for AntiScrapingManager."""
        return {
            "respect_robots_txt": self.respect_robots_txt,
            "user_agent_rotation": self.user_agent_rotation,
            "default_delay": self.request_delay,
            "max_concurrent_per_domain": self.max_concurrent_per_domain,
            "custom_user_agents": self.get_custom_user_agents(),
        }
    
    def get_circuit_breaker_config(self) -> dict:
        """Get configuration dict for CircuitBreaker."""
        return {
            "failure_threshold": self.circuit_breaker_failure_threshold,
            "recovery_timeout": self.circuit_breaker_recovery_timeout,
        }


@lru_cache()
def get_settings() -> AppSettings:
    """Get application settings (cached)."""
    return AppSettings() 