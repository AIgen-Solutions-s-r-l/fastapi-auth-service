# Email Login Technical Implementation Plan

This document outlines the specific code changes needed to implement email-based login while keeping the username field optional.

## 1. Update Auth Schemas

In `app/schemas/auth_schemas.py`:

```python
# Current
class LoginRequest(BaseModel):
    """Pydantic model for login request."""
    username: str
    password: str

    model_config = ConfigDict(from_attributes=True)

# Updated
class LoginRequest(BaseModel):
    """Pydantic model for login request."""
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)
```

## 2. Update User Model (Optional Fields)

In `app/models/user.py`, we should maintain the username column but consider making it nullable for future removal:

```python
# Current
username = Column(String(50), unique=True, index=True, nullable=False)

# Updated - no change yet since we need to maintain compatibility
# For now we'll keep username required, but the authentication will use email
```

## 3. Update User Service Authentication Method

In `app/services/user_service.py`:

```python
# Current
async def authenticate_user(self, username: str, password: str) -> Optional[User]:
    """
    Authenticate a user.

    Args:
        username: Username to authenticate
        password: Plain text password to verify

    Returns:
        Optional[User]: Authenticated user if successful, None otherwise
    """
    user = await self.get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

# Updated
async def authenticate_user(self, email: str, password: str) -> Optional[User]:
    """
    Authenticate a user using email.

    Args:
        email: Email to authenticate
        password: Plain text password to verify

    Returns:
        Optional[User]: Authenticated user if successful, None otherwise
    """
    user = await self.get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
```

## 4. Update Auth Router Login Endpoint

In `app/routers/auth_router.py`:

```python
# Current
@router.post(
    "/login",
    response_model=Token,
    description="Authenticate user and return JWT token",
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"}
    }
)
async def login(
        credentials: LoginRequest,
        db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate a user and return a JWT token."""
    try:
        user = await authenticate_user(db, credentials.username, credentials.password)
        if not user:
            logger.warning("Authentication failed", event_type="login_failed", username=credentials.username, reason="invalid_credentials")
            raise InvalidCredentialsError()

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        access_token = create_access_token(
            data={
                "sub": user.username,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", event_type="login_success", username=user.username)
        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        logger.error("Login error", event_type="login_error", username=credentials.username, error_type=type(e).__name__, error_details=str(e))
        raise InvalidCredentialsError() from e

# Updated
@router.post(
    "/login",
    response_model=Token,
    description="Authenticate user and return JWT token",
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"}
    }
)
async def login(
        credentials: LoginRequest,
        db: AsyncSession = Depends(get_db)
) -> Token:
    """Authenticate a user and return a JWT token."""
    try:
        user = await authenticate_user(db, credentials.email, credentials.password)
        if not user:
            logger.warning("Authentication failed", event_type="login_failed", email=credentials.email, reason="invalid_credentials")
            raise InvalidCredentialsError()

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        access_token = create_access_token(
            data={
                "sub": user.email,  # Use email instead of username
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", event_type="login_success", email=user.email, username=user.username)
        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        logger.error("Login error", event_type="login_error", email=credentials.email, error_type=type(e).__name__, error_details=str(e))
        raise InvalidCredentialsError() from e
```

## 5. Update Current User Function

In `app/core/auth.py`:

```python
# Current
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT token.

    Args:
        token: JWT token
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        AuthException: If token is invalid or user not found
    """
    credentials_exception = AuthException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_jwt_token(token)
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_service = UserService(db)
    user = await user_service.get_user_by_username(username)
    if user is None:
        raise credentials_exception
    return user

# Updated
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from the JWT token.

    Args:
        token: JWT token
        db: Database session

    Returns:
        User: Current authenticated user

    Raises:
        AuthException: If token is invalid or user not found
    """
    credentials_exception = AuthException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_jwt_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user_service = UserService(db)
    user = await user_service.get_user_by_email(email)
    if user is None:
        raise credentials_exception
    return user
```

## 6. Update Other Token Generation

Update all other places where tokens are generated or refreshed to use email as the subject, such as in the `/refresh` endpoint:

```python
# Current
access_token = create_access_token(
    data={
        "sub": user.username,
        "id": user.id,
        "is_admin": user.is_admin,
        "exp": expire_time.timestamp()
    },
    expires_delta=expires_delta
)

# Updated
access_token = create_access_token(
    data={
        "sub": user.email,
        "id": user.id,
        "is_admin": user.is_admin,
        "exp": expire_time.timestamp()
    },
    expires_delta=expires_delta
)
```

## 7. Update Related User Service Functions

New functions for backward compatibility:

```python
# Add a compatibility function to support existing code
async def authenticate_user_by_username_or_email(
    self, identifier: str, password: str
) -> Optional[User]:
    """
    Authenticate a user by username or email.
    Tries to find the user by email first, then by username.

    Args:
        identifier: Email or username to authenticate
        password: Plain text password to verify

    Returns:
        Optional[User]: Authenticated user if successful, None otherwise
    """
    # First try to find by email
    user = await self.get_user_by_email(identifier)
    
    # If not found, try by username
    if user is None:
        user = await self.get_user_by_username(identifier)
    
    # If user found, verify password
    if user and verify_password(password, user.hashed_password):
        return user
        
    return None
```

## 8. Database Migration Considerations

No immediate database migrations are needed since we're keeping the username field for now. However, we should document that a future migration will make the username field nullable and eventually remove it.

## 9. Testing Strategy

1. Create tests that verify login works with email
2. Test that JWT tokens are properly generated with email as subject
3. Test that the current_user dependency correctly identifies users by email
4. Test backward compatibility with existing code that may rely on username