#!/usr/bin/env python3
"""
Script to register a new email account and validate it using a token from the database.
"""

import requests
import json
import sys
import argparse
import os
import time
import psycopg2
from psycopg2.extras import DictCursor

# API endpoints
API_ENDPOINT = "http://localhost:8001/auth/register"
VERIFY_ENDPOINT = "http://localhost:8001/auth/verify-email"

# PostgreSQL connection details (as globals)
PG_HOST = "172.17.0.1"
PG_PORT = 5432
PG_USER = "testuser"
PG_PASSWORD = "testpassword"
PG_DATABASE = "main_db"

def get_pg_connection():
    """
    Create and return a PostgreSQL database connection.
    
    Returns:
        The PostgreSQL connection object or None if connection fails
    """
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            user=PG_USER,
            password=PG_PASSWORD,
            database=PG_DATABASE
        )
        print(f"Successfully connected to PostgreSQL database: {PG_DATABASE}")
        return conn
    except psycopg2.Error as e:
        print(f"Error connecting to PostgreSQL: {e}")
        return None

def get_db_info():
    """Print debug info about the database"""
    try:
        conn = get_pg_connection()
        if not conn:
            return False
            
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        # List tables
        cursor.execute("""
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname != 'pg_catalog' AND schemaname != 'information_schema'
        """)
        tables = cursor.fetchall()
        print(f"Database tables: {[t[0] for t in tables]}")
        
        # Count users
        try:
            cursor.execute("SELECT COUNT(*) FROM users")
            user_count = cursor.fetchone()[0]
            print(f"Total users in database: {user_count}")
        except psycopg2.Error as e:
            print(f"Error counting users: {e}")
        
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error getting database info: {e}")
        return False

def get_verification_token(email):
    """
    Retrieve the verification token from PostgreSQL database.
    
    Args:
        email: The email address to look up
        
    Returns:
        The verification token if found, None otherwise
    """
    try:
        conn = get_pg_connection()
        if not conn:
            return None
            
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        # First get the user_id for the email
        print(f"Looking up user with email: {email}")
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user_row = cursor.fetchone()
        
        if not user_row:
            print(f"User with email {email} not found in the database")
            
            # List recent users for debugging
            print("Recent users in database:")
            cursor.execute("SELECT id, email, is_verified FROM users ORDER BY id DESC LIMIT 5")
            recent_users = cursor.fetchall()
            for user in recent_users:
                print(f"  ID: {user['id']}, Email: {user['email']}, Verified: {user['is_verified']}")
            
            cursor.close()
            conn.close()
            return None
            
        user_id = user_row[0]
        print(f"Found user with ID: {user_id}")
        
        # Now get the verification token for this user
        cursor.execute(
            """
            SELECT token, created_at, expires_at 
            FROM email_verification_tokens 
            WHERE user_id = %s AND used = false 
            ORDER BY created_at DESC LIMIT 1
            """, 
            (user_id,)
        )
        
        token_row = cursor.fetchone()
        
        if not token_row:
            print(f"No unused verification token found for user ID {user_id}")
            
            # Check if there are any tokens for this user
            cursor.execute(
                """
                SELECT token, created_at, used 
                FROM email_verification_tokens 
                WHERE user_id = %s 
                ORDER BY created_at DESC
                """, 
                (user_id,)
            )
            all_tokens = cursor.fetchall()
            
            if all_tokens:
                print(f"Found {len(all_tokens)} tokens for user (including used ones):")
                for t in all_tokens:
                    print(f"  Token: {t['token'][:10]}..., Created: {t['created_at']}, Used: {t['used']}")
            else:
                print("No tokens found for this user.")
            
            cursor.close()
            conn.close()
            return None
            
        token = token_row['token']
        print(f"Found token created at {token_row['created_at']}, expires at {token_row['expires_at']}")
        
        cursor.close()
        conn.close()
        return token
        
    except psycopg2.Error as e:
        print(f"PostgreSQL error: {e}")
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
    global PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DATABASE
    
    parser = argparse.ArgumentParser(description='Register a new user and verify email')
    parser.add_argument('--email', required=True, help='Email address for registration')
    parser.add_argument('--password', required=True, help='Password for registration')
    parser.add_argument('--delay', type=int, default=2, help='Delay in seconds after registration')
    parser.add_argument('--pg-host', default=PG_HOST, help='PostgreSQL host')
    parser.add_argument('--pg-port', type=int, default=PG_PORT, help='PostgreSQL port')
    parser.add_argument('--pg-user', default=PG_USER, help='PostgreSQL user')
    parser.add_argument('--pg-password', default=PG_PASSWORD, help='PostgreSQL password')
    parser.add_argument('--pg-db', default=PG_DATABASE, help='PostgreSQL database name')
    
    args = parser.parse_args()
    
    # Update PostgreSQL connection details
    PG_HOST = args.pg_host
    PG_PORT = args.pg_port
    PG_USER = args.pg_user
    PG_PASSWORD = args.pg_password
    PG_DATABASE = args.pg_db
    
    # Show database info
    print("\n=== Database Information ===")
    get_db_info()
    
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
        token = get_verification_token(registered_email)
        
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