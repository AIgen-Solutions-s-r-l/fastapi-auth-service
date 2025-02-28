# Auth Service Email Enhancement Plan

## Current Architecture Analysis

After analyzing the existing codebase, I've gained a comprehensive understanding of the auth_service architecture and identified how to implement the new email functionalities while maintaining SOLID principles.

### Email System
- Uses `fastapi_mail` with a simple `send_email` function in `app/core/email.py` 
- Currently only used for password reset functionality
- Single email template found: `password_reset.html`

### User Management
- Well-structured service layer in `UserService`
- Registration, authentication, and password management implemented
- Password reset flow exists but without confirmation email
- No email verification system for registration currently exists

### Credit System
- `CreditService` handles credit balances and transactions
- Two transaction types: `CREDIT_ADDED` and `CREDIT_USED`
- No concept of plans, subscriptions, or renewal dates

### Architecture Pattern
- Follows SOLID principles with clear separation of concerns
- Models → Schemas → Services → Routers pattern
- Dependency injection used throughout

## Implementation Plan

### 1. Email Service Class

Create a proper service class to handle all email communication, following the existing service pattern:

```python
class EmailService:
    def __init__(self, background_tasks, db):
        self.background_tasks = background_tasks
        self.db = db
        
    async def send_registration_confirmation(self, user, confirmation_token):
        """Send registration confirmation email with verification link."""
        
    async def send_welcome_email(self, user):
        """Send welcome email after registration is confirmed."""
        
    async def send_payment_confirmation(self, user, plan, amount, renewal_date):
        """Send payment confirmation with plan purchase details and renewal date."""
        
    async def send_password_change_request(self, user, reset_token):
        """Send password change request verification email."""
        
    async def send_password_change_confirmation(self, user):
        """Send confirmation after password has been changed."""
        
    async def send_one_time_credit_purchase(self, user, amount, credits):
        """Send confirmation for one-time credit purchase."""
        
    async def send_plan_upgrade(self, user, old_plan, new_plan):
        """Send notification of plan upgrade."""
```

### 2. User Model and Schema Extensions

Add necessary fields to track email verification status:

```python
# Model extension
class User(Base):
    # Existing fields
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(255), nullable=True)
    verification_token_expires_at = Column(DateTime, nullable=True)

# Schema extension
class UserCreate(BaseModel):
    # Existing fields
    email_verification_url: Optional[str] = None
```

### 3. Email Templates

Create HTML templates for each required email type:

1. `registration_confirmation.html` - Email verification link for new registrations
2. `welcome.html` - Sent after successful email verification
3. `payment_confirmation.html` - For plan purchases with renewal date
4. `password_change_request.html` - Similar to existing password reset
5. `password_change_confirmation.html` - After password successfully changed
6. `one_time_credit_purchase.html` - For individual credit purchases
7. `plan_upgrade.html` - When upgrading to a higher tier plan

### 4. Credit System Extensions

#### Plan and Subscription Models

```python
class PlanTier(str, Enum):
    BASIC = "basic"
    STANDARD = "standard" 
    PREMIUM = "premium"

class Plan(Base):
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    tier = Column(String(20), nullable=False)
    credit_amount = Column(Numeric(10, 2), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    
class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=False)
    renewal_date = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan")
```

#### Enhanced Transaction Types

```python
class TransactionType(str, Enum):
    # Existing types
    CREDIT_ADDED = "credit_added"
    CREDIT_USED = "credit_used"
    
    # New types
    PLAN_PURCHASE = "plan_purchase"
    PLAN_RENEWAL = "plan_renewal"
    PLAN_UPGRADE = "plan_upgrade"
    ONE_TIME_PURCHASE = "one_time_purchase"
```

### 5. Service Methods Extension

#### UserService Extensions

```python
class UserService:
    # Existing methods...
    
    async def create_verification_token(self, user_id):
        """Generate and store email verification token."""
        
    async def verify_email(self, token):
        """Verify email with token and update user status."""
        
    async def resend_verification_email(self, email):
        """Resend verification email if expired or lost."""
```

#### CreditService Extensions

```python
class CreditService:
    # Existing methods...
    
    async def calculate_renewal_date(self, current_date):
        """
        Calculate renewal date (same day next month, same hour).
        Handles edge cases like month lengths and leap years.
        """
        
    async def add_credits_with_plan(self, user_id, plan_id):
        """
        Add credits based on plan and set up subscription with renewal date.
        """
        
    async def renew_plan(self, subscription_id):
        """
        Process plan renewal, add credits, and update renewal date.
        """
        
    async def upgrade_plan(self, user_id, new_plan_id):
        """
        Handle plan upgrade, update subscription, and adjust credits.
        """
        
    async def purchase_one_time_credits(self, user_id, amount, credit_amount):
        """
        Process one-time credit purchase without subscription.
        """
```

### 6. Integration Points

#### 1. Registration Flow Enhancement

```
User Registration → Create Verification Token → Send Registration Confirmation Email → 
User Clicks Verification Link → Verify Email → Send Welcome Email → Complete Registration
```

#### 2. Credit Purchase Flow Enhancement

```
Plan Purchase → Process Payment → Add Credits → Create/Update Subscription → 
Calculate Renewal Date → Send Payment Confirmation Email

OR

One-Time Purchase → Process Payment → Add Credits → 
Send One-Time Credits Purchase Email
```

#### 3. Plan Management Flow

```
Plan Upgrade → Update Subscription → Calculate New Renewal Date → 
Send Plan Upgrade Email
```

#### 4. Password Management Flow Enhancement

```
Password Change Request → Create Reset Token → Send Password Change Request Email →
User Confirms → Process Password Change → Send Password Change Confirmation Email
```

### 7. Router Updates

Update existing routes and add new ones to support these flows:

```python
# New routes
@router.post("/verify-email/{token}")
async def verify_email(token: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db))

@router.post("/resend-verification")
async def resend_verification(email: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db))

# Enhanced routes in credit_router.py
@router.post("/purchase-plan")
async def purchase_plan(...)

@router.post("/upgrade-plan")
async def upgrade_plan(...)

@router.post("/purchase-one-time")
async def purchase_one_time(...)
```

## Implementation Strategy

### Phase 1: Email Infrastructure

1. Create `EmailService` class
2. Design and implement all email templates
3. Add unit tests for email rendering and sending

### Phase 2: User Verification System

1. Update User model with verification fields
2. Implement verification token generation and validation
3. Update registration flow to include email verification
4. Add verification endpoints
5. Add welcome email after verification

### Phase 3: Credit System Extensions

1. Create Plan and Subscription models
2. Implement renewal date calculation logic
3. Extend credit transaction types
4. Implement plan purchase, renewal, and upgrade functionality

### Phase 4: Integration

1. Connect all components
2. Ensure emails are triggered at appropriate points
3. Implement proper error handling and retries for email sending

### Phase 5: Testing and Documentation

1. Unit tests for all new components
2. Integration tests for each workflow
3. Test edge cases for renewal dates (month end, leap years)
4. Document all changes and new features

## SOLID Principles Adherence

1. **Single Responsibility Principle**: Each service class has a specific responsibility
2. **Open/Closed Principle**: Extending functionality without modifying existing code
3. **Liskov Substitution Principle**: Subclasses remain compatible with base classes
4. **Interface Segregation Principle**: Clients only depend on interfaces they use
5. **Dependency Inversion Principle**: High-level modules depend on abstractions

## Error Handling and Edge Cases

1. **Email Sending Failures**: Implement retries and error logging
2. **Verification Token Expiration**: Handle expired tokens gracefully
3. **Renewal Date Calculation**: Handle month-end dates and leap years
4. **Duplicate Emails**: Prevent multiple emails of the same type in short periods
5. **Missing Templates**: Fallback mechanisms for missing email templates