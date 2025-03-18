import requests
import json

# Replace with your actual API endpoint
API_ENDPOINT = "http://localhost:8001/auth/register"
EMAIL = "rocchi.b.a@gmail.com"  # Replace with the desired email
PASSWORD = "Fuffa.123!"  # Replace with the desired password

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
        print("Request Headers:", headers)
        data = json.dumps(payload)
        response = requests.post(API_ENDPOINT, data=data, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        print("Response Headers:", response.headers)
        data = response.json()
        print(json.dumps(data, indent=4))
        return data
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    result = create_user()
    if result:
        print("User created successfully.")
    else:
        print("Failed to create user.")