# tests/conftest.py
import os
import logging
import pytest
import asyncio
from asyncio.events import AbstractEventLoop

# Set test environment
os.environ["PYTEST_RUNNING"] = "true"

# Configure logging
logging.basicConfig(level=logging.INFO)

pytest_plugins = ['pytest_asyncio']

@pytest.fixture(scope="session")
def event_loop() -> AbstractEventLoop:
    """Create an instance of the default event loop for each test case."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()