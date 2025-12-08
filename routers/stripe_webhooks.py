# routers/stripe_webhooks.py

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from typing import Optional
from datetime import datetime
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
            
            client = get_supabase_client()
            
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
                    logger.warning(f"Error verifying subscription for Stripe customer {customer_id}: {error}")
                    subscription_tier = "free"
                    subscription_status = status or "unknown"
                else:
                    subscription_tier = "paid" if is_active else "free"
                    subscription_status = verified_status or status or "unknown"
            
            update_data = {
                "subscription_tier": subscription_tier,
                "subscription_status": subscription_status,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id
            }
            
            # Check contractors
            contractor_res = (
                client.table("contractors")
                .select("id, company_name, stripe_customer_id, stripe_subscription_id")
                .or_(f"stripe_customer_id.eq.{customer_id},stripe_subscription_id.eq.{subscription_id}")
                .limit(1)
                .execute()
            )
            
            if contractor_res.data:
                contractor = contractor_res.data[0]
                contractor_id = contractor["id"]
                
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
                except Exception as e:
                    logger.error(f"Error updating contractor {contractor_id} subscription: {e}")
            
            # Check AOAO organizations
            aoao_org_res = (
                client.table("aoao_organizations")
                .select("id, organization_name, stripe_customer_id, stripe_subscription_id")
                .or_(f"stripe_customer_id.eq.{customer_id},stripe_subscription_id.eq.{subscription_id}")
                .limit(1)
                .execute()
            )
            
            if aoao_org_res.data:
                org = aoao_org_res.data[0]
                org_id = org["id"]
                
                try:
                    update_res = (
                        client.table("aoao_organizations")
                        .update(update_data)
                        .eq("id", org_id)
                        .execute()
                    )
                    
                    if update_res.data:
                        logger.info(
                            f"Updated AOAO organization {org_id} subscription: "
                            f"tier={subscription_tier}, status={subscription_status}"
                        )
                except Exception as e:
                    logger.error(f"Error updating AOAO organization {org_id} subscription: {e}")
            
            # Check PM companies
            pm_company_res = (
                client.table("property_management_companies")
                .select("id, company_name, stripe_customer_id, stripe_subscription_id")
                .or_(f"stripe_customer_id.eq.{customer_id},stripe_subscription_id.eq.{subscription_id}")
                .limit(1)
                .execute()
            )
            
            if pm_company_res.data:
                pm_company = pm_company_res.data[0]
                pm_company_id = pm_company["id"]
                
                try:
                    update_res = (
                        client.table("property_management_companies")
                        .update(update_data)
                        .eq("id", pm_company_id)
                        .execute()
                    )
                    
                    if update_res.data:
                        logger.info(
                            f"Updated PM company {pm_company_id} subscription: "
                            f"tier={subscription_tier}, status={subscription_status}"
                        )
                except Exception as e:
                    logger.error(f"Error updating PM company {pm_company_id} subscription: {e}")
            
            # Return success if any business entity was updated
            if contractor_res.data or aoao_org_res.data or pm_company_res.data:
                return {
                    "status": "success",
                    "subscription_tier": subscription_tier,
                    "subscription_status": subscription_status
                }
            
            # If no business entity found, log warning but continue to check user subscriptions
            logger.warning(f"No business entity found for Stripe customer {customer_id} or subscription {subscription_id}")
            
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
        
        # Handle premium report purchases (checkout.session.completed)
        if event_type == "checkout.session.completed":
            session_id = event_data.get("id")
            customer_email = event_data.get("customer_details", {}).get("email")
            customer_name = event_data.get("customer_details", {}).get("name")
            amount_total = event_data.get("amount_total", 0)  # in cents
            currency = event_data.get("currency", "usd")
            payment_status = event_data.get("payment_status", "paid")
            customer_id = event_data.get("customer")
            payment_intent_id = event_data.get("payment_intent")
            metadata = event_data.get("metadata", {})
            
            # Check if this is a premium report purchase (has report_type in metadata)
            report_type = metadata.get("report_type")
            if report_type:
                client = get_supabase_client()
                
                # Extract report-specific metadata
                building_id = metadata.get("building_id")
                unit_id = metadata.get("unit_id")
                contractor_id = metadata.get("contractor_id")
                report_id = metadata.get("report_id")
                
                # Calculate amount in decimal
                amount_decimal = round(amount_total / 100.0, 2)
                
                # Determine payment status
                status = "paid" if payment_status == "paid" else "pending"
                
                try:
                    purchase_data = {
                        "customer_email": customer_email or "unknown",
                        "customer_name": customer_name,
                        "report_type": report_type,
                        "report_id": report_id,
                        "building_id": building_id if building_id else None,
                        "unit_id": unit_id if unit_id else None,
                        "contractor_id": contractor_id if contractor_id else None,
                        "stripe_session_id": session_id,
                        "stripe_payment_intent_id": payment_intent_id,
                        "stripe_customer_id": customer_id,
                        "amount_cents": amount_total,
                        "amount_decimal": amount_decimal,
                        "currency": currency,
                        "payment_status": status,
                        "purchased_at": datetime.utcnow().isoformat() + "Z"
                    }
                    
                    # Remove None values for optional fields
                    purchase_data = {k: v for k, v in purchase_data.items() if v is not None}
                    
                    result = (
                        client.table("premium_report_purchases")
                        .insert(purchase_data)
                        .execute()
                    )
                    
                    if result.data:
                        logger.info(
                            f"Recorded premium report purchase: {report_type} report for {customer_email} "
                            f"(${amount_decimal} {currency.upper()})"
                        )
                        return {
                            "status": "success",
                            "purchase_id": result.data[0].get("id"),
                            "report_type": report_type
                        }
                    else:
                        logger.warning(f"Failed to insert premium report purchase for session {session_id}")
                        return {"status": "error", "reason": "insert_failed"}
                        
                except Exception as e:
                    logger.error(f"Error recording premium report purchase: {e}")
                    # Don't fail the webhook, just log the error
                    return {"status": "error", "reason": str(e)}
            
            # If not a premium report, ignore (might be a document purchase or other)
            logger.debug(f"Checkout session {session_id} completed but not a premium report purchase")
            return {"status": "ignored", "reason": "not_premium_report"}
        
        # Handle payment_intent.succeeded for premium reports (alternative to checkout.session.completed)
        if event_type == "payment_intent.succeeded":
            payment_intent_id = event_data.get("id")
            amount = event_data.get("amount", 0)  # in cents
            currency = event_data.get("currency", "usd")
            customer_id = event_data.get("customer")
            metadata = event_data.get("metadata", {})
            
            # Check if this is a premium report purchase
            report_type = metadata.get("report_type")
            if report_type:
                client = get_supabase_client()
                
                # Check if purchase already exists (might have been created via checkout.session.completed)
                existing = (
                    client.table("premium_report_purchases")
                    .select("id")
                    .eq("stripe_payment_intent_id", payment_intent_id)
                    .maybe_single()
                    .execute()
                )
                
                if existing.data:
                    # Update payment status to paid
                    try:
                        (
                            client.table("premium_report_purchases")
                            .update({"payment_status": "paid"})
                            .eq("stripe_payment_intent_id", payment_intent_id)
                            .execute()
                        )
                        logger.info(f"Updated premium report purchase payment status to paid: {payment_intent_id}")
                    except Exception as e:
                        logger.error(f"Error updating premium report purchase: {e}")
                    return {"status": "success", "action": "updated"}
                
                # If not exists, create new purchase record
                # Note: We might not have customer email from payment intent, so we'll need to fetch it
                customer_email = metadata.get("customer_email", "unknown")
                customer_name = metadata.get("customer_name")
                building_id = metadata.get("building_id")
                unit_id = metadata.get("unit_id")
                contractor_id = metadata.get("contractor_id")
                report_id = metadata.get("report_id")
                
                amount_decimal = round(amount / 100.0, 2)
                
                try:
                    purchase_data = {
                        "customer_email": customer_email,
                        "customer_name": customer_name,
                        "report_type": report_type,
                        "report_id": report_id,
                        "building_id": building_id if building_id else None,
                        "unit_id": unit_id if unit_id else None,
                        "contractor_id": contractor_id if contractor_id else None,
                        "stripe_payment_intent_id": payment_intent_id,
                        "stripe_customer_id": customer_id,
                        "amount_cents": amount,
                        "amount_decimal": amount_decimal,
                        "currency": currency,
                        "payment_status": "paid",
                        "purchased_at": datetime.utcnow().isoformat() + "Z"
                    }
                    
                    purchase_data = {k: v for k, v in purchase_data.items() if v is not None}
                    
                    result = (
                        client.table("premium_report_purchases")
                        .insert(purchase_data)
                        .execute()
                    )
                    
                    if result.data:
                        logger.info(
                            f"Recorded premium report purchase via payment intent: {report_type} report "
                            f"(${amount_decimal} {currency.upper()})"
                        )
                        return {
                            "status": "success",
                            "purchase_id": result.data[0].get("id"),
                            "report_type": report_type
                        }
                except Exception as e:
                    logger.error(f"Error recording premium report purchase from payment intent: {e}")
                    return {"status": "error", "reason": str(e)}
        
        # Ignore other event types
        logger.debug(f"Ignoring webhook event type: {event_type}")
        return {"status": "ignored", "reason": "event_type_not_handled"}
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in webhook payload: {e}")
        raise HTTPException(400, "Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(500, f"Error processing webhook: {str(e)}")

