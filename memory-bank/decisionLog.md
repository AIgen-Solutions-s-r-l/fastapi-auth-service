# Decision Log

## 2025-03-06: Endpoint Security Enhancement

### Context
We identified security issues with the authentication service:
1. Some auth endpoints that should be available only to verified users weren't properly restricted
2. There was a need to confirm that credit and stripe routes are properly secured for internal access only

### Decision
1. Modified the `/link/google` and `/unlink/google` endpoints to use `get_current_active_user` dependency instead of `get_current_user`
2. Added appropriate 403 responses to the documentation for these endpoints
3. Confirmed that credit router and stripe webhook router were already properly secured for internal access only through the `get_internal_service` dependency

### Rationale
- Using `get_current_active_user` ensures that only verified users can access these endpoints
- The `get_current_active_user` dependency checks for both authentication and email verification
- Credit and stripe endpoints were already properly secured using API key authentication through the `get_internal_service` dependency

### Implementation
- Updated the dependency injection in both Google account link/unlink endpoints
- Updated API documentation to reflect possible 403 responses
- Created detailed documentation in `endpoint_security_implementation_plan.md`