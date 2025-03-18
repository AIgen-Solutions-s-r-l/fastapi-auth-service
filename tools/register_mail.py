#!/usr/bin/env python3
"""
Script to register a new email account and validate it using a token from the database.
"""

import requests
import json
import asyncio
import sys
import argparse

# API endpoints (corrected port to 8001 where Auth Service is running)
API_ENDPOINT = "http://localhost:8001/auth/register"
VERIFY_ENDPOINT = "http://localhost:8001/auth/verify-email"

async def get_verification_token(email):
    """Retrieve the verification token from the database."""
    try:
        from app.core.database import engine
        from app.models.user import User, EmailVerificationToken
        from sqlalchemy import select
        
        async with engine.begin() as conn:
            # Find the user by email
            result = await conn.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                print("User not found in the database")
                return None
                
            # Find the verification token for the user
            result = await conn.execute(
                select(EmailVerificationToken)
                .where(EmailVerificationToken.user_id == user.id)
                .where(EmailVerificationToken.used == False)  # Get unused token
            )
            token = result.scalar_one_or_none()
            if not token:
                print("Verification token not found for user")
                return None
                
            return token.token
            
    except Exception as e:
        print(f"Error retrieving verification token from database: {e}")
        return None

def register_user(email, password):
    """Register a new user with the provided email and password."""
    payload = {
        "email": email,
        "password": password
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    try:
        print(f"Registering user with email: {email}")
        data = json.dumps(payload)
        headers["Content-Length"] = str(len(data))
        
        response = requests.post(API_ENDPOINT, data=data, headers=headers)
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 201:
            print(f"Error response: {response.text}")
            return None
            
        response_data = response.json()
        print("Registration response:", json.dumps(response_data, indent=4))
        
        return response_data
        
    except requests.exceptions.RequestException as e:
        print(f"Request error during registration: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error during registration: {e}")
        return None

def verify_email(token):
    """Verify the registered email using the provided token."""
    headers = {
        "Accept": "application/json"
    }
    
    params = {
        "token": token
    }
    
    try:
        print(f"Verifying email with token: {token}")
        response = requests.get(VERIFY_ENDPOINT, params=params, headers=headers)
        
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            return None
            
        response_data = response.json()
        print("Verification response:", json.dumps(response_data, indent=4))
        
        return response_data
        
    except requests.exceptions.RequestException as e:
        print(f"Request error during verification: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error during verification: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Register a new user and verify email')
    parser.add_argument('--email', required=True, help='Email address for registration')
    parser.add_argument('--password', required=True, help='Password for registration')
    
    args = parser.parse_args()
    
    # Register the user
    registration_result = register_user(args.email, args.password)
    
    if not registration_result:
        print("Failed to register user.")
        sys.exit(1)
    
    if "message" in registration_result and "email" in registration_result:
        registered_email = registration_result["email"]
        print(f"Registration successful for: {registered_email}")
        
        # Get verification token from database
        print("Retrieving verification token from database...")
        token = asyncio.run(get_verification_token(registered_email))
        
        if token:
            print(f"Verification token: {token}")
            
            # Verify the email
            verification_result = verify_email(token)
            
            if verification_result and verification_result.get("message") == "Email verified successfully":
                print("Email verification successful!")
                token_info = f"Access token: {verification_result.get('access_token')}"
                print(token_info)
                print("\nAccount successfully registered and email verified!")
            else:
                print("Failed to verify email.")
                sys.exit(1)
        else:
            print("Failed to retrieve verification token. Email verification skipped.")
            sys.exit(1)
    else:
        print("Failed to register user properly.")
        sys.exit(1)

if __name__ == "__main__":
    main()