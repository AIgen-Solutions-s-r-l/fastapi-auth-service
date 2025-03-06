# Endpoint Security Implementation Plan

## Issues Identified
1. Some auth endpoints that should be available only to verified users aren't properly restricted
2. Credit and Stripe routes should be available only internally and not exposed externally

## Current State Analysis

### Auth Router
- Some endpoints use `get_current_active_user` (which requires verification)
- Others use just `get_current_user` (which only requires authentication, not verification)
- Need to ensure endpoints requiring verification use the proper dependency

### Credit Router
- Currently uses `get_internal_service` dependency for all endpoints
- Already properly secured for internal access only

### Stripe Webhook Router
- Using `get_internal_service` dependency
- Already properly secured for internal access only

## Implementation Plan

### Auth Router Changes
Need to modify the following endpoints to use `get_current_active_user` instead of `get_current_user`:
- `/link/google` endpoint
- `/unlink/google` endpoint

### Credit and Stripe Routes
- No changes needed - they already use the `get_internal_service` dependency that ensures only internal services can access them
- This is implemented using the API key header check in `get_internal_service()`

## Classification of Auth Endpoints

### Public Endpoints (No Auth Required)
- `/login` - Authentication endpoint
- `/register` - Registration endpoint
- `/verify-email` - Email verification endpoint
- `/resend-verification` - Resend verification email
- `/password-reset-request` - Request password reset
- `/reset-password` - Reset password with token
- `/users/{user_id}/email` - Get user email by ID (public for interservice communication)
- `/users/by-email/{email}` - Get user by email (public for interservice communication)
- `/oauth/google/login` - Google auth initial endpoint
- `/oauth/google/callback` - Google auth callback endpoint
- `/test-email` - Test endpoint
- `/verify-email-templates` - Test endpoint

### Authenticated Endpoints (Require Verification)
- `/me` - Get current user profile (already using get_current_active_user)
- `/logout` - Logout (already using get_current_active_user)
- `/users/change-password` - Change password (already using get_current_active_user)
- `/users/change-email` - Change email (already using get_current_active_user)
- `/users/delete-account` - Delete account (already using get_current_active_user)
- `/refresh` - Refresh token (only needs valid token, not verification)
- `/link/google` - **NEEDS CHANGE** (currently using get_current_user)
- `/unlink/google` - **NEEDS CHANGE** (currently using get_current_user)