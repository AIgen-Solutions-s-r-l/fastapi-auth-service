"""Unit tests for the subscription cancellation API endpoint."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import status, HTTPException
from httpx import AsyncClient

from app.main import app # Assuming your FastAPI app instance is named 'app' in main.py
from app.models.user import User
from app.schemas.subscription_schemas import SubscriptionCancelRequest, SubscriptionCancelResponse
from app.core.auth import get_current_active_user # Added import

# Base URL for the endpoint
BASE_URL = "/auth/me/subscription/cancel"

@pytest.mark.asyncio
async def test_cancel_subscription_success(async_client: AsyncClient):
    """Test successful subscription cancellation."""
    mock_user = User(id=1, email="test@example.com", is_verified=True, auth_type="password")
    
    # Mock the get_current_active_user dependency
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    # Mock the StripeService and its cancel_user_subscription method
    mock_stripe_service_instance = AsyncMock()
    mock_stripe_service_instance.cancel_user_subscription.return_value = {
        "stripe_subscription_id": "sub_test123",
        "subscription_status": "active", # Stripe status is 'active' but cancel_at_period_end is true
        "period_end_date": "2025-12-31T23:59:59Z"
    }

    with patch("app.routers.auth.user_profile.StripeService", return_value=mock_stripe_service_instance) as mock_stripe_service_class:
        request_payload = SubscriptionCancelRequest(reason="No longer needed").model_dump()
        response = await async_client.post(BASE_URL, json=request_payload)

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["message"] == "Subscription cancellation initiated successfully. Access remains until 2025-12-31T23:59:59Z."
    assert response_data["subscription_status"] == "active"

    mock_stripe_service_class.assert_called_once() # Check StripeService was instantiated
    mock_stripe_service_instance.cancel_user_subscription.assert_called_once_with(
        user_id=mock_user.id,
        reason="No longer needed"
    )

    # Clean up dependency override
    del app.dependency_overrides[get_current_active_user]


@pytest.mark.asyncio
async def test_cancel_subscription_no_active_subscription(async_client: AsyncClient):
    """Test cancellation attempt when user has no active subscription."""
    mock_user = User(id=2, email="test2@example.com", is_verified=True, auth_type="password")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    mock_stripe_service_instance = AsyncMock()
    # Simulate StripeService raising HTTPException for not found
    mock_stripe_service_instance.cancel_user_subscription.side_effect = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription found to cancel."
    )

    with patch("app.routers.auth.user_profile.StripeService", return_value=mock_stripe_service_instance):
        request_payload = SubscriptionCancelRequest(reason="Test").model_dump()
        response = await async_client.post(BASE_URL, json=request_payload)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "No active subscription found to cancel."}
    
    mock_stripe_service_instance.cancel_user_subscription.assert_called_once_with(
        user_id=mock_user.id,
        reason="Test"
    )
    del app.dependency_overrides[get_current_active_user]


@pytest.mark.asyncio
async def test_cancel_subscription_already_canceled(async_client: AsyncClient):
    """Test cancellation attempt when subscription is already canceled."""
    mock_user = User(id=3, email="test3@example.com", is_verified=True, auth_type="password")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    mock_stripe_service_instance = AsyncMock()
    mock_stripe_service_instance.cancel_user_subscription.side_effect = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription is already canceled."
    )

    with patch("app.routers.auth.user_profile.StripeService", return_value=mock_stripe_service_instance):
        request_payload = SubscriptionCancelRequest(reason="Test").model_dump()
        response = await async_client.post(BASE_URL, json=request_payload)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json() == {"detail": "Subscription is already canceled."}
    del app.dependency_overrides[get_current_active_user]


@pytest.mark.asyncio
async def test_cancel_subscription_stripe_api_error(async_client: AsyncClient):
    """Test cancellation attempt when Stripe API returns an error."""
    mock_user = User(id=4, email="test4@example.com", is_verified=True, auth_type="password")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    mock_stripe_service_instance = AsyncMock()
    mock_stripe_service_instance.cancel_user_subscription.side_effect = HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stripe API error: Connection failed"
    )

    with patch("app.routers.auth.user_profile.StripeService", return_value=mock_stripe_service_instance):
        request_payload = SubscriptionCancelRequest(reason="Test").model_dump()
        response = await async_client.post(BASE_URL, json=request_payload)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    # The router wraps generic exceptions, so the detail might change
    # For this test, we check the status code and that the service method was called.
    # The actual detail from StripeService is "Stripe API error: Connection failed"
    # The router changes it to "An unexpected error occurred while canceling the subscription."
    # This is because the router's except Exception block catches it if StripeService doesn't raise HTTPException directly.
    # Let's adjust StripeService to re-raise Stripe's HTTPExceptions or wrap them carefully.
    # For now, the router's generic message is tested.
    # assert response.json() == {"detail": "Stripe API error: Connection failed"}
    # Updated assertion based on current router implementation:
    # The StripeService mock raises an HTTPException, which should be re-raised by the router.
    assert response.json() == {"detail": "Stripe API error: Connection failed"}

    del app.dependency_overrides[get_current_active_user]


@pytest.mark.asyncio
async def test_cancel_subscription_no_reason_provided(async_client: AsyncClient):
    """Test successful subscription cancellation when no reason is provided."""
    mock_user = User(id=5, email="test5@example.com", is_verified=True, auth_type="password")
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    mock_stripe_service_instance = AsyncMock()
    mock_stripe_service_instance.cancel_user_subscription.return_value = {
        "stripe_subscription_id": "sub_test567",
        "subscription_status": "active",
        "period_end_date": "2026-01-15T10:00:00Z"
    }

    with patch("app.routers.auth.user_profile.StripeService", return_value=mock_stripe_service_instance):
        # Send request with no 'reason' field (it's optional)
        response = await async_client.post(BASE_URL, json={}) # Empty JSON or specific model without reason

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["message"] == "Subscription cancellation initiated successfully. Access remains until 2026-01-15T10:00:00Z."
    assert response_data["subscription_status"] == "active"

    mock_stripe_service_instance.cancel_user_subscription.assert_called_once_with(
        user_id=mock_user.id,
        reason=None # Expect reason to be None
    )
    del app.dependency_overrides[get_current_active_user]

# TODO:
# - Test case for unauthenticated user (FastAPI should return 401 automatically due to Depends(get_current_active_user))
#   This might require testing the dependency itself or relying on FastAPI's behavior.