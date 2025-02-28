# Auth Service - Decision Log

This document tracks key architectural and design decisions made during the development of the auth_service project.

## February 28, 2025 - Authentication System Change from Username to Email

**Context:** The current authentication system uses username for login, but the requirement has changed to use email for authentication instead. Username will remain as an optional field for now but will be completely removed in the future.

**Decision:** Modify the authentication system to use email as the primary identifier for login instead of username while keeping the username field temporarily for backward compatibility.

**Rationale:** 
- Using email for authentication aligns with industry best practices, as email addresses are unique and users typically remember their email addresses better than usernames
- Email addresses are already required to be unique in the system, making them suitable as a primary identifier
- Keeping the username field temporarily allows for a smoother transition and backward compatibility with existing code and systems
- Moving to email-based authentication simplifies the user experience by reducing the number of credentials users need to remember

**Implementation:** Created detailed implementation plans:
- email_login_implementation_plan.md: High-level plan outlining the changes needed to implement email-based login
- email_login_technical_implementation.md: Detailed technical implementation plan with specific code changes required, including:
  - Updating authentication schemas to use email instead of username
  - Modifying user service authentication methods
  - Updating the authentication router login endpoint
  - Changing JWT token generation to use email as the subject instead of username
  - Updating token verification to retrieve users by email instead of username

**Expected Results:** Users will be able to log in using their email address and password, while the system maintains backward compatibility with existing code. This change will simplify the authentication flow and align with modern authentication best practices.

**Implementation Results:** Successfully implemented all planned changes while maintaining backward compatibility:
- Updated LoginRequest schema to accept either email or username with a validator to ensure at least one is provided
- Modified user service to authenticate with either email or username via the authenticate_user_by_username_or_email function
- Updated auth router login endpoint to use the new authentication function
- Changed JWT token generation to always use email as the subject for new tokens
- Enhanced token verification to support both email and username-based tokens for a smooth transition
- Fixed email change functionality to issue new tokens with the updated email address
- Created comprehensive tests for email-based login and updated all existing tests to work with the modified authentication system
- Addressed edge cases in authentication flows and token handling, including token refresh and user profile access

The implementation enables a seamless transition from username to email-based authentication while maintaining compatibility with existing tokens. This approach allows systems that depend on the current authentication flow to continue working while new authentications use email as the primary identifier.

## February 28, 2025 - Environment Variable Loading Fix

**Context:** The application wasn't loading environment variables from the .env file despite having a properly configured .env file. This caused the SendGrid API key to not be detected, resulting in errors: "SendGrid API key not configured (SENDGRID_API_KEY)" during application startup.

**Decision:** Update the `Settings` class in `app/core/config.py` to properly load environment variables from the .env file using pydantic-settings' configuration option and configure it to ignore extra fields.

**Rationale:** While the application was using pydantic-settings' BaseSettings class, it wasn't configured to load variables from a .env file. The application was only using direct OS environment variables via os.getenv(). By adding the proper configuration, we ensure that environment variables are loaded correctly from the .env file, which improves configuration management and deployment flexibility. Additionally, we needed to configure pydantic to ignore extra fields since the .env file contains some variables that aren't defined in the Settings class.

**Implementation:** Added the `model_config` attribute to the `Settings` class in `app/core/config.py`:
```python
model_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore"  # Ignore extra fields not defined in the class
)
```
This tells pydantic-settings to load environment variables from the .env file in the project root directory and ignore any extra fields that aren't defined in the Settings class.

**Results:** After making these changes, the application successfully loads all environment variables from the .env file, including the SendGrid API key. The email configuration is now validated successfully at startup with no issues or warnings.

## February 26, 2025 - Auth Router Endpoint Simplification

**Context:** The auth router currently has two similar endpoints for retrieving user email information: `/users/{user_id}/email` and `/users/{user_id}/profile`. The first returns only the email, while the second returns email, username, and verification status. This creates unnecessary duplication and potential confusion for API consumers.

**Decision:** Simplify the API by removing the `/users/{user_id}/profile` endpoint and its implementation (`get_email_and_username_by_user_id`), keeping only the `/users/{user_id}/email` endpoint that returns just the email.

**Rationale:** Having two endpoints with overlapping functionality increases maintenance burden and can confuse API consumers. Since the requirement is to have a function that returns only the email, it makes sense to use the existing `get_email_by_user_id` function and remove the redundant endpoint.

**Implementation:** Successfully implemented the plan outlined in auth_router_modification_plan.md:
- Removed the `/users/{user_id}/profile` endpoint and its implementation
- Kept the existing `/users/{user_id}/email` endpoint unchanged
- Updated all affected tests in the following files:
  - tests/test_auth_router_final.py
  - tests/test_auth_router_coverage_patched.py
  - tests/test_auth_router_final_uncovered.py
  - tests/test_auth_router_coverage.py
  - tests/test_auth_router_coverage_final.py
  - tests/test_auth_router_extended.py

**Results:** The API is now simpler and more focused, with a single endpoint for retrieving user email information. Manual testing confirms that the `/users/{user_id}/email` endpoint works correctly, returning just the email as expected, while the `/users/{user_id}/profile` endpoint returns a 404 Not Found response.

## February 26, 2025 - Subscription Tier System Update

**Context:** The current subscription tier system has 3 tiers (Basic, Standard, Premium), but new requirements specify a 5-tier system based on application counts (100, 200, 300, 500, 1000) with specific pricing for each tier.

**Decision:** Update the subscription tier system to implement the 5-tier structure with corresponding prices and credit amounts.

**Rationale:** The new tier structure better aligns with business requirements by providing more granular options for users with different application volume needs. This will improve revenue potential and user satisfaction by offering more tailored pricing options.

**Implementation:** Created a comprehensive plan in subscription_tier_update_plan.md that includes:
- Updating the PlanTier enum in app/models/plan.py to reflect the new tiers
- Creating a database migration to update existing plans and add new ones
- Updating any code references to the old tier names
- Testing plan creation, upgrades, and renewals with the new tier structure

## February 26, 2025 - Email Sending Improvements Implementation

**Context:** After diagnosing the email sending issues, we needed to implement the planned improvements to ensure reliable email delivery for user registration, password resets, and notifications.

**Decision:** Implement the comprehensive email system improvements outlined in the email_implementation.md plan.

**Rationale:** Reliable email delivery is critical for user verification, password resets, and notifications. The implemented improvements enhance reliability, error handling, and diagnostic capabilities, ensuring a better user experience.

**Implementation:** Successfully implemented the following improvements:
- Added diagnostic endpoints for testing email functionality (`/test-email` and `/verify-email-templates`)
- Enhanced error logging throughout the email sending process with detailed event types and context
- Implemented retry logic with exponential backoff for transient failures
- Added template verification functionality to ensure templates exist and can be rendered
- Added email configuration validation at startup to catch configuration issues early
- Updated the email service to use the improved email sending functions with retry logic

**Results:** The email system now has improved reliability, better error handling, and diagnostic capabilities to quickly identify and resolve any future issues. Users are now receiving registration confirmation emails and other notifications reliably.

## February 26, 2025 - Email Sending Diagnostic and Implementation Plan

**Context:** Users are not receiving registration confirmation emails when registering with an email address like rocchi.b.a@gmail.com. This issue affects the user experience and prevents proper account verification.

**Decision:** Develop a comprehensive diagnostic and implementation plan to identify and fix the email sending issues.

**Rationale:** Email functionality is critical for user verification, password resets, and notifications. A systematic approach to diagnosing and fixing the issue will ensure reliable email delivery and improve user experience.

**Implementation:** Created the following documentation and implementation plans:
- email_diagnostic_plan.md: Detailed diagnostic steps to identify the root cause of email sending failures
- email_implementation.md: Specific implementation steps to enhance email sending reliability, including:
  - Adding a test email endpoint for direct testing
  - Enhancing error logging in the email sending process
  - Implementing retry logic for transient failures
  - Adding template verification functionality
  - Validating email configuration at startup

## February 26, 2025 - Comprehensive Architectural Documentation

**Context:** Need for detailed architectural documentation, code structure analysis, security review, and documentation planning to guide future development of the auth_service project.

**Decision:** Create comprehensive architectural documentation covering system architecture, code structure, security considerations, and documentation needs.

**Rationale:** Detailed documentation provides a foundation for understanding the current state of the project, identifying improvement opportunities, and guiding future development in a consistent and secure manner.

**Implementation:** Created the following documentation:
- architecture.md: Detailed system architecture, component interactions, and data flows
- code_structure.md: Analysis of code organization, patterns, and refactoring opportunities
- security_review.md: Comprehensive security review with recommendations
- documentation_plan.md: Plan for improving and maintaining project documentation

## February 26, 2025 - Memory Bank Initialization

**Context:** Need for structured documentation and project tracking for the auth_service project.

**Decision:** Initialize a Memory Bank with core documentation files to track project context, progress, and decisions.

**Rationale:** A Memory Bank provides a centralized location for project documentation, making it easier to maintain context across development sessions and track architectural decisions over time.

**Implementation:** Created the following core Memory Bank files:
- productContext.md: Project overview, vision, goals, and constraints
- activeContext.md: Current session state and goals
- progress.md: Work completed and next steps
- decisionLog.md: This file, tracking key decisions and their rationale
- systemPatterns.md: Design patterns and architectural patterns used in the project

## Historical Decisions (Inferred from Project Structure)

### FastAPI Framework Selection

**Context:** Need for a modern, high-performance web framework for the authentication service.

**Decision:** Use FastAPI as the web framework.

**Rationale:** FastAPI offers automatic validation, serialization, interactive documentation, and high performance with async support, making it well-suited for an authentication service.

### JWT-based Authentication

**Context:** Need for a secure, stateless authentication mechanism.

**Decision:** Implement JWT-based authentication with configurable expiration.

**Rationale:** JWTs provide a secure, stateless way to handle authentication, allowing for easy scaling and reduced database load compared to session-based authentication.

### PostgreSQL Database

**Context:** Need for a reliable, feature-rich database for storing user data and transactions.

**Decision:** Use PostgreSQL with async support via SQLAlchemy.

**Rationale:** PostgreSQL offers robust transaction support, data integrity, and performance needed for an authentication service with credit system functionality.

### Credit System Implementation

**Context:** Need for tracking user credits and transactions.

**Decision:** Implement a dedicated credit system with balance tracking and transaction history.

**Rationale:** A separate credit system allows for better separation of concerns and more flexible handling of credit-related operations.

### Email Integration

**Context:** Need for user notifications and password reset functionality.

**Decision:** Implement email integration with customizable templates.

**Rationale:** Email notifications enhance user experience and security by providing confirmation of important actions and enabling secure password reset flows.