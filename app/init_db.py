import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.core.config import Settings
from app.models.user import Base

# Load the test database URL from settings
settings = Settings()
test_engine = create_async_engine(settings.database_url, echo=True)


async def init_test_db():
    """
    Initialize the test database by creating all tables defined in the models.
    """
    async with test_engine.begin() as conn:
        # Drop all tables (optional, only if you want a fresh start)
        await conn.run_sync(Base.metadata.drop_all)

        # Create all tables based on the models defined in Base
        await conn.run_sync(Base.metadata.create_all)

        print("Test database initialized successfully.")


# Run the initialization
if __name__ == "__main__":
    asyncio.run(init_test_db())