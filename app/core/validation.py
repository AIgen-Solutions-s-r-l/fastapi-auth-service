"""Input validation and sanitization utilities."""

import re
from typing import List, Optional
from urllib.parse import urlparse

from app.core.config import settings


def normalize_email(email: str) -> str:
    """
    Normalize email address for consistent storage and comparison.

    - Strips leading/trailing whitespace
    - Converts to lowercase

    Args:
        email: The email address to normalize

    Returns:
        Normalized email address
    """
    if not email:
        return email
    return email.strip().lower()


def validate_redirect_uri(redirect_uri: str) -> tuple[bool, Optional[str]]:
    """
    Validate a redirect URI against allowed domains to prevent open redirect attacks.

    Args:
        redirect_uri: The redirect URI to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not redirect_uri:
        return True, None

    try:
        parsed = urlparse(redirect_uri)

        # Must have a scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid redirect URI format"

        # Must be HTTPS in production (allow HTTP for localhost in development)
        if parsed.scheme not in ('https', 'http'):
            return False, "Redirect URI must use HTTPS"

        # Allow localhost for development
        if parsed.netloc in ('localhost', '127.0.0.1') or parsed.netloc.startswith('localhost:'):
            return True, None

        # In production, only HTTPS is allowed
        if parsed.scheme != 'https':
            return False, "Redirect URI must use HTTPS"

        # Check against allowed redirect domains from settings
        allowed_domains = getattr(settings, 'allowed_redirect_domains_list', [])
        if allowed_domains:
            domain = parsed.netloc.lower()
            # Check if the domain matches or is a subdomain of an allowed domain
            for allowed in allowed_domains:
                if domain == allowed.lower() or domain.endswith('.' + allowed.lower()):
                    return True, None
            return False, f"Redirect domain not in allowed list"

        # If no whitelist is configured, check against FRONTEND_URL
        frontend_url = getattr(settings, 'FRONTEND_URL', '')
        if frontend_url:
            frontend_parsed = urlparse(frontend_url)
            if parsed.netloc.lower() == frontend_parsed.netloc.lower():
                return True, None
            return False, "Redirect domain does not match frontend URL"

        # If no restrictions configured, allow (for backward compatibility)
        return True, None

    except Exception as e:
        return False, f"Invalid redirect URI: {str(e)}"


def sanitize_string(value: str, max_length: Optional[int] = None,
                   strip_whitespace: bool = True,
                   remove_control_chars: bool = True) -> str:
    """
    Sanitize a string input.

    Args:
        value: The string to sanitize
        max_length: Optional maximum length to truncate to
        strip_whitespace: Whether to strip leading/trailing whitespace
        remove_control_chars: Whether to remove control characters

    Returns:
        Sanitized string
    """
    if not value:
        return value

    result = value

    if strip_whitespace:
        result = result.strip()

    if remove_control_chars:
        # Remove ASCII control characters (0x00-0x1F, 0x7F) except common whitespace
        result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)

    if max_length and len(result) > max_length:
        result = result[:max_length]

    return result


def validate_token_format(token: str) -> tuple[bool, Optional[str]]:
    """
    Validate that a token has a valid format (alphanumeric, proper length).

    Args:
        token: The token to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not token:
        return False, "Token is required"

    # Tokens should be alphanumeric
    if not re.match(r'^[a-zA-Z0-9]+$', token):
        return False, "Invalid token format"

    # Tokens should be at least 32 characters (our tokens are 64)
    if len(token) < 32:
        return False, "Token too short"

    # Tokens shouldn't be excessively long
    if len(token) > 256:
        return False, "Token too long"

    return True, None


def validate_plan_name(name: str) -> tuple[bool, Optional[str]]:
    """
    Validate a plan name.

    Args:
        name: The plan name to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Plan name is required"

    name = name.strip()

    if len(name) < 1:
        return False, "Plan name cannot be empty"

    if len(name) > 100:
        return False, "Plan name must be 100 characters or less"

    return True, None


def validate_description(description: str, field_name: str = "Description",
                        max_length: int = 1000) -> tuple[bool, Optional[str]]:
    """
    Validate a description or free-form text field.

    Args:
        description: The description to validate
        field_name: Name of the field for error messages
        max_length: Maximum allowed length

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not description:
        return True, None  # Empty descriptions are allowed

    if len(description) > max_length:
        return False, f"{field_name} must be {max_length} characters or less"

    return True, None
