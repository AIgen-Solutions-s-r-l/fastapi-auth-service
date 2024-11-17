# app/tests/conftest.py
import pytest
import warnings

def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers",
        "asyncio: mark test as async test",
    )
    """Configure pytest with warning filters."""
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message="'crypt' is deprecated"
    )
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        module="motor"
    )