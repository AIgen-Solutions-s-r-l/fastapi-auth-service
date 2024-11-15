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