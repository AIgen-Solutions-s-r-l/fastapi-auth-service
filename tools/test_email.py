import requests
import json

# Replace with your actual API endpoint
API_ENDPOINT = "http://localhost:8001/auth/test-email"
EMAIL = "test1345635@example.com"  # Replace with the desired email

def test_email():
    payload = {
        "email": EMAIL,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        print("Request Headers:", headers)
        data = json.dumps(payload)
        headers["Content-Length"] = str(len(data))
        response = requests.post(API_ENDPOINT, data=data, headers=headers)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        print("Response Headers:", response.headers)
        response_data = response.json()
        print("Response:", json.dumps(response_data, indent=4))
        return response_data
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    result = test_email()
    if result:
        print("Test email sent successfully.")
    else:
        print("Failed to send test email.")