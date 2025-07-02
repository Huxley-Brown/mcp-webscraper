"""Advanced error handling and recovery mechanisms."""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type, Union

import httpx
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from tenacity import (
    AsyncRetrying,
    RetryError,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
)

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Classification of error severity levels."""
    LOW = "low"           # Temporary issues, retry likely to succeed
    MEDIUM = "medium"     # Some failures, retry with caution
    HIGH = "high"         # Serious issues, retry unlikely to succeed
    CRITICAL = "critical" # Fatal errors, do not retry


class ErrorCategory(Enum):
    """Categories of errors for different handling strategies."""
    NETWORK = "network"           # Connection, timeout, DNS issues
    HTTP = "http"                # HTTP status codes (4xx, 5xx)
    PARSING = "parsing"           # HTML parsing errors
    JAVASCRIPT = "javascript"     # Playwright/JS execution errors
    RATE_LIMIT = "rate_limit"     # Rate limiting errors
    AUTHENTICATION = "auth"       # Authentication/authorization errors
    CONTENT = "content"           # Content validation errors
    SYSTEM = "system"             # System resource errors
    UNKNOWN = "unknown"           # Unclassified errors


class ScrapingError(Exception):
    """Base exception for scraping-related errors."""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        url: Optional[str] = None,
        original_error: Optional[Exception] = None,
        retry_after: Optional[float] = None,
    ):
        """
        Initialize scraping error.
        
        Args:
            message: Human-readable error message
            category: Error category for handling strategy
            severity: Error severity level
            url: URL where error occurred
            original_error: Original exception that caused this error
            retry_after: Suggested delay before retry (seconds)
        """
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.url = url
        self.original_error = original_error
        self.retry_after = retry_after
        self.timestamp = time.time()


class NetworkError(ScrapingError):
    """Network-related errors (connection, DNS, timeout)."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.NETWORK)
        kwargs.setdefault('severity', ErrorSeverity.LOW)
        super().__init__(message, **kwargs)


class HTTPError(ScrapingError):
    """HTTP status code errors."""
    
    def __init__(self, message: str, status_code: int, **kwargs):
        kwargs.setdefault('category', ErrorCategory.HTTP)
        
        # Set severity based on status code
        if 400 <= status_code < 500:
            kwargs.setdefault('severity', ErrorSeverity.HIGH if status_code == 429 else ErrorSeverity.CRITICAL)
        else:  # 5xx errors
            kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        
        super().__init__(message, **kwargs)
        self.status_code = status_code


class RateLimitError(ScrapingError):
    """Rate limiting errors."""
    
    def __init__(self, message: str, retry_after: Optional[float] = None, **kwargs):
        kwargs.setdefault('category', ErrorCategory.RATE_LIMIT)
        kwargs.setdefault('severity', ErrorSeverity.LOW)
        kwargs.setdefault('retry_after', retry_after)
        super().__init__(message, **kwargs)


class JavaScriptError(ScrapingError):
    """JavaScript execution errors."""
    
    def __init__(self, message: str, **kwargs):
        kwargs.setdefault('category', ErrorCategory.JAVASCRIPT)
        kwargs.setdefault('severity', ErrorSeverity.MEDIUM)
        super().__init__(message, **kwargs)


class ErrorClassifier:
    """Classifies exceptions into appropriate scraping error types."""
    
    @staticmethod
    def classify_exception(exception: Exception, url: Optional[str] = None) -> ScrapingError:
        """
        Classify an exception into appropriate ScrapingError.
        
        Args:
            exception: Original exception
            url: URL where error occurred
            
        Returns:
            Classified ScrapingError
        """
        if isinstance(exception, ScrapingError):
            return exception
        
        # HTTPX errors
        if isinstance(exception, httpx.TimeoutException):
            return NetworkError(
                f"Request timeout: {exception}",
                url=url,
                original_error=exception,
                retry_after=5.0
            )
        elif isinstance(exception, httpx.ConnectError):
            return NetworkError(
                f"Connection error: {exception}",
                url=url,
                original_error=exception,
                retry_after=10.0
            )
        elif isinstance(exception, httpx.HTTPStatusError):
            if exception.response.status_code == 429:
                # Try to extract retry-after header
                retry_after = None
                if 'retry-after' in exception.response.headers:
                    try:
                        retry_after = float(exception.response.headers['retry-after'])
                    except ValueError:
                        retry_after = 60.0  # Default to 60 seconds
                
                return RateLimitError(
                    f"Rate limited (429): {exception}",
                    url=url,
                    original_error=exception,
                    retry_after=retry_after
                )
            else:
                return HTTPError(
                    f"HTTP {exception.response.status_code}: {exception}",
                    status_code=exception.response.status_code,
                    url=url,
                    original_error=exception
                )
        
        # Playwright errors
        elif isinstance(exception, PlaywrightTimeoutError):
            return JavaScriptError(
                f"Playwright timeout: {exception}",
                url=url,
                original_error=exception,
                retry_after=15.0
            )
        elif isinstance(exception, PlaywrightError):
            return JavaScriptError(
                f"Playwright error: {exception}",
                url=url,
                original_error=exception,
                severity=ErrorSeverity.HIGH
            )
        
        # Network-level errors
        elif isinstance(exception, (ConnectionError, OSError)):
            return NetworkError(
                f"Network error: {exception}",
                url=url,
                original_error=exception,
                retry_after=10.0
            )
        
        # Memory/system errors
        elif isinstance(exception, MemoryError):
            return ScrapingError(
                f"Memory error: {exception}",
                category=ErrorCategory.SYSTEM,
                severity=ErrorSeverity.CRITICAL,
                url=url,
                original_error=exception
            )
        
        # Generic errors
        else:
            return ScrapingError(
                f"Unknown error: {exception}",
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.MEDIUM,
                url=url,
                original_error=exception
            )


class CircuitBreaker:
    """Circuit breaker pattern implementation for failing services."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
            expected_exception: Exception type that triggers circuit breaking
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: When circuit is open or function fails
        """
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
                logger.info("Circuit breaker entering HALF_OPEN state")
            else:
                raise ScrapingError(
                    f"Circuit breaker is OPEN (failures: {self.failure_count})",
                    category=ErrorCategory.SYSTEM,
                    severity=ErrorSeverity.HIGH
                )
        
        try:
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            self._on_success()
            return result
            
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to reset."""
        return (
            self.last_failure_time is not None and
            time.time() - self.last_failure_time >= self.recovery_timeout
        )
    
    def _on_success(self):
        """Handle successful function execution."""
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            logger.info("Circuit breaker reset to CLOSED state")
        
        self.failure_count = 0
        self.last_failure_time = None
    
    def _on_failure(self):
        """Handle failed function execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


class RetryStrategy:
    """Advanced retry strategies for different error types."""
    
    @staticmethod
    def get_retry_config(error: ScrapingError) -> Dict[str, Any]:
        """
        Get retry configuration based on error type.
        
        Args:
            error: Classified scraping error
            
        Returns:
            Retry configuration for tenacity
        """
        base_config = {
            'reraise': True,
            'before_sleep': before_sleep_log(logger, logging.INFO),
        }
        
        if error.severity == ErrorSeverity.CRITICAL:
            # Don't retry critical errors
            return {**base_config, 'stop': stop_after_attempt(1)}
        
        elif error.category == ErrorCategory.RATE_LIMIT:
            # Longer waits for rate limiting
            wait_time = error.retry_after or 60.0
            return {
                **base_config,
                'stop': stop_after_attempt(3),
                'wait': wait_fixed(wait_time),
                'retry': retry_if_exception_type(RateLimitError),
            }
        
        elif error.category == ErrorCategory.NETWORK:
            # Exponential backoff for network errors
            return {
                **base_config,
                'stop': stop_after_attempt(5),
                'wait': wait_exponential(multiplier=1, min=2, max=30),
                'retry': retry_if_exception_type(NetworkError),
            }
        
        elif error.category == ErrorCategory.JAVASCRIPT:
            # Moderate retry for JS errors
            return {
                **base_config,
                'stop': stop_after_attempt(3),
                'wait': wait_exponential(multiplier=2, min=5, max=60),
                'retry': retry_if_exception_type(JavaScriptError),
            }
        
        elif error.category == ErrorCategory.HTTP:
            if error.severity == ErrorSeverity.HIGH:
                # Limited retry for client errors
                return {
                    **base_config,
                    'stop': stop_after_attempt(2),
                    'wait': wait_fixed(5),
                }
            else:
                # Standard retry for server errors
                return {
                    **base_config,
                    'stop': stop_after_attempt(4),
                    'wait': wait_exponential(multiplier=1, min=1, max=20),
                }
        
        else:
            # Default retry strategy
            return {
                **base_config,
                'stop': stop_after_attempt(3),
                'wait': wait_exponential(multiplier=1, min=1, max=10),
            }


class ErrorHandler:
    """Comprehensive error handling coordinator."""
    
    def __init__(self):
        """Initialize error handler."""
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.error_stats: Dict[str, int] = {}
        self.classifier = ErrorClassifier()
    
    def get_circuit_breaker(self, key: str) -> CircuitBreaker:
        """Get or create circuit breaker for a key (e.g., domain)."""
        if key not in self.circuit_breakers:
            self.circuit_breakers[key] = CircuitBreaker()
        return self.circuit_breakers[key]
    
    async def handle_with_retry(
        self,
        func: Callable,
        *args,
        circuit_breaker_key: Optional[str] = None,
        url: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with comprehensive error handling and retry.
        
        Args:
            func: Function to execute
            *args: Function arguments
            circuit_breaker_key: Key for circuit breaker (e.g., domain)
            url: URL for error context
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        circuit_breaker = None
        if circuit_breaker_key:
            circuit_breaker = self.get_circuit_breaker(circuit_breaker_key)
        
        try:
            if circuit_breaker:
                return await circuit_breaker.call(func, *args, **kwargs)
            else:
                return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                
        except Exception as e:
            # Classify the error
            classified_error = self.classifier.classify_exception(e, url)
            
            # Update statistics
            error_key = f"{classified_error.category.value}_{classified_error.severity.value}"
            self.error_stats[error_key] = self.error_stats.get(error_key, 0) + 1
            
            # Get retry configuration
            retry_config = RetryStrategy.get_retry_config(classified_error)
            
            # Log the error
            logger.warning(
                f"Error occurred: {classified_error.category.value} "
                f"({classified_error.severity.value}) - {classified_error}"
            )
            
            # Apply retry strategy
            try:
                async for attempt in AsyncRetrying(**retry_config):
                    with attempt:
                        if circuit_breaker:
                            return await circuit_breaker.call(func, *args, **kwargs)
                        else:
                            return await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
                            
            except RetryError:
                logger.error(f"All retry attempts failed for {url or 'unknown URL'}")
                raise classified_error
    
    def get_error_stats(self) -> Dict[str, int]:
        """Get error statistics."""
        return self.error_stats.copy()
    
    def reset_circuit_breakers(self):
        """Reset all circuit breakers."""
        for cb in self.circuit_breakers.values():
            cb.failure_count = 0
            cb.last_failure_time = None
            cb.state = "CLOSED" 