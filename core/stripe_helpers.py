# core/stripe_helpers.py

from typing import Optional
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

