# Decision Log

## 2025-03-06: Internal Endpoint Security Implementation

### Context
Two endpoints in the authentication service were identified as needing internal-only access restrictions:
1. `/auth/users/{user_id}/email` - Retrieves a user's email by their ID
2. `/auth/users/by-email/{email}` - Retrieves user details by email address

These endpoints expose sensitive user information and shouldn't be publicly accessible.

### Decision
1. Modified both endpoints to require the `get_internal_service` dependency
2. Updated logging to include service identification in all log entries
3. Changed event types to standardize as "internal_endpoint_access" and "internal_endpoint_error"
4. Added 403 responses to the API documentation
5. Updated endpoint docstrings to clearly indicate internal-only status

### Rationale
- Service-to-service communication requires proper authentication
- User email addresses and details are sensitive personal information
- Using `get_internal_service` enforces API key authentication
- Consistent logging enables better security auditing and monitoring
- Clear documentation helps developers understand access restrictions

### Implementation
- Added the `get_internal_service` dependency to both endpoint function signatures
- Added service_id parameter to all logging calls
- Updated OpenAPI documentation with 403 responses
- Created detailed documentation in `endpoint_security_documentation.md`
- Created code change specifications in `endpoint_security_code_changes.md`

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

## 2025-03-06: Hide Internal Endpoints from API Schema

### Context
Internal endpoints `/auth/users/{user_id}/email` and `/auth/users/by-email/{email}` were already secured with the `get_internal_service` dependency, but they were still visible in the public API documentation (Swagger/OpenAPI).

### Decision
1. Added `include_in_schema=False` to both internal endpoint definitions
2. Fixed and updated tests in `test_internal_endpoints.py` to handle proper user ID retrieval
3. Updated test assertions to account for FastAPI's behavior with missing headers

### Rationale
- Endpoints used only for internal service-to-service communication should not be visible in public API documentation
- Hiding internal endpoints from the API schema reduces the discovery surface for potential attackers
- "Security through obscurity" is not a primary defense but provides an additional layer of protection
- The updated tests properly validate that these endpoints remain secure and functioning correctly

### Implementation
- Added `include_in_schema=False` to endpoint decorators in `auth_router.py`
- Fixed test code to properly retrieve user IDs from the database for testing
- Updated test assertions to account for FastAPI's validation behavior (422 status vs 403)
- Documented changes in `endpoint_security_code_changes.md`