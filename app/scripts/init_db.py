# app/scripts/init_db.py
import asyncio
import sys
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import Base and engine
from app.core.base import Base
from app.core.database import engine
from app.models.user import User  # Import User model explicitly
from sqlalchemy import text


async def init_test_db():
    """
    Initialize the test database by creating all tables defined in the models.
    """
    try:
        # Log tables before creation
        logger.info("Tables before creation: %s", Base.metadata.tables.keys())

        async with engine.begin() as conn:
            # Drop all tables (optional, only if you want a fresh start)
            await conn.run_sync(Base.metadata.drop_all)

            # Create all tables based on the models defined in Base
            await conn.run_sync(Base.metadata.create_all)

            # Verify table creation
            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            result = await conn.execute(query)
            tables = result.fetchall()
            logger.info("Created tables in database: %s", tables)

            logger.info("Test database initialized successfully.")

    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise


def main():
    """
    Main function to run the database initialization
    """
    try:
        asyncio.run(init_test_db())
    except KeyboardInterrupt:
        logger.info("Database initialization interrupted")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()