# Endpoint Security Enhancement Plan

## Current Security Issues

Based on the analysis of the auth_service codebase, we've identified several security vulnerabilities:

1. **Endpoints Accessible to Unverified Users**: Multiple endpoints that should only be available to verified users are currently accessible to anyone with a JWT token, regardless of verification status.

2. **Internal Service Routes Exposed Externally**: Credit and Stripe routes, which should only be used by other microservices, are currently exposed externally without proper service-to-service authentication.

3. **Missing Authentication Mechanism**: No dedicated authentication mechanism exists for service-to-service communication, making it difficult to secure microservice interactions.

## Authentication Levels

We need to establish clear authentication levels for all endpoints:

1. **Public Endpoints**: 
   - No authentication required
   - Examples: Login, Register, Password Reset Request

2. **JWT-Authenticated Endpoints**: 
   - Requires a valid JWT token
   - Used for unverified users who have authenticated
   - Examples: Verify Email, Resend Verification

3. **Verified User Endpoints**: 
   - Requires a valid JWT token AND verified user status
   - Used for actions that should only be available to verified users
   - Examples: Change Password, Delete Account, Get User Profile

4. **Internal Service Endpoints**: 
   - Only accessible to other microservices via API key
   - Not exposed externally
   - Examples: Credit Operations, Stripe Integrations

## Implementation Plan

### 1. Service-to-Service Authentication

Create a new authentication dependency for internal service communication:

```python
async def get_internal_service(
    api_key: str = Header(..., description="API key for service-to-service communication"),
    db: AsyncSession = Depends(get_db)
) -> str:
    """
    Authenticate internal service based on API key.
    
    Returns the service name if valid, raises exception if invalid.
    """
    if api_key != settings.INTERNAL_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key for internal service access"
        )
    
    # Could also implement service-specific keys and permissions
    return "internal_service"
```

Update `app/core/config.py` to include the API key configuration:

```python
# Service-to-service authentication
INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "")
```

### 2. Endpoint Classification and Updates

#### Auth Router Endpoints

| Endpoint | Current Auth | Required Auth | Action |
|----------|--------------|--------------|--------|
| `/auth/login` | None | None (Public) | No change |
| `/auth/register` | None | None (Public) | No change |
| `/auth/verify-email` | None | None (Public) | No change (needed for email verification) |
| `/auth/resend-verification` | None | None (Public) | No change (needed for users who didn't receive email) |
| `/auth/users/by-email/{email}` | None | `get_current_active_user` | Add verification requirement |
| `/auth/users/change-email` | `oauth2_scheme` | `get_current_active_user` | Update to verified-only |
| `/auth/users/change-password` | `oauth2_scheme` | `get_current_active_user` | Update to verified-only |
| `/auth/users/delete-account` | `oauth2_scheme` | `get_current_active_user` | Update to verified-only |
| `/auth/logout` | `oauth2_scheme` | `get_current_user` | No change (can be used by unverified) |
| `/auth/password-reset-request` | None | None (Public) | No change |
| `/auth/reset-password` | None | None (Public) | No change |
| `/auth/refresh` | None | None (Public) | No change |
| `/auth/me` | `oauth2_scheme` | `get_current_user` | No change (can be used by unverified) |
| `/auth/users/{user_id}/email` | None | `get_internal_service` | Make internal-only |
| `/auth/test-email` | None | `get_internal_service` | Make internal-only |
| `/auth/verify-email-templates` | None | `get_internal_service` | Make internal-only |
| `/auth/oauth/google/login` | None | None (Public) | No change |
| `/auth/oauth/google/callback` | None | None (Public) | No change |
| `/auth/link/google` | `get_current_user` | `get_current_active_user` | Update to verified-only |
| `/auth/unlink/google` | `get_current_user` | `get_current_active_user` | Update to verified-only |

#### Credit Router Endpoints

All endpoints in the credit router should be internal-only, as these should only be accessed by other services, not directly by users:

| Endpoint | Current Auth | Required Auth | Action |
|----------|--------------|--------------|--------|
| `/credits/balance` | `get_current_active_user` | `get_internal_service` | Make internal-only |
| `/credits/use` | `get_current_active_user` | `get_internal_service` | Make internal-only |
| `/credits/add` | `get_current_active_user` | `get_internal_service` | Make internal-only |
| `/credits/transactions` | `get_current_active_user` | `get_internal_service` | Make internal-only |
| `/credits/stripe/add` | `get_current_active_user` | `get_internal_service` | Make internal-only |

#### Stripe Webhook Endpoints

These endpoints should also be internal-only:

| Endpoint | Current Auth | Required Auth | Action |
|----------|--------------|--------------|--------|
| `/webhook/stripe` | None | `get_internal_service` | Make internal-only |

### 3. Implementation Steps

1. Create a new authentication dependency in `app/core/auth.py` for service-to-service authentication:
   - Implement `get_internal_service()` function
   - Update config to include API key settings

2. Update Auth Router endpoints:
   - Apply `get_current_active_user` to endpoints that should require verification
   - Apply `get_internal_service` to endpoints that should be internal-only

3. Update Credit Router:
   - Modify all endpoints to use `get_internal_service` instead of `get_current_active_user`
   - Update route documentation to reflect internal usage

4. Update Stripe Webhook Router:
   - Add `get_internal_service` dependency to webhook endpoint
   - Update documentation to reflect internal usage

5. Update Tests:
   - Modify tests to include appropriate API keys for internal endpoints
   - Update user authentication in tests to handle verification requirements

### 4. Backward Compatibility Considerations

To ensure a smooth transition for other services that depend on these endpoints:

1. Consider a transition period where both authentication methods are accepted:
   ```python
   async def get_service_or_user(
       request: Request,
       api_key: str = Header(None),
       current_user: Optional[User] = Depends(get_current_active_user_optional)
   ):
       """Allow either service auth or user auth during transition."""
       if api_key and api_key == settings.INTERNAL_API_KEY:
           return "internal_service"
       if current_user:
           return current_user
       raise HTTPException(status_code=403, detail="Either API key or user authentication required")
   ```

2. Add detailed documentation for other teams to understand the new API key requirement.

3. Coordinate deployment with other services to ensure they start sending the API key.

## Monitoring and Enforcement

Add additional monitoring to track unauthorized access attempts:

1. Enhance logging for failed authentication attempts with api_key failures
2. Create alerts for unusual access patterns
3. Implement rate limiting for failed authentication attempts

## Example Implementation

Here's an example implementation for an internal service route:

```python
@router.get("/balance", response_model=CreditBalanceResponse)
async def get_credit_balance(
    user_id: int,
    service: str = Depends(get_internal_service),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user's credit balance.
    
    This is an internal endpoint for service-to-service communication.
    """
    credit_service = CreditService(db)
    return await credit_service.get_balance(user_id)