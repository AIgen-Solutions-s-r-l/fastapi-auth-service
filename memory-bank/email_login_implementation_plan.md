# Email Login Implementation Plan

## Current System Overview

Currently, the authentication system is using username-based login:

1. The login endpoint (`/login`) accepts a `LoginRequest` schema with `username` and `password` fields
2. The authentication process uses `authenticate_user()` which looks up a user by username and verifies the password
3. Upon successful authentication, a JWT token is generated with the username stored in the `sub` claim
4. The `get_current_user` function uses this token to identify users throughout the system

## Requirements

1. Update the login process to use email and password instead of username and password
2. Keep username field in the User model as optional for now (to be removed in future)
3. Maintain backward compatibility with existing code where possible
4. Update relevant endpoints and authentication flows to reflect this change

## Implementation Plan

### 1. Update Schema Definitions

Modify `app/schemas/auth_schemas.py`:
- Update `LoginRequest` to replace `username` with `email` as the login identifier
- Update other schema classes that might be impacted by this change

### 2. Update User Service Authentication

Modify `app/services/user_service.py`:
- Modify the `authenticate_user` method to authenticate using email instead of username
- Ensure all related methods support the new authentication flow

### 3. Update Authentication Router

Modify `app/routers/auth_router.py`:
- Update the login endpoint to handle email-based authentication
- Update JWT token generation to use email as the subject instead of username
- Modify error messages and logging to reflect email-based authentication

### 4. Update Authentication Core

Modify `app/core/auth.py`:
- Update `get_current_user` and related functions to properly handle email-based tokens
- Ensure token verification works with email-based subjects

### 5. Update Registration Flow

Ensure the registration process:
- Makes username optional
- Validates email properly
- Sets up the user record correctly for email-based authentication

### 6. Testing Plan

1. Create tests for email-based login functionality
2. Test backward compatibility with existing endpoints
3. Verify email validation and error handling
4. Test JWT token generation and verification with email-based subjects

### 7. Future Considerations

- Plan for the complete removal of the username field in the future
- Consider how this change might impact UI/frontend components that rely on username
- Document the transition to help users adapt to the change