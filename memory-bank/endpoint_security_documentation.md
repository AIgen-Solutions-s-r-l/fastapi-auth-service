# Endpoint Security Documentation

## Security Classification System

The auth_service employs a multi-layered security approach to protect endpoints based on their requirements:

1. **Public Endpoints**: Open access to anyone, no authentication required
2. **Authenticated Endpoints**: Require valid JWT token (authentication)
3. **Verified User Endpoints**: Require valid JWT token AND email verification
4. **Internal Service Endpoints**: Require API key authentication, not accessible externally

## Security Enforcement Mechanisms

### Authentication Types

```mermaid
graph TD
    A[Request] --> B{Authentication<br>Required?}
    B -->|No| C[Public Access]
    B -->|Yes| D{Auth Type?}
    D -->|JWT Token| E[User Authentication]
    D -->|API Key| F[Internal Service Authentication]
    E --> G{Email<br>Verified?}
    G -->|No| H[Authenticated User]
    G -->|Yes| I[Verified User]
    F --> J[Internal Service]
```

### Security Dependencies

- `get_current_user`: Validates JWT token, confirms user exists (authentication only)
- `get_current_active_user`: Validates JWT token, confirms user exists AND email is verified
- `get_internal_service`: Validates API key for internal service access

## Endpoint Security Classification

### Public Endpoints (No Auth Required)

```mermaid
graph LR
    A[Public Endpoints] --> B[/auth/login]
    A --> C[/auth/register]
    A --> D[/auth/verify-email]
    A --> E[/auth/resend-verification]
    A --> F[/auth/password-reset-request]
    A --> G[/auth/reset-password]
    A --> H[/auth/users/{user_id}/email]
    A --> I[/auth/users/by-email/{email}]
    A --> J[/auth/oauth/google/login]
    A --> K[/auth/oauth/google/callback]
    A --> L[/auth/test-email]
    A --> M[/auth/verify-email-templates]
```

### Authenticated Endpoints (JWT Token Required)

```mermaid
graph LR
    A[Authenticated Endpoints] --> B[/auth/refresh]
```

### Verified User Endpoints (JWT Token + Email Verification Required)

```mermaid
graph LR
    A[Verified User Endpoints] --> B[/auth/me]
    A --> C[/auth/logout]
    A --> D[/auth/users/change-password]
    A --> E[/auth/users/change-email]
    A --> F[/auth/users/delete-account]
    A --> G[/auth/link/google]
    A --> H[/auth/unlink/google]
```

### Internal Service Endpoints (API Key Required)

```mermaid
graph LR
    A[Internal Service Endpoints] --> B[/credits/balance]
    A --> C[/credits/add]
    A --> D[/credits/use]
    A --> E[/credits/transactions]
    A --> F[/stripe/webhook]
    A --> G[/stripe/create-checkout-session]
    A --> H[/stripe/setup-intent]
    A --> I[/stripe/payment-methods]
    A --> J[/stripe/create-subscription]
```

## Authentication Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Auth Service
    participant D as Database
    
    C->>A: Request to protected endpoint
    alt Public Endpoint
        A->>C: Process request (no auth check)
    else Internal Service Endpoint
        A->>A: Check API key from header
        alt Valid API key
            A->>C: Process request
        else Invalid API key
            A->>C: 401 Unauthorized
        end
    else User Endpoint
        A->>A: Extract JWT from Auth header
        A->>A: Decode & verify JWT signature
        A->>D: Fetch user record
        alt User exists & token valid
            A->>A: Check if endpoint requires verification
            alt Verification Required
                A->>A: Check if user.is_verified == true
                alt User Verified
                    A->>C: Process request
                else User Not Verified
                    A->>C: 403 Forbidden (Email not verified)
                end
            else No Verification Required
                A->>C: Process request
            end
        else Invalid token or user not found
            A->>C: 401 Unauthorized
        end
    end
```

## Authorization Implementation Details

### JWT Authentication Flow

```mermaid
flowchart TD
    A[Request with JWT] --> B[Extract Bearer token from<br>Authorization header]
    B --> C{Token present?}
    C -->|No| D[401 Unauthorized]
    C -->|Yes| E[Decode JWT]
    E --> F{Token valid?}
    F -->|No| G[401 Unauthorized]
    F -->|Yes| H[Extract user_id from payload]
    H --> I[Query database for user]
    I --> J{User exists?}
    J -->|No| K[401 Unauthorized]
    J -->|Yes| L[Return User model]
```

### Email Verification Check

```mermaid
flowchart TD
    A[get_current_active_user] --> B[get_current_user]
    B --> C[JWT Validation]
    C --> D[Return User]
    D --> E{User.is_verified?}
    E -->|Yes| F[Return Verified User]
    E -->|No| G[403 Forbidden:<br>Email not verified]
```

### Internal Service Authentication Flow

```mermaid
flowchart TD
    A[Request to internal endpoint] --> B[Extract API key from<br>X-API-Key header]
    B --> C{API key present?}
    C -->|No| D[401 Unauthorized]
    C -->|Yes| E{API key == configured key?}
    E -->|No| F[401 Unauthorized]
    E -->|Yes| G[Allow access to<br>internal endpoint]
```

## Updated Security Implementation

### Endpoint Protection Changes

1. **Modified `/link/google` endpoint**:
   - Changed dependency from `get_current_user` to `get_current_active_user`
   - Added 403 error response documentation
   - Now requires email verification

2. **Modified `/unlink/google` endpoint**:
   - Changed dependency from `get_current_user` to `get_current_active_user`
   - Added 403 error response documentation
   - Now requires email verification

3. **Confirmed Credit Router Protection**:
   - All endpoints secured with `get_internal_service` dependency
   - Only accessible through internal service calls with valid API key

4. **Confirmed Stripe Webhook Router Protection**:
   - All endpoints secured with `get_internal_service` dependency
   - Only accessible through internal service calls with valid API key