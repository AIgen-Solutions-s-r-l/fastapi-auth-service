# Username Removal Implementation Plan

## Overview
The customer has requested to completely remove the username functionality and use email exclusively as the primary identifier for users. This document outlines the comprehensive plan to implement this change. Since there are no external systems or clients depending on the current username-based API endpoints, we can take a direct approach without backward compatibility concerns.

## Current State
The authentication system currently supports both username and email identification with these key characteristics:
- User model has both `username` and `email` fields, both marked as unique
- API endpoints use username in paths (e.g., `/users/{username}/...`)
- JWT tokens already use email as the subject for new tokens with backward compatibility for username-based tokens
- Authentication supports both username and email login
- Email verification, password reset, and other security features are in place

## Implementation Goals
1. Completely remove the username field from the database schema
2. Use email as the primary identifier for all users
3. Handle duplicate emails by keeping only one user record for each email
4. Update all API endpoints to use email instead of username
5. Remove all username-related code and simplify to email-only authentication
6. Update all affected tests

## Migration Strategy
Since there are no backward compatibility requirements and this is a development environment, we will take a direct, comprehensive approach:

1. Create a database migration to handle duplicate emails and remove the username column
2. Remove all username-related code from models, schemas, and services
3. Rename and update all API endpoints to use email in paths
4. Update all tests to use email-only authentication

## Detailed Implementation Plan

### 1. Database Changes

#### Create Alembic Migration
Create a new migration that will:
- Handle any duplicate email addresses (should not be an issue in development)
- Remove the username column from the users table
- Update any foreign key constraints if needed

```python
# New alembic migration
"""remove_username_field

Revision ID: xxxxxxxxxxxx
Revises: previous_migration_id
Create Date: 2025-03-04

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'xxxxxxxxxxxx'
down_revision = 'previous_migration_id'
branch_labels = None
depends_on = None

def upgrade():
    # Remove username column
    op.drop_column('users', 'username')
    
    # Update indexes
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

def downgrade():
    # Add username column back
    op.add_column('users', sa.Column('username', sa.String(50), nullable=True))
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
```

### 2. Model Changes

#### Update User Model
Modify the User model to remove the username field:

```python
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    # Remove username field
    email = Column(String(100), unique=True, index=True, nullable=False)
    # Rest of the model remains unchanged
```

### 3. Schema Changes

#### Update Auth Schemas
Modify Pydantic schemas to remove username fields:

1. `LoginRequest`: Remove username field, only use email
2. `UserCreate`: Remove username field
3. `UserResponse`: Remove username field
4. `RegistrationResponse`: Remove username field

### 4. API Endpoint Changes

#### Update Auth Router Endpoints
1. Rename all URL paths that use username to use email:
   - `/users/{username}` → `/users/{email}`
   - `/users/{username}/email` → `/users/email` (or remove if redundant)
   - `/users/{username}/password` → `/users/{email}/password`

2. Update all method signatures and logic to use email as the identifier

### 5. Service Changes

#### Update User Service
1. Remove username-specific methods:
   - `get_user_by_username()`
   - `authenticate_user_by_username_or_email()` → simplify to `authenticate_user()`

2. Update methods to use email as the primary identifier:
   - `create_user()` - remove username parameter
   - `update_user_password()` - use email instead of username
   - `delete_user()` - use email instead of username

### 6. Security and Token Updates

1. Update token generation to exclusively use email as subject (already implemented)
2. Remove any username-related token validation logic

### 7. Test Updates

1. Update all test fixtures to use email-only authentication
2. Update all test cases that use username to use email instead
3. Remove username-specific test cases that are no longer relevant

### 8. Documentation Updates

1. Update project documentation to reflect email-only authentication
2. Update API documentation to remove username references

## Impact Analysis

### Code Impact
- **High Impact Areas**:
  - User model (core database entity)
  - Auth router (multiple endpoint paths and parameter changes)
  - User service (authentication and user management logic)
  - Tests (many tests rely on username-based authentication)

- **Medium Impact Areas**:
  - Email service (references to username in templates)
  - JWT token handling (already uses email but has backward compatibility for username)
  - Database schema (migration required)

- **Low Impact Areas**:
  - Credit-related services (may have minor references to username)
  - Stripe webhook handling (should be user ID based)
  - Healthcheck endpoints (no direct user interaction)

### Performance Impact
- **Query Performance**: Using email as the primary identifier should have no significant impact on database performance as both username and email have indexes.
- **Token Size**: JWT tokens might be slightly larger due to email addresses typically being longer than usernames, but the impact should be negligible.

### Security Impact
- **Positive**: Simplifies authentication logic, reducing potential for security bugs.
- **Neutral**: Email addresses are already being used for important functions like password resets.
- **Consideration**: Email addresses are more easily tied to real-world identities; ensure privacy policies reflect this.

## Testing Strategy

### Unit Tests
1. Update all unit tests to use email-only authentication
2. Add specific tests for:
   - Login with email
   - User creation with email only
   - Password reset with email
   - Email change processes

### Integration Tests
1. Update integration test fixtures to use email-only authentication
2. Test full authentication flows:
   - Registration → Verification → Login
   - Password reset flow
   - Email change flow

### Test Data Generation
Create test data generators that use email-only format.

## Rollback Plan

In case of issues, a rollback strategy is:

1. Run alembic downgrade to restore the username column
2. Revert code changes to restore username functionality
3. Ensure any data migration has a backup strategy

## Implementation Sequence

To minimize disruption during development, we recommend this sequence:

1. **Database Migration**: First create and test the migration to remove username
2. **Model Updates**: Update the User model to remove username field
3. **Service Layer Updates**: Remove username from service layer methods
4. **Schema Updates**: Update Pydantic models to remove username
5. **API Endpoint Updates**: Change API paths and parameters from username to email
6. **Test Updates**: Update all tests to match the new structure
7. **Documentation**: Update any documentation to reflect the changes

This sequence allows for phased testing at each step and minimizes the risk of breaking the entire authentication system at once.

## Detailed Implementation Plan

### 1. Database Schema Changes

#### 1.1 Alembic Migration
Create a new migration script to:
- Handle duplicate emails by keeping only one record per email (oldest/first record)
- Remove unique constraint on the username field
- Remove the username column completely

```python
"""Remove username field and use email as primary identifier"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

# revision identifiers
revision = 'remove_username_field'
down_revision = 'previous_migration_id'  # Update with actual previous migration
branch_labels = None
depends_on = None

def upgrade():
    # Step 1: Handle duplicate emails - keep only one user per email (the oldest one)
    op.execute(text("""
        WITH email_duplicates AS (
            SELECT email, MIN(id) as keep_id
            FROM users
            GROUP BY email
            HAVING COUNT(*) > 1
        )
        DELETE FROM users
        WHERE id IN (
            SELECT u.id
            FROM users u
            JOIN email_duplicates ed ON u.email = ed.email
            WHERE u.id != ed.keep_id
        )
    """))
    
    # Step 2: Remove unique constraint on username
    op.drop_constraint('users_username_key', 'users', type_='unique')
    
    # Step 3: Remove username column
    op.drop_column('users', 'username')

def downgrade():
    # Add username column back (for rollback if needed)
    op.add_column('users', sa.Column('username', sa.String(50), nullable=True))
    
    # Generate usernames from emails
    op.execute(text("""
        UPDATE users
        SET username = SUBSTRING(email FROM 1 FOR POSITION('@' IN email) - 1) 
            || '_' || id
    """))
    
    # Make username not nullable
    op.alter_column('users', 'username', nullable=False)
    
    # Add unique constraint back
    op.create_unique_constraint('users_username_key', 'users', ['username'])
```

### 2. Model Changes

#### 2.1 Update User Model
Modify `app/models/user.py` to remove username field:

```python
class User(Base):
    """
    SQLAlchemy model representing a user in the database.

    Attributes:
        id (int): The primary key for the user.
        email (str): Unique email for the user (primary identifier).
        hashed_password (str): Hashed password for the user.
        is_admin (bool): Flag indicating if user has admin privileges.
        is_verified (bool): Flag indicating if email has been verified.
        verification_token (str): Token for email verification.
        verification_token_expires_at (datetime): Expiration time for verification token.
        stripe_customer_id (str): Stripe customer ID for payment processing.
        google_id (str): Google OAuth user ID for OAuth authentication.
        auth_type (str): Authentication type - "password", "google", or "both".
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Nullable for OAuth-only users
    google_id = Column(String(255), nullable=True, unique=True)
    auth_type = Column(String(20), default="password", nullable=False)  # "password", "google", "both"
    is_admin = Column(Boolean, default=False, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    verification_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)

    # Relationships
    credits = relationship("UserCredit", back_populates="user", uselist=False, cascade="all, delete-orphan")
    credit_transactions = relationship("CreditTransaction", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
```

### 3. Schema Changes

#### 3.1 Update Authentication Schemas
Modify `app/schemas/auth_schemas.py` to remove username fields:

```python
# Remove username from LoginRequest
class LoginRequest(BaseModel):
    """Pydantic model for login request."""
    email: EmailStr
    password: str

    model_config = ConfigDict(from_attributes=True)

# Update UserCreate schema
class UserCreate(BaseModel):
    """Pydantic model for creating a new user."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters long")
    email_verification_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Update UserResponse schema
class UserResponse(BaseModel):
    """Schema for user response data."""
    email: EmailStr
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)

# Update RegistrationResponse schema
class RegistrationResponse(BaseModel):
    """Schema for registration response."""
    message: str
    email: EmailStr
    verification_sent: bool

    model_config = ConfigDict(from_attributes=True)
```

### 4. Service Layer Changes

#### 4.1 Update UserService
Modify `app/services/user_service.py` to remove username-related functionality:

```python
class UserService:
    """Service class for user operations."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: Email to look up

        Returns:
            Optional[User]: User if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password: str,
        is_admin: bool = False,
        auto_verify: bool = False
    ) -> User:
        """
        Create a new user.

        Args:
            email: Email for new user
            password: Plain text password
            is_admin: Whether user is admin
            auto_verify: Whether to auto-verify the email

        Returns:
            User: Created user

        Raises:
            HTTPException: If email already exists
        """
        try:
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                is_admin=is_admin,
                is_verified=auto_verify
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user.

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

    # ... other methods with username parameter removed and updated accordingly ...
```

#### 4.2 Modify function exports for backward compatibility
Update the exported functions at the bottom of `user_service.py`:

```python
# Function exports
async def create_user(db: AsyncSession, email: str, password: str, is_admin: bool = False) -> User:
    """Create a new user."""
    service = UserService(db)
    return await service.create_user(email, password, is_admin)

async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate a user using email."""
    service = UserService(db)
    return await service.authenticate_user(email, password)

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email."""
    service = UserService(db)
    return await service.get_user_by_email(email)

# ... remove username-related exports ...
```

### 5. API Endpoint Changes

#### 5.1 Update Auth Router Endpoints
Modify `app/routers/auth_router.py` to use email instead of username:

From:
```python
@router.get("/users/{username}", response_model=UserResponse)
async def get_user_details(username: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_username(db, username)
    # ...
```

To:
```python
@router.get("/users/{email}", response_model=UserResponse)
async def get_user_details(email: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_email(db, email)
    # ...
```

#### 5.2 Update the Login Endpoint
Modify the login endpoint to use email exclusively:

```python
@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    """Authenticate a user and return a JWT token."""
    try:
        user = await authenticate_user(db, credentials.email, credentials.password)
        if not user:
            logger.warning("Authentication failed", event_type="login_failed", email=credentials.email, reason="invalid_credentials")
            raise InvalidCredentialsError()

        # Calculate expiration time using timezone-aware datetime
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # Use email as the subject
        access_token = create_access_token(
            data={
                "sub": user.email,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )
        logger.info("User login successful", event_type="login_success", email=user.email)
        return Token(access_token=access_token, token_type="bearer")
    except Exception as e:
        logger.error("Login error", event_type="login_error", email=credentials.email, error_type=type(e).__name__, error_details=str(e))
        raise InvalidCredentialsError() from e
```

#### 5.3 Update Register Endpoint
Modify the registration endpoint to only use email:

```python
@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegistrationResponse)
async def register_user(user: UserCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> RegistrationResponse:
    """Register a new user and send a verification email."""
    try:
        # Create the user (initially not verified)
        new_user = await create_user(db, str(user.email), user.password)
        
        # Send verification email
        user_service = UserService(db)
        verification_sent = await user_service.send_verification_email(new_user, background_tasks)

        logger.info("User registered", 
                  event_type="user_registered", 
                  email=str(user.email),
                  verification_sent=verification_sent)

        return RegistrationResponse(
            message="User registered successfully. Please check your email to verify your account.",
            email=str(new_user.email),
            verification_sent=verification_sent
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error("Registration failed", 
                   event_type="registration_error", 
                   email=str(user.email), 
                   error_type=type(e).__name__,
                   error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail={"message": "Registration failed", "detail": str(e)}
        ) from e
```

#### 5.4 Update User Management Endpoints
Change all endpoints that use username in the path:

```python
# Change from /users/{username}/password to /users/{email}/password
@router.put("/users/{email}/password", responses={...})
async def change_password(email: str, passwords: PasswordChange, ...):
    ...

# Change from /users/{username} to /users/{email}
@router.delete("/users/{email}", responses={...})
async def remove_user(email: str, password: str, ...):
    ...

# Change from /users/{username}/email to /users/{email}/change-email
@router.put("/users/{email}/change-email", responses={...})
async def change_email(email: str, email_change: EmailChange, ...):
    ...
```

### 6. JWT Token Handling

#### 6.1 Simplify Token Refresh
Remove code that handles username-based tokens:

```python
@router.post("/refresh", response_model=Token)
async def refresh_token(refresh_request: RefreshToken, db: AsyncSession = Depends(get_db)) -> Token:
    """Refresh an existing JWT token."""
    try:
        # Verify the existing token
        payload = verify_jwt_token(refresh_request.token)
        
        # Get identifier from token (will always be email now)
        subject = payload.get("sub")
        
        # Find user by email
        user = await get_user_by_email(db, subject)
            
        if not user:
            logger.error("Token refresh failed - user not found", event_type="token_refresh_error", email=subject, error_type="user_not_found")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

        # Calculate new expiration time
        expires_delta = timedelta(minutes=60)
        expire_time = datetime.now(timezone.utc) + expires_delta

        # Create new access token
        access_token = create_access_token(
            data={
                "sub": user.email,
                "id": user.id,
                "is_admin": user.is_admin,
                "exp": expire_time.timestamp()
            },
            expires_delta=expires_delta
        )

        logger.info("Token refreshed successfully", event_type="token_refresh_success", email=user.email)

        return Token(access_token=access_token, token_type="bearer")

    except jwt.JWTError as e:
        logger.error("Token refresh failed - invalid token", event_type="token_refresh_error", error_type="jwt_error", error_details=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        ) from e
```

### 7. Tests Update

#### 7.1 Update Test Fixtures
Modify test fixtures to use email only:

```python
@pytest.fixture
def test_user():
    return {
        "email": "test@example.com",
        "password": "test_password"
    }

@pytest.fixture
async def created_test_user(test_user, test_db):
    user = await create_user(test_db, test_user["email"], test_user["password"])
    return user
```

#### 7.2 Update API Tests
Modify API tests to use email-based authentication:

```python
async def test_login(client, test_user, test_db):
    # Create test user
    await create_user(test_db, test_user["email"], test_user["password"])
    
    # Test login
    response = await client.post(
        "/login",
        json={"email": test_user["email"], "password": test_user["password"]}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
```

## Implementation Timeline

### Phase 1: Database Migration (Day 1)
- Create Alembic migration to handle duplicate emails and remove username field
- Apply migration to database

### Phase 2: Core Code Changes (Day 2-3)
- Update User model
- Update authentication schemas
- Update user service
- Update auth router endpoints

### Phase 3: Testing & Verification (Day 4)
- Update tests to use email-based authentication
- Run all tests to verify changes
- Fix any failed tests

### Phase 4: Final Verification (Day 5)
- Manually test all endpoints
- Verify JWT token creation and validation
- Ensure all functionality works with email-only authentication

## Affected Files

1. **Database Migration**
   - `alembic/versions/[new_migration]_remove_username_field.py`

2. **Models**
   - `app/models/user.py`

3. **Schemas**
   - `app/schemas/auth_schemas.py`

4. **Service Layer**
   - `app/services/user_service.py`
   - `app/services/oauth_service.py` (may need updates if it uses username)

5. **API Layer**
   - `app/routers/auth_router.py`
   - `app/core/auth.py`

6. **Tests**
   - `tests/test_auth_router.py`
   - `tests/test_email_login.py`
   - `tests/conftest.py` (for test fixtures)
   - Other test files that use authentication

## Risks and Mitigations

1. **Data Loss Risk**: Removal of users with duplicate emails
   - Mitigation: Since this is a development environment, data loss is acceptable
   - For production environments, would implement a more gradual approach with data migration

2. **Breaking Changes**: API endpoints change from username to email paths
   - Mitigation: Document all endpoint changes for frontend developers
   - Implement the changes all at once to avoid partial inconsistency

3. **OAuth Integration**: If OAuth relies on username
   - Mitigation: Update OAuth service to use email as primary identifier
   - Test OAuth flow thoroughly after changes

## Post-Implementation Verification

After implementation, verify:
1. New users can register using email only
2. Existing users can log in with email
3. Password reset works
4. Email verification works
5. JWT tokens contain email as subject
6. All tests pass
7. OAuth authentication works (Google sign-in)

## Rollback Plan

If critical issues are discovered during implementation:
1. Use the downgrade function in the Alembic migration to restore username field
2. Revert code changes to use username + email
3. Run tests to verify system is back to previous state