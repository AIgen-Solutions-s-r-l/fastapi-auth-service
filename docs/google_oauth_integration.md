# Google OAuth 2.0 Integration

This document explains how to set up and use Google OAuth 2.0 authentication with the authentication service.

## Overview

Google OAuth 2.0 integration allows users to sign in to your application using their Google accounts. The authentication service handles the OAuth flow and translates Google authentication into your standard JWT tokens, maintaining compatibility with existing microservices.

## How It Works

The Google OAuth 2.0 flow works as follows:

1. User clicks "Sign in with Google" on your frontend
2. Frontend requests a Google authorization URL from the auth service
3. Frontend redirects the user to Google's login page
4. User authenticates with Google and grants permissions
5. Google redirects back to your application with an authorization code
6. Frontend sends this code to the auth service
7. Auth service exchanges the code for Google tokens and user information
8. Auth service finds or creates the user in your database
9. Auth service returns a JWT token, same as with password authentication
10. Frontend stores the JWT token and uses it for API calls

This approach maintains compatibility with your microservices because the resulting JWT token is identical in structure to tokens from password-based authentication.

## Setting Up Google OAuth

### 1. Create Google OAuth Credentials

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth client ID"
5. Select "Web application" as the application type
6. Add your authorized JavaScript origins (e.g., `http://localhost:8000`)
7. Add your authorized redirect URIs (e.g., `http://localhost:8000/auth/google/callback`)
8. Click "Create" to generate your client ID and client secret

### 2. Configure Environment Variables

Add the following environment variables to your `.env` file:

```
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
OAUTH_SCOPES=openid email profile
```

### 3. Run Database Migrations

Apply the database migrations to add OAuth-related fields to your user model:

```bash
alembic upgrade head
```

## API Endpoints

### Get Google Login URL

```
GET /auth/oauth/google/login
```

**Query Parameters:**
- `redirect_uri` (optional): Custom redirect URI for this request

**Response:**
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/auth?client_id=..."
}
```

### Process Google Callback

```
POST /auth/oauth/google/callback
```

**Request Body:**
```json
{
  "code": "4/0AeaYSHDGS...",
  "state": "optional-state-parameter"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJ...",
  "token_type": "bearer"
}
```

### Link Google Account (for existing users)

```
POST /auth/link/google
```

**Request Body:**
```json
{
  "provider": "google",
  "code": "4/0AeaYSHDGS...",
  "password": "current-password"
}
```

**Response:**
```json
{
  "message": "Google account linked successfully"
}
```

### Unlink Google Account

```
POST /auth/unlink/google
```

**Response:**
```json
{
  "message": "Google account unlinked successfully"
}
```

## Frontend Integration

### Basic Frontend Integration

```javascript
// 1. Get Google login URL
async function getGoogleLoginUrl() {
  const response = await fetch('http://localhost:8000/auth/oauth/google/login');
  const data = await response.json();
  return data.auth_url;
}

// 2. Redirect to Google
function redirectToGoogle() {
  getGoogleLoginUrl().then(url => {
    window.location.href = url;
  });
}

// 3. Handle callback from Google
async function handleGoogleCallback(code) {
  const response = await fetch('http://localhost:8000/auth/oauth/google/callback', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code })
  });
  
  const data = await response.json();
  // Store token in local storage
  localStorage.setItem('token', data.access_token);
  // Redirect to dashboard
  window.location.href = '/dashboard';
}

// On your callback page
function processCallback() {
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get('code');
  
  if (code) {
    handleGoogleCallback(code);
  }
}
```

### Account Linking

To allow users to link their Google account to an existing account:

```javascript
async function linkGoogleAccount(code, password) {
  const token = localStorage.getItem('token'); // Current JWT token
  
  const response = await fetch('http://localhost:8000/auth/link/google', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      provider: 'google',
      code,
      password
    })
  });
  
  const data = await response.json();
  return data;
}
```

## User Model Changes

The User model has been updated with these new fields:

- `google_id`: A unique identifier from Google
- `auth_type`: Indicates how the user authenticates ("password", "google", or "both")
- `hashed_password`: Now nullable to support OAuth-only users

## Database Schema Updates

The migration script adds the following changes to your database:

- Makes the `hashed_password` column nullable for OAuth-only users
- Adds the `google_id` column (String, nullable, unique)
- Adds the `auth_type` column (String, default="password")
- Creates a unique index on `google_id`

## Security Considerations

1. **Token Security**: JWT tokens should be stored securely on the frontend (e.g., in HttpOnly cookies)
2. **HTTPS**: Always use HTTPS in production to secure OAuth callbacks
3. **State Parameter**: Implement the state parameter to prevent CSRF attacks
4. **Scope Limitations**: Only request the minimum scopes needed
5. **Account Linking**: Require password verification when linking Google accounts to existing accounts

## Troubleshooting

### Common Issues

1. **Invalid Client ID**: Ensure your GOOGLE_CLIENT_ID environment variable is set correctly
2. **Redirect URI Mismatch**: The redirect URI in your code must exactly match one of the authorized redirect URIs in your Google Cloud Console
3. **Missing Scopes**: Ensure the OAUTH_SCOPES environment variable includes at least "openid email profile"
4. **Database Migration**: Ensure you've run the migration to add the new user fields

### Verifying Configuration

You can verify your OAuth configuration at startup by checking the logs. The service validates the OAuth configuration and logs any issues.

## Example Implementation

See the example implementation in `examples/google_oauth_example.html` for a complete frontend integration demo.