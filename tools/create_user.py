import requests
import json
import asyncio

# Replace with your actual API endpoint
API_ENDPOINT = "http://localhost:8001/auth/register"
VERIFY_ENDPOINT = "http://localhost:8001/auth/verify-email"
LOGIN_ENDPOINT = "http://localhost:8001/auth/login"
EMAIL = "test1345635@example.com"  # Replace with the desired email
PASSWORD = "password"  # Replace with the desired password

async def get_verification_token(email):
    try:
        from app.core.database import engine
        from app.models.user import User, EmailVerificationToken
        from sqlalchemy import select
        async with engine.begin() as conn:
            result = await conn.execute(select(User).where(User.email == email))
            user = result.scalar_one_or_none()
            if not user:
                print("User not found")
                return None
            result = await conn.execute(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))
            token = result.scalar_one_or_none()
            if not token:
                print("Token not found")
                return None
            return token.token
    except Exception as e:
        print(f"Error getting token: {e}")
        return None

def create_user():
    payload = {
        "email": EMAIL,
        "password": PASSWORD
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        print("Register Request Headers:", headers)
        data = json.dumps(payload)
        headers["Content-Length"] = str(len(data))
        response = requests.post(API_ENDPOINT, data=data, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        print("Register Response Headers:", response.headers)
        response_data = response.json()
        print("Register Response:", json.dumps(response_data, indent=4))

        # Extract verification token
        if "message" in response_data and "email" in response_data and "verification_sent" in response_data:
            return response_data
        else:
            print("Failed to extract verification token.")
            return None

    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

def verify_email(token):
    headers = {
        "Accept": "application/json"
    }
    params = {
        "token": token
    }
    try:
        print("Verify Request Headers:", headers)
        response = requests.get(VERIFY_ENDPOINT, params=params, headers=headers)
        response.raise_for_status()
        print("Verify Response Headers:", response.headers)
        response_data = response.json()
        print("Verify Response:", json.dumps(response_data, indent=4))
        return response_data
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

def get_token(email, password):
    payload = {
        "email": email,
        "password": password
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        print("Login Request Headers:", headers)
        data = json.dumps(payload)
        headers["Content-Length"] = str(len(data))
        response = requests.post(LOGIN_ENDPOINT, data=data, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        print("Login Response Headers:", response.headers)
        response_data = response.json()
        print("Login Response:", json.dumps(response_data, indent=4))
        return response_data["access_token"]
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None
    except KeyError:
        print("Error: 'access_token' not found in response.")
        return None

if __name__ == "__main__":
    registration_result = create_user()
    if registration_result:
        # Extract token from registration result
        email = registration_result["email"]
        print(f"Email: {email}")
        
        # Extract token from registration result
        #token = registration_result.get("message").split("token=")[1]
        #print(f"Extracted Token: {token}")
        token = asyncio.run(get_verification_token(email))
        if token:
            print(f"Extracted Token from DB: {token}")

            verification_result = verify_email(token)
            if verification_result:
                print("Email verified successfully.")
                access_token = get_token(email, PASSWORD)
                if access_token:
                    print(f"Access Token: {access_token}")
                else:
                    print("Failed to retrieve access token.")
            else:
                print("Failed to verify email.")
        else:
            print("Failed to extract token from DB.")
    else:
        print("Failed to create user.")