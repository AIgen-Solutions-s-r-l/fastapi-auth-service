# Authentication Service Endpoint Security Documentation

## Security Classifications

The Authentication Service endpoints follow a classification system to determine access requirements:

### 1. Public Endpoints

- **No authentication required**
- Examples: `/login`, `/register`, `/password-reset-request`
- Accessible by anyone, including anonymous users
- Used for initial user interactions that don't require authentication

### 2. User-Authenticated Endpoints

- **JWT token required** (via Bearer authentication)
- Examples: `/me`, `/users/change-password`, `/users/change-email`
- Accessible only by authenticated users
- Protected by the `get_current_user` dependency

### 3. Internal-Only Endpoints

- **API key required** (via header)
- Examples: `/users/{user_id}/email`, `/users/by-email/{email}`
- Accessible only by other microservices using the INTERNAL_API_KEY
- Protected by the `get_internal_service` dependency
- Not meant for direct user access

### 4. Hybrid Endpoints (Service or User)

- **Either API key or JWT token required**
- Protected by the `get_service_or_user` dependency
- Allows flexible access during transition periods

## Internal Endpoints

Internal endpoints are designed for service-to-service communication only and should never be exposed directly to users or external systems.

### Recently Secured Endpoints

The following endpoints have been secured as internal-only:

1. `GET /auth/users/{user_id}/email`
   - Purpose: Retrieve a user's email address by user ID
   - Primary consumers: Other microservices that need to access user email

2. `GET /auth/users/by-email/{email}`
   - Purpose: Retrieve user details by email address
   - Primary consumers: Other microservices that need to validate users

### Authentication Mechanism

Internal endpoints use API key authentication:

1. The calling service must include the `api-key` header with the correct INTERNAL_API_KEY value
2. The `get_internal_service` dependency validates this key
3. If valid, the endpoint executes; if invalid, a 403 Forbidden response is returned

```python
# Example of securing an endpoint as internal-only
@router.get("/some-internal-endpoint")
async def internal_endpoint(
    service_id: str = Depends(get_internal_service),
    # other dependencies...
):
    # Endpoint implementation
```

### Security Considerations

1. **API Key Management**
   - The INTERNAL_API_KEY should be rotated periodically
   - Each environment (dev, staging, prod) should use a different key
   - Never log or expose the key

2. **Network Security**
   - Internal endpoints should be protected at the network level when possible
   - Consider using a service mesh or API gateway for additional protection

3. **Logging and Monitoring**
   - All access to internal endpoints is logged with the service identifier
   - Regular audits should be performed to ensure proper usage

## Service-to-Service Authentication Flow

When one service needs to call an internal endpoint on the Auth Service:

1. The calling service includes the INTERNAL_API_KEY in the request header:
   ```
   api-key: <INTERNAL_API_KEY value>
   ```

2. The Auth Service validates the API key via the `get_internal_service` dependency

3. If valid, the endpoint processes the request and returns the response
   If invalid, the endpoint returns a 403 Forbidden response

## Testing Internal Endpoints

When testing internal endpoints:

1. **Manually (using curl):**
   ```bash
   curl -X GET "http://localhost:8000/auth/users/123/email" \
     -H "api-key: your-internal-api-key"
   ```

2. **Automated Tests:**
   ```python
   # Example pytest test for an internal endpoint
   def test_internal_endpoint_with_valid_api_key(client):
       headers = {"api-key": settings.INTERNAL_API_KEY}
       response = client.get("/auth/users/123/email", headers=headers)
       assert response.status_code == 200
       
   def test_internal_endpoint_without_api_key(client):
       response = client.get("/auth/users/123/email")
       assert response.status_code == 403
   ```

## Security Best Practices

1. **Always use the correct dependency** for the endpoint's security classification
2. **Document security requirements** in endpoint docstrings and responses
3. **Include appropriate error responses** (401, 403) in the OpenAPI documentation
4. **Use consistent logging** with service identification for audit trails
5. **Regularly review endpoint security** to ensure proper protection

## Conclusion

Proper endpoint security classification ensures that sensitive operations are appropriately protected. By securing internal endpoints with API key authentication, we maintain the principle of least privilege and ensure that only authorized services can access sensitive user information.