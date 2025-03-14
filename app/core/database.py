import os
import asyncio
import time
from typing import AsyncGenerator, Optional, Dict, Any

from app.core.config import settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.log.logging import logger
from app.core.db_utils import (
    with_exponential_backoff,
    classify_exception,
    healthcheck_database
)
from app.core.db_exceptions import (
    ConnectionRefusedError,
    ConnectionLostError,
    ConnectionTimeoutError
)

# Get the appropriate database URL based on environment
database_url = settings.test_database_url if os.getenv(
    "PYTEST_RUNNING") == "true" else settings.database_url

# Connection pool settings
pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
pool_recycle = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 minutes

# Log database initialization
logger.info(
    "Database initialization",
    event_type="database_init",
    database_url=database_url,
    test_mode=os.getenv("PYTEST_RUNNING") == "true",
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=pool_timeout,
    pool_recycle=pool_recycle
)

# Create engine with enhanced connection pool settings
engine = create_async_engine(
    database_url,
    echo=True,
    pool_size=pool_size,
    max_overflow=max_overflow,
    pool_timeout=pool_timeout,
    pool_recycle=pool_recycle,
    pool_pre_ping=True  # Verify connections before usage
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False
)

# Track connection status for service degradation decisions
_last_connection_error: Optional[float] = None
_connection_error_count: int = 0
_in_degraded_mode: bool = False
MAX_ERROR_COUNT_BEFORE_DEGRADATION = 3
ERROR_RESET_PERIOD = 300  # 5 minutes


@with_exponential_backoff(max_retries=3, initial_delay=0.5, max_delay=5.0)
async def get_db() -> AsyncGenerator:
    """Dependency to obtain a new database session for each request."""
    global _last_connection_error, _connection_error_count, _in_degraded_mode
    
    try:
        async with AsyncSessionLocal() as session:
            # Session created successfully, reset error counters
            if _last_connection_error is not None:
                # Check if we should reset error count based on time
                current_time = time.time()
                if current_time - _last_connection_error > ERROR_RESET_PERIOD:
                    _connection_error_count = 0
                    _last_connection_error = None
                    if _in_degraded_mode:
                        _in_degraded_mode = False
                        logger.info(
                            "Exiting database degraded mode after successful connection",
                            event_type="db_degraded_mode_exit"
                        )
            
            logger.debug(
                "Database session created",
                event_type="db_session_created"
            )
            yield session
            logger.debug("Database session closed", event_type="db_session_closed")
            
    except SQLAlchemyError as e:
        # Track connection errors for service degradation
        current_time = time.time()
        _last_connection_error = current_time
        _connection_error_count += 1
        
        # Check if we should enter degraded mode
        if (not _in_degraded_mode and 
            _connection_error_count >= MAX_ERROR_COUNT_BEFORE_DEGRADATION):
            _in_degraded_mode = True
            logger.warning(
                "Entering database degraded mode after multiple connection failures",
                event_type="db_degraded_mode_enter",
                error_count=_connection_error_count
            )
        
        # Classify the exception and get error details
        exception_class, error_details = classify_exception(e)
        
        # Enhanced error logging with structured data
        logger.error(
            "Database session error",
            event_type="db_session_error",
            error_type=type(e).__name__,
            error_details=str(e),
            classified_as=exception_class.__name__,
            in_degraded_mode=_in_degraded_mode,
            error_count=_connection_error_count,
            **error_details
        )
        
        # Let the decorator handle retries and proper exception raising
        raise


async def check_db_health() -> Dict[str, Any]:
    """Check database health and return status information."""
    try:
        async with AsyncSessionLocal() as session:
            return await healthcheck_database(session)
    except Exception as e:
        exception_class, error_details = classify_exception(e)
        return {
            "status": "unhealthy",
            "error": str(e),
            "error_type": exception_class.__name__,
            "in_degraded_mode": _in_degraded_mode,
            "error_count": _connection_error_count,
            "error_details": error_details
        }
