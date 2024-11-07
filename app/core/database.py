from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import Settings

# Load settings
settings = Settings()

# Create the asynchronous engine for PostgreSQL
engine = create_async_engine(settings.database_url, echo=True)

# Define an async session factory with the engine
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()

async def get_db():
    """
    Dependency to provide a new database session for each request.
    Uses the async session factory to yield a database session.

    Yields:
        AsyncSession: The database session.
    """
    async with AsyncSessionLocal() as session:
        yield session
