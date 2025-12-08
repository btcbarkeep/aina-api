# routers/financials.py

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta

from dependencies.auth import get_current_user, CurrentUser
from core.supabase_client import get_supabase_client
from core.logging_config import logger
from core.stripe_helpers import get_subscription_revenue, get_total_revenue_for_period

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
        
        # Fetch actual revenue from Stripe
        stripe_revenue = get_total_revenue_for_period(start_dt, end_dt)
        if "error" not in stripe_revenue:
            revenue_data["stripe"] = {
                "total_revenue": stripe_revenue.get("total_revenue", 0),
                "total_revenue_decimal": stripe_revenue.get("total_revenue_decimal", 0.0),
                "subscription_revenue": stripe_revenue.get("subscription_revenue", 0),
                "subscription_revenue_decimal": stripe_revenue.get("subscription_revenue_decimal", 0.0),
                "currency": stripe_revenue.get("currency", "usd"),
                "invoice_count": stripe_revenue.get("invoice_count", 0),
            }
        else:
            revenue_data["stripe"] = {
                "error": stripe_revenue.get("error", "Unable to fetch Stripe revenue"),
                "note": "Stripe integration may not be configured or there was an error fetching revenue data"
            }
        
        # Fetch premium report purchase revenue
        premium_reports_result = (
            client.table("premium_report_purchases")
            .select("amount_cents, amount_decimal, currency, payment_status, purchased_at")
            .eq("payment_status", "paid")
            .gte("purchased_at", start_dt.isoformat())
            .lte("purchased_at", end_dt.isoformat())
            .execute()
        )
        
        premium_reports_total_cents = 0
        premium_reports_total_decimal = 0.0
        premium_reports_count = 0
        
        for purchase in (premium_reports_result.data or []):
            premium_reports_total_cents += purchase.get("amount_cents", 0)
            premium_reports_total_decimal += purchase.get("amount_decimal", 0.0)
            premium_reports_count += 1
        
        revenue_data["premium_reports"] = {
            "total_revenue_cents": premium_reports_total_cents,
            "total_revenue_decimal": round(premium_reports_total_decimal, 2),
            "purchase_count": premium_reports_count,
            "currency": "usd"  # Assuming USD for now
        }
        
        # Add premium reports to summary
        revenue_data["summary"]["total_revenue_cents"] = (
            revenue_data.get("stripe", {}).get("total_revenue", 0) + premium_reports_total_cents
        )
        revenue_data["summary"]["total_revenue_decimal"] = round(
            revenue_data.get("stripe", {}).get("total_revenue_decimal", 0.0) + premium_reports_total_decimal, 2
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
    
    Returns detailed list of all paid subscriptions with revenue information from Stripe.
    """
    if current_user.role != "super_admin":
        raise HTTPException(403, "Only super admins can view financial data")
    
    client = get_supabase_client()
    
    try:
        subscriptions = []
        
        # Get user subscriptions with Stripe revenue
        user_subs_result = (
            client.table("user_subscriptions")
            .select("id, user_id, subscription_tier, subscription_status, stripe_subscription_id, stripe_customer_id, created_at")
            .eq("subscription_tier", "paid")
            .in_("subscription_status", ["active", "trialing"])
            .execute()
        )
        
        for sub in (user_subs_result.data or []):
            revenue_info = {}
            if sub.get("stripe_subscription_id") or sub.get("stripe_customer_id"):
                revenue_info = get_subscription_revenue(
                    stripe_subscription_id=sub.get("stripe_subscription_id"),
                    stripe_customer_id=sub.get("stripe_customer_id")
                )
            
            subscriptions.append({
                "subscription_type": "user",
                "subscription_id": sub.get("id"),
                "user_id": sub.get("user_id"),
                "subscription_tier": sub.get("subscription_tier"),
                "subscription_status": sub.get("subscription_status"),
                "stripe_subscription_id": sub.get("stripe_subscription_id"),
                "revenue": revenue_info,
                "created_at": sub.get("created_at"),
            })
        
        # Get contractor subscriptions with Stripe revenue
        contractors_result = (
            client.table("contractors")
            .select("id, company_name, subscription_tier, subscription_status, stripe_subscription_id, stripe_customer_id, created_at")
            .eq("subscription_tier", "paid")
            .in_("subscription_status", ["active", "trialing"])
            .execute()
        )
        
        for contractor in (contractors_result.data or []):
            revenue_info = {}
            if contractor.get("stripe_subscription_id") or contractor.get("stripe_customer_id"):
                revenue_info = get_subscription_revenue(
                    stripe_subscription_id=contractor.get("stripe_subscription_id"),
                    stripe_customer_id=contractor.get("stripe_customer_id")
                )
            
            subscriptions.append({
                "subscription_type": "contractor",
                "subscription_id": contractor.get("id"),
                "company_name": contractor.get("company_name"),
                "subscription_tier": contractor.get("subscription_tier"),
                "subscription_status": contractor.get("subscription_status"),
                "stripe_subscription_id": contractor.get("stripe_subscription_id"),
                "revenue": revenue_info,
                "created_at": contractor.get("created_at"),
            })
        
        # Get AOAO organization subscriptions with Stripe revenue
        aoao_result = (
            client.table("aoao_organizations")
            .select("id, organization_name, subscription_tier, subscription_status, stripe_subscription_id, stripe_customer_id, created_at")
            .eq("subscription_tier", "paid")
            .in_("subscription_status", ["active", "trialing"])
            .execute()
        )
        
        for org in (aoao_result.data or []):
            revenue_info = {}
            if org.get("stripe_subscription_id") or org.get("stripe_customer_id"):
                revenue_info = get_subscription_revenue(
                    stripe_subscription_id=org.get("stripe_subscription_id"),
                    stripe_customer_id=org.get("stripe_customer_id")
                )
            
            subscriptions.append({
                "subscription_type": "aoao_organization",
                "subscription_id": org.get("id"),
                "organization_name": org.get("organization_name"),
                "subscription_tier": org.get("subscription_tier"),
                "subscription_status": org.get("subscription_status"),
                "stripe_subscription_id": org.get("stripe_subscription_id"),
                "revenue": revenue_info,
                "created_at": org.get("created_at"),
            })
        
        # Get PM company subscriptions with Stripe revenue
        pm_result = (
            client.table("property_management_companies")
            .select("id, company_name, subscription_tier, subscription_status, stripe_subscription_id, stripe_customer_id, created_at")
            .eq("subscription_tier", "paid")
            .in_("subscription_status", ["active", "trialing"])
            .execute()
        )
        
        for company in (pm_result.data or []):
            revenue_info = {}
            if company.get("stripe_subscription_id") or company.get("stripe_customer_id"):
                revenue_info = get_subscription_revenue(
                    stripe_subscription_id=company.get("stripe_subscription_id"),
                    stripe_customer_id=company.get("stripe_customer_id")
                )
            
            subscriptions.append({
                "subscription_type": "pm_company",
                "subscription_id": company.get("id"),
                "company_name": company.get("company_name"),
                "subscription_tier": company.get("subscription_tier"),
                "subscription_status": company.get("subscription_status"),
                "stripe_subscription_id": company.get("stripe_subscription_id"),
                "revenue": revenue_info,
                "created_at": company.get("created_at"),
            })
        
        # Calculate totals
        total_monthly_revenue = 0
        total_annual_revenue = 0
        
        for sub in subscriptions:
            revenue = sub.get("revenue", {})
            if "error" not in revenue:
                amount = revenue.get("amount", 0)
                interval = revenue.get("interval", "month")
                
                if interval == "month":
                    total_monthly_revenue += amount
                    total_annual_revenue += amount * 12
                elif interval == "year":
                    total_annual_revenue += amount
                    total_monthly_revenue += amount / 12
        
        return {
            "success": True,
            "total_subscriptions": len(subscriptions),
            "total_monthly_revenue": total_monthly_revenue,
            "total_monthly_revenue_decimal": total_monthly_revenue / 100.0,
            "total_annual_revenue": total_annual_revenue,
            "total_annual_revenue_decimal": total_annual_revenue / 100.0,
            "subscriptions": subscriptions,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get subscription breakdown: {e}")
        raise HTTPException(500, f"Failed to get subscription breakdown: {str(e)}")


@router.get("/premium-reports/breakdown")
def get_premium_reports_breakdown(
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    current_user: CurrentUser = Depends(get_current_user)
):
    """
    Get detailed premium report purchase breakdown (Super Admin only).
    
    Returns list of all premium report purchases with revenue information.
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
        
        # Fetch premium report purchases
        query = (
            client.table("premium_report_purchases")
            .select("*")
            .eq("payment_status", "paid")
            .gte("purchased_at", start_dt.isoformat())
            .lte("purchased_at", end_dt.isoformat())
            .order("purchased_at", desc=True)
        )
        
        result = query.execute()
        purchases = result.data or []
        
        # Calculate totals
        total_revenue_cents = 0
        total_revenue_decimal = 0.0
        report_type_counts = {}
        
        for purchase in purchases:
            amount_cents = purchase.get("amount_cents", 0)
            amount_decimal = purchase.get("amount_decimal", 0.0)
            report_type = purchase.get("report_type", "unknown")
            
            total_revenue_cents += amount_cents
            total_revenue_decimal += amount_decimal
            
            if report_type not in report_type_counts:
                report_type_counts[report_type] = {"count": 0, "revenue_cents": 0, "revenue_decimal": 0.0}
            
            report_type_counts[report_type]["count"] += 1
            report_type_counts[report_type]["revenue_cents"] += amount_cents
            report_type_counts[report_type]["revenue_decimal"] += amount_decimal
        
        # Round decimal values
        total_revenue_decimal = round(total_revenue_decimal, 2)
        for report_type in report_type_counts:
            report_type_counts[report_type]["revenue_decimal"] = round(
                report_type_counts[report_type]["revenue_decimal"], 2
            )
        
        return {
            "success": True,
            "period": {
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat()
            },
            "total_purchases": len(purchases),
            "total_revenue_cents": total_revenue_cents,
            "total_revenue_decimal": total_revenue_decimal,
            "currency": "usd",
            "report_type_breakdown": report_type_counts,
            "purchases": purchases
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get premium reports breakdown: {e}")
        raise HTTPException(500, f"Failed to get premium reports breakdown: {str(e)}")

