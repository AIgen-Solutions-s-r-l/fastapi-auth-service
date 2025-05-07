import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models.user import User, PasswordResetToken
from app.core.security import get_password_hash
from datetime import datetime, UTC, timedelta
import secrets
import string

async def create_test_user():
    # Create database engine and session
    engine = create_async_engine("postgresql+asyncpg://testuser:testpassword@172.17.0.1:5432/main_db")
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Check if test user already exists
        user = await session.get(User, 1)
        
        if not user:
            # Create test user
            user = User(
                id=1,
                email="test@example.com",
                hashed_password=get_password_hash("password123"),
                auth_type="email",
                is_admin=False,
                is_verified=True,
                account_status="active",
                has_consumed_initial_trial=False,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
            )
            session.add(user)
            await session.commit()
            print("Test user created")
        else:
            print("Test user already exists")
        
        # Create a password reset token for the test user
        # Generate a random token
        alphabet = string.ascii_letters + string.digits
        token = ''.join(secrets.choice(alphabet) for _ in range(64))
        
        # Create token record
        reset_token = PasswordResetToken(
            token=token,
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            used=False
        )
        
        session.add(reset_token)
        await session.commit()
        
        print(f"Password reset token created: {token}")
        return token

if __name__ == "__main__":
    token = asyncio.run(create_test_user())