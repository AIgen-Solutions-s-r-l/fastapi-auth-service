# Decision Log

## 2025-03-06: Authentication Refactoring - JWT Tokens Only After Email Verification

**Context:**
- Currently, the authentication system issues JWT tokens to users during login regardless of whether their email has been verified.
- This creates a security issue as unverified users can access the system.

**Decision:**
- Modify the login endpoint to check if a user's email is verified before issuing a JWT token.
- Return a 403 Forbidden response with a clear message if a user attempts to log in without verifying their email.
- Update tests to reflect this new behavior.

**Alternatives Considered:**
- Allow login but restrict access to certain endpoints: This would be more complex to implement and maintain.
- Use a different token type for unverified users: This would add unnecessary complexity to the authentication system.

**Consequences:**
- Improved security as only verified users can access the system.
- Slightly more complex onboarding flow for users.
- Frontend applications will need to handle the new error response.

**Implementation Plan:**
- See detailed plan in [auth_verification_refactor_plan.md](auth_verification_refactor_plan.md)