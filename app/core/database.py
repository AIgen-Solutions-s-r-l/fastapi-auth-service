import os
from app.core.config import Settings
from app.core.base import Base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.logging_config import LogConfig

logger = LogConfig.get_logger()
settings = Settings()

database_url = settings.test_database_url if os.getenv(
    "PYTEST_RUNNING") == "true" else settings.database_url
logger.info("Database initialization", extra={
    "event_type": "database_init",
    "database_url": database_url,
    "test_mode": os.getenv("PYTEST_RUNNING") == "true"
})

engine = create_async_engine(database_url, echo=True)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)


async def get_db():
    """Dependency to obtain a new database session for each request."""
    try:
        async with AsyncSessionLocal() as session:
            logger.debug("Database session created", extra={
                "event_type": "db_session_created"
            })
            yield session
            logger.debug("Database session closed", extra={
                "event_type": "db_session_closed"
            })
    except Exception as e:
        logger.error("Database session error", extra={
            "event_type": "db_session_error",
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        raise
