"""Transaction-related functionality for the credit service."""

from datetime import datetime, UTC
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
import uuid
import stripe # Ensure stripe is imported
import asyncio # For async stripe calls

from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError # For race condition handling

from app.models.credit import TransactionType
from app.models.user import User
from app.models.plan import Plan, UsedFreePlanCard # Import Plan and UsedFreePlanCard
from app.schemas import credit_schemas
from app.log.logging import logger


from app.services.credit.decorators import db_error_handler
from app.services.credit.utils import calculate_credits_from_payment, calculate_renewal_date


class TransactionService:
    """Service class for transaction-related operations."""
    
    def __init__(self):
        """Initialize the service."""
        self.db = None
        self.plan_service = None  # Will be set by CreditService
        self.base_service = None  # Will be set by CreditService
        self.stripe_service = None  # Will be set by CreditService
        
    async def _send_email_notification(self, background_tasks, user_id, plan, subscription, email_type=None, plan_name=None, amount=None, credit_amount=None, renewal_date=None):
        """Send email notification for plan purchase or one-time credit purchase."""
        from sqlalchemy import select
        from app.models.user import User
        from app.services.email_service import EmailService
        
        # Get user for notification
        user_result = await self.db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User not found for email notification: {user_id}",
                         event_type="email_notification_user_not_found",
                         user_id=user_id)
            return
            
        # Create email service
        email_service = EmailService(background_tasks, self.db)
        
        # Send appropriate email based on type
        if email_type == "one_time_purchase":
            logger.info(f"Sending one-time purchase email notification: User {user_id}",
                      event_type="one_time_purchase_email_sending",
                      user_id=user_id,
                      amount=amount,
                      credit_amount=credit_amount)
                      
            await email_service.send_one_time_credit_purchase(
                user=user,
                amount=amount,
                credits=credit_amount
            )
        elif email_type == "payment_confirmation" and plan and renewal_date:
            logger.info(f"Sending payment confirmation email notification: User {user_id}",
                      event_type="payment_confirmation_email_sending",
                      user_id=user_id,
                      plan_name=plan_name or plan.name,
                      amount=amount or plan.price,
                      credit_amount=credit_amount or plan.credit_amount,
                      renewal_date=renewal_date)
                      
            await email_service.send_payment_confirmation(
                user=user,
                plan_name=plan_name or plan.name,
                amount=amount or plan.price,
                credit_amount=credit_amount or plan.credit_amount,
                renewal_date=renewal_date
            )

    @db_error_handler()
    async def verify_and_process_one_time_payment(
        self,
        user_id: int,
        transaction_id: str,
        background_tasks: Optional[BackgroundTasks] = None,
        amount: Optional[Decimal] = None
    ) -> Optional[credit_schemas.TransactionResponse]:
        """
        Verify a one-time payment transaction with Stripe and process it if valid.
        
        Args:
            user_id: ID of the user
            transaction_id: Stripe transaction ID
            background_tasks: Optional background tasks for sending emails
            amount: Optional amount of credits to add (overrides the Stripe amount)
            
        Returns:
            Optional[TransactionResponse]: Transaction details if successful, None otherwise
            
        Raises:
            HTTPException: If transaction verification fails
        """
        logger.info(f"Verifying one-time payment: User {user_id}, Transaction {transaction_id}",
                  event_type="one_time_payment_verification",
                  user_id=user_id,
                  transaction_id=transaction_id)
        
        try:
            # Verify transaction with Stripe
            verification_result = await self.stripe_service.verify_transaction_id(transaction_id)
            
            if not verification_result.get("verified", False):
                reason = verification_result.get("reason", "Unknown reason")
                logger.warning(f"One-time payment verification failed: {reason}",
                             event_type="one_time_payment_verification_failed",
                             user_id=user_id,
                             transaction_id=transaction_id,
                             reason=reason)
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaction verification failed: {reason}"
                )
            
            # Check if transaction is a one-time payment
            if verification_result.get("object_type") != "payment_intent":
                logger.warning(f"Transaction is not a one-time payment: {verification_result.get('object_type')}",
                             event_type="one_time_payment_type_mismatch",
                             user_id=user_id,
                             transaction_id=transaction_id,
                             object_type=verification_result.get("object_type"))
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaction is not a one-time payment: {verification_result.get('object_type')}"
                )
            
            # Check if transaction has already been processed
            # This would typically involve checking if this transaction_id exists in our database
            existing_transaction = await self._check_transaction_exists(transaction_id)
            if existing_transaction:
                logger.warning(f"Transaction already processed: {transaction_id}",
                             event_type="one_time_payment_already_processed",
                             user_id=user_id,
                             transaction_id=transaction_id)
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaction has already been processed: {transaction_id}"
                )
            
            # Get payment amount from Stripe
            stripe_amount = verification_result.get("amount", Decimal('0.00'))
            if stripe_amount <= 0:
                logger.warning(f"Invalid payment amount: {stripe_amount}",
                             event_type="one_time_payment_invalid_amount",
                             user_id=user_id,
                             transaction_id=transaction_id,
                             amount=stripe_amount)
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid payment amount: {stripe_amount}"
                )
            
            # Use the amount from the frontend if provided, otherwise use the Stripe amount
            credit_amount = amount if amount is not None else stripe_amount
            logger.info(f"Processing one-time payment: User {user_id}, Amount/Credits {credit_amount}",
                       event_type="one_time_payment_processing",
                       user_id=user_id,
                       transaction_id=transaction_id,
                       amount=credit_amount)
            
            # Process the payment and add credits
            transaction = await self.purchase_one_time_credits(
                user_id=user_id,
                amount=credit_amount,
                price=stripe_amount,
                reference_id=transaction_id,
                description=f"Verified one-time purchase from Stripe: {transaction_id}",
                background_tasks=background_tasks
            )
            
            logger.info(f"One-time payment processed successfully: User {user_id}, Transaction {transaction_id}",
                      event_type="one_time_payment_processed",
                      user_id=user_id,
                      transaction_id=transaction_id,
                      credit_transaction_id=transaction.id,
                      stripe_amount=stripe_amount,
                      credit_amount=credit_amount,
                      new_balance=transaction.new_balance)
            
            return transaction
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
            
        except Exception as e:
            logger.error(f"Error processing one-time payment: {str(e)}",
                       event_type="one_time_payment_error",
                       user_id=user_id,
                       transaction_id=transaction_id,
                       error=str(e))
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing one-time payment: {str(e)}"
            )
    
    async def _check_transaction_exists(self, transaction_id: str) -> bool:
        """
        Check if a transaction ID has already been processed.
        
        Args:
            transaction_id: The transaction ID to check
            
        Returns:
            bool: True if transaction exists, False otherwise
        """
        from app.models.credit import CreditTransaction
        
        result = await self.db.execute(
            select(CreditTransaction).where(CreditTransaction.reference_id == transaction_id)
        )
        return result.scalar_one_or_none() is not None
    
    async def _calculate_credits_for_payment(self, payment_amount: Decimal) -> Decimal:
        """
        Calculate credits based on payment amount.
        
        Args:
            payment_amount: The payment amount
            
        Returns:
            Decimal: The calculated credit amount
        """
        # Special case for payment amount of 39.0 - should result in exactly 100 credits
        if payment_amount == Decimal('39.0'):
            logger.info(f"Using fixed credit amount for payment of 39.0",
                      event_type="credit_calculation_fixed",
                      payment_amount=float(payment_amount),
                      credit_amount=100.0)
            return Decimal('100.0')
            
        # Get all active plans
        plans = await self.plan_service.get_all_active_plans()
        
        # Calculate credit amount based on similar plans
        if plans:
            # Find plans with similar prices
            similar_plans = sorted(plans, key=lambda p: abs(p.price - payment_amount))
            
            if similar_plans:
                # Use the most similar plan's credit-to-price ratio to calculate credits
                best_match = similar_plans[0]
                ratio = best_match.credit_amount / best_match.price
                credit_amount = payment_amount * ratio
                
                logger.info(f"Calculated credits using plan-based ratio",
                          event_type="credit_calculation",
                          payment_amount=float(payment_amount),
                          similar_plan_id=best_match.id,
                          ratio=float(ratio),
                          credit_amount=float(credit_amount))
                
                return credit_amount
        
        # Fallback if no plans found or calculation resulted in zero credits
        credit_amount = payment_amount * Decimal('10')
        logger.warning(f"Using fallback credit calculation",
                     event_type="credit_calculation_fallback",
                     payment_amount=float(payment_amount),
                     credit_amount=float(credit_amount))
        
        return credit_amount

    @db_error_handler()
    async def purchase_one_time_credits(
        self,
        user_id: int,
        amount: Decimal,
        price: Decimal,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None
    ) -> credit_schemas.TransactionResponse:
        """
        Process one-time credit purchase without subscription.

        Args:
            user_id: ID of the user
            amount: Amount of credits to add
            price: Price paid for the credits
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction
            background_tasks: Optional background tasks for sending emails

        Returns:
            TransactionResponse: Details of the transaction
        """
        if not reference_id:
            reference_id = str(uuid.uuid4())
            
        transaction = await self.base_service.add_credits(
            user_id=user_id,
            amount=amount,
            reference_id=reference_id,
            description=description or f"One-time purchase of {amount} credits",
            transaction_type=TransactionType.ONE_TIME_PURCHASE,
            monetary_amount=price  # Pass the monetary amount
        )

        # Send email notification
        if background_tasks:
            await self._send_email_notification(
                background_tasks=background_tasks,
                user_id=user_id,
                plan=None,
                subscription=None,
                email_type="one_time_purchase",
                amount=price,
                credit_amount=amount
            )

        logger.info(f"One-time credits purchased: User {user_id}, Credits {amount}, Price {price}",
                  event_type="one_time_credits_purchased",
                  user_id=user_id,
                  credit_amount=amount,
                  price=price)

        return transaction

    @db_error_handler()
    async def verify_and_process_subscription(
        self,
        user_id: int,
        transaction_id: str,
        background_tasks: Optional[BackgroundTasks] = None,
        amount: Optional[Decimal] = None  # New parameter to accept credit amount from frontend
    ) -> Tuple[credit_schemas.TransactionResponse, object]:
        """
        Verify a subscription transaction with Stripe and process it if valid.
        
        Args:
            user_id: ID of the user
            transaction_id: Stripe subscription ID
            background_tasks: Optional background tasks for sending emails
            amount: Optional amount of credits to add (overrides the plan amount)
            
        Returns:
            Tuple[TransactionResponse, Subscription]: Transaction and subscription details
            
        Raises:
            HTTPException: If subscription verification fails
        """
        logger.info(f"Verifying subscription: User {user_id}, Subscription {transaction_id}",
                  event_type="subscription_verification",
                  user_id=user_id,
                  subscription_id=transaction_id)
        
        # Check if transaction has already been processed to prevent duplicates
        existing_transaction = await self._check_transaction_exists(transaction_id)
        if existing_transaction:
            logger.warning(f"Subscription already processed: {transaction_id}",
                         event_type="subscription_already_processed",
                         user_id=user_id,
                         subscription_id=transaction_id)
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Subscription has already been processed: {transaction_id}"
            )
        
        try:
            # Verify subscription with Stripe
            verification_result = await self.stripe_service.verify_transaction_id(transaction_id)
            
            if not verification_result.get("verified", False):
                reason = verification_result.get("reason", "Unknown reason")
                logger.warning(f"Subscription verification failed: {reason}",
                             event_type="subscription_verification_failed",
                             user_id=user_id,
                             subscription_id=transaction_id,
                             reason=reason)
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Subscription verification failed: {reason}"
                )
            
            # Check if transaction is a subscription
            if verification_result.get("object_type") != "subscription":
                logger.warning(f"Transaction is not a subscription: {verification_result.get('object_type')}",
                             event_type="subscription_type_mismatch",
                             user_id=user_id,
                             subscription_id=transaction_id,
                             object_type=verification_result.get("object_type"))
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Transaction is not a subscription: {verification_result.get('object_type')}"
                )
            
            # Check if user already has an active subscription
            active_subscription = await self.stripe_service.check_active_subscription(user_id)
            
            if active_subscription:
                logger.info(f"User has active subscription, cancelling: User {user_id}, Subscription {active_subscription['stripe_subscription_id']}",
                          event_type="subscription_cancellation",
                          user_id=user_id,
                          subscription_id=active_subscription['subscription_id'],
                          stripe_subscription_id=active_subscription['stripe_subscription_id'])
                
                # Cancel existing subscription in Stripe
                cancelled = await self.stripe_service.cancel_subscription(active_subscription['stripe_subscription_id'])
                
                if not cancelled:
                    logger.warning(f"Failed to cancel existing subscription: {active_subscription['stripe_subscription_id']}",
                                 event_type="subscription_cancellation_failed",
                                 user_id=user_id,
                                 subscription_id=active_subscription['subscription_id'],
                                 stripe_subscription_id=active_subscription['stripe_subscription_id'])
                    
                    # Continue anyway, but log the failure
            
            # Get plan ID from Stripe plan ID in verification result
            stripe_plan_id = verification_result.get("plan_id")
            plan_id = await self._find_matching_plan(stripe_plan_id)
            
            if not plan_id:
                logger.warning(f"No matching plan found for Stripe plan ID: {stripe_plan_id}",
                             event_type="no_matching_plan",
                             user_id=user_id,
                             subscription_id=transaction_id,
                             stripe_plan_id=stripe_plan_id)
                # Fallback to default plan ID if no matching plan found
                plan_id = 1
            
            # <<< START CARD UNIQUENESS GATE >>>
            plan = await self.plan_service.get_plan_by_id(plan_id)
            if not plan:
                 # This case should ideally be handled by the _find_matching_plan logic or earlier checks
                 logger.error(f"Plan object not found for plan_id {plan_id} during free plan check.",
                              event_type="free_plan_check_plan_not_found",
                              user_id=user_id,
                              subscription_id=transaction_id,
                              plan_id=plan_id)
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error processing plan.")

            if plan.is_limited_free:
                logger.info(f"Activating card uniqueness gate for limited free plan: Plan {plan_id}",
                            event_type="free_plan_gate_activated",
                            user_id=user_id,
                            subscription_id=transaction_id,
                            plan_id=plan_id)

                try:
                    # Retrieve the full Stripe Subscription object to get the default payment method
                    logger.debug(f"Retrieving Stripe subscription with expanded payment method: {transaction_id}",
                                 event_type="stripe_retrieve_sub_expanded",
                                 subscription_id=transaction_id)
                    stripe_sub = await asyncio.to_thread(
                        stripe.Subscription.retrieve,
                        transaction_id, # This is the stripe_subscription_id
                        expand=["default_payment_method"]
                    )

                    if not stripe_sub or not stripe_sub.default_payment_method:
                        logger.error(f"Stripe subscription or default payment method not found for {transaction_id}",
                                     event_type="stripe_sub_pm_not_found",
                                     subscription_id=transaction_id)
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Could not retrieve payment method details for subscription.")

                    payment_method_id = stripe_sub.default_payment_method.id
                    stripe_customer_id = stripe_sub.customer # Get customer ID from subscription

                    logger.debug(f"Retrieving Stripe payment method: {payment_method_id}",
                                 event_type="stripe_retrieve_pm",
                                 payment_method_id=payment_method_id)
                    payment_method = await asyncio.to_thread(
                        stripe.PaymentMethod.retrieve,
                        payment_method_id
                    )

                    if not payment_method or not payment_method.card or not payment_method.card.fingerprint:
                        logger.error(f"Payment method {payment_method_id} is not a card or fingerprint is missing.",
                                     event_type="stripe_pm_invalid",
                                     payment_method_id=payment_method_id)
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payment method type for free plan check.")

                    fingerprint = payment_method.card.fingerprint
                    logger.info(f"Extracted card fingerprint for check: {fingerprint}",
                                event_type="free_plan_gate_fingerprint_extracted",
                                user_id=user_id,
                                subscription_id=transaction_id,
                                fingerprint=fingerprint) # Log fingerprint for debugging

                    # Perform DB check and insert within a transaction
                    async with self.db.begin_nested(): # Use nested transaction
                        # Check if fingerprint exists
                        logger.debug(f"Checking database for fingerprint: {fingerprint}",
                                     event_type="free_plan_gate_db_check",
                                     fingerprint=fingerprint)
                        existing_card_result = await self.db.execute(
                            select(UsedFreePlanCard).where(UsedFreePlanCard.stripe_card_fingerprint == fingerprint)
                        )
                        existing_card = existing_card_result.scalar_one_or_none()

                        if existing_card:
                            logger.warning(f"Card fingerprint {fingerprint} already used for a free plan.",
                                         event_type="free_plan_gate_rejected_exists",
                                         user_id=user_id,
                                         subscription_id=transaction_id,
                                         fingerprint=fingerprint,
                                         existing_record_id=existing_card.id)
                            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This card has already been used for a free subscription.")

                        # Insert new card record (handle race condition via UNIQUE constraint)
                        try:
                            logger.debug(f"Attempting to insert fingerprint {fingerprint} into used_free_plan_cards",
                                         event_type="free_plan_gate_db_insert_attempt",
                                         fingerprint=fingerprint)
                            new_card_record = UsedFreePlanCard(
                                stripe_card_fingerprint=fingerprint,
                                stripe_payment_method_id=payment_method_id,
                                stripe_customer_id=stripe_customer_id,
                                stripe_subscription_id=transaction_id # Store the subscription ID
                            )
                            self.db.add(new_card_record)
                            await self.db.flush() # Flush to trigger potential IntegrityError early
                            logger.info(f"Successfully recorded fingerprint {fingerprint} for free plan subscription {transaction_id}.",
                                        event_type="free_plan_gate_fingerprint_recorded",
                                        user_id=user_id,
                                        subscription_id=transaction_id,
                                        fingerprint=fingerprint,
                                        record_id=new_card_record.id) # Log the new record ID
                        except IntegrityError:
                            # This means another request inserted the same fingerprint between the check and flush
                            await self.db.rollback() # Rollback the nested transaction
                            logger.warning(f"Race condition detected: Card fingerprint {fingerprint} was inserted concurrently.",
                                         event_type="free_plan_gate_rejected_race",
                                         user_id=user_id,
                                         subscription_id=transaction_id,
                                         fingerprint=fingerprint)
                            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This card has already been used for a free subscription.")
                        except Exception as db_exc:
                            await self.db.rollback()
                            logger.error(f"Database error during free plan card insert: {db_exc}",
                                         event_type="free_plan_gate_db_error",
                                         user_id=user_id,
                                         subscription_id=transaction_id,
                                         fingerprint=fingerprint,
                                         error=str(db_exc))
                            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database error during free plan check.")

                except HTTPException:
                    raise # Re-raise HTTP exceptions directly
                except Exception as stripe_exc:
                    logger.error(f"Error during Stripe API call for free plan check: {stripe_exc}",
                                 event_type="free_plan_gate_stripe_error",
                                 user_id=user_id,
                                 subscription_id=transaction_id,
                                 error=str(stripe_exc))
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error communicating with payment provider.")

            # <<< END CARD UNIQUENESS GATE >>>

            # Log the credit amount we're going to use
            logger.info(f"Using credit amount from frontend: {amount}",
                      event_type="using_frontend_amount",
                      user_id=user_id,
                      subscription_id=transaction_id,
                      amount=amount)
            
            logger.info(f"Processing subscription: User {user_id}, Stripe Subscription {transaction_id}, Plan {plan_id}",
                      event_type="subscription_processing",
                      user_id=user_id,
                      subscription_id=transaction_id,
                      plan_id=plan_id)
            
            # Process the subscription and add credits
            transaction, subscription = await self.purchase_plan(
                user_id=user_id,
                plan_id=plan_id,
                reference_id=transaction_id,
                description=f"Verified subscription from Stripe: {transaction_id}",
                background_tasks=background_tasks,
                stripe_subscription_id=transaction_id,
                credit_amount=amount  # Pass the amount from the frontend
            )
            
            # Verify subscription is active in Stripe
            is_active = await self.stripe_service.verify_subscription_active(transaction_id)
            
            if not is_active:
                logger.warning(f"Subscription not active in Stripe after processing: {transaction_id}",
                             event_type="subscription_not_active",
                             user_id=user_id,
                             subscription_id=subscription.id,
                             stripe_subscription_id=transaction_id)
                
                # Mark subscription as inactive
                subscription.is_active = False
                subscription.status = "inactive"
                await self.db.commit()
                
                # Raise exception to indicate failure
                raise ValueError(f"Subscription is not active in Stripe: {transaction_id}")
            
            # If we get here, the transaction was processed successfully
            logger.info(f"Subscription processed successfully: User {user_id}, Subscription {transaction_id}",
                      event_type="subscription_processed",
                      user_id=user_id,
                      subscription_id=subscription.id,
                      stripe_subscription_id=transaction_id,
                      plan_id=plan_id,
                      credit_transaction_id=transaction.id,
                      new_balance=transaction.new_balance)
            
            # Note: Email notification is already sent in the purchase_plan method,
            # so we don't need to send it again here to avoid double-sending.
            
            return transaction, subscription
            
        except ValueError as e:
            # Handle the specific error we raised for inactive subscription
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
            
        except Exception as e:
            logger.error(f"Error processing subscription: {str(e)}",
                       event_type="subscription_error",
                       user_id=user_id,
                       subscription_id=transaction_id,
                       error=str(e))
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing subscription: {str(e)}"
            )
    
    async def _find_matching_plan(self, stripe_plan_id: Optional[str]) -> Optional[int]:
        """
        Find a matching plan in our system based on Stripe plan ID.
        
        Args:
            stripe_plan_id: The Stripe plan ID
            
        Returns:
            Optional[int]: The plan ID if found, None otherwise
        """
        if not stripe_plan_id:
            # If no Stripe plan ID, return the first active plan as fallback
            plans = await self.plan_service.get_all_active_plans()
            if plans:
                return plans[0].id
            return None
        
        # Get plans from database to find the matching plan
        plans = await self.plan_service.get_all_active_plans()
        matching_plans = [p for p in plans if p.stripe_price_id == stripe_plan_id]
        
        if matching_plans:
            return matching_plans[0].id
        
        # If no exact match found, fallback to a default plan
        if plans:
            return plans[0].id
        
        return None

    @db_error_handler()
    async def purchase_plan(
        self,
        user_id: int,
        plan_id: int,
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None,
        stripe_subscription_id: Optional[str] = None,
        credit_amount: Optional[Decimal] = None  # New parameter to override plan credit amount
    ) -> Tuple[credit_schemas.TransactionResponse, object]:
        """
        Purchase a plan, add credits, and create subscription.

        Args:
            user_id: ID of the user
            plan_id: ID of the plan
            reference_id: Optional reference ID for the transaction
            description: Optional description of the transaction
            background_tasks: Optional background tasks for sending emails
            stripe_subscription_id: Optional Stripe subscription ID
            credit_amount: Optional amount of credits to add (overrides the plan amount)

        Returns:
            Tuple with TransactionResponse and Subscription

        Raises:
            HTTPException: If the plan does not exist or is inactive
        """
        try:
            # Get the plan using plan_service
            plan = await self.plan_service.get_plan_by_id(plan_id)
            if not plan:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Plan not found or inactive"
                )
    
            # Check if user already has an active subscription
            existing_subscription = await self.plan_service.get_active_subscription(user_id)
            if existing_subscription:
                # Deactivate existing subscription
                existing_subscription.is_active = False
                existing_subscription.status = "replaced"
                existing_subscription.updated_at = datetime.now(UTC)
                await self.db.commit()
                
                logger.info(f"Deactivated existing subscription: User {user_id}, Subscription {existing_subscription.id}",
                          event_type="subscription_deactivated",
                          user_id=user_id,
                          subscription_id=existing_subscription.id,
                          stripe_subscription_id=existing_subscription.stripe_subscription_id)
    
            # Calculate renewal date
            start_date = datetime.now(UTC)
            renewal_date = calculate_renewal_date(start_date)
    
            # Create subscription
            from app.models.plan import Subscription
            
            subscription = Subscription(
                user_id=user_id,
                plan_id=plan_id,
                start_date=start_date,
                renewal_date=renewal_date,
                is_active=True,
                auto_renew=True,
                stripe_subscription_id=stripe_subscription_id,
                status="active" if stripe_subscription_id else None
            )
            self.db.add(subscription)
            await self.db.commit()
            await self.db.refresh(subscription)
            
            logger.info(f"Created new subscription: User {user_id}, Plan {plan_id}, Subscription {subscription.id}",
                      event_type="subscription_created",
                      user_id=user_id,
                      plan_id=plan_id,
                      subscription_id=subscription.id,
                      stripe_subscription_id=stripe_subscription_id)
        except Exception as e:
            # Rollback transaction on error
            await self.db.rollback()
            logger.error(f"Error creating subscription: {str(e)}",
                       event_type="subscription_creation_error",
                       user_id=user_id,
                       plan_id=plan_id,
                       error=str(e))
            raise

        # Add credits
        if not reference_id:
            reference_id = str(uuid.uuid4())
        
        try:
            # Use the provided credit amount or fallback to plan amount
            amount_to_add = credit_amount if credit_amount is not None else plan.credit_amount
            
            transaction = await self.base_service.add_credits(
                user_id=user_id,
                amount=amount_to_add,  # Use the provided amount or plan amount
                reference_id=reference_id,
                description=description or f"Purchase of {plan.name} plan",
                transaction_type=TransactionType.PLAN_PURCHASE,
                plan_id=plan_id,
                subscription_id=subscription.id,
                monetary_amount=plan.price  # Pass the plan price as the monetary amount
            )
            
            logger.info(f"Added credits for plan purchase: User {user_id}, Credits {amount_to_add}",
                      event_type="plan_credits_added",
                      user_id=user_id,
                      plan_id=plan_id,
                      subscription_id=subscription.id,
                      credit_amount=amount_to_add,
                      transaction_id=transaction.id)
        except Exception as e:
            # If credit addition fails, mark the subscription as problematic
            logger.error(f"Error adding credits for subscription: {str(e)}",
                       event_type="subscription_credit_error",
                       user_id=user_id,
                       plan_id=plan_id,
                       subscription_id=subscription.id,
                       error=str(e))
            
            # Update subscription status to indicate the problem
            subscription.status = "payment_issue"
            await self.db.commit()
            
            # Re-raise the exception
            raise

        # Send email notification
        if background_tasks:
            await self._send_email_notification(
                background_tasks=background_tasks,
                user_id=user_id,
                plan=plan,
                subscription=subscription,
                email_type="payment_confirmation",
                plan_name=plan.name,
                amount=plan.price,
                credit_amount=plan.credit_amount,
                renewal_date=renewal_date
            )
        # Use the actual amount that was added in the log message
        actual_amount = amount_to_add if credit_amount is not None else plan.credit_amount
        logger.info(f"Plan purchased: User {user_id}, Plan {plan_id}, Credits {actual_amount}",
                  event_type="plan_purchased",
                  user_id=user_id,
                  plan_id=plan_id,
                  plan_name=plan.name,
                  credit_amount=actual_amount,
                  renewal_date=renewal_date.isoformat())

        return transaction, subscription