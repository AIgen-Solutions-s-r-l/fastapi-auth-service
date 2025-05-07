import asyncio
import httpx
import json

async def test_password_reset():
    # Step 1: Request a password reset token
    async with httpx.AsyncClient(base_url="http://localhost:8018") as client:
        # First, request a password reset token
        response = await client.post(
            "/auth/password-reset-request",
            json={"email": "test@example.com"}
        )
        print(f"Password reset request response: {response.status_code}")
        print(response.json())
        
        # In a real scenario, we would get the token from the email
        # For testing, we'll create a token directly in the database
        
        # Step 2: Reset the password using the token
        # For testing purposes, we'll use a hardcoded token
        # In a real scenario, you would extract this from the email
        response = await client.post(
            "/auth/password-reset",
            json={"token": "test_token", "new_password": "newpassword123"}
        )
        print(f"Password reset response: {response.status_code}")
        print(response.json())

if __name__ == "__main__":
    asyncio.run(test_password_reset())