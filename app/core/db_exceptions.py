"""PostgreSQL Database Exceptions Module.

This module defines specialized exceptions for database-related errors,
providing consistent error handling, clear error messages, and appropriate
HTTP status codes for various database failure scenarios.
"""

from fastapi import status
from enum import Enum, auto
from typing import Optional, Dict, Any

from app.core.exceptions import AuthException


class DatabaseErrorCode(Enum):
    """Enumeration of specific database error codes for classification and handling."""
    
    # Connection Errors
    CONNECTION_REFUSED = auto()  # Cannot establish initial connection
    CONNECTION_LOST = auto()     # Connection lost during operation
    CONNECTION_TIMEOUT = auto()  # Connection attempt timed out
    
    # Authentication Errors
    AUTH_FAILED = auto()         # Invalid credentials
    
    # Resource Errors
    INSUFFICIENT_RESOURCES = auto()  # Server out of memory/connections
    
    # Data Errors
    INTEGRITY_ERROR = auto()     # Constraint violation
    DATA_ERROR = auto()          # Data type mismatch
    
    # System Errors
    SYSTEM_ERROR = auto()        # Server system error
    
    # Unknown/Other
    UNKNOWN_ERROR = auto()       # Unclassified database error


class DatabaseException(AuthException):
    """Base exception for database-related errors."""
    
    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_503_SERVICE_UNAVAILABLE,
        headers: Optional[Dict[str, Any]] = None,
        error_code: DatabaseErrorCode = DatabaseErrorCode.UNKNOWN_ERROR,
        retry_after: Optional[int] = None,
        error_details: Optional[Dict[str, Any]] = None
    ):
        self.error_code = error_code
        self.error_details = error_details or {}
        
        # Add retry-after header for service unavailable errors
        if status_code == status.HTTP_503_SERVICE_UNAVAILABLE and retry_after:
            headers = headers or {}
            headers['Retry-After'] = str(retry_after)
        
        # Format detail with error code
        detail_with_code = {
            "detail": detail,
            "error_code": error_code.name,
            "error_details": self.error_details
        }
        
        super().__init__(
            detail=detail_with_code,
            status_code=status_code,
            headers=headers
        )


class ConnectionRefusedError(DatabaseException):
    """Raised when the database server refuses connections."""
    
    def __init__(
        self,
        detail: str = "Database connection refused",
        retry_after: Optional[int] = 30,
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=DatabaseErrorCode.CONNECTION_REFUSED,
            retry_after=retry_after,
            error_details=error_details
        )


class ConnectionLostError(DatabaseException):
    """Raised when an established database connection is lost."""
    
    def __init__(
        self,
        detail: str = "Database connection lost",
        retry_after: Optional[int] = 10,
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=DatabaseErrorCode.CONNECTION_LOST,
            retry_after=retry_after,
            error_details=error_details
        )


class ConnectionTimeoutError(DatabaseException):
    """Raised when a database connection attempt times out."""
    
    def __init__(
        self,
        detail: str = "Database connection timed out",
        retry_after: Optional[int] = 20,
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=DatabaseErrorCode.CONNECTION_TIMEOUT,
            retry_after=retry_after,
            error_details=error_details
        )


class DatabaseAuthError(DatabaseException):
    """Raised when database authentication fails."""
    
    def __init__(
        self,
        detail: str = "Database authentication failed",
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=DatabaseErrorCode.AUTH_FAILED,
            error_details=error_details
        )


class InsufficientResourcesError(DatabaseException):
    """Raised when the database server has insufficient resources."""
    
    def __init__(
        self,
        detail: str = "Database server has insufficient resources",
        retry_after: Optional[int] = 60,
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code=DatabaseErrorCode.INSUFFICIENT_RESOURCES,
            retry_after=retry_after,
            error_details=error_details
        )


class IntegrityError(DatabaseException):
    """Raised when a database integrity constraint is violated."""
    
    def __init__(
        self,
        detail: str = "Database integrity constraint violated",
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_409_CONFLICT,
            error_code=DatabaseErrorCode.INTEGRITY_ERROR,
            error_details=error_details
        )


class DataError(DatabaseException):
    """Raised when data doesn't match expected types/constraints."""
    
    def __init__(
        self,
        detail: str = "Invalid data for database operation",
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=DatabaseErrorCode.DATA_ERROR,
            error_details=error_details
        )


class SystemError(DatabaseException):
    """Raised when there's a database system error."""
    
    def __init__(
        self,
        detail: str = "Database system error",
        error_details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code=DatabaseErrorCode.SYSTEM_ERROR,
            error_details=error_details
        )