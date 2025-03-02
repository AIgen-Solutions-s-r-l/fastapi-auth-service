"""Router for Stripe webhook endpoints."""

import json
import stripe
from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal

from app.core.database import get_db
from app.core.config import settings
from app.log.logging import logger
from app.services.credit_service import CreditService
from app.services.stripe_service import StripeService

router = APIRouter(prefix="/webhook", tags=["webhook"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook_handler(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle Stripe webhook events.
    
    This endpoint receives webhook events from Stripe and processes them based on event type.
    Supported events include:
    - invoice.payment_succeeded: Handle subscription renewals
    - customer.subscription.updated: Update subscription status
    - payment_intent.succeeded: Process one-time payments
    
    Args:
        request: FastAPI request object containing the Stripe webhook payload
        background_tasks: FastAPI background tasks for async operations
        db: Database session
        
    Returns:
        Status and processing information
        
    Raises:
        HTTPException: If the webhook signature is invalid or an error occurs
    """
    try:
        # Get the Stripe signature from headers
        stripe_signature = request.headers.get("Stripe-Signature")
        if not stripe_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stripe signature missing"
            )
            
        # Get the raw payload
        payload = await request.body()
        payload_str = payload.decode('utf-8')
        
        # Verify and construct the event
        try:
            event = stripe.Webhook.construct_event(
                payload=payload_str,
                sig_header=stripe_signature,
                secret=settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError as e:
            # Invalid payload
            logger.error(f"Invalid Stripe webhook payload: {str(e)}",
                      event_type="stripe_webhook_error",
                      error=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payload: {str(e)}"
            )
        except stripe.error.SignatureVerificationError as e:
            # Invalid signature
            logger.error(f"Invalid Stripe signature: {str(e)}",
                      event_type="stripe_webhook_error",
                      error=str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid signature: {str(e)}"
            )
            
        # Log the event
        logger.info(f"Received Stripe webhook event: {event['type']}",
                  event_type="stripe_webhook_received",
                  stripe_event_type=event['type'],
                  stripe_event_id=event['id'])
                  
        # Initialize services
        credit_service = CreditService(db)
        stripe_service = StripeService()
        
        # Process based on event type
        event_type = event['type']
        event_data = event['data']['object']
        
        # Track processing
        processed = False
        processing_result = None
        
        if event_type == 'invoice.payment_succeeded':
            # Handle subscription renewal
            subscription_id = event_data.get('subscription')
            if subscription_id:
                # Find the subscription in our system
                subscription = await credit_service.get_subscription_by_stripe_id(subscription_id)
                if subscription:
                    # Renew the subscription
                    transaction, updated_subscription = await credit_service.renew_subscription(
                        subscription_id=subscription.id,
                        background_tasks=background_tasks
                    )
                    
                    processed = True
                    processing_result = {
                        "subscription_id": subscription.id,
                        "transaction_id": transaction.id if transaction else None,
                        "credits_added": transaction.amount if transaction else None
                    }
                    
                    logger.info(f"Processed subscription renewal from webhook",
                              event_type="stripe_webhook_renewal_processed",
                              subscription_id=subscription.id,
                              stripe_subscription_id=subscription_id,
                              transaction_id=transaction.id if transaction else None)
                else:
                    logger.warning(f"Subscription not found in our system: {subscription_id}",
                                 event_type="stripe_webhook_subscription_not_found",
                                 stripe_subscription_id=subscription_id)
            
        elif event_type == 'customer.subscription.updated':
            # Handle subscription status update
            subscription_id = event_data.get('id')
            customer_id = event_data.get('customer')
            status_value = event_data.get('status')
            
            if subscription_id and status_value:
                # Update subscription status
                await credit_service.update_subscription_status(
                    stripe_subscription_id=subscription_id,
                    status=status_value
                )
                
                # If customer exists in our system, log the update
                user = await credit_service.get_user_by_stripe_customer_id(customer_id)
                if user:
                    processed = True
                    processing_result = {
                        "user_id": user.id,
                        "subscription_id": subscription_id,
                        "status": status_value
                    }
                    
                    logger.info(f"Updated subscription status from webhook",
                              event_type="stripe_webhook_subscription_updated",
                              user_id=user.id,
                              stripe_subscription_id=subscription_id,
                              status=status_value)
                else:
                    logger.warning(f"Customer not found in our system: {customer_id}",
                                 event_type="stripe_webhook_customer_not_found",
                                 stripe_customer_id=customer_id)
            
        elif event_type == 'payment_intent.succeeded':
            # Handle one-time payment
            payment_intent_id = event_data.get('id')
            customer_id = event_data.get('customer')
            
            if payment_intent_id and customer_id:
                # Get user by Stripe customer ID
                user = await credit_service.get_user_by_stripe_customer_id(customer_id)
                if user:
                    # Analyze the transaction
                    transaction_data = stripe_service._format_transaction(event_data)
                    analysis = await stripe_service.analyze_transaction(transaction_data)
                    
                    # Process one-time purchase
                    if analysis["transaction_type"] == "oneoff":
                        # Get the payment amount
                        payment_amount = analysis["amount"]
                        
                        # Get plans to calculate credit-to-price ratio
                        plans = await credit_service.get_all_active_plans()
                        credit_amount = None
                        
                        if plans:
                            # Find plans with similar prices
                            similar_plans = sorted(plans, key=lambda p: abs(p.price - payment_amount))
                            
                            if similar_plans:
                                # Use the most similar plan's credit-to-price ratio to calculate credits
                                best_match = similar_plans[0]
                                ratio = best_match.credit_amount / best_match.price
                                credit_amount = payment_amount * ratio
                                
                                logger.info(f"Calculated webhook credits using plan-based ratio",
                                          event_type="webhook_credit_calculation",
                                          payment_amount=float(payment_amount),
                                          similar_plan_id=best_match.id,
                                          ratio=float(ratio),
                                          credit_amount=float(credit_amount))
                        
                        # Fallback if no plans found or calculation resulted in zero credits
                        if not credit_amount or credit_amount <= 0:
                            # Use a default ratio as fallback (e.g., $1 = 10 credits)
                            credit_amount = payment_amount * Decimal('10')
                            logger.warning(f"Using fallback credit calculation in webhook",
                                         event_type="webhook_credit_calculation_fallback",
                                         payment_amount=float(payment_amount),
                                         credit_amount=float(credit_amount))
                        
                        # Add credits
                        transaction = await credit_service.purchase_one_time_credits(
                            user_id=user.id,
                            amount=credit_amount,
                            price=payment_amount,
                            reference_id=payment_intent_id,
                            description=f"One-time purchase from Stripe webhook: {payment_intent_id}",
                            background_tasks=background_tasks
                        )
                        
                        processed = True
                        processing_result = {
                            "user_id": user.id,
                            "transaction_id": transaction.id,
                            "credits_added": credit_amount,
                            "payment_intent_id": payment_intent_id
                        }
                        
                        logger.info(f"Processed one-time payment from webhook",
                                  event_type="stripe_webhook_payment_processed",
                                  user_id=user.id,
                                  payment_intent_id=payment_intent_id,
                                  credits_added=credit_amount,
                                  transaction_id=transaction.id)
                    else:
                        logger.info(f"Payment intent not processed as one-off payment: {payment_intent_id}",
                                  event_type="stripe_webhook_payment_not_oneoff",
                                  payment_intent_id=payment_intent_id,
                                  transaction_type=analysis["transaction_type"])
                else:
                    logger.warning(f"Customer not found in our system: {customer_id}",
                                 event_type="stripe_webhook_customer_not_found",
                                 stripe_customer_id=customer_id)
        
        # Return response
        return {
            "status": "success",
            "event_id": event['id'],
            "event_type": event_type,
            "processed": processed,
            "result": processing_result
        }
        
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {str(e)}",
                   event_type="stripe_webhook_error",
                   error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error processing webhook: {str(e)}"
        )