# app/core/exceptions.py
from fastapi import HTTPException, status


class AuthException(HTTPException):
    """Base exception for authentication errors"""

    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail={
            "error": self.__class__.__name__,
            "message": detail
        })


class UserAlreadyExistsError(AuthException):
    """Raised when attempting to register a user that already exists"""

    def __init__(self, identifier: str):
        super().__init__(
            detail=f"User with identifier '{identifier}' already exists",
            status_code=status.HTTP_409_CONFLICT  # 409 è più appropriato per conflitti
        )


class InvalidCredentialsError(AuthException):
    """Raised when login credentials are invalid"""

    def __init__(self):
        super().__init__(
            detail="Invalid credentials",
            status_code=status.HTTP_401_UNAUTHORIZED
        )


class UserNotFoundError(AuthException):
    """Raised when a user is not found"""

    def __init__(self, identifier: str):
        super().__init__(
            detail=f"User with identifier '{identifier}' not found",
            status_code=status.HTTP_404_NOT_FOUND
        )


class ResumeException(HTTPException):
    """Base exception for resume-related errors"""

    def __init__(self, detail: str, status_code: int):
        super().__init__(status_code=status_code, detail={
            "error": self.__class__.__name__,
            "message": detail
        })


class ResumeNotFoundError(ResumeException):
    """Raised when a resume cannot be found"""

    def __init__(self, detail: str):
        super().__init__(
            detail=f"Resume not found: {detail}",
            status_code=status.HTTP_404_NOT_FOUND
        )


class ResumeDuplicateError(ResumeException):
    """Raised when attempting to create a duplicate resume"""

    def __init__(self, user_id: int):
        super().__init__(
            detail=f"Resume already exists for user_id: {user_id}",
            status_code=status.HTTP_409_CONFLICT
        )


class ResumeValidationError(ResumeException):
    """Raised when resume data fails validation"""

    def __init__(self, detail: str):
        super().__init__(
            detail=f"Resume validation failed: {detail}",
            status_code=status.HTTP_400_BAD_REQUEST
        )


class DatabaseOperationError(ResumeException):
    """Raised when a database operation fails"""

    def __init__(self, detail: str):
        super().__init__(
            detail=f"Database operation failed: {detail}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
