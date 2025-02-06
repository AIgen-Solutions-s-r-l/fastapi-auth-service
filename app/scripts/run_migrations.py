#!/usr/bin/env python3
import subprocess
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from app.core.config import settings

def wait_for_db():
    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")

    retries = 30
    while retries > 0:
        try:
            engine = create_engine(url)
            engine.connect()
            print("Database is ready!")
            return True
        except OperationalError:
            retries -= 1
            if retries == 0:
                print("Could not connect to the database. Exiting...")
                return False
            print(f"Database not ready. Waiting... ({retries} attempts left)")
            time.sleep(2)

def run_migrations():
    print("Running database migrations...")
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("Migrations completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running migrations: {e}")
        return False

if __name__ == "__main__":
    if not wait_for_db():
        sys.exit(1)
    if not run_migrations():
        sys.exit(1)
    sys.exit(0)