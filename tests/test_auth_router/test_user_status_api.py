"""Unit tests for the User Status API endpoint (/api/v1/users/me/status)."""

import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta, UTC
from decimal import Decimal
import stripe # Add missing import
import asyncio # Add import for asyncio

from app.models.user import User
from app.models.credit import UserCredit
from app.models.plan import Plan, Subscription
from app.schemas.auth_schemas import UserStatusResponse, SubscriptionStatusResponse
from app.schemas.trial_schemas import TrialEligibilityResponse, TrialEligibilityReasonCode # Added
from app.core.security import create_access_token

# Test user data
TEST_USER_EMAIL = "statususer@example.com"
TEST_USER_PASSWORD = "statuspassword"

@pytest.mark.asyncio
async def test_get_user_status_with_active_subscription(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test successfully retrieving user status with an active subscription."""
    user = test_user_with_profile_data # This fixture should create a user

    # Ensure the user from fixture is the one we want, or create a specific one
    # For simplicity, let's assume test_user_with_profile_data is our target user
    # If not, create a new user for this test
    
    # Create a plan
    plan = Plan(
        name="Pro Plan",
        credit_amount=Decimal("100.00"),
        price=Decimal("19.99"),
        stripe_price_id="price_pro_test",
        stripe_product_id="prod_pro_test",
    )
    db.add(plan)
    await db.flush()

    # Create a subscription for the user
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_active_status",
        status="active",
        is_active=True,
        renewal_date=datetime.now(UTC) + timedelta(days=30),
        start_date=datetime.now(UTC) - timedelta(days=5)
    )
    
    # Save these values for the mock
    current_period_end = datetime.now(UTC) + timedelta(days=30)
    trial_end_date = None
    cancel_at_period_end = False
    db.add(subscription)

    # Create user credits
    user_credit = UserCredit(user_id=user.id, balance=Decimal("50.00"))
    db.add(user_credit)
    
    user.account_status = "active" # Ensure user account status is set
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await db.refresh(plan)
    await db.refresh(subscription)
    await db.refresh(user_credit)


    # Generate access token for the user
    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Mock the Stripe API call within UserService.get_user_status_details
    # The actual Stripe call is stripe.Subscription.retrieve
    mock_stripe_sub_data = {
        "id": "sub_test_active_status",
        "status": "active",
        "current_period_end": int(current_period_end.timestamp()),
        "trial_end": None,
        "cancel_at_period_end": cancel_at_period_end,
        # Add other fields as necessary if your code uses them
    }
 
    # Mock asyncio.to_thread specifically for the stripe call
    async def mock_to_thread_side_effect(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == "sub_test_active_status" # Check subscription ID
            return mock_stripe_sub_data
        raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    with patch("asyncio.to_thread", AsyncMock(side_effect=mock_to_thread_side_effect)) as mock_asyncio_to_thread:
        response = await client.get("/auth/me/status", headers=headers) # Added await
 
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "active"
    assert data["credits_remaining"] == 50
    assert data["subscription"] is not None
    assert data["subscription"]["stripe_subscription_id"] == "sub_test_active_status"
    assert data["subscription"]["status"] == "active"
    assert data["subscription"]["plan_name"] == "Pro Plan"
    assert data["subscription"]["cancel_at_period_end"] is False
    assert data["subscription"]["trial_end_date"] is None
    assert datetime.fromisoformat(data["subscription"]["current_period_end"].replace("Z", "+00:00")).date() == (datetime.now(UTC) + timedelta(days=30)).date()
    
    # Verify asyncio.to_thread was called correctly
    mock_asyncio_to_thread.assert_called_once_with(stripe.Subscription.retrieve, "sub_test_active_status")


@pytest.mark.asyncio
async def test_get_user_status_no_subscription(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test successfully retrieving user status when the user has no active subscription."""
    user = test_user_with_profile_data
    
    # Create user credits
    user_credit = UserCredit(user_id=user.id, balance=Decimal("25.00"))
    db.add(user_credit)
    
    user.account_status = "new_user"
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await db.refresh(user_credit)

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}
 
    response = await client.get("/auth/me/status", headers=headers) # Added await
 
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "new_user"
    assert data["credits_remaining"] == 25
    assert data["subscription"] is None

@pytest.mark.asyncio
async def test_get_user_status_trialing_subscription(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test successfully retrieving user status with a trialing subscription."""
    user = test_user_with_profile_data
    
    plan = Plan(
        name="Trial Plan",
        credit_amount=Decimal("10.00"),
        price=Decimal("0.00"),
        stripe_price_id="price_trial_test",
        stripe_product_id="prod_trial_test",
    )
    db.add(plan)
    await db.flush()

    trial_end_timestamp = datetime.now(UTC) + timedelta(days=14)
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_trialing_status",
        status="trialing", # DB status
        is_active=True,
        renewal_date=trial_end_timestamp + timedelta(days=1), # Renewal after trial
        start_date=datetime.now(UTC) - timedelta(days=1)
    )
    
    # Save these values for the mock
    current_period_end = trial_end_timestamp
    trial_end_date = trial_end_timestamp
    cancel_at_period_end = False
    db.add(subscription)

    user_credit = UserCredit(user_id=user.id, balance=Decimal("10.00"))
    db.add(user_credit)
    
    user.account_status = "trialing"
    db.add(user)
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_stripe_sub_data = {
        "id": "sub_test_trialing_status",
        "status": "trialing", # Stripe status
        "current_period_end": int(current_period_end.timestamp()), # End of current period (trial)
        "trial_end": int(trial_end_date.timestamp()),
        "cancel_at_period_end": cancel_at_period_end,
    }
 
    # Mock asyncio.to_thread specifically for the stripe call
    def mock_to_thread_side_effect(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == "sub_test_trialing_status" # Check subscription ID
            return mock_stripe_sub_data
        raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    with patch("asyncio.to_thread", side_effect=mock_to_thread_side_effect) as mock_asyncio_to_thread:
        response = await client.get("/auth/me/status", headers=headers) # Added await
 
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "trialing"
    assert data["credits_remaining"] == 10
    assert data["subscription"] is not None
    assert data["subscription"]["stripe_subscription_id"] == "sub_test_trialing_status"
    assert data["subscription"]["status"] == "trialing"
    assert data["subscription"]["plan_name"] == "Trial Plan"
    assert datetime.fromisoformat(data["subscription"]["trial_end_date"].replace("Z", "+00:00")).date() == trial_end_timestamp.date()
    assert datetime.fromisoformat(data["subscription"]["current_period_end"].replace("Z", "+00:00")).date() == trial_end_timestamp.date()
    assert data["subscription"]["cancel_at_period_end"] is False
    
    # Verify asyncio.to_thread was called correctly
    mock_asyncio_to_thread.assert_called_once_with(stripe.Subscription.retrieve, "sub_test_trialing_status")


@pytest.mark.asyncio
async def test_get_user_status_unauthorized(client: AsyncClient):
    """Test attempting to get user status without authentication."""
    response = await client.get("/auth/me/status") # Added await
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    # The response format might be slightly different, just check that it contains an authentication error
    response_json = response.json()
    assert "detail" in response_json
    assert "authenticated" in str(response_json["detail"]).lower()

@pytest.mark.asyncio
async def test_get_user_status_stripe_api_error(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test handling of Stripe API error when fetching subscription details."""
    user = test_user_with_profile_data
    
    plan = Plan(name="Error Plan", credit_amount=1, price=1, stripe_product_id="prod_err", stripe_price_id="price_err")
    db.add(plan)
    await db.flush()

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_stripe_error",
        status="active",
        is_active=True,
        renewal_date=datetime.now(UTC) + timedelta(days=30)
    )
    db.add(subscription)
    user_credit = UserCredit(user_id=user.id, balance=Decimal("5.00"))
    db.add(user_credit)
    user.account_status = "active"
    db.add(user)
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Mock asyncio.to_thread to raise StripeError when stripe.Subscription.retrieve is called
    def mock_to_thread_side_effect(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == "sub_test_stripe_error" # Check subscription ID
            raise stripe.error.APIError("Stripe API is down")
        raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")
 
    with patch("app.services.user_service.asyncio.to_thread", side_effect=mock_to_thread_side_effect) as mock_asyncio_to_thread:
        response = await client.get("/auth/me/status", headers=headers) # Added await
  
    assert response.status_code == status.HTTP_200_OK # Endpoint should still succeed, but subscription details might be from DB / defaults
    data = response.json()
    
    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "active"
    assert data["credits_remaining"] == 5
    assert data["subscription"] is not None
    # Check that it falls back to DB status if Stripe fails
    assert data["subscription"]["status"] == "active" 
    assert data["subscription"]["stripe_subscription_id"] == "sub_test_stripe_error"
    assert data["subscription"]["plan_name"] == "Error Plan"
    # Dates might be None if Stripe call failed and they weren't in DB mock
    assert data["subscription"]["trial_end_date"] is None 
    assert data["subscription"]["current_period_end"] is None
    assert data["subscription"]["cancel_at_period_end"] is False
    
    # Verify asyncio.to_thread was called correctly
    mock_asyncio_to_thread.assert_called_once_with(stripe.Subscription.retrieve, "sub_test_stripe_error")


@pytest.mark.asyncio
async def test_get_user_status_frozen_account(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test successfully retrieving user status for a user with a frozen account."""
    user = test_user_with_profile_data
    
    plan = Plan(
        name="Frozen Plan",
        credit_amount=Decimal("0"),
        price=Decimal("9.99"),
        stripe_price_id="price_frozen_test",
        stripe_product_id="prod_frozen_test",
    )
    db.add(plan)
    await db.flush()

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_frozen_status",
        status="past_due", # DB status
        is_active=False, # A frozen/past_due subscription is typically not active
        renewal_date=datetime.now(UTC) - timedelta(days=5), # Renewal date in the past
        start_date=datetime.now(UTC) - timedelta(days=35)
    )
    
    # Save these values for the mock
    current_period_end = datetime.now(UTC) - timedelta(days=5)
    trial_end_date = None
    cancel_at_period_end = False
    db.add(subscription)

    user_credit = UserCredit(user_id=user.id, balance=Decimal("5.00"))
    db.add(user_credit)
    
    user.account_status = "frozen" # Key status for this test
    db.add(user)
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_stripe_sub_data = {
        "id": "sub_test_frozen_status",
        "status": "past_due", # Stripe status
        "current_period_end": int(current_period_end.timestamp()),
        "trial_end": None,
        "cancel_at_period_end": cancel_at_period_end,
    }
 
    # Mock asyncio.to_thread specifically for the stripe call
    def mock_to_thread_side_effect(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == "sub_test_frozen_status" # Check subscription ID
            return mock_stripe_sub_data
        raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    with patch("asyncio.to_thread", side_effect=mock_to_thread_side_effect) as mock_asyncio_to_thread:
        response = await client.get("/auth/me/status", headers=headers) # Added await
  
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "frozen"
    assert data["credits_remaining"] == 5
    assert data["subscription"] is not None
    assert data["subscription"]["stripe_subscription_id"] == "sub_test_frozen_status"
    assert data["subscription"]["status"] == "past_due"
    assert data["subscription"]["plan_name"] == "Frozen Plan"
    assert data["subscription"]["cancel_at_period_end"] is False
    assert data["subscription"]["trial_end_date"] is None
    assert datetime.fromisoformat(data["subscription"]["current_period_end"].replace("Z", "+00:00")).date() == (datetime.now(UTC) - timedelta(days=5)).date()
    
    # Verify asyncio.to_thread was called correctly
    mock_asyncio_to_thread.assert_called_once_with(stripe.Subscription.retrieve, "sub_test_frozen_status")


@pytest.mark.asyncio
async def test_get_user_status_canceled_subscription(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test successfully retrieving user status for a user with a canceled subscription."""
    user = test_user_with_profile_data
    
    plan = Plan(
        name="Canceled Plan",
        credit_amount=Decimal("0"),
        price=Decimal("9.99"),
        stripe_price_id="price_canceled_test",
        stripe_product_id="prod_canceled_test",
    )
    db.add(plan)
    await db.flush()

    # Subscription was active, then canceled
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_canceled_status",
        status="canceled", # DB status
        is_active=False,
        renewal_date=datetime.now(UTC) - timedelta(days=10), # Renewal would have been in past
        start_date=datetime.now(UTC) - timedelta(days=40)
    )
    
    # Save these values for the mock
    current_period_end = datetime.now(UTC) - timedelta(days=10)
    trial_end_date = None
    cancel_at_period_end = False
    db.add(subscription)

    user_credit = UserCredit(user_id=user.id, balance=Decimal("2.00"))
    db.add(user_credit)
    
    user.account_status = "active" # User account might still be active, but subscription is canceled
    db.add(user)
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_stripe_sub_data = {
        "id": "sub_test_canceled_status",
        "status": "canceled", # Stripe status
        "current_period_end": int(current_period_end.timestamp()),
        "trial_end": None,
        "cancel_at_period_end": cancel_at_period_end, # Or True if it was set to cancel at period end and period ended
        "canceled_at": int(current_period_end.timestamp()),
    }
 
    # Mock asyncio.to_thread specifically for the stripe call
    def mock_to_thread_side_effect(func, *args, **kwargs):
        if func == stripe.Subscription.retrieve:
            assert args[0] == "sub_test_canceled_status" # Check subscription ID
            return mock_stripe_sub_data
        raise NotImplementedError(f"Unexpected call to asyncio.to_thread with {func.__name__}")

    with patch("asyncio.to_thread", side_effect=mock_to_thread_side_effect) as mock_asyncio_to_thread:
        response = await client.get("/auth/me/status", headers=headers) # Added await
  
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "active" # User account can be active even if sub is canceled
    assert data["credits_remaining"] == 2
    assert data["subscription"] is not None # API returns the latest (canceled) subscription
    assert data["subscription"]["stripe_subscription_id"] == "sub_test_canceled_status"
    assert data["subscription"]["status"] == "canceled"
    assert data["subscription"]["plan_name"] == "Canceled Plan"
    assert data["subscription"]["trial_end_date"] is None
    assert data["subscription"]["cancel_at_period_end"] is False
    assert datetime.fromisoformat(data["subscription"]["current_period_end"].replace("Z", "+00:00")).date() == (datetime.now(UTC) - timedelta(days=10)).date()
    
    # Verify asyncio.to_thread was called correctly
    mock_asyncio_to_thread.assert_called_once_with(stripe.Subscription.retrieve, "sub_test_canceled_status")

# TODO: Add test for user not found (e.g., token for a deleted user, if get_current_active_user allows it)
# This might be tricky if get_current_active_user already raises 401/404.
# If get_current_active_user handles "user not found" by raising 401, then that's covered by unauthorized.
# If it raises 404, a specific test might be needed if the desired behavior for /me/status is different.

# TODO: Add test for when user.credits is None (though current User model initializes it)

# TODO: Add test for when user.subscriptions is empty or None. (Covered by test_get_user_status_no_subscription)

# TODO: Add test for subscription status sync logic (Stripe status differs from DB status)


@pytest.mark.asyncio
async def test_get_trial_eligibility_eligible(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test /users/me/trial-eligibility when user is eligible."""
    user = test_user_with_profile_data
    user.has_consumed_initial_trial = False
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Mock the UserService.get_trial_eligibility method
    mock_eligibility_response = TrialEligibilityResponse(
        is_eligible=True,
        reason_code=TrialEligibilityReasonCode.ELIGIBLE,
        message="User is eligible for a free trial."
    )
    with patch("app.routers.auth.user_profile.UserService.get_trial_eligibility", AsyncMock(return_value=mock_eligibility_response)) as mock_get_eligibility:
        response = await client.get("/auth/me/trial-eligibility", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_eligible"] is True
    assert data["reason_code"] == "ELIGIBLE"
    assert data["message"] == "User is eligible for a free trial."
    mock_get_eligibility.assert_called_once()


@pytest.mark.asyncio
async def test_get_trial_eligibility_consumed_trial(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test /users/me/trial-eligibility when user has consumed trial."""
    user = test_user_with_profile_data
    user.has_consumed_initial_trial = True
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_eligibility_response = TrialEligibilityResponse(
        is_eligible=False,
        reason_code=TrialEligibilityReasonCode.TRIAL_CONSUMED,
        message="User has already consumed their initial free trial."
    )
    with patch("app.routers.auth.user_profile.UserService.get_trial_eligibility", AsyncMock(return_value=mock_eligibility_response)) as mock_get_eligibility:
        response = await client.get("/auth/me/trial-eligibility", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_eligible"] is False
    assert data["reason_code"] == "TRIAL_CONSUMED"
    mock_get_eligibility.assert_called_once()


@pytest.mark.asyncio
async def test_get_trial_eligibility_currently_in_trial(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test /users/me/trial-eligibility when user is currently in trial."""
    user = test_user_with_profile_data
    user.has_consumed_initial_trial = False
    await db.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_eligibility_response = TrialEligibilityResponse(
        is_eligible=False,
        reason_code=TrialEligibilityReasonCode.CURRENTLY_IN_TRIAL,
        message="User is currently in an active trial period."
    )
    with patch("app.routers.auth.user_profile.UserService.get_trial_eligibility", AsyncMock(return_value=mock_eligibility_response)) as mock_get_eligibility:
        response = await client.get("/auth/me/trial-eligibility", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_eligible"] is False
    assert data["reason_code"] == "CURRENTLY_IN_TRIAL"
    mock_get_eligibility.assert_called_once()


@pytest.mark.asyncio
async def test_get_trial_eligibility_unauthorized(client: AsyncClient):
    """Test /users/me/trial-eligibility when unauthorized."""
    response = await client.get("/auth/me/trial-eligibility")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_trial_eligibility_service_error(
    client: AsyncClient, db: AsyncSession, test_user_with_profile_data: User
):
    """Test /users/me/trial-eligibility when the service layer raises an unexpected error."""
    user = test_user_with_profile_data
    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    with patch("app.routers.auth.user_profile.UserService.get_trial_eligibility", AsyncMock(side_effect=Exception("Service layer error"))) as mock_get_eligibility:
        response = await client.get("/auth/me/trial-eligibility", headers=headers)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "An unexpected error occurred while checking trial eligibility."
    mock_get_eligibility.assert_called_once()