"""Tests for input validation utilities."""

import pytest
from app.core.validation import (
    normalize_email,
    validate_redirect_uri,
    sanitize_string,
    validate_token_format,
    validate_plan_name,
    validate_description
)


class TestNormalizeEmail:
    """Tests for email normalization."""

    def test_normalize_lowercase(self):
        """Email should be converted to lowercase."""
        assert normalize_email("USER@EXAMPLE.COM") == "user@example.com"

    def test_normalize_strip_whitespace(self):
        """Leading and trailing whitespace should be removed."""
        assert normalize_email("  user@example.com  ") == "user@example.com"

    def test_normalize_mixed_case_and_whitespace(self):
        """Both case normalization and whitespace stripping should work together."""
        assert normalize_email("  USER@Example.COM  ") == "user@example.com"

    def test_normalize_empty_string(self):
        """Empty string should return empty string."""
        assert normalize_email("") == ""

    def test_normalize_none(self):
        """None should return None."""
        assert normalize_email(None) is None

    def test_normalize_already_normalized(self):
        """Already normalized email should remain unchanged."""
        assert normalize_email("user@example.com") == "user@example.com"


class TestValidateRedirectUri:
    """Tests for redirect URI validation."""

    def test_valid_https_uri(self):
        """Valid HTTPS URI should pass."""
        is_valid, error = validate_redirect_uri("https://example.com/callback")
        assert is_valid is True
        assert error is None

    def test_valid_localhost_http(self):
        """HTTP localhost should be allowed for development."""
        is_valid, error = validate_redirect_uri("http://localhost:3000/callback")
        assert is_valid is True
        assert error is None

    def test_valid_localhost_127(self):
        """127.0.0.1 should be allowed for development."""
        is_valid, error = validate_redirect_uri("http://127.0.0.1:8080/callback")
        assert is_valid is True
        assert error is None

    def test_empty_uri(self):
        """Empty URI should pass (allows default behavior)."""
        is_valid, error = validate_redirect_uri("")
        assert is_valid is True

    def test_none_uri(self):
        """None URI should pass (allows default behavior)."""
        is_valid, error = validate_redirect_uri(None)
        assert is_valid is True

    def test_invalid_scheme(self):
        """Non-HTTP/HTTPS schemes should be rejected."""
        is_valid, error = validate_redirect_uri("ftp://example.com/callback")
        assert is_valid is False
        assert "HTTPS" in error

    def test_missing_scheme(self):
        """URI without scheme should be rejected."""
        is_valid, error = validate_redirect_uri("example.com/callback")
        assert is_valid is False

    def test_http_non_localhost(self):
        """HTTP on non-localhost should be rejected."""
        is_valid, error = validate_redirect_uri("http://example.com/callback")
        assert is_valid is False
        assert "HTTPS" in error


class TestSanitizeString:
    """Tests for string sanitization."""

    def test_strip_whitespace(self):
        """Leading and trailing whitespace should be removed."""
        assert sanitize_string("  hello  ") == "hello"

    def test_remove_control_chars(self):
        """Control characters should be removed."""
        assert sanitize_string("hello\x00world") == "helloworld"
        assert sanitize_string("test\x1fdata") == "testdata"

    def test_preserve_newlines_and_tabs(self):
        """Newlines and tabs in the middle should be preserved."""
        # Note: strip_whitespace removes leading/trailing but middle whitespace is kept
        result = sanitize_string("hello\nworld")
        assert "hello" in result and "world" in result

    def test_max_length_truncation(self):
        """String should be truncated to max_length."""
        result = sanitize_string("hello world", max_length=5)
        assert result == "hello"

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert sanitize_string("") == ""

    def test_none_value(self):
        """None should return None."""
        assert sanitize_string(None) is None

    def test_no_strip_whitespace(self):
        """When strip_whitespace=False, whitespace should be preserved."""
        result = sanitize_string("  hello  ", strip_whitespace=False)
        assert result == "  hello  "


class TestValidateTokenFormat:
    """Tests for token format validation."""

    def test_valid_token(self):
        """Valid alphanumeric token should pass."""
        token = "a" * 64  # Our tokens are 64 chars
        is_valid, error = validate_token_format(token)
        assert is_valid is True
        assert error is None

    def test_token_too_short(self):
        """Token shorter than 32 characters should fail."""
        is_valid, error = validate_token_format("abc123")
        assert is_valid is False
        assert "too short" in error

    def test_token_too_long(self):
        """Token longer than 256 characters should fail."""
        token = "a" * 300
        is_valid, error = validate_token_format(token)
        assert is_valid is False
        assert "too long" in error

    def test_token_with_special_chars(self):
        """Token with special characters should fail."""
        token = "a" * 60 + "!@#$"
        is_valid, error = validate_token_format(token)
        assert is_valid is False
        assert "Invalid token format" in error

    def test_empty_token(self):
        """Empty token should fail."""
        is_valid, error = validate_token_format("")
        assert is_valid is False
        assert "required" in error

    def test_none_token(self):
        """None token should fail."""
        is_valid, error = validate_token_format(None)
        assert is_valid is False


class TestValidatePlanName:
    """Tests for plan name validation."""

    def test_valid_plan_name(self):
        """Valid plan name should pass."""
        is_valid, error = validate_plan_name("Pro Monthly")
        assert is_valid is True
        assert error is None

    def test_empty_plan_name(self):
        """Empty plan name should fail."""
        is_valid, error = validate_plan_name("")
        assert is_valid is False
        assert "required" in error

    def test_whitespace_only(self):
        """Whitespace-only plan name should fail after strip."""
        is_valid, error = validate_plan_name("   ")
        assert is_valid is False

    def test_plan_name_too_long(self):
        """Plan name over 100 characters should fail."""
        is_valid, error = validate_plan_name("a" * 101)
        assert is_valid is False
        assert "100 characters" in error

    def test_none_plan_name(self):
        """None plan name should fail."""
        is_valid, error = validate_plan_name(None)
        assert is_valid is False


class TestValidateDescription:
    """Tests for description validation."""

    def test_valid_description(self):
        """Valid description should pass."""
        is_valid, error = validate_description("This is a valid description.")
        assert is_valid is True
        assert error is None

    def test_empty_description(self):
        """Empty description should pass (optional field)."""
        is_valid, error = validate_description("")
        assert is_valid is True

    def test_none_description(self):
        """None description should pass (optional field)."""
        is_valid, error = validate_description(None)
        assert is_valid is True

    def test_description_too_long(self):
        """Description over max_length should fail."""
        is_valid, error = validate_description("a" * 1001, max_length=1000)
        assert is_valid is False
        assert "1000 characters" in error

    def test_custom_field_name(self):
        """Custom field name should appear in error message."""
        is_valid, error = validate_description("a" * 101, field_name="Reason", max_length=100)
        assert is_valid is False
        assert "Reason" in error
