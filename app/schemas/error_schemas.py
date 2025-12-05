"""Standardized error response schemas for API documentation."""

from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Detail of a single validation error."""
    loc: List[str] = Field(
        ...,
        description="Location of the error (e.g., ['body', 'email'])",
        examples=[["body", "email"]]
    )
    msg: str = Field(
        ...,
        description="Human-readable error message",
        examples=["field required"]
    )
    type: str = Field(
        ...,
        description="Error type identifier",
        examples=["value_error.missing"]
    )


class ValidationErrorResponse(BaseModel):
    """Response returned for validation errors (422)."""
    error: str = Field(
        default="ValidationError",
        description="Error type identifier"
    )
    message: str = Field(
        default="Invalid request data",
        description="Human-readable error message"
    )
    details: List[ErrorDetail] = Field(
        ...,
        description="List of validation errors"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "ValidationError",
                "message": "Invalid request data",
                "details": [
                    {
                        "loc": ["body", "email"],
                        "msg": "field required",
                        "type": "value_error.missing"
                    }
                ]
            }
        }
    }


class ErrorResponse(BaseModel):
    """Standard error response for API errors."""
    detail: str = Field(
        ...,
        description="Human-readable error message",
        examples=["Invalid credentials"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Invalid credentials"
            }
        }
    }


class AuthErrorResponse(BaseModel):
    """Error response for authentication failures."""
    detail: str = Field(
        ...,
        description="Authentication error message",
        examples=["Could not validate credentials"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Could not validate credentials"
            }
        }
    }


class NotFoundErrorResponse(BaseModel):
    """Error response for resource not found (404)."""
    detail: str = Field(
        ...,
        description="Resource not found message",
        examples=["User not found"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "User not found"
            }
        }
    }


class ForbiddenErrorResponse(BaseModel):
    """Error response for forbidden access (403)."""
    detail: str = Field(
        ...,
        description="Access denied message",
        examples=["Not authorized to access this resource"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Not authorized to access this resource"
            }
        }
    }


class RateLimitErrorResponse(BaseModel):
    """Error response for rate limiting (429)."""
    detail: str = Field(
        default="Rate limit exceeded",
        description="Rate limit error message"
    )
    retry_after: Optional[int] = Field(
        None,
        description="Seconds until the rate limit resets"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "detail": "Rate limit exceeded",
                "retry_after": 60
            }
        }
    }


class InternalErrorResponse(BaseModel):
    """Error response for internal server errors (500)."""
    error: str = Field(
        default="InternalServerError",
        description="Error type identifier"
    )
    message: str = Field(
        default="An unexpected error occurred.",
        description="Human-readable error message"
    )
    request_id: Optional[str] = Field(
        None,
        description="Request ID for debugging and support",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "InternalServerError",
                "message": "An unexpected error occurred.",
                "request_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    }


class DatabaseErrorResponse(BaseModel):
    """Error response for database errors."""
    error: str = Field(
        default="DatabaseError",
        description="Error type identifier"
    )
    message: str = Field(
        default="A database error occurred. Please try again later.",
        description="Human-readable error message"
    )
    request_id: Optional[str] = Field(
        None,
        description="Request ID for debugging and support"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "DatabaseError",
                "message": "A database error occurred. Please try again later.",
                "request_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }
    }


# Common response definitions for OpenAPI documentation
COMMON_RESPONSES = {
    400: {
        "model": ErrorResponse,
        "description": "Bad Request - Invalid input data"
    },
    401: {
        "model": AuthErrorResponse,
        "description": "Unauthorized - Authentication required or invalid credentials"
    },
    403: {
        "model": ForbiddenErrorResponse,
        "description": "Forbidden - Not authorized to access this resource"
    },
    404: {
        "model": NotFoundErrorResponse,
        "description": "Not Found - Resource does not exist"
    },
    422: {
        "model": ValidationErrorResponse,
        "description": "Validation Error - Request data failed validation"
    },
    429: {
        "model": RateLimitErrorResponse,
        "description": "Too Many Requests - Rate limit exceeded"
    },
    500: {
        "model": InternalErrorResponse,
        "description": "Internal Server Error - Unexpected error occurred"
    }
}


def get_error_responses(*status_codes: int) -> Dict[int, Dict[str, Any]]:
    """
    Get error response definitions for specified status codes.

    Args:
        *status_codes: HTTP status codes to include

    Returns:
        Dictionary of error responses for OpenAPI documentation

    Example:
        @router.get("/endpoint", responses=get_error_responses(400, 401, 404))
    """
    return {code: COMMON_RESPONSES[code] for code in status_codes if code in COMMON_RESPONSES}
