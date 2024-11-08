# tests/conftest.py
import logging
import os

# Set test environment
os.environ["PYTEST_RUNNING"] = "true"

# Configure logging
logging.basicConfig(level=logging.INFO)

pytest_plugins = ['pytest_asyncio']

