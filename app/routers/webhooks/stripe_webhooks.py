import stripe
from fastapi import APIRouter, Request, HTTPException, Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.log.logging import logger
from app.services.webhook_service import WebhookService # New import
# from app.services.stripe_service import StripeService
# from app.services.user_service import UserService
# from app.services.credit_service import CreditService

router = APIRouter()

# Ensure Stripe API key and webhook secret are set
if not settings.STRIPE_SECRET_KEY:
    logger.critical("STRIPE_SECRET_KEY not set in environment variables.")
    # Potentially raise an error or exit if this is critical at startup
if not settings.STRIPE_WEBHOOK_SECRET:
    logger.critical("STRIPE_WEBHOOK_SECRET not set in environment variables.")
    # Potentially raise an error or exit

stripe.api_key = settings.STRIPE_SECRET_KEY


async def verify_stripe_signature(
    request: Request,
    stripe_signature: str = Header(None) # Stripe-Signature
):
    """
    Verifies the Stripe webhook signature.
    Raises HTTPException 400 if signature is missing or invalid.
    """
    if not stripe_signature:
        logger.error("Stripe-Signature header missing from webhook request.")
        raise HTTPException(status_code=400, detail="Stripe-Signature header missing.")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("Stripe webhook secret is not configured on the server.")
        # This is a server-side configuration issue, so 500 might be more appropriate
        raise HTTPException(status_code=500, detail="Webhook secret not configured.")

    try:
        payload = await request.body()
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError as e:
        # Invalid payload
        logger.error(f"Invalid webhook payload: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        logger.error(f"Invalid Stripe webhook signature: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error verifying webhook signature: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during webhook signature verification: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error verifying webhook signature.")


# Dependency to provide WebhookService
def get_webhook_service(db: AsyncSession = Depends(get_db)) -> WebhookService:
    """Dependency to provide WebhookService instance."""
    return WebhookService(db)

@router.post("/stripe", summary="Handle Stripe Webhooks")
async def stripe_webhook_endpoint(
    event: stripe.Event = Depends(verify_stripe_signature),
    webhook_service: WebhookService = Depends(get_webhook_service)
):
    """
    Endpoint to receive and process Stripe webhooks.
    Signature is verified by the `verify_stripe_signature` dependency.
    """
    logger.info(
        f"Received Stripe event: ID={event.id}, Type={event.type}",
        event_id=event.id,
        event_type=event.type
    )

    # Idempotency check
    if await webhook_service.is_event_processed(event.id):
        logger.info(f"Event {event.id} ({event.type}) already processed. Skipping.", event_id=event.id, event_type=event.type)
        return {"status": "success", "message": f"Event {event.id} already processed."}

    # Dispatch event to specific handlers based on event.type
    try:
        if event.type == "checkout.session.completed":
            await webhook_service.handle_checkout_session_completed(event)
        elif event.type == "customer.subscription.created":
            await webhook_service.handle_customer_subscription_created(event)
        elif event.type == "customer.subscription.updated":
            await webhook_service.handle_customer_subscription_updated(event)
        elif event.type == "invoice.payment_succeeded":
            await webhook_service.handle_invoice_payment_succeeded(event)
        elif event.type == "invoice.payment_failed":
            await webhook_service.handle_invoice_payment_failed(event)
        else:
            logger.warning(f"Received unhandled event type: {event.type}", event_id=event.id, event_type=event.type)
            # Still mark as processed if we don't want retries for unhandled types
            await webhook_service.mark_event_as_processed(event.id, event.type)
            return {"status": "success", "message": f"Webhook received for unhandled event type: {event.type}"}

        # Mark event as processed after successful handling
        await webhook_service.mark_event_as_processed(event.id, event.type)
        logger.info(f"Successfully processed event: {event.id} ({event.type})", event_id=event.id, event_type=event.type)
        return {"status": "success", "message": f"Successfully processed event: {event.id} ({event.type})"}
    except HTTPException: # Re-raise HTTPExceptions from service layer
        raise
    except Exception as e: # Catch-all for unexpected errors in handlers
        logger.error(
            f"Error processing event {event.id} ({event.type}): {e}",
            event_id=event.id,
            event_type=event.type,
            exc_info=True
        )
        # Do NOT mark as processed here, so Stripe can retry for server-side errors
        raise HTTPException(status_code=500, detail=f"Error processing event {event.id} ({event.type}): {e}")

# Placeholder for actual event handler functions/methods
# These would typically reside in a service layer (e.g., StripeWebhookService)
# and be called from the endpoint.

# async def handle_checkout_session_completed(event: stripe.Event, db: AsyncSession):
#     # Logic from TASK-BE-20250506-173100_WebhookHandling.md
#     # - Retrieve PaymentMethod fingerprint
#     # - Call Fraud Gate service
#     # - ...
#     pass

# async def handle_customer_subscription_created(event: stripe.Event, db: AsyncSession):
#     # Logic from TASK-BE-20250506-173100_WebhookHandling.md
#     # - Grant credits
#     # - Update User.has_consumed_initial_trial
#     # - Update User.account_status
#     # - Publish event
#     # - Store card fingerprint
#     pass

# async def handle_customer_subscription_updated(event: stripe.Event, db: AsyncSession):
#     # Logic from TASK-BE-20250506-173100_WebhookHandling.md
#     # - Update Subscription and User.account_status
#     # - Publish events
#     pass

# async def handle_invoice_payment_succeeded(event: stripe.Event, db: AsyncSession):
#     # Logic from TASK-BE-20250506-173100_WebhookHandling.md
#     # - Update User.account_status
#     # - Publish event
#     pass

# async def handle_invoice_payment_failed(event: stripe.Event, db: AsyncSession):
#     # Logic from TASK-BE-20250506-173100_WebhookHandling.md
#     # - Update User.account_status
#     # - Publish event
#     pass