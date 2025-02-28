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

## Transaction Flow

### One-time Purchase Flow

1. Customer makes a payment through Stripe checkout
2. Frontend calls `/credits/stripe/add` with the payment intent ID
3. Backend verifies the transaction in Stripe
4. Credits are calculated based on plan ratios (explained below)
5. Confirmation email is sent to the user
6. User can immediately use the new credits

### Subscription Flow

1. Customer subscribes to a plan through Stripe checkout
2. Frontend calls `/credits/stripe/add` with the subscription ID
3. Backend verifies the subscription in Stripe
4. Credits are added to the user's account based on the plan
5. A subscription record is created/updated in our database
6. Confirmation email is sent to the user
7. When the subscription renews:
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
- Transaction type mismatch: Returns 400 Bad Request
- Insufficient credits: Returns 400 Bad Request
- Invalid webhook signature: Returns 401 Unauthorized
- Server errors: Returns 500 Internal Server Error with details

All errors are properly logged with relevant context for troubleshooting.

## Credit Calculation

### For Subscriptions
For subscription-based purchases, the credit amount is determined by the plan configuration in the database.

### For One-time Purchases
One-time purchases use a dynamic credit calculation approach:

1. Find plans with similar prices to the payment amount
2. Use the credit-to-price ratio from the most similar plan
3. Calculate credits = payment amount × ratio

For example, if:
- Plan A costs $10 and provides 120 credits (ratio = 12)
- Plan B costs $50 and provides 700 credits (ratio = 14)
- Customer pays $30

The system would use the ratio from Plan B (as it's closer to $30 than Plan A), resulting in $30 × 14 = 420 credits.

If no similar plans are found, the system falls back to a default ratio as a safety measure.

## Testing

Use the provided test files to verify the integration:
- `tests/test_stripe_integration.py`: Tests for the Stripe service and credit endpoints
- `tests/test_stripe_webhook.py`: Tests for webhook handling