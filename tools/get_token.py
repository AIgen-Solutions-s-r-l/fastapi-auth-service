import requests
import json

# Replace with your actual API endpoint and credentials
API_ENDPOINT = "http://localhost:8001/auth/login"  # Assuming the service is running locally
USERNAME = "testuser"  # Replace with a valid username
PASSWORD = "testpassword"  # Replace with a valid password

def get_token():
    payload = {
        "email": USERNAME,
        "password": PASSWORD
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(API_ENDPOINT, data=json.dumps(payload), headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        return data["access_token"]
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None
    except KeyError:
        print("Error: 'access_token' not found in response.")
        return None

if __name__ == "__main__":
    token = get_token()
    if token:
        print(f"Bearer Token: {token}")
    else:
        print("Failed to retrieve token.")