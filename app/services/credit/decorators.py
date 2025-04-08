"""Decorators for the credit service module."""

import functools
from typing import Callable, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.log.logging import logger

# Type variable for generic function return type
T = TypeVar('T')


def db_error_handler(status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR):
    """
    Decorator for handling database errors in service methods.
    
    Args:
        status_code: HTTP status code to use in the exception
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except IntegrityError as e:
                # Get self (service instance) from args
                self = args[0]
                await self.db.rollback()
                logger.exception(f"Database error in {func.__name__}: {str(e)}")
                raise HTTPException(
                    status_code=status_code,
                    detail=f"Database error: {str(e)}"
                )
            except HTTPException:
                # Re-raise HTTP exceptions
                raise
            except Exception as e:
                # Get self (service instance) from args
                self = args[0]
                await self.db.rollback()
                logger.error(f"Error in {func.__name__}: {str(e)}")
                raise HTTPException(
                    status_code=status_code,
                    detail=f"Error: {str(e)}"
                )
        return wrapper
    return decorator