# Endpoint Security Implementation Plan

## Overview

This document outlines the plan to secure two endpoints that should be internal-only rather than publicly accessible:

1. `/auth/users/{user_id}/email` (lines 971-1019 in auth_router.py)
2. `/auth/users/by-email/{email}` (lines 378-407 in auth_router.py)

## Current State

- Both endpoints are currently accessible without internal service authentication
- The codebase already implements a `get_internal_service` dependency for restricting endpoints to internal services
- The INTERNAL_API_KEY is configured in settings

## Implementation Details

### 1. Endpoint: `/auth/users/{user_id}/email`

**Current Implementation:**
```python
@router.get("/users/{user_id}/email",
    response_model=Dict[str, str],
    responses={
        200: {"description": "User email retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_email_by_user_id(user_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Get user's email by user ID without requiring authentication."""
    # ...implementation...
```

**Changes Required:**
- Replace `db: AsyncSession = Depends(get_db)` with `service_id: str = Depends(get_internal_service), db: AsyncSession = Depends(get_db)`
- Update docstring to clearly indicate this is an internal service endpoint
- Add 403 response to the responses dictionary
- Enhance logging to include service identification for audit purposes

### 2. Endpoint: `/auth/users/by-email/{email}`

**Current Implementation:**
```python
@router.get(
    "/users/by-email/{email}",
    response_model=UserResponse,
    responses={
        200: {"description": "User details retrieved successfully"},
        404: {"description": "User not found"}
    }
)
async def get_user_details(
        email: str,
        db: AsyncSession = Depends(get_db)
) -> UserResponse:
    """Retrieve user details by email."""
    # ...implementation...
```

**Changes Required:**
- Replace `db: AsyncSession = Depends(get_db)` with `service_id: str = Depends(get_internal_service), db: AsyncSession = Depends(get_db)`
- Update docstring to clearly indicate this is an internal service endpoint
- Add 403 response to the responses dictionary
- Enhance logging to include service identification for audit purposes

## Enhanced Logging Requirements

For both endpoints, implement the following logging enhancements:

1. **Access Logging:**
   - Log all successful internal service access with the service identifier
   - Use event type `internal_endpoint_access` for successful access

2. **Security Logging:**
   - `get_internal_service` already logs unauthorized access attempts
   - Add additional context to logs (endpoint path, request method)

3. **Error Logging:**
   - Log all errors with appropriate error types
   - Include service identifier in error logs
   - Use consistent event types: `internal_endpoint_error`

## Error Handling

Implement robust error handling:

1. **Unauthorized Access:**
   - Already handled by `get_internal_service` with 403 Forbidden
   - Ensure error messages don't leak sensitive information

2. **Not Found Errors:**
   - Maintain existing 404 handling for user not found cases
   - Include appropriate logging

3. **Server Errors:**
   - Catch and properly log unexpected exceptions
   - Return appropriate 500 responses without exposing internal details

## Documentation Updates

Update documentation to reflect these security changes:

1. **API Documentation:**
   - Clearly mark both endpoints as internal-only
   - Document the required INTERNAL_API_KEY header

2. **Security Documentation:**
   - Document the internal endpoint security model
   - Provide examples for internal services on how to authenticate

## Testing Strategy

Test the following scenarios:

1. Access without API key (should return 403)
2. Access with invalid API key (should return 403)
3. Access with valid API key but user not found (should return 404)
4. Access with valid API key and valid user (should return 200)
5. Verify all appropriate events are being logged

## Implementation Code

The implementation will involve modifying the two endpoint functions in `app/routers/auth_router.py` to use the `get_internal_service` dependency.