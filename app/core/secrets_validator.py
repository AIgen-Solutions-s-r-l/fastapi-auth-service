"""Secrets validation module for startup security checks.

This module validates that all required secrets and configurations are
properly set before the application starts. It helps prevent deployment
issues where missing or weak secrets could compromise security.
"""

import os
import re
from typing import List, Dict, Any, Tuple, Optional
from enum import Enum
from dataclasses import dataclass

from app.log.logging import logger


class SecretSeverity(str, Enum):
    """Severity level for secret validation issues."""
    CRITICAL = "critical"  # Service cannot start safely
    WARNING = "warning"    # Service can start but functionality may be limited
    INFO = "info"          # Non-essential but recommended


@dataclass
class ValidationIssue:
    """A single validation issue."""
    setting: str
    message: str
    severity: SecretSeverity
    recommendation: Optional[str] = None


class SecretsValidator:
    """
    Validates secrets and sensitive configuration at startup.

    This validator checks:
    - Required secrets are present and non-empty
    - Secrets meet minimum security requirements (length, entropy)
    - No default/placeholder values are used in production
    - Critical security settings are properly configured
    """

    # Patterns that indicate default/placeholder values
    PLACEHOLDER_PATTERNS = [
        r"your[-_]?secret[-_]?key",
        r"change[-_]?me",
        r"placeholder",
        r"default[-_]?key",
        r"xxx+",
        r"test[-_]?key",
        r"example",
    ]

    # Minimum lengths for various secret types
    MIN_LENGTHS = {
        "secret_key": 32,
        "api_key": 20,
        "webhook_secret": 20,
    }

    def __init__(self, settings):
        """Initialize validator with settings object."""
        self.settings = settings
        self.issues: List[ValidationIssue] = []
        self.is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    def validate_all(self) -> Tuple[bool, Dict[str, Any]]:
        """
        Run all validation checks.

        Returns:
            Tuple of (is_valid, details) where is_valid is True if no critical
            issues were found.
        """
        self.issues = []

        # Core authentication secrets
        self._validate_secret_key()
        self._validate_database_url()

        # Optional but important secrets
        self._validate_internal_api_key()
        self._validate_stripe_secrets()
        self._validate_oauth_secrets()
        self._validate_email_secrets()

        # Summarize results
        critical_issues = [i for i in self.issues if i.severity == SecretSeverity.CRITICAL]
        warning_issues = [i for i in self.issues if i.severity == SecretSeverity.WARNING]
        info_issues = [i for i in self.issues if i.severity == SecretSeverity.INFO]

        is_valid = len(critical_issues) == 0

        return is_valid, {
            "valid": is_valid,
            "is_production": self.is_production,
            "critical_count": len(critical_issues),
            "warning_count": len(warning_issues),
            "info_count": len(info_issues),
            "issues": [
                {
                    "setting": i.setting,
                    "message": i.message,
                    "severity": i.severity.value,
                    "recommendation": i.recommendation
                }
                for i in self.issues
            ]
        }

    def _is_placeholder(self, value: str) -> bool:
        """Check if a value looks like a placeholder."""
        if not value:
            return False
        lower_value = value.lower()
        for pattern in self.PLACEHOLDER_PATTERNS:
            if re.search(pattern, lower_value, re.IGNORECASE):
                return True
        return False

    def _add_issue(
        self,
        setting: str,
        message: str,
        severity: SecretSeverity,
        recommendation: Optional[str] = None
    ):
        """Add a validation issue."""
        self.issues.append(ValidationIssue(
            setting=setting,
            message=message,
            severity=severity,
            recommendation=recommendation
        ))

    def _validate_secret_key(self):
        """Validate the JWT secret key."""
        secret_key = self.settings.secret_key

        if not secret_key:
            self._add_issue(
                "SECRET_KEY",
                "JWT secret key is not set",
                SecretSeverity.CRITICAL,
                "Generate a secure random key: openssl rand -hex 32"
            )
            return

        if self._is_placeholder(secret_key):
            severity = SecretSeverity.CRITICAL if self.is_production else SecretSeverity.WARNING
            self._add_issue(
                "SECRET_KEY",
                "JWT secret key appears to be a placeholder value",
                severity,
                "Generate a secure random key: openssl rand -hex 32"
            )
            return

        min_length = self.MIN_LENGTHS["secret_key"]
        if len(secret_key) < min_length:
            severity = SecretSeverity.CRITICAL if self.is_production else SecretSeverity.WARNING
            self._add_issue(
                "SECRET_KEY",
                f"JWT secret key is too short ({len(secret_key)} chars, minimum {min_length})",
                severity,
                "Use a longer key for better security"
            )

    def _validate_database_url(self):
        """Validate database connection URL."""
        db_url = self.settings.database_url

        if not db_url:
            self._add_issue(
                "DATABASE_URL",
                "Database URL is not set",
                SecretSeverity.CRITICAL,
                "Set DATABASE_URL to your PostgreSQL connection string"
            )
            return

        # Check for common insecure patterns
        if "localhost" in db_url and self.is_production:
            self._add_issue(
                "DATABASE_URL",
                "Database URL points to localhost in production",
                SecretSeverity.WARNING,
                "Use a proper database host in production"
            )

        if "password=" in db_url.lower() and ("password=postgres" in db_url.lower() or "password=password" in db_url.lower()):
            self._add_issue(
                "DATABASE_URL",
                "Database password appears to be a default value",
                SecretSeverity.WARNING if not self.is_production else SecretSeverity.CRITICAL,
                "Use a strong, unique database password"
            )

    def _validate_internal_api_key(self):
        """Validate internal service API key."""
        api_key = self.settings.INTERNAL_API_KEY

        if not api_key:
            self._add_issue(
                "INTERNAL_API_KEY",
                "Internal API key is not set",
                SecretSeverity.WARNING,
                "Set INTERNAL_API_KEY for service-to-service authentication"
            )
            return

        min_length = self.MIN_LENGTHS["api_key"]
        if len(api_key) < min_length:
            self._add_issue(
                "INTERNAL_API_KEY",
                f"Internal API key is too short ({len(api_key)} chars, minimum {min_length})",
                SecretSeverity.WARNING,
                "Use a longer API key for better security"
            )

    def _validate_stripe_secrets(self):
        """Validate Stripe configuration."""
        stripe_key = self.settings.STRIPE_SECRET_KEY
        webhook_secret = self.settings.STRIPE_WEBHOOK_SECRET

        if not stripe_key:
            self._add_issue(
                "STRIPE_SECRET_KEY",
                "Stripe secret key is not set",
                SecretSeverity.WARNING,
                "Payment functionality will not work without Stripe configuration"
            )
        elif stripe_key.startswith("sk_test_") and self.is_production:
            self._add_issue(
                "STRIPE_SECRET_KEY",
                "Using Stripe test key in production",
                SecretSeverity.CRITICAL,
                "Use a live Stripe key (sk_live_) in production"
            )

        if not webhook_secret:
            self._add_issue(
                "STRIPE_WEBHOOK_SECRET",
                "Stripe webhook secret is not set",
                SecretSeverity.WARNING,
                "Webhook signature verification will be disabled"
            )

    def _validate_oauth_secrets(self):
        """Validate OAuth configuration."""
        client_id = self.settings.GOOGLE_CLIENT_ID
        client_secret = self.settings.GOOGLE_CLIENT_SECRET

        if not client_id or not client_secret:
            self._add_issue(
                "GOOGLE_CLIENT_ID/SECRET",
                "Google OAuth credentials are not set",
                SecretSeverity.INFO,
                "Google OAuth login will not be available"
            )
        elif self._is_placeholder(client_id) or self._is_placeholder(client_secret):
            self._add_issue(
                "GOOGLE_CLIENT_ID/SECRET",
                "Google OAuth credentials appear to be placeholder values",
                SecretSeverity.WARNING,
                "Configure valid Google OAuth credentials"
            )

    def _validate_email_secrets(self):
        """Validate email configuration."""
        sendgrid_key = self.settings.SENDGRID_API_KEY

        if not sendgrid_key:
            self._add_issue(
                "SENDGRID_API_KEY",
                "SendGrid API key is not set",
                SecretSeverity.WARNING,
                "Email functionality (verification, password reset) will not work"
            )


def validate_secrets_on_startup(settings) -> Tuple[bool, Dict[str, Any]]:
    """
    Convenience function to validate secrets at application startup.

    Args:
        settings: The application settings object

    Returns:
        Tuple of (is_valid, details)
    """
    validator = SecretsValidator(settings)
    is_valid, details = validator.validate_all()

    # Log the validation results
    if not is_valid:
        logger.error(
            "Secrets validation failed with critical issues",
            event_type="secrets_validation_failed",
            critical_count=details["critical_count"],
            warning_count=details["warning_count"]
        )
        for issue in details["issues"]:
            if issue["severity"] == "critical":
                logger.error(
                    f"CRITICAL: {issue['setting']} - {issue['message']}",
                    event_type="secret_validation_issue",
                    setting=issue["setting"],
                    severity=issue["severity"]
                )
    else:
        if details["warning_count"] > 0:
            logger.warning(
                "Secrets validation passed with warnings",
                event_type="secrets_validation_warnings",
                warning_count=details["warning_count"],
                info_count=details["info_count"]
            )
            for issue in details["issues"]:
                if issue["severity"] == "warning":
                    logger.warning(
                        f"WARNING: {issue['setting']} - {issue['message']}",
                        event_type="secret_validation_issue",
                        setting=issue["setting"],
                        severity=issue["severity"]
                    )
        else:
            logger.info(
                "Secrets validation passed",
                event_type="secrets_validation_success"
            )

    return is_valid, details
