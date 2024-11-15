# app/core/error_handlers.py
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import AuthException


async def auth_exception_handler(
        request: Request,
        exc: AuthException
) -> JSONResponse:  # specifica esplicitamente il tipo di ritorno
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError
) -> JSONResponse:  # specifica esplicitamente il tipo di ritorno
    return JSONResponse(
        status_code=422,
        content={
            "error": "ValidationError",
            "message": "Invalid request data",
            "details": exc.errors()
        }
    )
