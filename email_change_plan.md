# Email Change Feature Implementation Plan

## Overview
Implement a secure endpoint to allow users to change their email address with proper validation and authentication.

## Technical Details

### 1. Schema Changes (auth_schemas.py)
```python
class EmailChange(BaseModel):
    new_email: EmailStr  # Using Pydantic's EmailStr for validation
    current_password: str
```

### 2. Service Layer Changes (user_service.py)
Add new method to UserService class:
```python
async def update_user_email(
    self,
    username: str,
    current_password: str,
    new_email: str
) -> User:
    """
    Update user's email address.
    
    Args:
        username: Username of user to update
        current_password: Current password for verification
        new_email: New email address
        
    Returns:
        User: Updated user object
        
    Raises:
        HTTPException: If authentication fails or email is already in use
    """
```

### 3. Router Changes (auth_router.py)
Add new endpoint:
```python
@router.put(
    "/users/{username}/email",
    response_model=Dict[str, str],
    responses={
        200: {"description": "Email successfully updated"},
        400: {"description": "Email already in use"},
        401: {"description": "Invalid password"},
        404: {"description": "User not found"}
    }
)
async def change_email(
    username: str,
    email_change: EmailChange,
    db: AsyncSession = Depends(get_db),
    token: str = Depends(oauth2_scheme)
)
```

### 4. Testing Plan (test_auth_router.py)
Test cases to implement:
1. Successful email change
   - Verify new email is saved
   - Verify old email is no longer valid
2. Security tests
   - Attempt change with wrong password
   - Attempt change without authentication
   - Attempt change to another user's email
3. Validation tests
   - Invalid email format
   - Email already in use
4. Edge cases
   - Same email as current
   - Very long email addresses

## Security Considerations
1. Require authentication
2. Verify current password
3. Validate new email format
4. Check email uniqueness
5. Proper error messages (avoid user enumeration)
6. Rate limiting consideration

## Implementation Steps
1. Create schema changes
2. Implement service layer method
3. Add router endpoint
4. Write tests
5. Manual testing
6. Documentation update

## Future Enhancements (Optional)
1. Email verification for new address
2. Notification to old email address
3. Grace period before change is final
4. Audit logging of email changes