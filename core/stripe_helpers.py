# core/stripe_helpers.py

from typing import Optional
from datetime import datetime
from fastapi import HTTPException
from core.config import settings
from core.logging_config import logger

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    stripe = None


def get_stripe_client():
    """Get Stripe client instance."""
    if not STRIPE_AVAILABLE:
        raise HTTPException(500, "Stripe SDK not available")
    
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(500, "Stripe secret key not configured")
    
    return stripe


def verify_stripe_session(
    session_id: str,
    document_id: Optional[str] = None
) -> bool:
    """
    Verify a Stripe Checkout Session.
    
    Args:
        session_id: Stripe Checkout Session ID
        document_id: Optional document ID to verify access for
    
    Returns:
        True if session is valid and paid, False otherwise
    """
    if not STRIPE_AVAILABLE or not settings.STRIPE_SECRET_KEY:
        logger.warning("Stripe not configured - payment verification disabled")
        return False
    
    try:
        stripe_client = get_stripe_client()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Retrieve the session
        session = stripe_client.checkout.Session.retrieve(session_id)
        
        # Check if session is completed and paid
        if session.payment_status != "paid":
            logger.warning(f"Stripe session {session_id} not paid: {session.payment_status}")
            return False
        
        # Check if session status is complete
        if session.status != "complete":
            logger.warning(f"Stripe session {session_id} not complete: {session.status}")
            return False
        
        # If document_id provided, verify it's in the session metadata or line items
        if document_id:
            # Check metadata
            metadata = session.metadata or {}
            session_doc_ids = metadata.get("document_ids", "")
            
            # Support comma-separated list of document IDs
            if session_doc_ids:
                doc_ids = [d.strip() for d in session_doc_ids.split(",")]
                if document_id not in doc_ids:
                    logger.warning(f"Document {document_id} not in session {session_id} metadata")
                    return False
            
            # Also check line items metadata if available
            if hasattr(session, "line_items"):
                try:
                    line_items = stripe_client.checkout.Session.list_line_items(session_id)
                    for item in line_items.data:
                        item_metadata = item.price.metadata or {}
                        if item_metadata.get("document_id") == document_id:
                            return True
                except Exception as e:
                    logger.debug(f"Could not check line items: {e}")
        
        return True
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error verifying session {session_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error verifying Stripe session {session_id}: {e}")
        return False


def verify_stripe_payment_intent(
    payment_intent_id: str,
    document_id: Optional[str] = None
) -> bool:
    """
    Verify a Stripe Payment Intent.
    
    Args:
        payment_intent_id: Stripe Payment Intent ID
        document_id: Optional document ID to verify access for
    
    Returns:
        True if payment intent is valid and succeeded, False otherwise
    """
    if not STRIPE_AVAILABLE or not settings.STRIPE_SECRET_KEY:
        logger.warning("Stripe not configured - payment verification disabled")
        return False
    
    try:
        stripe_client = get_stripe_client()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Retrieve the payment intent
        payment_intent = stripe_client.PaymentIntent.retrieve(payment_intent_id)
        
        # Check if payment succeeded
        if payment_intent.status != "succeeded":
            logger.warning(f"Payment intent {payment_intent_id} not succeeded: {payment_intent.status}")
            return False
        
        # If document_id provided, verify it's in the metadata
        if document_id:
            metadata = payment_intent.metadata or {}
            payment_doc_ids = metadata.get("document_ids", "")
            
            if payment_doc_ids:
                doc_ids = [d.strip() for d in payment_doc_ids.split(",")]
                if document_id not in doc_ids:
                    logger.warning(f"Document {document_id} not in payment intent {payment_intent_id} metadata")
                    return False
        
        return True
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error verifying payment intent {payment_intent_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error verifying Stripe payment intent {payment_intent_id}: {e}")
        return False


def verify_contractor_subscription(
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Verify a contractor's Stripe subscription status.
    
    Args:
        stripe_customer_id: Stripe customer ID
        stripe_subscription_id: Stripe subscription ID (preferred if available)
    
    Returns:
        Tuple of (is_active: bool, subscription_status: Optional[str], error_message: Optional[str])
        - is_active: True if subscription is active and paid
        - subscription_status: Current subscription status from Stripe
        - error_message: Error message if verification failed
    """
    if not STRIPE_AVAILABLE or not settings.STRIPE_SECRET_KEY:
        logger.warning("Stripe not configured - subscription verification disabled")
        return False, None, "Stripe not configured"
    
    if not stripe_customer_id and not stripe_subscription_id:
        return False, None, "No Stripe customer or subscription ID provided"
    
    try:
        stripe_client = get_stripe_client()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # If subscription_id provided, use it directly (preferred)
        if stripe_subscription_id:
            subscription = stripe_client.Subscription.retrieve(stripe_subscription_id)
            status = subscription.status
            
            # Check if subscription is active
            is_active = status in ["active", "trialing"]
            
            return is_active, status, None
        
        # Otherwise, look up by customer_id
        if stripe_customer_id:
            # Get the most recent active subscription for this customer
            subscriptions = stripe_client.Subscription.list(
                customer=stripe_customer_id,
                status="all",
                limit=1
            )
            
            if not subscriptions.data:
                return False, None, "No subscription found for this customer"
            
            subscription = subscriptions.data[0]
            status = subscription.status
            
            # Check if subscription is active
            is_active = status in ["active", "trialing"]
            
            return is_active, status, None
        
        return False, None, "No valid Stripe identifiers provided"
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error verifying subscription: {e}")
        return False, None, f"Stripe API error: {str(e)}"
    except Exception as e:
        logger.error(f"Error verifying Stripe subscription: {e}")
        return False, None, f"Error: {str(e)}"


def get_subscription_tier_from_stripe(
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None
) -> str:
    """
    Get subscription tier ("free" or "paid") based on Stripe subscription status.
    
    Args:
        stripe_customer_id: Stripe customer ID
        stripe_subscription_id: Stripe subscription ID (preferred if available)
    
    Returns:
        "paid" if subscription is active, "free" otherwise
    """
    is_active, status, _ = verify_contractor_subscription(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id
    )
    
    return "paid" if is_active else "free"


def get_subscription_revenue(
    stripe_subscription_id: Optional[str] = None,
    stripe_customer_id: Optional[str] = None
) -> dict:
    """
    Get revenue information for a Stripe subscription.
    
    Args:
        stripe_subscription_id: Stripe subscription ID (preferred)
        stripe_customer_id: Stripe customer ID (fallback)
    
    Returns:
        Dictionary with:
        - amount: Monthly/annual amount in cents
        - currency: Currency code (e.g., "usd")
        - interval: "month" or "year"
        - status: Subscription status
        - current_period_start: Start of current billing period
        - current_period_end: End of current billing period
        - error: Error message if failed
    """
    if not STRIPE_AVAILABLE or not settings.STRIPE_SECRET_KEY:
        return {"error": "Stripe not configured"}
    
    try:
        stripe_client = get_stripe_client()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        subscription = None
        
        # Get subscription by ID if provided
        if stripe_subscription_id:
            subscription = stripe_client.Subscription.retrieve(stripe_subscription_id)
        elif stripe_customer_id:
            # Get most recent subscription for customer
            subscriptions = stripe_client.Subscription.list(
                customer=stripe_customer_id,
                status="all",
                limit=1
            )
            if subscriptions.data:
                subscription = subscriptions.data[0]
        
        if not subscription:
            return {"error": "No subscription found"}
        
        # Extract revenue info
        amount = 0
        currency = "usd"
        interval = "month"
        
        if subscription.items.data:
            price = subscription.items.data[0].price
            amount = price.unit_amount or 0
            currency = price.currency or "usd"
            interval = price.recurring.interval if price.recurring else "month"
        
        return {
            "amount": amount,
            "amount_decimal": amount / 100.0,  # Convert cents to dollars
            "currency": currency,
            "interval": interval,
            "status": subscription.status,
            "current_period_start": subscription.current_period_start,
            "current_period_end": subscription.current_period_end,
            "created": subscription.created,
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error getting subscription revenue: {e}")
        return {"error": f"Stripe API error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error getting subscription revenue: {e}")
        return {"error": f"Error: {str(e)}"}


def get_total_revenue_for_period(
    start_date: datetime,
    end_date: datetime
) -> dict:
    """
    Get total revenue from Stripe for a given time period.
    
    Args:
        start_date: Start of period
        end_date: End of period
    
    Returns:
        Dictionary with:
        - total_revenue: Total revenue in cents
        - total_revenue_decimal: Total revenue in dollars
        - currency: Currency code
        - subscription_count: Number of active subscriptions
        - error: Error message if failed
    """
    if not STRIPE_AVAILABLE or not settings.STRIPE_SECRET_KEY:
        return {"error": "Stripe not configured"}
    
    try:
        stripe_client = get_stripe_client()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Get all paid invoices in the period
        invoices = stripe_client.Invoice.list(
            created={
                "gte": int(start_date.timestamp()),
                "lte": int(end_date.timestamp())
            },
            status="paid",
            limit=100  # Adjust if needed
        )
        
        total_revenue = 0
        currency = "usd"
        
        for invoice in invoices.data:
            if invoice.amount_paid:
                total_revenue += invoice.amount_paid
                currency = invoice.currency or "usd"
        
        # Also get active subscriptions and their recurring revenue
        subscriptions = stripe_client.Subscription.list(
            status="active",
            limit=100
        )
        
        subscription_revenue = 0
        for sub in subscriptions.data:
            if sub.items.data:
                price = sub.items.data[0].price
                amount = price.unit_amount or 0
                # Calculate prorated revenue for period
                # This is simplified - you may want more sophisticated calculation
                subscription_revenue += amount
        
        return {
            "total_revenue": total_revenue,
            "total_revenue_decimal": total_revenue / 100.0,
            "subscription_revenue": subscription_revenue,
            "subscription_revenue_decimal": subscription_revenue / 100.0,
            "currency": currency,
            "subscription_count": len(subscriptions.data),
            "invoice_count": len(invoices.data),
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error getting total revenue: {e}")
        return {"error": f"Stripe API error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error getting total revenue: {e}")
        return {"error": f"Error: {str(e)}"}

