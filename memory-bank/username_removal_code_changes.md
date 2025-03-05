# Username Removal Code Changes

## Issues Found

From the code review, I've found three remaining references to "username" that need to be updated:

1. In `app/services/user_service.py`, line 118:
   ```python
   detail="Invalid username or password"
   ```
   This needs to be changed to "Invalid email or password" for consistency.

2. In `app/core/auth.py`:
   - Line 29: Comment mentions "email and username in the 'sub' claim for backward compatibility"
   - Lines 59-61: Code that attempts to find a user by username as fallback:
     ```python
     # If not found, try to find by username (old tokens)
     if user is None:
         user = await user_service.get_user_by_username(subject)
     ```

## Specific Changes Required

### 1. Update app/services/user_service.py

```diff
@@ -117,7 +117,7 @@
         if not user:
             raise HTTPException(
                 status_code=status.HTTP_401_UNAUTHORIZED,
-                detail="Invalid username or password"
+                detail="Invalid email or password"
             )
```

### 2. Update app/core/auth.py

```diff
@@ -26,7 +26,7 @@
     """
     Get the current authenticated user from the JWT token.
-    Supports both email and username in the 'sub' claim for backward compatibility.
+    Uses email in the 'sub' claim for authentication.

     Args:
         token: JWT token
@@ -56,10 +56,6 @@
     # Try to find user by email first (new tokens)
     user = await user_service.get_user_by_email(subject)
     
-    # If not found, try to find by username (old tokens)
-    if user is None:
-        user = await user_service.get_user_by_username(subject)
-        
     if user is None:
         raise credentials_exception
         
```

## Testing Plan

After making these changes, we should:

1. Verify that authentication still works properly with email-based login
2. Ensure that JWT tokens with email as the subject are correctly validated
3. Check that error messages are consistent across the application

## Implementation Notes

- The `get_user_by_username()` method referenced in `auth.py` does not exist in the current implementation, so removing this code will fix a potential runtime error.
- These changes complete the migration to email-only authentication.
- After implementing these changes, all tests should be run to ensure everything works correctly.