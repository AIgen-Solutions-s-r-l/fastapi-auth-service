#!/usr/bin/env python3
"""
Script to perform login authentication and retrieve the bearer token.
"""

import requests
import json
import argparse

# API endpoint using port 9000
API_ENDPOINT = "http://localhost:9000/auth/login"

def get_token(email, password):
    """
    Authenticate with the auth service and retrieve a bearer token.
    
    Args:
        email: User email
        password: User password
        
    Returns:
        The bearer token if successful, None otherwise
    """
    payload = {
        "email": email,
        "password": password
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        print(f"Authenticating user: {email}")
        data = json.dumps(payload)
        headers["Content-Length"] = str(len(data))
        
        response = requests.post(API_ENDPOINT, data=data, headers=headers)
        print(f"Response status code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error response: {response.text}")
            return None
            
        response_data = response.json()
        token = response_data.get("access_token")
        
        if not token:
            print("Error: 'access_token' not found in response")
            return None
            
        return {
            "token": token,
            "token_type": response_data.get("token_type", "bearer"),
            "full_response": response_data
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Request error during authentication: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode error during authentication: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Login and retrieve authentication token')
    parser.add_argument('--email', required=True, help='Email address for login')
    parser.add_argument('--password', required=True, help='Password for login')
    parser.add_argument('--show-full', action='store_true', help='Show full response details')
    
    args = parser.parse_args()
    
    # Authenticate and get token
    result = get_token(args.email, args.password)
    
    if result:
        print("\n=== Authentication Successful ===")
        print(f"Bearer Token: {result['token']}")
        print(f"Token Type: {result['token_type']}")
        
        # Show how to use the token in curl or other API requests
        print("\n=== Example Usage with curl ===")
        print(f"curl -H 'Authorization: Bearer {result['token']}' http://localhost:9000/auth/me")
        
        # Optionally show full response details
        if args.show_full:
            print("\n=== Full Response ===")
            print(json.dumps(result['full_response'], indent=4))
    else:
        print("Failed to retrieve token.")

if __name__ == "__main__":
    main()