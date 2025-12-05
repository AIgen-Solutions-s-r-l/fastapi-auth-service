"""Error handlers for the application with consistent request_id tracking."""
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from typing import Dict, Any

from sqlalchemy.exc import SQLAlchemyError
from app.log.logging import logger
from app.core.exceptions import AuthException
from app.core.responses import DecimalJSONResponse
from app.core.db_exceptions import DatabaseException
from app.middleware.request_id import get_request_id


def _build_error_response(
    error: str,
    message: str,
    status_code: int,
    details: Any = None,
    include_request_id: bool = True
) -> Dict[str, Any]:
    """
    Build a consistent error response structure.

    All error responses follow the same format for consistency:
    - error: Error type identifier (e.g., "ValidationError", "AuthError")
    - message: Human-readable error message
    - request_id: Unique request identifier for debugging (if enabled)
    - details: Additional error details (optional)
    """
    response = {
        "error": error,
        "message": message
    }

    if include_request_id:
        request_id = get_request_id()
        if request_id:
            response["request_id"] = request_id

    if details is not None:
        response["details"] = details

    return response


async def auth_exception_handler(request: Request, exc: AuthException) -> DecimalJSONResponse:
    """Handle authentication exceptions."""
    # Extract error type from context if available
    error_type = exc.context.get("error_type", "AuthError") if hasattr(exc, "context") else "AuthError"
    user_id = exc.context.get("user_id", "unknown") if hasattr(exc, "context") else "unknown"
    
    # Determine if this is a token expiration error
    is_token_expired = error_type == "TokenExpired"
    
    # Get the detail for logging
    error_detail = getattr(exc, 'error_detail', exc.detail)
    
    # Use warning level for expected auth errors like token expiration, exception level for others
    if is_token_expired:
        logger.warning(
            f'Auth error on {request.url}: Token expired',
            event_type='auth_warning',
            error_type=error_type,
            user_id=user_id,
            status_code=exc.status_code,
            path=str(request.url)
        )
    else:
        logger.error(
            f'Auth error on {request.url}: {error_detail}',
            event_type='auth_error',
            error_type=error_type,
            user_id=user_id,
            status_code=exc.status_code,
            path=str(request.url)
        )
    
    # Return user-friendly response without exposing internal details
    # Keep the original format for compatibility with tests
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content={"detail": error_detail}
    )

async def database_exception_handler(request: Request, exc: DatabaseException) -> DecimalJSONResponse:
    """Handle database exceptions with appropriate status codes and retry information."""
    error_detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
    logger.error(f'Database error on {request.url}',
        event_type='db_api_error',
        error_code=exc.error_code.name if hasattr(exc, 'error_code') else "UNKNOWN_ERROR",
        error_details=getattr(exc, 'error_details', {}),
        status_code=getattr(exc, 'status_code', 500)
    )
    
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
        headers=exc.headers
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> DecimalJSONResponse:
    """Handle validation exceptions."""
    request_id = get_request_id()
    logger.warning(
        f'Validation error on {request.url}',
        event_type='validation_error',
        path=str(request.url),
        method=request.method,
        errors=exc.errors()
    )
    return DecimalJSONResponse(
        status_code=422,
        content=_build_error_response(
            error="ValidationError",
            message="Invalid request data",
            status_code=422,
            details=exc.errors()
        )
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> DecimalJSONResponse:
    """Handle HTTP exceptions."""
    # Use warning for client errors (4xx), error for server errors (5xx)
    log_level = logger.warning if 400 <= exc.status_code < 500 else logger.error
    log_level(
        f'HTTP error on {request.url}',
        event_type='http_error',
        status_code=exc.status_code,
        path=str(request.url),
        method=request.method,
        detail=str(exc.detail)[:200]  # Truncate for logging
    )

    # If detail is already a dict with message, keep it as is
    if isinstance(exc.detail, dict) and "message" in exc.detail:
        response = exc.detail.copy()
        request_id = get_request_id()
        if request_id:
            response["request_id"] = request_id
        return DecimalJSONResponse(
            status_code=exc.status_code,
            content=response
        )

    # Map status codes to error types
    error_type_map = {
        400: "BadRequest",
        401: "Unauthorized",
        403: "Forbidden",
        404: "NotFound",
        405: "MethodNotAllowed",
        409: "Conflict",
        429: "RateLimitExceeded",
    }
    error_type = error_type_map.get(exc.status_code, "HTTPError")

    return DecimalJSONResponse(
        status_code=exc.status_code,
        content=_build_error_response(
            error=error_type,
            message=str(exc.detail),
            status_code=exc.status_code
        )
    )

async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> DecimalJSONResponse:
    """Handle SQLAlchemy exceptions."""
    logger.error(
        f'SQLAlchemy error on {request.url}',
        event_type='db_sqlalchemy_error',
        error_type=type(exc).__name__,
        path=str(request.url),
        method=request.method,
        exc_info=True
    )

    return DecimalJSONResponse(
        status_code=500,
        content=_build_error_response(
            error="DatabaseError",
            message="A database error occurred. Please try again later.",
            status_code=500
        )
    )


async def generic_exception_handler(request: Request, exc: Exception) -> DecimalJSONResponse:
    """Handle generic/unhandled exceptions."""
    logger.error(
        f'Unhandled error on {request.url}',
        event_type='unhandled_error',
        error_type=type(exc).__name__,
        path=str(request.url),
        method=request.method,
        exc_info=True
    )
    return DecimalJSONResponse(
        status_code=500,
        content=_build_error_response(
            error="InternalServerError",
            message="An unexpected error occurred.",
            status_code=500
        )
    )
