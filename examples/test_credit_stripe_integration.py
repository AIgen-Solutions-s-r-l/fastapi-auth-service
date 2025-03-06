"""
Script to test the integration between our credit system and Stripe.

This script will:
1. Generate an authentication token for our test user
2. Call the credit API endpoints using the test Stripe data
3. Verify that credits are properly added based on Stripe transactions
"""

import asyncio
import json
import os
import sys
import httpx
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt
from pydantic import BaseModel
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Add the current directory to the path so we can import app modules
sys.path.append(os.getcwd())

from app.core.config import settings
from app.core.auth import create_access_token

# Load environment variables and Stripe test data
load_dotenv()
with open('stripe_test_data.json', 'r') as f:
    STRIPE_TEST_DATA = json.load(f)

# API configuration
API_URL = "http://localhost:8000"
TEST_USER_EMAIL = "test_stripe@example.com"
TEST_USER_ID = 40  # This should match the user ID created in prepare_test_environment.py


async def get_auth_token():
    """Generate an authentication token for the test user."""
    # Create a token with a 30-minute expiry
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": TEST_USER_EMAIL, "user_id": TEST_USER_ID},
        expires_delta=access_token_expires
    )
    return access_token


async def get_credit_balance(token):
    """
    Get the current credit balance of the test user.
    
    Args:
        token: Authentication token
        
    Returns:
        Dict with user_id, balance, and updated_at
    """
    print("\n=== Getting Credit Balance ===")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_URL}/credits/balance",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            balance_data = response.json()
            print(f"Current balance: {balance_data['balance']} credits")
            print(f"Last updated: {balance_data['updated_at']}")
            return balance_data
        else:
            print(f"Error getting balance: {response.status_code} - {response.text}")
            return None


async def add_credits_from_stripe_transaction(token, transaction_id, transaction_type):
    """
    Add credits using the Stripe transaction.
    
    Args:
        token: Authentication token
        transaction_id: Stripe transaction ID
        transaction_type: "oneoff" or "subscription"
        
    Returns:
        Dict with transaction response data or None if error
    """
    print(f"\n=== Adding Credits from Stripe {transaction_type.capitalize()} Transaction ===")
    print(f"Transaction ID: {transaction_id}")
    
    request_data = {
        "transaction_id": transaction_id,
        "transaction_type": transaction_type
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/credits/stripe/add",
            json=request_data,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            result = response.json()
            
            print(f"Transaction processed successfully:")
            print(f"- Transaction type: {result['transaction']['transaction_type']}")
            print(f"- Amount: ${result['transaction']['amount']}")
            
            if result['credit_transaction_id']:
                print(f"- Credit transaction ID: {result['credit_transaction_id']}")
                
            if result['subscription_id']:
                print(f"- Subscription ID: {result['subscription_id']}")
                
            print(f"- New balance: {result['new_balance']} credits")
            
            return result
        else:
            print(f"Error processing transaction: {response.status_code} - {response.text}")
            return None


async def test_oneoff_transaction():
    """Test adding credits from a one-time Stripe transaction."""
    # Get the first payment intent from test data
    if not STRIPE_TEST_DATA["payment_intents"]:
        print("No payment intents found in test data")
        return False
        
    payment_intent = STRIPE_TEST_DATA["payment_intents"][0]
    payment_intent_id = payment_intent["id"]
    
    # Get authentication token
    token = await get_auth_token()
    
    # Get initial balance
    initial_balance = await get_credit_balance(token)
    if not initial_balance:
        return False
    
    # Add credits using the payment intent
    result = await add_credits_from_stripe_transaction(
        token=token,
        transaction_id=payment_intent_id,
        transaction_type="oneoff"
    )
    
    if not result:
        return False
    
    # Get updated balance
    updated_balance = await get_credit_balance(token)
    if not updated_balance:
        return False
    
    # Verify balance was increased
    initial_amount = Decimal(str(initial_balance["balance"]))
    updated_amount = Decimal(str(updated_balance["balance"]))
    expected_increase = result["transaction"]["amount"] * Decimal('10')  # Assuming $1 = 10 credits
    
    print("\n=== Verification ===")
    print(f"Initial balance: {initial_amount} credits")
    print(f"Updated balance: {updated_amount} credits")
    print(f"Increase: {updated_amount - initial_amount} credits")
    print(f"Expected increase: {expected_increase} credits")
    
    if updated_amount > initial_amount:
        print("\n✅ Test passed! Credits were successfully added.")
        return True
    else:
        print("\n❌ Test failed! Balance did not increase as expected.")
        return False


async def main():
    """Main function to test the credit system Stripe integration."""
    print("=== Testing Credit System Stripe Integration ===")
    
    # Run the tests
    try:
        # Test one-time transaction
        oneoff_result = await test_oneoff_transaction()
        
        # Print summary
        print("\n=== Test Summary ===")
        
        if oneoff_result:
            print("✅ One-time transaction test: PASSED")
        else:
            print("❌ One-time transaction test: FAILED")
            
    except Exception as e:
        print(f"\n❌ Error running tests: {str(e)}")
    
    print("\nTest run complete.")


if __name__ == "__main__":
    asyncio.run(main())