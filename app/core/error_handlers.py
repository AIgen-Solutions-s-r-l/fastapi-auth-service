"""Error handlers for the application."""
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError

from sqlalchemy.exc import SQLAlchemyError
from app.log.logging import logger
from app.core.exceptions import AuthException
from app.core.responses import DecimalJSONResponse
from app.core.db_exceptions import DatabaseException

async def auth_exception_handler(request: Request, exc: AuthException) -> DecimalJSONResponse:
    """Handle authentication exceptions."""
    logger.exception(f'Auth error on {request.url}: {exc.detail}')
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )

async def database_exception_handler(request: Request, exc: DatabaseException) -> DecimalJSONResponse:
    """Handle database exceptions with appropriate status codes and retry information."""
    logger.error(
        f'Database error on {request.url}: {exc.detail}',
        event_type='db_api_error',
        error_code=exc.error_code.name if hasattr(exc, 'error_code') else None,
        error_details=exc.error_details if hasattr(exc, 'error_details') else {},
        status_code=exc.status_code
    )
    
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
        headers=exc.headers
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> DecimalJSONResponse:
    """Handle validation exceptions."""
    logger.error(f'Validation error on {request.url}: {exc.errors()}')
    return DecimalJSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Invalid request data",
            "details": exc.errors()
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> DecimalJSONResponse:
    """Handle HTTP exceptions."""
    logger.error(f'HTTP error on {request.url}: {exc.detail}')
    # If detail is already a dict with message, keep it as is
    if isinstance(exc.detail, dict) and "message" in exc.detail:
        return DecimalJSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    # Otherwise wrap the string detail in a dict with message field
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content={"detail": {"message": str(exc.detail)}}
    )

async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> DecimalJSONResponse:
    """Handle SQLAlchemy exceptions."""
    logger.error(
        f'SQLAlchemy error on {request.url}: {exc}',
        event_type='db_sqlalchemy_error',
        error_type=type(exc).__name__,
        exc_info=True
    )
    
    return DecimalJSONResponse(
        status_code=500,
        content={"error": "DatabaseError", "message": "A database error occurred. Please try again later."}
    )

async def generic_exception_handler(request: Request, exc: Exception) -> DecimalJSONResponse:
    """Handle generic exceptions."""
    logger.error(f'Unhandled error on {request.url}: {exc}', exc_info=True)
    return DecimalJSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred."}
    )
