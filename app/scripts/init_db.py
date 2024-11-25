import asyncio
import sys
from pathlib import Path
from app.core.logging_config import LogConfig

# Add project root to Python path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app.core.base import Base
from app.core.database import engine
from app.models.user import User
from sqlalchemy import text

logger = LogConfig.get_logger()


async def init_test_db():
    """Initialize the test database by creating all tables defined in the models."""
    try:
        logger.info("Starting database initialization", extra={
            "event_type": "db_init_start",
            "tables": list(Base.metadata.tables.keys())
        })

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

            query = text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            result = await conn.execute(query)
            tables = result.fetchall()

            logger.info("Database tables created", extra={
                "event_type": "db_tables_created",
                "tables": [table[0] for table in tables]
            })

    except Exception as e:
        logger.error("Database initialization failed", extra={
            "event_type": "db_init_error",
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        raise


def main():
    """Main function to run the database initialization"""
    try:
        asyncio.run(init_test_db())
    except KeyboardInterrupt:
        logger.info("Database initialization interrupted", extra={
            "event_type": "db_init_interrupted"
        })
    except Exception as e:
        logger.error("Database initialization error", extra={
            "event_type": "db_init_error",
            "error_type": type(e).__name__,
            "error_details": str(e)
        })
        sys.exit(1)


if __name__ == "__main__":
    main()