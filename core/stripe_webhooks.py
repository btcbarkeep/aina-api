# routers/stripe_webhooks.py

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from typing import Optional
import json

from core.config import settings
from core.logging_config import logger
from core.supabase_client import get_supabase_client
from core.stripe_helpers import verify_contractor_subscription, get_stripe_client, verify_contractor_subscription as verify_user_subscription
from core.subscription_helpers import create_or_update_user_subscription

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    stripe = None

router = APIRouter(
    prefix="/webhooks/stripe",
    tags=["Webhooks"],
)


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Stripe webhook signature.
    
    Args:
        payload: Raw request body
        signature: Stripe-Signature header value
    
    Returns:
        True if signature is valid, False otherwise
    """
    if not STRIPE_AVAILABLE or not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("Stripe webhook secret not configured - signature verification disabled")
        return True  # Allow in development, but log warning
    
    try:
        stripe_client = get_stripe_client()
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Verify the webhook signature
        event = stripe.Webhook.construct_event(
            payload, signature, settings.STRIPE_WEBHOOK_SECRET
        )
        return True
    except ValueError as e:
        logger.error(f"Invalid payload in webhook: {e}")
        return False
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature in webhook: {e}")
        return False
    except Exception as e:
        logger.error(f"Error verifying webhook signature: {e}")
        return False


@router.post("/subscription")
async def handle_stripe_subscription_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature")
):
    """
    Handle Stripe subscription webhook events.
    
    This endpoint processes Stripe webhook events related to subscriptions:
    - customer.subscription.created
    - customer.subscription.updated
    - customer.subscription.deleted
    - customer.subscription.trial_will_end
    
    **Setup:**
    1. Configure webhook endpoint in Stripe Dashboard: `https://your-api.com/webhooks/stripe/subscription`
    2. Select events: `customer.subscription.*`
    3. Add webhook signing secret to `STRIPE_WEBHOOK_SECRET` environment variable
    
    **Security:**
    - Webhook signature is verified using `STRIPE_WEBHOOK_SECRET`
    - Only processes events for contractors with matching `stripe_customer_id` or `stripe_subscription_id`
    """
    if not STRIPE_AVAILABLE:
        raise HTTPException(500, "Stripe SDK not available")
    
    # Get raw body
    body = await request.body()
    
    # Verify webhook signature
    if stripe_signature:
        if not verify_webhook_signature(body, stripe_signature):
            raise HTTPException(400, "Invalid webhook signature")
    
    try:
        # Parse the event
        event = json.loads(body.decode('utf-8'))
        
        event_type = event.get("type")
        event_data = event.get("data", {}).get("object", {})
        
        logger.info(f"Received Stripe webhook event: {event_type}")
        
        # Handle subscription events
        if event_type in [
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "customer.subscription.trial_will_end"
        ]:
            subscription_id = event_data.get("id")
            customer_id = event_data.get("customer")
            status = event_data.get("status")
            
            if not subscription_id or not customer_id:
                logger.warning(f"Missing subscription_id or customer_id in webhook event: {event_type}")
                return {"status": "ignored", "reason": "missing_ids"}
            
            # Find contractor by Stripe customer ID or subscription ID
            client = get_supabase_client()
            contractor_res = (
                client.table("contractors")
                .select("id, company_name, stripe_customer_id, stripe_subscription_id")
                .or_(f"stripe_customer_id.eq.{customer_id},stripe_subscription_id.eq.{subscription_id}")
                .limit(1)
                .execute()
            )
            
            if not contractor_res.data:
                logger.warning(f"No contractor found for Stripe customer {customer_id} or subscription {subscription_id}")
                return {"status": "ignored", "reason": "contractor_not_found"}
            
            contractor = contractor_res.data[0]
            contractor_id = contractor["id"]
            
            # Determine subscription tier and status
            if event_type == "customer.subscription.deleted":
                subscription_tier = "free"
                subscription_status = "canceled"
            else:
                # Verify subscription status with Stripe
                is_active, verified_status, error = verify_contractor_subscription(
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id
                )
                
                if error:
                    logger.warning(f"Error verifying subscription for contractor {contractor_id}: {error}")
                    subscription_tier = "free"
                    subscription_status = status or "unknown"
                else:
                    subscription_tier = "paid" if is_active else "free"
                    subscription_status = verified_status or status or "unknown"
            
            # Update contractor
            update_data = {
                "subscription_tier": subscription_tier,
                "subscription_status": subscription_status,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id
            }
            
            try:
                update_res = (
                    client.table("contractors")
                    .update(update_data)
                    .eq("id", contractor_id)
                    .execute()
                )
                
                if update_res.data:
                    logger.info(
                        f"Updated contractor {contractor_id} subscription: "
                        f"tier={subscription_tier}, status={subscription_status}"
                    )
                    return {
                        "status": "success",
                        "contractor_id": contractor_id,
                        "subscription_tier": subscription_tier,
                        "subscription_status": subscription_status
                    }
                else:
                    logger.error(f"Failed to update contractor {contractor_id} subscription")
                    return {"status": "error", "reason": "update_failed"}
                    
            except Exception as e:
                logger.error(f"Error updating contractor {contractor_id} subscription: {e}")
                raise HTTPException(500, f"Failed to update contractor subscription: {str(e)}")
            
            # Also check for user subscriptions
            user_subscription_res = (
                client.table("user_subscriptions")
                .select("id, user_id, role, stripe_customer_id, stripe_subscription_id")
                .or_(f"stripe_customer_id.eq.{customer_id},stripe_subscription_id.eq.{subscription_id}")
                .execute()
            )
            
            if user_subscription_res.data:
                for user_sub in user_subscription_res.data:
                    user_id = user_sub["user_id"]
                    role = user_sub["role"]
                    
                    # Determine subscription tier and status
                    if event_type == "customer.subscription.deleted":
                        subscription_tier = "free"
                        subscription_status = "canceled"
                        is_trial = False
                    else:
                        # Verify subscription status with Stripe
                        is_active, verified_status, error = verify_user_subscription(
                            stripe_customer_id=customer_id,
                            stripe_subscription_id=subscription_id
                        )
                        
                        if error:
                            logger.warning(f"Error verifying subscription for user {user_id}, role {role}: {error}")
                            subscription_tier = "free"
                            subscription_status = status or "unknown"
                            is_trial = False
                        else:
                            subscription_tier = "paid" if is_active else "free"
                            subscription_status = verified_status or status or "unknown"
                            # Check if subscription is in trial
                            is_trial = subscription_status == "trialing"
                    
                    # Update user subscription
                    try:
                        create_or_update_user_subscription(
                            user_id=user_id,
                            role=role,
                            subscription_tier=subscription_tier,
                            subscription_status=subscription_status,
                            stripe_customer_id=customer_id,
                            stripe_subscription_id=subscription_id,
                            is_trial=is_trial
                        )
                        
                        logger.info(
                            f"Updated user {user_id} subscription for role {role}: "
                            f"tier={subscription_tier}, status={subscription_status}"
                        )
                    except Exception as e:
                        logger.error(f"Error updating user {user_id} subscription for role {role}: {e}")
        
        # Ignore other event types
        logger.debug(f"Ignoring webhook event type: {event_type}")
        return {"status": "ignored", "reason": "event_type_not_handled"}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook payload: {e}")
        raise HTTPException(400, "Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(500, f"Error processing webhook: {str(e)}")

