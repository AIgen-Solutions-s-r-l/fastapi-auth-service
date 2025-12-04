# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-based authentication microservice with JWT authentication, Google OAuth 2.0, Stripe payment integration, and a credit system. Uses PostgreSQL with async SQLAlchemy ORM.

## Common Commands

### Development
```bash
poetry install                              # Install dependencies
uvicorn app.main:app --reload --port 8080   # Run development server
python run_api_server.py                    # Alternative: run via script
```

### Testing
```bash
poetry run pytest                                    # Run all tests
poetry run pytest --cov=app                          # Run with coverage
poetry run pytest -k test_login                      # Run tests matching pattern
poetry run pytest tests/test_auth_router/test_login.py::test_login_success  # Single test
```

### Code Quality
```bash
poetry run black .      # Format code
poetry run isort .      # Sort imports
poetry run flake8       # Lint
```

### Database Migrations
```bash
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                              # Apply migrations
alembic downgrade -1                              # Rollback one
```

## Architecture

```
app/
├── core/           # Auth dependencies, config, database, security, logging
├── models/         # SQLAlchemy ORM models (User, UserCredit, Plan, Subscription)
├── routers/        # API endpoints
│   ├── auth/       # Authentication (user_auth, social_auth, email/password management)
│   ├── webhooks/   # Stripe webhooks
│   └── credit_router.py, healthcheck_router.py
├── schemas/        # Pydantic request/response models
├── services/       # Business logic (user_service, stripe_service, credit/)
├── templates/      # Email templates
└── main.py         # FastAPI app entry point
```

**Layered pattern**: Routers → Services → Models/Database

## Security Model

Four endpoint security levels (dependencies in `app/core/auth.py`):
1. **Public**: No auth (login, register, password reset)
2. **Authenticated**: JWT token via `get_current_user`
3. **Verified User**: JWT + email verified via `get_current_active_user`
4. **Internal Service**: API key via `get_internal_service` (X-API-Key header)

## Key Models

- **User**: `email`, `hashed_password` (nullable for OAuth-only), `google_id`, `auth_type` ("password"/"google"/"both"), `is_verified`, `stripe_customer_id`
- **UserCredit**: Credit balance per user (Numeric 10,2)
- **CreditTransaction**: Credit operation audit trail
- **Plan/Subscription**: Stripe subscription plans and user subscriptions

## Testing Notes

- Uses SQLite (`sqlite+aiosqlite:///./test.db`) for tests
- Async tests with `pytest-asyncio` (auto mode configured in `pytest.ini`)
- Test fixtures in `tests/conftest.py`

## Environment Variables

Key settings needed in `.env`:
- `DATABASE_URL`: PostgreSQL connection (postgresql+asyncpg://...)
- `SECRET_KEY`, `ALGORITHM` (HS256), `ACCESS_TOKEN_EXPIRE_MINUTES`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
- Mail settings: `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM`, `MAIL_SERVER`
- `FRONTEND_URL`: For email verification links
