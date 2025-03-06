# Decision Log

## 2025-03-05: Remove Username Field
### Context
- System was using both username and email for user identification
- Email was already being used as the primary identifier in most places
- Having both fields added unnecessary complexity

### Decision
- Remove username field entirely
- Use email as the sole identifier for users
- Update all templates and services to use email instead of username

### Consequences
Positive:
- Simplified user model
- Clearer identification using email only
- Reduced complexity in authentication flow
- Better alignment with modern authentication practices

Negative:
- Migration needed for existing data
- Need to update all references to username
- Some tests need to be updated

### Status
- Implementation in progress
- Migration created
- Email service updated
- Templates verified

### Next Steps
1. Run database migration
2. Update remaining tests
3. Verify all functionality works with email only

## 2025-03-06: Change Verify Email Endpoint to GET
### Context
- Current verify-email endpoint uses POST method
- Email verification links are typically accessed via GET requests from email clients
- POST is not ideal for links in emails as they should be clickable without requiring a form submission

### Decision
- Change verify-email endpoint from POST to GET
- Update related tests and documentation
- Keep the same response format and validation logic

### Consequences
Positive:
- Better user experience as verification links work directly when clicked
- More aligned with REST principles for read operations
- Follows common industry practice for email verification

Negative:
- Need to update any clients using the current POST endpoint
- Token needs to be passed as a query parameter instead of in request body
- Slightly less secure as GET parameters might be logged in server logs

### Status
- Planning implementation
- Documentation being updated

### Next Steps
1. Update endpoint in auth_router.py
2. Add comprehensive tests
3. Update API documentation
4. Deploy changes