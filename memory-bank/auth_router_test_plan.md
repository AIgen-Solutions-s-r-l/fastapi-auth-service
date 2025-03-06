# Auth Router Test Plan

## Overview
This document outlines the test plan for the authentication router (`auth_router.py`). The tests will cover key functionality including login, registration, email verification, and error cases.

## Test Structure

### 1. Test Environment Setup
- Create pytest fixtures for:
  - Database session
  - FastAPI test client
  - Mock email service
  - Mock user service
  - Authentication dependencies

### 2. Test Categories

#### 2.1 Login Tests
- **Successful Login**
  - Input: Valid email and password
  - Expected: JWT token and 200 status
  - Verify token structure and expiry

- **Invalid Credentials**
  - Test invalid password
  - Test non-existent email
  - Expected: 401 status with appropriate error message

- **Missing/Malformed Data**
  - Test missing email
  - Test missing password
  - Test invalid email format
  - Expected: 422 status with validation errors

#### 2.2 Registration Tests
- **Successful Registration**
  - Input: Valid email and password
  - Expected: 201 status and verification email sent
  - Verify user created in database

- **Duplicate Registration**
  - Test registering existing email
  - Expected: 409 status with conflict error

- **Invalid Registration Data**
  - Test invalid email format
  - Test weak password
  - Expected: 422 status with validation errors

#### 2.3 Email Verification Tests
- **Successful Verification**
  - Input: Valid verification token
  - Expected: 200 status and user marked as verified
  - Verify welcome email sent

- **Invalid Token Tests**
  - Test invalid token format
  - Test expired token
  - Test already used token
  - Expected: 400 status with appropriate error

#### 2.4 Error Cases
- **Rate Limiting**
  - Test excessive login attempts
  - Test excessive registration attempts
  - Expected: 429 status when limit exceeded

- **Invalid Requests**
  - Test malformed JSON
  - Test invalid content types
  - Expected: Appropriate error responses

### 3. Implementation Details

#### 3.1 Test File Structure
```python
tests/
  conftest.py              # Common fixtures
  test_auth_router/
    __init__.py
    test_login.py         # Login related tests
    test_registration.py  # Registration related tests
    test_verification.py  # Email verification tests
    test_error_cases.py   # Error handling tests
```

#### 3.2 Key Dependencies to Mock
- Email service
- Database operations
- JWT token generation
- External service calls

### 4. Test Data Management
- Use fixtures for common test data
- Clean up test data after each test
- Use unique identifiers for test isolation

### 5. Coverage Goals
- Aim for >90% code coverage
- Focus on edge cases and error conditions
- Include integration tests for key flows

## Next Steps
1. Create test directory structure
2. Implement base fixtures
3. Implement test cases in order of priority
4. Add integration tests
5. Verify coverage goals

## Implementation Plan
1. Switch to code mode
2. Create test directory structure
3. Implement fixtures and base test setup
4. Implement test cases following the outlined structure
5. Run tests and verify coverage