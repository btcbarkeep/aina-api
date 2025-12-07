# routers/financials.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger

router = APIRouter(
    prefix="/financials",
    tags=["Financials"],
)


@router.get("/revenue")
def get_revenue(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get revenue summary (Super Admin only).
    
    Returns subscription revenue breakdown by:
    - User subscriptions
    - Contractor subscriptions
    - AOAO organization subscriptions
    - PM company subscriptions
    """
    if current_user.role != "super_admin":
        raise HTTPException(403, "Only super admins can view financial data")
    
    client = get_supabase_client()
    
    try:
        # Parse dates
        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except:
                raise HTTPException(400, "Invalid start_date format. Use ISO format.")
        else:
            start_dt = datetime.now() - timedelta(days=30)  # Default to last 30 days
        
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except:
                raise HTTPException(400, "Invalid end_date format. Use ISO format.")
        else:
            end_dt = datetime.now()
        
        revenue_data = {
            "period": {
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat()
            },
            "subscriptions": {
                "user_subscriptions": {
                    "total": 0,
                    "active_paid": 0,
                    "trials": 0
                },
                "contractors": {
                    "total": 0,
                    "active_paid": 0,
                    "trials": 0
                },
                "aoao_organizations": {
                    "total": 0,
                    "active_paid": 0,
                    "trials": 0
                },
                "pm_companies": {
                    "total": 0,
                    "active_paid": 0,
                    "trials": 0
                }
            },
            "summary": {
                "total_subscriptions": 0,
                "total_active_paid": 0,
                "total_trials": 0
            }
        }
        
        # Count user subscriptions
        user_subs_result = (
            client.table("user_subscriptions")
            .select("subscription_tier, subscription_status, is_trial")
            .execute()
        )
        
        for sub in (user_subs_result.data or []):
            revenue_data["subscriptions"]["user_subscriptions"]["total"] += 1
            if sub.get("subscription_tier") == "paid" and sub.get("subscription_status") in ["active", "trialing"]:
                revenue_data["subscriptions"]["user_subscriptions"]["active_paid"] += 1
            if sub.get("is_trial"):
                revenue_data["subscriptions"]["user_subscriptions"]["trials"] += 1
        
        # Count contractor subscriptions
        contractors_result = (
            client.table("contractors")
            .select("subscription_tier, subscription_status")
            .execute()
        )
        
        for contractor in (contractors_result.data or []):
            revenue_data["subscriptions"]["contractors"]["total"] += 1
            if contractor.get("subscription_tier") == "paid" and contractor.get("subscription_status") in ["active", "trialing"]:
                revenue_data["subscriptions"]["contractors"]["active_paid"] += 1
            if contractor.get("subscription_status") == "trialing":
                revenue_data["subscriptions"]["contractors"]["trials"] += 1
        
        # Count AOAO organization subscriptions
        aoao_result = (
            client.table("aoao_organizations")
            .select("subscription_tier, subscription_status")
            .execute()
        )
        
        for org in (aoao_result.data or []):
            revenue_data["subscriptions"]["aoao_organizations"]["total"] += 1
            if org.get("subscription_tier") == "paid" and org.get("subscription_status") in ["active", "trialing"]:
                revenue_data["subscriptions"]["aoao_organizations"]["active_paid"] += 1
            if org.get("subscription_status") == "trialing":
                revenue_data["subscriptions"]["aoao_organizations"]["trials"] += 1
        
        # Count PM company subscriptions
        pm_result = (
            client.table("property_management_companies")
            .select("subscription_tier, subscription_status")
            .execute()
        )
        
        for company in (pm_result.data or []):
            revenue_data["subscriptions"]["pm_companies"]["total"] += 1
            if company.get("subscription_tier") == "paid" and company.get("subscription_status") in ["active", "trialing"]:
                revenue_data["subscriptions"]["pm_companies"]["active_paid"] += 1
            if company.get("subscription_status") == "trialing":
                revenue_data["subscriptions"]["pm_companies"]["trials"] += 1
        
        # Calculate summary
        revenue_data["summary"]["total_subscriptions"] = (
            revenue_data["subscriptions"]["user_subscriptions"]["total"] +
            revenue_data["subscriptions"]["contractors"]["total"] +
            revenue_data["subscriptions"]["aoao_organizations"]["total"] +
            revenue_data["subscriptions"]["pm_companies"]["total"]
        )
        
        revenue_data["summary"]["total_active_paid"] = (
            revenue_data["subscriptions"]["user_subscriptions"]["active_paid"] +
            revenue_data["subscriptions"]["contractors"]["active_paid"] +
            revenue_data["subscriptions"]["aoao_organizations"]["active_paid"] +
            revenue_data["subscriptions"]["pm_companies"]["active_paid"]
        )
        
        revenue_data["summary"]["total_trials"] = (
            revenue_data["subscriptions"]["user_subscriptions"]["trials"] +
            revenue_data["subscriptions"]["contractors"]["trials"] +
            revenue_data["subscriptions"]["aoao_organizations"]["trials"] +
            revenue_data["subscriptions"]["pm_companies"]["trials"]
        )
        
        return revenue_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get revenue data: {e}")
        raise HTTPException(500, f"Failed to get revenue data: {str(e)}")


@router.get("/subscriptions/breakdown")
def get_subscription_breakdown(
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get detailed subscription breakdown (Super Admin only).
    
    Returns detailed list of all paid subscriptions with revenue information.
    """
    if current_user.role != "super_admin":
        raise HTTPException(403, "Only super admins can view financial data")
    
    # This would integrate with Stripe to get actual revenue data
    # For now, return subscription counts
    return {
        "message": "Stripe integration for actual revenue data coming soon",
        "note": "Use /financials/revenue for subscription counts"
    }

