"""Async wrappers for Stripe API calls to prevent blocking the event loop."""

import asyncio
from typing import Any, Optional, Dict
from functools import wraps

import stripe

from app.core.config import settings
from app.log.logging import logger

# Initialize Stripe configuration
stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


async def run_stripe_async(func, *args, **kwargs) -> Any:
    """
    Run a synchronous Stripe API call in a thread pool to avoid blocking.

    Args:
        func: The Stripe API function to call
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result from the Stripe API call

    Raises:
        stripe.error.StripeError: If the Stripe API call fails
    """
    try:
        result = await asyncio.to_thread(func, *args, **kwargs)
        return result
    except stripe.error.StripeError as e:
        logger.error(
            "Stripe API error",
            event_type="stripe_api_error",
            error_type=type(e).__name__,
            error_code=getattr(e, 'code', None),
            error_message=str(e),
        )
        raise


class AsyncStripeCustomer:
    """Async wrapper for Stripe Customer operations."""

    @staticmethod
    async def create(**params) -> stripe.Customer:
        """Create a new Stripe customer."""
        return await run_stripe_async(stripe.Customer.create, **params)

    @staticmethod
    async def retrieve(customer_id: str, **params) -> stripe.Customer:
        """Retrieve a Stripe customer by ID."""
        return await run_stripe_async(stripe.Customer.retrieve, customer_id, **params)

    @staticmethod
    async def modify(customer_id: str, **params) -> stripe.Customer:
        """Modify a Stripe customer."""
        return await run_stripe_async(stripe.Customer.modify, customer_id, **params)

    @staticmethod
    async def delete(customer_id: str) -> stripe.Customer:
        """Delete a Stripe customer."""
        return await run_stripe_async(stripe.Customer.delete, customer_id)

    @staticmethod
    async def list(**params) -> stripe.ListObject:
        """List Stripe customers."""
        return await run_stripe_async(stripe.Customer.list, **params)


class AsyncStripeSubscription:
    """Async wrapper for Stripe Subscription operations."""

    @staticmethod
    async def create(**params) -> stripe.Subscription:
        """Create a new Stripe subscription."""
        return await run_stripe_async(stripe.Subscription.create, **params)

    @staticmethod
    async def retrieve(subscription_id: str, **params) -> stripe.Subscription:
        """Retrieve a Stripe subscription by ID."""
        return await run_stripe_async(stripe.Subscription.retrieve, subscription_id, **params)

    @staticmethod
    async def modify(subscription_id: str, **params) -> stripe.Subscription:
        """Modify a Stripe subscription."""
        return await run_stripe_async(stripe.Subscription.modify, subscription_id, **params)

    @staticmethod
    async def cancel(subscription_id: str, **params) -> stripe.Subscription:
        """Cancel a Stripe subscription."""
        return await run_stripe_async(stripe.Subscription.cancel, subscription_id, **params)

    @staticmethod
    async def list(**params) -> stripe.ListObject:
        """List Stripe subscriptions."""
        return await run_stripe_async(stripe.Subscription.list, **params)


class AsyncStripePaymentIntent:
    """Async wrapper for Stripe PaymentIntent operations."""

    @staticmethod
    async def create(**params) -> stripe.PaymentIntent:
        """Create a new PaymentIntent."""
        return await run_stripe_async(stripe.PaymentIntent.create, **params)

    @staticmethod
    async def retrieve(payment_intent_id: str, **params) -> stripe.PaymentIntent:
        """Retrieve a PaymentIntent by ID."""
        return await run_stripe_async(stripe.PaymentIntent.retrieve, payment_intent_id, **params)

    @staticmethod
    async def confirm(payment_intent_id: str, **params) -> stripe.PaymentIntent:
        """Confirm a PaymentIntent."""
        return await run_stripe_async(stripe.PaymentIntent.confirm, payment_intent_id, **params)

    @staticmethod
    async def cancel(payment_intent_id: str, **params) -> stripe.PaymentIntent:
        """Cancel a PaymentIntent."""
        return await run_stripe_async(stripe.PaymentIntent.cancel, payment_intent_id, **params)


class AsyncStripeInvoice:
    """Async wrapper for Stripe Invoice operations."""

    @staticmethod
    async def retrieve(invoice_id: str, **params) -> stripe.Invoice:
        """Retrieve an invoice by ID."""
        return await run_stripe_async(stripe.Invoice.retrieve, invoice_id, **params)

    @staticmethod
    async def list(**params) -> stripe.ListObject:
        """List invoices."""
        return await run_stripe_async(stripe.Invoice.list, **params)


class AsyncStripeSetupIntent:
    """Async wrapper for Stripe SetupIntent operations."""

    @staticmethod
    async def create(**params) -> stripe.SetupIntent:
        """Create a new SetupIntent."""
        return await run_stripe_async(stripe.SetupIntent.create, **params)

    @staticmethod
    async def retrieve(setup_intent_id: str, **params) -> stripe.SetupIntent:
        """Retrieve a SetupIntent by ID."""
        return await run_stripe_async(stripe.SetupIntent.retrieve, setup_intent_id, **params)

    @staticmethod
    async def confirm(setup_intent_id: str, **params) -> stripe.SetupIntent:
        """Confirm a SetupIntent."""
        return await run_stripe_async(stripe.SetupIntent.confirm, setup_intent_id, **params)

    @staticmethod
    async def cancel(setup_intent_id: str, **params) -> stripe.SetupIntent:
        """Cancel a SetupIntent."""
        return await run_stripe_async(stripe.SetupIntent.cancel, setup_intent_id, **params)


class AsyncStripePaymentMethod:
    """Async wrapper for Stripe PaymentMethod operations."""

    @staticmethod
    async def create(**params) -> stripe.PaymentMethod:
        """Create a new PaymentMethod."""
        return await run_stripe_async(stripe.PaymentMethod.create, **params)

    @staticmethod
    async def retrieve(payment_method_id: str, **params) -> stripe.PaymentMethod:
        """Retrieve a PaymentMethod by ID."""
        return await run_stripe_async(stripe.PaymentMethod.retrieve, payment_method_id, **params)

    @staticmethod
    async def attach(payment_method_id: str, **params) -> stripe.PaymentMethod:
        """Attach a PaymentMethod to a Customer."""
        return await run_stripe_async(stripe.PaymentMethod.attach, payment_method_id, **params)

    @staticmethod
    async def detach(payment_method_id: str) -> stripe.PaymentMethod:
        """Detach a PaymentMethod from a Customer."""
        return await run_stripe_async(stripe.PaymentMethod.detach, payment_method_id)

    @staticmethod
    async def list(**params) -> stripe.ListObject:
        """List PaymentMethods."""
        return await run_stripe_async(stripe.PaymentMethod.list, **params)


class AsyncStripeWebhook:
    """Async wrapper for Stripe Webhook operations."""

    @staticmethod
    async def construct_event(payload: bytes, sig_header: str, webhook_secret: str) -> stripe.Event:
        """Construct a Stripe event from webhook payload."""
        # This is CPU-bound, so we run it in a thread
        return await run_stripe_async(
            stripe.Webhook.construct_event,
            payload,
            sig_header,
            webhook_secret
        )


class AsyncStripeCheckoutSession:
    """Async wrapper for Stripe Checkout Session operations."""

    @staticmethod
    async def create(**params) -> stripe.checkout.Session:
        """Create a new Checkout Session."""
        return await run_stripe_async(stripe.checkout.Session.create, **params)

    @staticmethod
    async def retrieve(session_id: str, **params) -> stripe.checkout.Session:
        """Retrieve a Checkout Session by ID."""
        return await run_stripe_async(stripe.checkout.Session.retrieve, session_id, **params)


# Convenience aliases
Customer = AsyncStripeCustomer
Subscription = AsyncStripeSubscription
PaymentIntent = AsyncStripePaymentIntent
Invoice = AsyncStripeInvoice
SetupIntent = AsyncStripeSetupIntent
PaymentMethod = AsyncStripePaymentMethod
Webhook = AsyncStripeWebhook
CheckoutSession = AsyncStripeCheckoutSession
