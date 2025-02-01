# app/core/error_handlers.py
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging

from app.core.exceptions import AuthException

logger = logging.getLogger('uvicorn.error')

async def auth_exception_handler(request: Request, exc: AuthException) -> JSONResponse:
    logger.error(f'Auth error on {request.url}: {exc.detail}')
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.error(f'Validation error on {request.url}: {exc.errors()}')
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Invalid request data",
            "details": exc.errors()
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.error(f'HTTP error on {request.url}: {exc.detail}')
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "HTTPException", "message": str(exc.detail)}
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f'Unhandled error on {request.url}: {exc}', exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred."}
    )
