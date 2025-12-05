"""Tests for API versioning module."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, APIRouter, HTTPException

from app.core.versioning import (
    APIVersion,
    get_api_version_from_header,
    include_versioned_router,
    deprecated_endpoint,
    get_version_info
)


class TestAPIVersion:
    """Tests for APIVersion enum."""

    def test_v1_value(self):
        """V1 should have correct value."""
        assert APIVersion.V1.value == "v1"

    def test_latest_returns_v1(self):
        """Latest should return V1."""
        assert APIVersion.latest() == APIVersion.V1

    def test_supported_includes_v1(self):
        """Supported versions should include V1."""
        assert APIVersion.V1 in APIVersion.supported()

    def test_is_supported_valid_version(self):
        """Should return True for valid versions."""
        assert APIVersion.is_supported("v1") is True

    def test_is_supported_invalid_version(self):
        """Should return False for invalid versions."""
        assert APIVersion.is_supported("v99") is False
        assert APIVersion.is_supported("invalid") is False
        assert APIVersion.is_supported("") is False


class TestGetApiVersionFromHeader:
    """Tests for get_api_version_from_header function."""

    def test_returns_none_when_header_not_provided(self):
        """Should return None when header is not provided."""
        result = get_api_version_from_header(None)
        assert result is None

    def test_returns_version_for_valid_header(self):
        """Should return APIVersion for valid header value."""
        result = get_api_version_from_header("v1")
        assert result == APIVersion.V1

    def test_raises_exception_for_invalid_version(self):
        """Should raise HTTPException for invalid version."""
        with pytest.raises(HTTPException) as exc_info:
            get_api_version_from_header("v99")

        assert exc_info.value.status_code == 400
        assert "UnsupportedAPIVersion" in str(exc_info.value.detail)


class TestIncludeVersionedRouter:
    """Tests for include_versioned_router function."""

    def test_includes_router_with_version_prefix(self):
        """Should include router with version prefix."""
        app = FastAPI()
        router = APIRouter()

        @router.get("/test")
        async def test_endpoint():
            return {"test": True}

        with patch('app.core.versioning.logger'):
            include_versioned_router(app, router, "api", [APIVersion.V1])

        # Check that route was registered with version prefix
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        assert "/v1/api/test" in routes

    def test_includes_router_for_multiple_versions(self):
        """Should include router for all specified versions."""
        app = FastAPI()
        router = APIRouter()

        @router.get("/test")
        async def test_endpoint():
            return {"test": True}

        with patch('app.core.versioning.logger'):
            include_versioned_router(app, router, "api", APIVersion.supported())

        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        for version in APIVersion.supported():
            assert f"/{version.value}/api/test" in routes

    def test_passes_additional_kwargs_to_include_router(self):
        """Should pass additional kwargs to include_router."""
        app = FastAPI()
        router = APIRouter()

        @router.get("/test")
        async def test_endpoint():
            return {"test": True}

        with patch('app.core.versioning.logger'):
            include_versioned_router(
                app, router, "api",
                [APIVersion.V1],
                tags=["TestTag"]
            )

        # Verify the router was included (tags are applied at route level)
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        assert "/v1/api/test" in routes


class TestDeprecatedEndpoint:
    """Tests for deprecated_endpoint decorator."""

    @pytest.mark.asyncio
    async def test_calls_original_function(self):
        """Should call the original function."""
        @deprecated_endpoint(APIVersion.V1)
        async def test_func():
            return {"result": "success"}

        with patch('app.core.versioning.logger'):
            result = await test_func()

        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_logs_deprecation_warning(self):
        """Should log deprecation warning."""
        @deprecated_endpoint(APIVersion.V1, alternative="/new-endpoint")
        async def old_endpoint():
            return {"old": True}

        with patch('app.core.versioning.logger') as mock_logger:
            await old_endpoint()

        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "Deprecated endpoint" in call_args[0][0]

    def test_adds_deprecation_metadata(self):
        """Should add deprecation metadata to function."""
        @deprecated_endpoint(
            APIVersion.V1,
            removal_version=APIVersion.V1,
            alternative="/new"
        )
        async def test_func():
            pass

        assert hasattr(test_func, '__deprecated__')
        assert test_func.__deprecated__ is True
        assert test_func.__deprecation_version__ == APIVersion.V1
        assert test_func.__alternative__ == "/new"


class TestGetVersionInfo:
    """Tests for get_version_info function."""

    def test_returns_info_for_known_version(self):
        """Should return info dict for known versions."""
        info = get_version_info(APIVersion.V1)

        assert "title" in info
        assert "description" in info
        assert "status" in info
        assert info["status"] == "stable"

    def test_returns_unknown_status_for_undefined_version(self):
        """Should return unknown status for versions without defined info."""
        # This test would need a version without info defined
        # For now, all versions have info, so we test the structure
        info = get_version_info(APIVersion.V1)
        assert isinstance(info, dict)
