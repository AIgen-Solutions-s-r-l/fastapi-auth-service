"""Tests for subscription cancellation endpoint."""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import patch, MagicMock
from fastapi import status
from sqlalchemy import select

from app.models.plan import Subscription, Plan
from app.models.user import User


@pytest.fixture
def mock_stripe_cancel(monkeypatch):
    """Mock the Stripe cancel_subscription method."""
    async def mock_cancel(*args, **kwargs):
        return True
    
    with patch("app.services.credit.stripe_integration.StripeIntegrationService.cancel_subscription", 
               side_effect=mock_cancel) as mock:
        yield mock


@pytest.mark.asyncio
async def test_cancel_subscription_success(client, db, auth_header, mock_stripe_cancel):
    """Test successful subscription cancellation."""
    # Get the authenticated user from the database
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == "auth_test@example.com"))
    user = result.scalar_one()
    
    # Create a test plan
    plan = Plan(
        name="Test Plan",
        description="Test Plan Description",
        price=10.0,
        credit_amount=100,
        is_active=True,
        stripe_price_id="price_123",
        stripe_product_id="prod_123"
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    # Create a test subscription
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        start_date=datetime.now(UTC),
        renewal_date=datetime.now(UTC) + timedelta(days=30),
        is_active=True,
        auto_renew=True,
        stripe_subscription_id="sub_123",
        status="active"
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    
    # Make the request to cancel the subscription
    response = client.post(
        "/credits/subscriptions/cancel",
        json={
            "subscription_id": subscription.id,
            "cancel_in_stripe": True
        },
        headers=auth_header
    )
    
    # Check the response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["plan_name"] == "Test Plan"
    assert data["message"] == "Subscription successfully canceled"
    
    # Verify the subscription was updated in the database
    result = await db.execute(select(Subscription).where(Subscription.id == subscription.id))
    updated_subscription = result.scalar_one()
    assert updated_subscription.is_active is False
    assert updated_subscription.status == "canceled"
    assert updated_subscription.auto_renew is False
    
    # Verify Stripe cancellation was called
    mock_stripe_cancel.assert_called_once_with("sub_123")


@pytest.mark.asyncio
async def test_cancel_subscription_already_canceled(client, db, auth_header):
    """Test cancellation of an already canceled subscription."""
    # Get the authenticated user from the database
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == "auth_test@example.com"))
    user = result.scalar_one()
    
    # Create a test plan
    plan = Plan(
        name="Test Plan 2",
        description="Test Plan Description",
        price=10.0,
        credit_amount=100,
        is_active=True,
        stripe_price_id="price_456",
        stripe_product_id="prod_456"
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    # Create an already canceled subscription
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        start_date=datetime.now(UTC),
        renewal_date=datetime.now(UTC) + timedelta(days=30),
        is_active=False,
        auto_renew=False,
        stripe_subscription_id="sub_456",
        status="canceled"
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    
    # Make the request to cancel the subscription
    response = client.post(
        "/credits/subscriptions/cancel",
        json={
            "subscription_id": subscription.id,
            "cancel_in_stripe": True
        },
        headers=auth_header
    )
    
    # Check the response
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is False
    assert "already canceled" in data["message"]


@pytest.mark.asyncio
async def test_cancel_subscription_unauthorized(client, db, auth_header):
    """Test cancellation of another user's subscription."""
    # Get the authenticated user from the database (user1)
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == "auth_test@example.com"))
    user1 = result.scalar_one()
    
    # Create a second test user (user2)
    user2 = User(
        email="user2@example.com",
        hashed_password="hashed_password",
        auth_type="password",
        is_admin=False,
        is_verified=True
    )
    db.add(user2)
    await db.commit()
    await db.refresh(user2)
    
    # Create a test plan
    plan = Plan(
        name="Test Plan 3",
        description="Test Plan Description",
        price=10.0,
        credit_amount=100,
        is_active=True,
        stripe_price_id="price_789",
        stripe_product_id="prod_789"
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    
    # Create a subscription for user2
    subscription = Subscription(
        user_id=user2.id,
        plan_id=plan.id,
        start_date=datetime.now(UTC),
        renewal_date=datetime.now(UTC) + timedelta(days=30),
        is_active=True,
        auto_renew=True,
        stripe_subscription_id="sub_789",
        status="active"
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    
    # Make the request to cancel the subscription as user1
    # (auth_header is for user1)
    response = client.post(
        "/credits/subscriptions/cancel",
        json={
            "subscription_id": subscription.id,
            "cancel_in_stripe": True
        },
        headers=auth_header
    )
    
    # Check the response
    assert response.status_code == status.HTTP_403_FORBIDDEN
    data = response.json()
    assert "permission" in data["detail"]["message"]