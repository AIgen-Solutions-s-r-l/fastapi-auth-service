# Email-Only Authentication Documentation

## Overview

This document describes the authentication system of the Auth Service, which has been refactored to use email addresses as the sole user identifier, removing the previously used username field.

## Rationale

The decision to migrate from username+email to email-only was driven by several factors:

1. **Simplification**: Using a single identifier (email) simplifies the codebase, user flows, and database schema.
2. **Industry Standard**: Many modern applications use email as the primary identifier.
3. **Reduced User Friction**: Users no longer need to remember both a username and email.
4. **Uniqueness Guarantee**: Email addresses are already required to be unique in the system.
5. **Customer Request**: As per customer requirements, the system needed to be simplified to use email exclusively.

## Technical Implementation

### User Model

The User model now uses email as the primary identifier for authentication purposes:

```python
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Made nullable for OAuth-only users
    # Other fields...
```

### JWT Tokens

JWT tokens now exclusively use the email address in the `sub` (subject) claim:

```python
def create_access_token(email: str, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT access token.
    
    Args:
        email: The email to encode in the token
        expires_delta: Optional custom expiration time
        
    Returns:
        str: The encoded JWT
    """
    to_encode = {"sub": email}
    # Rest of implementation...
```

### Authentication Endpoints

All authentication endpoints now use email as the identifier:

1. **Login**: Uses email + password
2. **Registration**: Requires email + password
3. **Password Reset**: Identified by email
4. **User Management**: Users are referenced by their email address

### OAuth Integration

OAuth integration (Google) links external accounts with the user's email address:

```python
async def handle_oauth_callback(token_info, email, provider_id):
    # Find existing user by email
    user = await user_service.get_user_by_email(email)
    
    # Create or link account based on email
    # ...
```

## API Endpoints

All endpoints that previously accepted or returned username now exclusively work with email:

- POST `/auth/login`: Accepts email + password
- POST `/auth/register`: Accepts email + password
- GET `/auth/users/by-email/{email}`: Gets user by email
- PUT `/auth/users/change-email`: Changes email address
- POST `/auth/password-reset-request`: Requests password reset by email

## Migration Considerations

### User Data Migration

The database migration removes the username column:

```python
# Migration file: e66712ccad45_remove_username_field.py

def upgrade():
    op.drop_column('users', 'username')

def downgrade():
    op.add_column('users', sa.Column('username', sa.String(length=50), nullable=True))
```

### Token Compatibility

The authentication system had a backward compatibility mechanism for tokens that contained username instead of email in the `sub` claim. This has been removed as part of this refactoring, meaning older tokens using username as the subject will no longer work.

### API Clients

API clients need to be updated to:
1. Use email instead of username for authentication
2. Remove any username fields from registration forms
3. Update user profile management to work with email only

## Testing

The test suite has been updated to work with email-only authentication:
- All test fixtures now use email as the primary identifier
- Test assertions have been updated to check for email instead of username
- OAuth and other authentication flows have been tested with the email-only approach

## Security Considerations

This change does not impact the security of the system, as:
1. Email addresses were already required to be unique
2. Password policies remain unchanged
3. JWT token security is maintained
4. Two-factor authentication compatibility is preserved