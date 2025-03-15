"""Database utilities for connection management and error handling.

This module provides utilities for managing database connections, implementing
retry mechanisms with exponential backoff, error classification, and detailed logging.
"""

import asyncio
import random
import time
from functools import wraps
from typing import Dict, Any, Callable, TypeVar, Optional, Type, Tuple, Union, List

from sqlalchemy.exc import SQLAlchemyError, OperationalError, DatabaseError
from sqlalchemy.sql import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db_exceptions import (
    ConnectionRefusedError,
    ConnectionLostError,
    ConnectionTimeoutError,
    DatabaseAuthError,
    InsufficientResourcesError,
    IntegrityError,
    DataError,
    SystemError,
    DatabaseException,
    DatabaseErrorCode
)
from app.log.logging import logger

# Type variable for return type
T = TypeVar('T')

# Define exceptions that should be retried by default
retry_exceptions = [
    ConnectionRefusedError,
    ConnectionLostError,
    ConnectionTimeoutError,
    InsufficientResourcesError,
    OperationalError
]

# PostgreSQL error codes mapping to our custom error types
PG_ERROR_CODE_MAP = {
    # Connection errors
    '08001': ConnectionRefusedError,  # Unable to establish connection
    '08006': ConnectionLostError,     # Connection failure
    '08P01': ConnectionLostError,     # Protocol violation
    
    # Authentication errors
    '28P01': DatabaseAuthError,       # Invalid password
    '28000': DatabaseAuthError,       # Invalid authorization specification
    
    # Resource errors
    '53000': InsufficientResourcesError,  # Insufficient resources
    '53100': InsufficientResourcesError,  # Disk full
    '53200': InsufficientResourcesError,  # Out of memory
    '53300': InsufficientResourcesError,  # Too many connections
    '53400': InsufficientResourcesError,  # Configuration limit exceeded
    
    # Data errors - integrity constraints
    '23000': IntegrityError,          # Integrity constraint violation
    '23001': IntegrityError,          # Restrict violation
    '23502': IntegrityError,          # Not null violation
    '23503': IntegrityError,          # Foreign key violation
    '23505': IntegrityError,          # Unique violation
    '23514': IntegrityError,          # Check violation
    
    # Data errors - invalid data
    '22000': DataError,               # Data exception
    '22001': DataError,               # String data right truncation
    '22003': DataError,               # Numeric value out of range
    '22007': DataError,               # Invalid datetime format
    '22P02': DataError,               # Invalid text representation
    
    # System errors
    '57000': SystemError,             # Operator intervention
    '57014': SystemError,             # Query canceled
    '58000': SystemError,             # System error
    '58030': SystemError,             # IO error
    'XX000': SystemError,             # Internal error
}

def classify_exception(
    exc: Exception
) -> Tuple[Type[DatabaseException], Dict[str, Any]]:
    """Classify a database exception to a more specific error type.

    Args:
        exc: The exception to classify

    Returns:
        Tuple containing the exception class and error details
    """
    error_details = {
        "original_error": str(exc),
        "error_type": type(exc).__name__
    }
    
    # Handle SQLAlchemy errors
    if isinstance(exc, SQLAlchemyError):
        # Extract PostgreSQL error code if available
        pg_code = getattr(exc, 'pgcode', None)
        if pg_code:
            error_details["pg_code"] = pg_code
            exception_class = PG_ERROR_CODE_MAP.get(pg_code, DatabaseException)
            return exception_class, error_details
        
        # Specific SQLAlchemy error handling
        if isinstance(exc, OperationalError):
            error_str = str(exc).lower()
            
            if "connection refused" in error_str:
                return ConnectionRefusedError, error_details
            elif "timeout" in error_str:
                return ConnectionTimeoutError, error_details
            elif "lost connection" in error_str or "broken pipe" in error_str:
                return ConnectionLostError, error_details
            elif "authentication" in error_str or "password" in error_str:
                return DatabaseAuthError, error_details
            elif "too many connections" in error_str or "out of memory" in error_str:
                return InsufficientResourcesError, error_details
    
    # Socket/connection errors
    error_str = str(exc).lower()
    if "connection refused" in error_str:
        return ConnectionRefusedError, error_details
    elif "timeout" in error_str:
        return ConnectionTimeoutError, error_details
    elif "connection" in error_str and ("reset" in error_str or "closed" in error_str):
        return ConnectionLostError, error_details
    
    # Default generic database exception
    return DatabaseException, error_details


def with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 0.5,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retry_errors: Optional[List[Type[Exception]]] = None,
    jitter: bool = True
):
    """Decorator for retrying database operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Multiplier for delay after each retry
        retry_errors: List of exceptions that should trigger a retry
        jitter: Whether to add random jitter to delay
    
    Returns:
        Decorated function with retry logic
    """
    retry_error_types = retry_errors or retry_exceptions
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = initial_delay
            
            # Log the operation we're attempting
            func_name = func.__name__
            logger.debug(
                f"Attempting database operation: {func_name}",
                event_type="db_operation_attempt",
                operation=func_name
            )
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                
                except Exception as exc:
                    # Store last exception for potential re-raise
                    last_exception = exc
                    
                    # Classify the exception
                    exception_class, error_details = classify_exception(exc)
                    
                    # Check if we should retry this exception
                    should_retry = False
                    for retry_exc in retry_error_types:
                        if isinstance(exc, retry_exc) or exception_class == retry_exc:
                            should_retry = True
                            break
                    
                    # If we shouldn't retry or out of retries, raise appropriate exception
                    if not should_retry or attempt >= max_retries:
                        logger.error(
                            f"Database operation failed after {attempt + 1} attempts: {func_name}",
                            event_type="db_operation_failed",
                            operation=func_name,
                            attempts=attempt + 1,
                            error_type=type(exc).__name__,
                            error_details=error_details,
                            exception_class=exception_class.__name__
                        )
                        
                        # Raise our classified exception
                        if should_retry and attempt >= max_retries:
                            # We're out of retries for a retriable error
                            raise exception_class(
                                detail=f"Database operation failed after {attempt + 1} attempts",
                                error_details=error_details
                            )
                        else:
                            # Non-retriable error, raise with original details
                            raise exception_class(
                                detail=str(exc),
                                error_details=error_details
                            )
                    
                    # Calculate next delay with exponential backoff
                    jitter_value = random.uniform(0.8, 1.2) if jitter else 1.0
                    next_delay = min(delay * backoff_factor * jitter_value, max_delay)
                    
                    logger.warning(
                        f"Database operation attempt {attempt + 1}/{max_retries} failed, retrying in {next_delay:.2f}s: {func_name}",
                        event_type="db_operation_retry",
                        operation=func_name,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=next_delay,
                        error_type=type(exc).__name__,
                        error_details=error_details
                    )
                    
                    await asyncio.sleep(next_delay)
                    delay = next_delay
            
            # This should never happen, but added as a fallback
            raise last_exception
        
        return wrapper
    
    return decorator


async def healthcheck_database(db_session) -> Dict[str, Any]:
    """Perform a health check on the database.
    
    Args:
        db_session: SQLAlchemy async session
    
    Returns:
        Dictionary with health check results
    """
    start_time = time.time()
    try:
        # Simple query to test database connectivity
        result = await db_session.execute(text("SELECT 1"))
        row = result.scalar()
        
        response_time = time.time() - start_time
        
        return {
            "status": "healthy" if row == 1 else "degraded",
            "response_time_ms": round(response_time * 1000, 2),
            "message": "Database connection successful"
        }
    except Exception as exc:
        exception_class, error_details = classify_exception(exc)
        
        elapsed_time = time.time() - start_time
        
        logger.error(
            "Database health check failed",
            event_type="db_healthcheck_failed",
            error_type=exception_class.__name__,
            response_time_ms=round(elapsed_time * 1000, 2),
            error_details=error_details
        )
        
        return {
            "status": "unhealthy",
            "response_time_ms": round(elapsed_time * 1000, 2),
            "error": str(exc),
            "error_type": exception_class.__name__,
            "error_details": error_details
        }


@with_exponential_backoff(max_retries=3, initial_delay=0.5)
async def execute_db_operation(
    session: AsyncSession,
    operation: Callable[..., T],
    *args,
    **kwargs
) -> T:
    """Execute a database operation with retry logic.
    
    Args:
        session: SQLAlchemy async session
        operation: Database operation function to execute
        *args: Positional arguments for the operation
        **kwargs: Keyword arguments for the operation
    
    Returns:
        Result of the database operation
    """
    try:
        return await operation(session, *args, **kwargs)
    except Exception as exc:
        # Let the decorator handle retries and exception classification
        raise