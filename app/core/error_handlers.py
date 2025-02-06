"""Error handlers for the application."""
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
import logging

from app.core.exceptions import AuthException
from app.core.responses import DecimalJSONResponse

logger = logging.getLogger('uvicorn.error')

async def auth_exception_handler(request: Request, exc: AuthException) -> DecimalJSONResponse:
    """Handle authentication exceptions."""
    logger.error(f'Auth error on {request.url}: {exc.detail}')
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content=exc.detail
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
    return DecimalJSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTPException", "message": str(exc.detail)}
    )

async def generic_exception_handler(request: Request, exc: Exception) -> DecimalJSONResponse:
    """Handle generic exceptions."""
    logger.error(f'Unhandled error on {request.url}: {exc}', exc_info=True)
    return DecimalJSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred."}
    )
