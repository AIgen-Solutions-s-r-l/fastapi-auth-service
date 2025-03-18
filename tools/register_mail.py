#!/usr/bin/env python3
"""
Script to register a new email account and validate it using a token from the database.
"""

import requests
import json
import sys
import argparse
import os
import sqlite3
import time

# API endpoints
API_ENDPOINT = "http://localhost:8001/auth/register"
VERIFY_ENDPOINT = "http://localhost:8001/auth/verify-email"

def get_db_info(db_path="test.db"):
    """Print debug info about the database"""
    try:
        if not os.path.exists(db_path):
            print(f"Database file not found: {db_path}")
            return False
        
        print(f"Database file exists: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # List tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print(f"Database tables: {[t[0] for t in tables]}")
        
        # Count users
        try:
            cursor.execute("SELECT COUNT(*) FROM users;")
            user_count = cursor.fetchone()[0]
            print(f"Total users in database: {user_count}")
        except sqlite3.OperationalError as e:
            print(f"Error counting users: {e}")
        
        conn.close()
        return True
    except Exception as e:
        print(f"Error getting database info: {e}")
        return False

def get_verification_token(email, db_path="test.db"):
    """
    Retrieve the verification token from the database directly using SQLite.
    
    Args:
        email: The email address to look up
        db_path: Path to the SQLite database file
        
    Returns:
        The verification token if found, None otherwise
    """
    try:
        # Make sure the database file exists
        if not os.path.exists(db_path):
            print(f"Database file not found: {db_path}")
            return None
            
        # Connect to the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()
        
        # First get the user_id for the email
        print(f"Looking up user with email: {email}")
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user_row = cursor.fetchone()
        
        if not user_row:
            print(f"User with email {email} not found in the database")
            
            # List recent users for debugging
            print("Recent users in database:")
            cursor.execute("SELECT id, email, is_verified FROM users ORDER BY id DESC LIMIT 5")
            recent_users = cursor.fetchall()
            for user in recent_users:
                print(f"  ID: {user['id']}, Email: {user['email']}, Verified: {user['is_verified']}")
            
            return None
            
        user_id = user_row[0]
        print(f"Found user with ID: {user_id}")
        
        # Now get the verification token for this user
        cursor.execute(
            "SELECT token, created_at, expires_at FROM email_verification_tokens "
            "WHERE user_id = ? AND used = 0 "
            "ORDER BY created_at DESC LIMIT 1", 
            (user_id,)
        )
        
        token_row = cursor.fetchone()
        
        if not token_row:
            print(f"No unused verification token found for user ID {user_id}")
            
            # Check if there are any tokens for this user
            cursor.execute(
                "SELECT token, created_at, used FROM email_verification_tokens "
                "WHERE user_id = ? ORDER BY created_at DESC", 
                (user_id,)
            )
            all_tokens = cursor.fetchall()
            
            if all_tokens:
                print(f"Found {len(all_tokens)} tokens for user (including used ones):")
                for t in all_tokens:
                    print(f"  Token: {t['token'][:10]}..., Created: {t['created_at']}, Used: {t['used']}")
            else:
                print("No tokens found for this user.")
            
            return None
            
        token = token_row['token']
        print(f"Found token created at {token_row['created_at']}, expires at {token_row['expires_at']}")
        conn.close()
        return token
        
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        return None
    except Exception as e:
        print(f"Error retrieving verification token: {e}")
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
    parser.add_argument('--db', default='test.db', help='Path to the SQLite database file')
    parser.add_argument('--delay', type=int, default=2, help='Delay in seconds after registration')
    
    args = parser.parse_args()
    
    # Show database info
    print("\n=== Database Information ===")
    get_db_info(args.db)
    
    # Register the user
    print("\n=== Registering User ===")
    registration_result = register_user(args.email, args.password)
    
    if not registration_result:
        print("Failed to register user.")
        sys.exit(1)
    
    if "message" in registration_result and "email" in registration_result:
        registered_email = registration_result["email"]
        print(f"Registration successful for: {registered_email}")
        
        # Wait for database operations to complete
        print(f"Waiting {args.delay} seconds for database operations to complete...")
        time.sleep(args.delay)
        
        # Get verification token from database
        print("\n=== Retrieving Verification Token ===")
        token = get_verification_token(registered_email, args.db)
        
        if token:
            print(f"Verification token: {token}")
            
            # Verify the email
            print("\n=== Verifying Email ===")
            verification_result = verify_email(token)
            
            if verification_result and verification_result.get("message") == "Email verified successfully":
                print("Email verification successful!")
                token_info = f"Access token: {verification_result.get('access_token')}"
                print(token_info)
                print("\nAccount successfully registered and email verified!")
                
                # Output how to use the token
                print("\n=== Example Usage with curl ===")
                print(f"curl -H 'Authorization: Bearer {verification_result.get('access_token')}' http://localhost:8001/auth/me")
                
                return 0
            else:
                print("Failed to verify email.")
                sys.exit(1)
        else:
            print("Failed to retrieve verification token. Email verification skipped.")
            print("You can manually verify the email by checking the email verification link.")
            sys.exit(1)
    else:
        print("Failed to register user properly.")
        sys.exit(1)

if __name__ == "__main__":
    main()