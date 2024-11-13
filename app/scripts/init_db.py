# app/scripts/init_db.py
import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.base import Base
from app.core.database import engine
# Import models to register them with Base
import app.models


async def init_test_db():
    """
    Initialize the test database by creating all tables defined in the models.
    """
    try:
        async with engine.begin() as conn:
            # Drop all tables (optional, only if you want a fresh start)
            await conn.run_sync(Base.metadata.drop_all)

            # Create all tables based on the models defined in Base
            await conn.run_sync(Base.metadata.create_all)

            print("Test database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(init_test_db())