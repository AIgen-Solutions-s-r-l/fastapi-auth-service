# Stripe Integration for Credits System

This document explains how the credits system integrates with Stripe for payment processing, subscriptions, and one-time purchases.

## Overview

The integration allows users to purchase credits through two methods:
1. **One-time purchases**: User makes a single payment and receives a fixed amount of credits
2. **Subscriptions**: User subscribes to a plan and receives credits periodically (e.g., monthly)

The system handles both payment types through a unified API and automatically processes Stripe webhook events to keep subscriptions up-to-date.

## Database Schema

The database has been extended to include Stripe-related fields:

- **User Model**: 
  - `stripe_customer_id`: Stripe customer ID for the user

- **Plan Model**:
  - `stripe_price_id`: Stripe price ID (used for subscriptions)
  - `stripe_product_id`: Stripe product ID

- **Subscription Model**:
  - `stripe_subscription_id`: Stripe subscription ID
  - `stripe_customer_id`: Stripe customer ID (duplicated for efficient lookup)
  - `status`: Subscription status (active, canceled, past_due, etc.)

## API Endpoints

### Add Credits

**Endpoint**: `POST /credits/add`

This endpoint now supports automatic detection of Stripe transaction IDs. If the `reference_id` parameter starts with a Stripe prefix (e.g., "pi_", "sub_"), the system will:

1. Verify the transaction with Stripe
2. Determine if it's a one-time payment or subscription
3. Process it accordingly

**Request Schema**:
```json
{
  "amount": 100.00,                // Required: Amount of credits to add
  "reference_id": "pi_1234567890", // Optional: Can be a Stripe transaction ID
  "description": "Credit purchase" // Optional: Description of the transaction
}
```

**Response Schema**:
```json
{
  "id": 123,
  "user_id": 456,
  "amount": 100.00,
  "transaction_type": "ONE_TIME_PURCHASE",
  "created_at": "2025-04-09T01:00:00Z",
  "new_balance": 500.00,
  "reference_id": "pi_1234567890",
  "description": "One-time purchase from Stripe: pi_1234567890"
}
```

### Add Credits from Stripe Transaction

**Endpoint**: `POST /credits/stripe/add`

This endpoint receives a request containing either:
- A Stripe transaction ID, or
- A customer email address

Based on the provided information, it:
1. Looks up the transaction in Stripe
2. Analyzes the transaction to determine its type (subscription or one-time purchase)
3. Adds the appropriate credits to the user's account
4. Returns the transaction details and updated credit balance

**Request Schema**:
```json
{
  "transaction_id": "pi_1234567890",  // Optional: Stripe transaction ID
  "email": "customer@example.com",    // Optional: Customer email (if transaction_id not provided)
  "transaction_type": "oneoff",       // Required: "oneoff" or "subscription"
  "metadata": {}                      // Optional: Additional metadata
}
```

**Response Schema**:
```json
{
  "applied": true,
  "transaction": {
    "transaction_id": "pi_1234567890",
    "transaction_type": "oneoff",
    "amount": 29.99,
    "customer_id": "cus_1234567890",
    "customer_email": "customer@example.com",
    "created_at": "2025-02-28T22:05:42Z"
  },
  "credit_transaction_id": 123,
  "new_balance": 500.00
}
```

### Webhook Handler

**Endpoint**: `POST /webhook/stripe`

This endpoint receives webhook events from Stripe and processes them based on event type:

- `invoice.payment_succeeded`: Handles subscription renewals
- `customer.subscription.updated`: Updates subscription status
- `payment_intent.succeeded`: Processes one-time payments

The webhook handler verifies the Stripe signature to ensure the request is legitimate before processing.

## Transaction Handling System

The system now includes a comprehensive transaction handling system that differentiates between one-time payments and subscriptions:

### One-time Payment Handling

1. **Transaction Verification**: The system verifies that the transaction ID exists in Stripe and is in a valid state (succeeded or processing).
2. **Duplicate Prevention**: Checks if the transaction has already been processed to prevent duplicate credits.
3. **Credit Calculation**: Calculates the appropriate number of credits based on the payment amount.
4. **Credit Addition**: Adds the calculated credits to the user's account.
5. **Logging**: Logs all steps of the process with appropriate log levels.

### Subscription Handling

1. **Subscription Verification**: Verifies that the subscription exists in Stripe and is in an active state.
2. **Existing Subscription Check**: Checks if the user already has an active subscription.
3. **Subscription Cancellation**: If an active subscription exists, it is cancelled through the Stripe API.
4. **New Subscription Registration**: Registers the new subscription in the system.
5. **Credit Addition**: Adds the appropriate credits to the user's account based on the plan.
6. **Logging**: Logs all steps of the process with appropriate log levels.

## Transaction Flow

### One-time Purchase Flow

1. Customer makes a payment through Stripe checkout
2. Frontend calls `/credits/add` with the payment intent ID as the reference_id
3. Backend detects the Stripe payment intent ID and verifies the transaction in Stripe
4. Backend checks if the transaction has already been processed
5. Credits are calculated based on plan ratios (explained below)
6. Credits are added to the user's account
7. Confirmation email is sent to the user
8. User can immediately use the new credits

### Subscription Flow

1. Customer subscribes to a plan through Stripe checkout
2. Frontend calls `/credits/add` with the subscription ID as the reference_id
3. Backend detects the Stripe subscription ID and verifies the subscription in Stripe
4. Backend checks if the user already has an active subscription
5. If an active subscription exists, it is cancelled through the Stripe API
6. A new subscription record is created in our database
7. Credits are added to the user's account based on the plan
8. Confirmation email is sent to the user
9. When the subscription renews:
   - Stripe sends an `invoice.payment_succeeded` webhook event
   - Our webhook handler processes the event
   - Additional credits are added to the user's account
   - Renewal confirmation email is sent to the user

## Webhook Processing

The webhook handler follows these steps for each event:

1. Verifies the Stripe signature using `STRIPE_WEBHOOK_SECRET`
2. Extracts event data and determines the event type
3. Processes the event based on its type:
   
   - For `invoice.payment_succeeded`:
     - Find the associated subscription in our database
     - If found, add credits to the user's account
     - Update the subscription's renewal date
   
   - For `customer.subscription.updated`:
     - Find the associated subscription in our database
     - Update its status (active, canceled, past_due, etc.)
     - If status changed to inactive, handle accordingly
   
   - For `payment_intent.succeeded`:
     - Analyze the payment to determine if it's a one-time purchase
     - If so, add credits to the user's account
     - Send confirmation email

## Configuration

The following environment variables are used for Stripe configuration:

- `STRIPE_SECRET_KEY`: Your Stripe API secret key
- `STRIPE_WEBHOOK_SECRET`: Secret for validating webhook signatures
- `STRIPE_API_VERSION`: Stripe API version (default: "2023-10-16")

## Error Handling

The integration includes comprehensive error handling:

- Transaction not found: Returns 404 Not Found
- Transaction already processed: Returns 400 Bad Request
- Transaction verification failed: Returns 400 Bad Request
- Transaction type mismatch: Returns 400 Bad Request
- Subscription not active: Returns 400 Bad Request
- No matching plan found: Returns 404 Not Found
- Insufficient credits: Returns 400 Bad Request
- Invalid webhook signature: Returns 401 Unauthorized
- Server errors: Returns 500 Internal Server Error with details

All errors are properly logged with relevant context for troubleshooting, including:
- User ID
- Transaction ID
- Error details
- Operation type

## Credit Amount

### For Subscriptions
For subscription-based purchases, the credit amount is determined by the plan configuration in the database.

### For One-time Purchases
For one-time purchases, the credit amount is now directly passed from the frontend:

1. The frontend specifies exactly how many credits to add in the "amount" field
2. No calculation or conversion is performed in the backend
3. This provides a direct pass-through of the credit amount

The system uses the exact credit amount specified in the request, creating a transparent and predictable credit allocation system. This direct credit amount pass-through feature simplifies the integration between frontend and backend systems.

For example:
- If the frontend sends a request with "amount": 500, exactly 500 credits will be added
- The payment amount in Stripe and the credit amount can be different, allowing for flexible pricing models
- This approach gives the frontend complete control over credit allocation

## Testing

Use the provided test files to verify the integration:
- `tests/test_credit_service.py`: Tests for the credit service, including transaction handling
- `tests/test_stripe_integration.py`: Tests for the Stripe service and credit endpoints
- `tests/test_stripe_webhook.py`: Tests for webhook handling

The tests include scenarios for:
- Verifying and processing valid one-time payments
- Handling already processed transactions
- Handling failed transaction verifications
- Verifying and processing valid subscriptions
- Handling users with existing subscriptions
- Cancelling subscriptions