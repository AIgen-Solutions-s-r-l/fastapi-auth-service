# tests/conftest.py
import pytest
import logging

logging.basicConfig(level=logging.INFO)

pytest_plugins = ['pytest_asyncio']

def pytest_configure(config):
    """Configure pytest"""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as async"
    )