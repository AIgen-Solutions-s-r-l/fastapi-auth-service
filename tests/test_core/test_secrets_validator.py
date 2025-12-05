"""Tests for secrets validation module."""

import pytest
from unittest.mock import MagicMock, patch

from app.core.secrets_validator import (
    SecretsValidator,
    SecretSeverity,
    ValidationIssue,
    validate_secrets_on_startup
)


class TestSecretSeverity:
    """Tests for SecretSeverity enum."""

    def test_severity_values(self):
        """Should have expected severity values."""
        assert SecretSeverity.CRITICAL.value == "critical"
        assert SecretSeverity.WARNING.value == "warning"
        assert SecretSeverity.INFO.value == "info"


class TestSecretsValidator:
    """Tests for SecretsValidator class."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings object."""
        settings = MagicMock()
        settings.secret_key = "a" * 32  # Valid length
        settings.database_url = "postgresql://user:pass@host/db"
        settings.INTERNAL_API_KEY = "a" * 20
        settings.STRIPE_SECRET_KEY = "sk_live_test"
        settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        settings.GOOGLE_CLIENT_ID = "client_id"
        settings.GOOGLE_CLIENT_SECRET = "client_secret"
        settings.SENDGRID_API_KEY = "sendgrid_key"
        return settings

    def test_valid_configuration_passes(self, mock_settings):
        """Should pass with valid configuration."""
        with patch.dict('os.environ', {'ENVIRONMENT': 'development'}):
            validator = SecretsValidator(mock_settings)
            is_valid, details = validator.validate_all()

        assert is_valid is True
        assert details["critical_count"] == 0

    def test_missing_secret_key_is_critical(self, mock_settings):
        """Missing secret key should be critical."""
        mock_settings.secret_key = ""

        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}):
            validator = SecretsValidator(mock_settings)
            is_valid, details = validator.validate_all()

        assert is_valid is False
        assert details["critical_count"] >= 1
        assert any(i["setting"] == "SECRET_KEY" for i in details["issues"])

    def test_placeholder_secret_key_detected(self, mock_settings):
        """Should detect placeholder secret key."""
        mock_settings.secret_key = "your-secret-key-here"

        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}):
            validator = SecretsValidator(mock_settings)
            is_valid, details = validator.validate_all()

        assert is_valid is False
        secret_issue = next(
            (i for i in details["issues"] if i["setting"] == "SECRET_KEY"),
            None
        )
        assert secret_issue is not None
        assert "placeholder" in secret_issue["message"].lower()

    def test_short_secret_key_warning(self, mock_settings):
        """Short secret key should generate warning."""
        mock_settings.secret_key = "short"

        with patch.dict('os.environ', {'ENVIRONMENT': 'development'}):
            validator = SecretsValidator(mock_settings)
            is_valid, details = validator.validate_all()

        secret_issue = next(
            (i for i in details["issues"] if i["setting"] == "SECRET_KEY"),
            None
        )
        assert secret_issue is not None
        assert "short" in secret_issue["message"].lower()

    def test_missing_database_url_is_critical(self, mock_settings):
        """Missing database URL should be critical."""
        mock_settings.database_url = ""

        validator = SecretsValidator(mock_settings)
        is_valid, details = validator.validate_all()

        assert is_valid is False
        assert any(
            i["setting"] == "DATABASE_URL" and i["severity"] == "critical"
            for i in details["issues"]
        )

    def test_stripe_test_key_in_production(self, mock_settings):
        """Should warn about Stripe test key in production."""
        mock_settings.STRIPE_SECRET_KEY = "sk_test_123"

        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}):
            validator = SecretsValidator(mock_settings)
            is_valid, details = validator.validate_all()

        assert is_valid is False  # Critical in production
        stripe_issue = next(
            (i for i in details["issues"] if "STRIPE" in i["setting"]),
            None
        )
        assert stripe_issue is not None
        assert stripe_issue["severity"] == "critical"

    def test_missing_oauth_is_info_level(self, mock_settings):
        """Missing OAuth should be info level (not critical)."""
        mock_settings.GOOGLE_CLIENT_ID = ""
        mock_settings.GOOGLE_CLIENT_SECRET = ""

        validator = SecretsValidator(mock_settings)
        is_valid, details = validator.validate_all()

        assert is_valid is True  # Should still be valid
        oauth_issue = next(
            (i for i in details["issues"] if "GOOGLE" in i["setting"]),
            None
        )
        assert oauth_issue is not None
        assert oauth_issue["severity"] == "info"

    def test_missing_email_is_warning(self, mock_settings):
        """Missing email config should be warning level."""
        mock_settings.SENDGRID_API_KEY = ""

        validator = SecretsValidator(mock_settings)
        is_valid, details = validator.validate_all()

        assert is_valid is True
        email_issue = next(
            (i for i in details["issues"] if "SENDGRID" in i["setting"]),
            None
        )
        assert email_issue is not None
        assert email_issue["severity"] == "warning"

    def test_localhost_db_in_production_warns(self, mock_settings):
        """Should warn about localhost database in production."""
        mock_settings.database_url = "postgresql://user:pass@localhost/db"

        with patch.dict('os.environ', {'ENVIRONMENT': 'production'}):
            validator = SecretsValidator(mock_settings)
            is_valid, details = validator.validate_all()

        db_issue = next(
            (i for i in details["issues"]
             if i["setting"] == "DATABASE_URL" and "localhost" in i["message"]),
            None
        )
        assert db_issue is not None


class TestValidateSecretsOnStartup:
    """Tests for validate_secrets_on_startup function."""

    def test_logs_critical_issues(self):
        """Should log critical issues."""
        mock_settings = MagicMock()
        mock_settings.secret_key = ""
        mock_settings.database_url = ""
        mock_settings.INTERNAL_API_KEY = ""
        mock_settings.STRIPE_SECRET_KEY = ""
        mock_settings.STRIPE_WEBHOOK_SECRET = ""
        mock_settings.GOOGLE_CLIENT_ID = ""
        mock_settings.GOOGLE_CLIENT_SECRET = ""
        mock_settings.SENDGRID_API_KEY = ""

        with patch('app.core.secrets_validator.logger') as mock_logger:
            with patch.dict('os.environ', {'ENVIRONMENT': 'production'}):
                is_valid, details = validate_secrets_on_startup(mock_settings)

        assert is_valid is False
        mock_logger.error.assert_called()

    def test_logs_success_with_no_issues(self):
        """Should log success when validation passes."""
        mock_settings = MagicMock()
        mock_settings.secret_key = "a" * 32
        mock_settings.database_url = "postgresql://user:pass@host/db"
        mock_settings.INTERNAL_API_KEY = "a" * 20
        mock_settings.STRIPE_SECRET_KEY = "sk_live_test"
        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        mock_settings.GOOGLE_CLIENT_ID = "client_id"
        mock_settings.GOOGLE_CLIENT_SECRET = "client_secret"
        mock_settings.SENDGRID_API_KEY = "sendgrid_key"

        with patch('app.core.secrets_validator.logger') as mock_logger:
            with patch.dict('os.environ', {'ENVIRONMENT': 'development'}):
                is_valid, details = validate_secrets_on_startup(mock_settings)

        assert is_valid is True


class TestPlaceholderDetection:
    """Tests for placeholder value detection."""

    @pytest.fixture
    def validator(self):
        """Create validator instance."""
        mock_settings = MagicMock()
        return SecretsValidator(mock_settings)

    def test_detects_your_secret_key(self, validator):
        """Should detect 'your-secret-key' pattern."""
        assert validator._is_placeholder("your-secret-key") is True
        assert validator._is_placeholder("your_secret_key") is True

    def test_detects_change_me(self, validator):
        """Should detect 'change-me' pattern."""
        assert validator._is_placeholder("change-me") is True
        assert validator._is_placeholder("changeme") is True

    def test_detects_placeholder(self, validator):
        """Should detect 'placeholder' pattern."""
        assert validator._is_placeholder("placeholder_value") is True

    def test_detects_xxx_pattern(self, validator):
        """Should detect 'xxx' pattern."""
        assert validator._is_placeholder("xxxxxxxxxxxx") is True

    def test_does_not_detect_valid_values(self, validator):
        """Should not detect valid random values."""
        assert validator._is_placeholder("a1b2c3d4e5f6g7h8") is False
        assert validator._is_placeholder("real_api_key_12345") is False
