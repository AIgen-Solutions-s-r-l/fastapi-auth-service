"""Unit tests for the User Status API endpoint (/api/v1/users/me/status)."""

import pytest
from httpx import AsyncClient
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta, UTC
from decimal import Decimal
import stripe # Add missing import

from app.models.user import User
from app.models.credit import UserCredit
from app.models.plan import Plan, Subscription
from app.schemas.auth_schemas import UserStatusResponse, SubscriptionStatusResponse
from app.core.security import create_access_token

# Test user data
TEST_USER_EMAIL = "statususer@example.com"
TEST_USER_PASSWORD = "statuspassword"

@pytest.mark.asyncio
async def test_get_user_status_with_active_subscription(
    client: AsyncClient, db_session: AsyncSession, test_user_with_profile_data: User
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
    db_session.add(plan)
    await db_session.flush()

    # Create a subscription for the user
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_active_status",
        status="active",
        is_active=True,
        renewal_date=datetime.now(UTC) + timedelta(days=30),
        start_date=datetime.now(UTC) - timedelta(days=5),
        current_period_end_stripe_mock=datetime.now(UTC) + timedelta(days=30), # For mocking
        trial_end_date_stripe_mock=None, # For mocking
        cancel_at_period_end_stripe_mock=False # For mocking
    )
    db_session.add(subscription)

    # Create user credits
    user_credit = UserCredit(user_id=user.id, balance=Decimal("50.00"))
    db_session.add(user_credit)
    
    user.account_status = "active" # Ensure user account status is set
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(plan)
    await db_session.refresh(subscription)
    await db_session.refresh(user_credit)


    # Generate access token for the user
    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Mock the Stripe API call within UserService.get_user_status_details
    # The actual Stripe call is stripe.Subscription.retrieve
    mock_stripe_sub_data = {
        "id": "sub_test_active_status",
        "status": "active",
        "current_period_end": int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
        "trial_end": None,
        "cancel_at_period_end": False,
        # Add other fields as necessary if your code uses them
    }

    with patch("stripe.Subscription.retrieve", AsyncMock(return_value=mock_stripe_sub_data)) as mock_stripe_retrieve:
        response = await client.get("/auth/me/status", headers=headers)

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
    
    mock_stripe_retrieve.assert_called_once_with("sub_test_active_status")


@pytest.mark.asyncio
async def test_get_user_status_no_subscription(
    client: AsyncClient, db_session: AsyncSession, test_user_with_profile_data: User
):
    """Test successfully retrieving user status when the user has no active subscription."""
    user = test_user_with_profile_data
    
    # Create user credits
    user_credit = UserCredit(user_id=user.id, balance=Decimal("25.00"))
    db_session.add(user_credit)
    
    user.account_status = "new_user"
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(user_credit)

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    response = await client.get("/auth/me/status", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "new_user"
    assert data["credits_remaining"] == 25
    assert data["subscription"] is None

@pytest.mark.asyncio
async def test_get_user_status_trialing_subscription(
    client: AsyncClient, db_session: AsyncSession, test_user_with_profile_data: User
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
    db_session.add(plan)
    await db_session.flush()

    trial_end_timestamp = datetime.now(UTC) + timedelta(days=14)
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_trialing_status",
        status="trialing", # DB status
        is_active=True,
        renewal_date=trial_end_timestamp + timedelta(days=1), # Renewal after trial
        start_date=datetime.now(UTC) - timedelta(days=1),
        current_period_end_stripe_mock=trial_end_timestamp, # For mocking
        trial_end_date_stripe_mock=trial_end_timestamp, # For mocking
        cancel_at_period_end_stripe_mock=False # For mocking
    )
    db_session.add(subscription)

    user_credit = UserCredit(user_id=user.id, balance=Decimal("10.00"))
    db_session.add(user_credit)
    
    user.account_status = "trialing"
    db_session.add(user)
    await db_session.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_stripe_sub_data = {
        "id": "sub_test_trialing_status",
        "status": "trialing", # Stripe status
        "current_period_end": int(trial_end_timestamp.timestamp()), # End of current period (trial)
        "trial_end": int(trial_end_timestamp.timestamp()),
        "cancel_at_period_end": False,
    }

    with patch("stripe.Subscription.retrieve", AsyncMock(return_value=mock_stripe_sub_data)) as mock_stripe_retrieve:
        response = await client.get("/auth/me/status", headers=headers)

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
    
    mock_stripe_retrieve.assert_called_once_with("sub_test_trialing_status")


@pytest.mark.asyncio
async def test_get_user_status_unauthorized(client: AsyncClient):
    """Test attempting to get user status without authentication."""
    response = await client.get("/auth/me/status")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Not authenticated"}

@pytest.mark.asyncio
async def test_get_user_status_stripe_api_error(
    client: AsyncClient, db_session: AsyncSession, test_user_with_profile_data: User
):
    """Test handling of Stripe API error when fetching subscription details."""
    user = test_user_with_profile_data
    
    plan = Plan(name="Error Plan", credit_amount=1, price=1, stripe_product_id="prod_err", stripe_price_id="price_err")
    db_session.add(plan)
    await db_session.flush()

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_stripe_error",
        status="active",
        is_active=True,
        renewal_date=datetime.now(UTC) + timedelta(days=30)
    )
    db_session.add(subscription)
    user_credit = UserCredit(user_id=user.id, balance=Decimal("5.00"))
    db_session.add(user_credit)
    user.account_status = "active"
    db_session.add(user)
    await db_session.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    # Mock stripe.Subscription.retrieve to raise a StripeError
    with patch("stripe.Subscription.retrieve", AsyncMock(side_effect=stripe.error.APIError("Stripe API is down"))) as mock_stripe_retrieve:
        response = await client.get("/auth/me/status", headers=headers)

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
    
    mock_stripe_retrieve.assert_called_once_with("sub_test_stripe_error")


@pytest.mark.asyncio
async def test_get_user_status_frozen_account(
    client: AsyncClient, db_session: AsyncSession, test_user_with_profile_data: User
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
    db_session.add(plan)
    await db_session.flush()

    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_frozen_status",
        status="past_due", # DB status
        is_active=False, # A frozen/past_due subscription is typically not active
        renewal_date=datetime.now(UTC) - timedelta(days=5), # Renewal date in the past
        start_date=datetime.now(UTC) - timedelta(days=35),
        current_period_end_stripe_mock=datetime.now(UTC) - timedelta(days=5),
        trial_end_date_stripe_mock=None,
        cancel_at_period_end_stripe_mock=False
    )
    db_session.add(subscription)

    user_credit = UserCredit(user_id=user.id, balance=Decimal("5.00"))
    db_session.add(user_credit)
    
    user.account_status = "frozen" # Key status for this test
    db_session.add(user)
    await db_session.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_stripe_sub_data = {
        "id": "sub_test_frozen_status",
        "status": "past_due", # Stripe status
        "current_period_end": int((datetime.now(UTC) - timedelta(days=5)).timestamp()),
        "trial_end": None,
        "cancel_at_period_end": False,
    }

    with patch("stripe.Subscription.retrieve", AsyncMock(return_value=mock_stripe_sub_data)) as mock_stripe_retrieve:
        response = await client.get("/auth/me/status", headers=headers)

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
    
    mock_stripe_retrieve.assert_called_once_with("sub_test_frozen_status")


@pytest.mark.asyncio
async def test_get_user_status_canceled_subscription(
    client: AsyncClient, db_session: AsyncSession, test_user_with_profile_data: User
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
    db_session.add(plan)
    await db_session.flush()

    # Subscription was active, then canceled
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        stripe_subscription_id="sub_test_canceled_status",
        status="canceled", # DB status
        is_active=False,
        renewal_date=datetime.now(UTC) - timedelta(days=10), # Renewal would have been in past
        start_date=datetime.now(UTC) - timedelta(days=40),
        end_date=datetime.now(UTC) - timedelta(days=10), # Actual cancellation date
        current_period_end_stripe_mock=datetime.now(UTC) - timedelta(days=10),
        trial_end_date_stripe_mock=None,
        cancel_at_period_end_stripe_mock=False # Explicitly canceled, not at period end
    )
    db_session.add(subscription)

    user_credit = UserCredit(user_id=user.id, balance=Decimal("2.00"))
    db_session.add(user_credit)
    
    user.account_status = "active" # User account might still be active, but subscription is canceled
    db_session.add(user)
    await db_session.commit()

    token_data = {"sub": user.email, "id": user.id}
    access_token = create_access_token(data=token_data)
    headers = {"Authorization": f"Bearer {access_token}"}

    mock_stripe_sub_data = {
        "id": "sub_test_canceled_status",
        "status": "canceled", # Stripe status
        "current_period_end": int((datetime.now(UTC) - timedelta(days=10)).timestamp()),
        "trial_end": None,
        "cancel_at_period_end": False, # Or True if it was set to cancel at period end and period ended
        "canceled_at": int((datetime.now(UTC) - timedelta(days=10)).timestamp()),
    }

    with patch("stripe.Subscription.retrieve", AsyncMock(return_value=mock_stripe_sub_data)) as mock_stripe_retrieve:
        response = await client.get("/auth/me/status", headers=headers)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["user_id"] == str(user.id)
    assert data["account_status"] == "active" # User account can be active even if sub is canceled
    assert data["credits_remaining"] == 2
    assert data["subscription"] is not None # API returns the latest (canceled) subscription
    assert data["subscription"]["stripe_subscription_id"] == "sub_test_canceled_status"
    assert data["subscription"]["status"] == "canceled"
    assert data["subscription"]["plan_name"] == "Canceled Plan"
    assert datetime.fromisoformat(data["subscription"]["current_period_end"].replace("Z", "+00:00")).date() == (datetime.now(UTC) - timedelta(days=10)).date()
    
    mock_stripe_retrieve.assert_called_once_with("sub_test_canceled_status")

# TODO: Add test for user not found (e.g., token for a deleted user, if get_current_active_user allows it)
# This might be tricky if get_current_active_user already raises 401/404.
# If get_current_active_user handles "user not found" by raising 401, then that's covered by unauthorized.
# If it raises 404, a specific test might be needed if the desired behavior for /me/status is different.

# TODO: Add test for when user.credits is None (though current User model initializes it)

# TODO: Add test for when user.subscriptions is empty or None. (Covered by test_get_user_status_no_subscription)

# TODO: Add test for subscription status sync logic (Stripe status differs from DB status)