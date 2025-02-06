"""Router for credit-related endpoints."""

from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.responses import DecimalJSONResponse
from app.models.user import User
from app.schemas import credit_schemas
from app.services.credit_service import CreditService, InsufficientCreditsError

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get(
    "/balance",
    response_model=credit_schemas.CreditBalanceResponse,
    response_class=DecimalJSONResponse
)
async def get_credit_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's credit balance.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        CreditBalanceResponse: Current credit balance
    """
    credit_service = CreditService(db)
    user_id = current_user.id if isinstance(current_user, User) else current_user['id']
    return await credit_service.get_balance(user_id)


@router.post(
    "/add",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def add_credits(
    request: credit_schemas.AddCreditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add credits to user's balance.

    Args:
        request: Credit addition details
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details
    """
    credit_service = CreditService(db)
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        return await credit_service.add_credits(
            user_id=user_id,
            amount=request.amount,
            reference_id=request.reference_id,
            description=request.description
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error adding credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing credit addition"
        )


@router.post(
    "/use",
    response_model=credit_schemas.TransactionResponse,
    response_class=DecimalJSONResponse
)
async def use_credits(
    request: credit_schemas.UseCreditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Use credits from user's balance.

    Args:
        request: Credit usage details
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionResponse: Transaction details
    """
    credit_service = CreditService(db)
    try:
        user_id = current_user.id if isinstance(current_user, User) else current_user['id']
        return await credit_service.use_credits(
            user_id=user_id,
            amount=request.amount,
            reference_id=request.reference_id,
            description=request.description
        )
    except InsufficientCreditsError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error using credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing credit usage"
        )


@router.get(
    "/transactions",
    response_model=credit_schemas.TransactionHistoryResponse,
    response_class=DecimalJSONResponse
)
async def get_transaction_history(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's credit transaction history.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        current_user: Authenticated user
        db: Database session

    Returns:
        TransactionHistoryResponse: List of transactions and total count
    """
    credit_service = CreditService(db)
    user_id = current_user.id if isinstance(current_user, User) else current_user['id']
    return await credit_service.get_transaction_history(
        user_id=user_id,
        skip=skip,
        limit=limit
    )