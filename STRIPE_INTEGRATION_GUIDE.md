# Stripe Integration Guide

## Overview

The document download endpoint now supports a hybrid access control model that allows:
- **Public documents** (`is_public=True`): 
  * Free access without authentication (rate limited), OR
  * Stripe payment verification (for paid public documents)
- **Private documents** (`is_public=False`): Only accessible by:
  1. **Owner access** - User who uploaded the document (highest priority)
  2. **Permission-based access** - Authenticated user with document access permissions
  **NOTE:** Stripe payments are NOT allowed for private documents - they remain private to the owner and authorized users only

## Setup

### 1. Environment Variables

Add these to your environment (Render, `.env`, etc.):

```bash
STRIPE_SECRET_KEY=sk_test_...  # Your Stripe secret key (required for all Stripe features)
STRIPE_WEBHOOK_SECRET=whsec_...  # Required for webhook verification (subscriptions, payments)
```

**Note:** `STRIPE_SECRET_KEY` is required for:
- Document payment verification
- Subscription management
- Revenue tracking and financials
- Webhook processing

### 2. Install Dependencies

The Stripe SDK has been added to `requirements.txt`. Install with:

```bash
pip install -r requirements.txt
```

### 3. Stripe Webhook Configuration

For subscription management and payment tracking, configure Stripe webhooks:

1. **In Stripe Dashboard:**
   - Go to Developers → Webhooks
   - Add endpoint: `https://your-api-domain.com/stripe-webhooks/`
   - Select events to listen for:
     - `customer.subscription.created`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
     - `invoice.payment_succeeded`
     - `invoice.payment_failed`
     - `checkout.session.completed` (for document payments)

2. **Copy the webhook signing secret:**
   - After creating the webhook, copy the "Signing secret"
   - Add it to your environment as `STRIPE_WEBHOOK_SECRET`

3. **Test the webhook:**
   - Use Stripe CLI: `stripe listen --forward-to localhost:8000/stripe-webhooks/`
   - Or use Stripe Dashboard → Send test webhook

## Usage

### Public Documents - Free Access

Public documents can be accessed without authentication:

```bash
curl "https://api.ainaprotocol.com/uploads/documents/{document_id}/download"
```

**Rate Limiting:** Free public documents are limited to 20 requests per minute per IP/user.

### Public Documents - Paid Access

Public documents can also be sold via Stripe. Users who pay can access them:

```bash
curl "https://api.ainaprotocol.com/uploads/documents/{document_id}/download?stripe_session_id={session_id}"
```

### Private Documents - Option 1: Owner Access

If you uploaded the document, you can access it directly with authentication:

```bash
curl -H "Authorization: Bearer {jwt_token}" \
  "https://api.ainaprotocol.com/uploads/documents/{document_id}/download"
```

The system automatically checks if the authenticated user is the document owner (`uploaded_by` field matches user ID).

### Private Documents - Important Note

**Private documents (`is_public=False`) cannot be purchased via Stripe.** They are only accessible by:
- The document owner (uploader)
- Users with document access permissions

If you attempt to use Stripe payment for a private document, you will receive a 403 Forbidden error.

### Public Documents - Stripe Checkout Session

For **public documents** that you want to sell, when a user completes a Stripe Checkout, include the document ID in the session metadata:

```python
import stripe

stripe.api_key = "sk_test_..."

session = stripe.checkout.Session.create(
    payment_method_types=['card'],
    line_items=[{
        'price_data': {
            'currency': 'usd',
            'product_data': {
                'name': 'Document Access',
            },
            'unit_amount': 2000,  # $20.00
        },
        'quantity': 1,
    }],
    mode='payment',
    success_url='https://ainareports.com/success',
    cancel_url='https://ainareports.com/cancel',
    metadata={
        'document_ids': 'doc_123,doc_456'  # Comma-separated list
    }
)
```

Then the user can download with:

```bash
curl "https://api.ainaprotocol.com/uploads/documents/{document_id}/download?stripe_session_id={session_id}"
```

### Public Documents - Payment Intent

Alternatively, use Payment Intent metadata:

```python
payment_intent = stripe.PaymentIntent.create(
    amount=2000,
    currency='usd',
    metadata={
        'document_ids': 'doc_123,doc_456'
    }
)
```

Download with:

```bash
curl "https://api.ainaprotocol.com/uploads/documents/{document_id}/download?stripe_payment_intent_id={payment_intent_id}"
```

### Private Documents - Option 4: Permission-Based Access

If a user is authenticated and has document access permissions (via role-based access control), they can access the document:

```bash
curl -H "Authorization: Bearer {jwt_token}" \
  "https://api.ainaprotocol.com/uploads/documents/{document_id}/download"
```

**Note:** Owner access takes priority over permission-based access. If you're the owner, you'll always have access regardless of permissions.

## API Response

### Success Response

```json
{
  "document_id": "uuid-here",
  "download_url": "https://s3.amazonaws.com/...",
  "expires_in": 3600,
  "access_method": "free|authenticated|stripe_session|stripe_payment_intent",
  "is_public": true
}
```

### Error Responses

**403 Forbidden** (for private documents without owner access or permissions):
```json
{
  "detail": "Access denied. This document is private. Only the uploader or users with appropriate permissions can access this document."
}
```

**403 Forbidden** (if Stripe payment attempted on private document):
```json
{
  "detail": "Access denied. This document is private and cannot be purchased. Only the uploader or users with appropriate permissions can access this document."
}
```

**402 Payment Required** (for private documents with invalid payment):
```json
{
  "detail": "Payment verification failed. Please ensure your payment was completed successfully."
}
```

**429 Too Many Requests** (rate limit exceeded):
```json
{
  "detail": "Rate limit exceeded. Maximum 20 requests per 60 seconds."
}
```

**404 Not Found**:
```json
{
  "detail": "Document not found"
}
```

## Subscription Management

### Overview

Stripe is used for managing subscriptions for:
- **Users** (individual subscriptions)
- **Contractors** (business subscriptions)
- **AOAO Organizations** (business subscriptions)
- **Property Management Companies** (business subscriptions)

### Subscription Fields

Each subscription-enabled entity stores:
- `stripe_customer_id` - Stripe Customer ID
- `stripe_subscription_id` - Stripe Subscription ID
- `subscription_tier` - "free" or "paid"
- `subscription_status` - "active", "trialing", "canceled", "past_due", etc.

### Syncing Subscriptions

Use the sync endpoints to update subscription status from Stripe:

**Contractor:**
```bash
POST /contractors/{contractor_id}/sync-subscription
```

**AOAO Organization:**
```bash
POST /aoao-organizations/{organization_id}/sync-subscription
```

**PM Company:**
```bash
POST /pm-companies/{company_id}/sync-subscription
```

**User:**
```bash
POST /subscriptions/me/sync
```

These endpoints fetch the latest subscription status from Stripe and update the database.

### Webhook Processing

The `/stripe-webhooks/` endpoint automatically processes:
- Subscription creation/updates/deletions
- Payment success/failure events
- Updates subscription status in database automatically

## Financials & Revenue Tracking

### Overview

The financials endpoints provide revenue tracking and subscription analytics (Super Admin only).

### Revenue Summary

**Endpoint:** `GET /financials/revenue`

Returns:
- Subscription counts by type (users, contractors, AOAO, PM companies)
- Active paid subscriptions count
- Trial subscriptions count
- **Stripe revenue data** (if `STRIPE_SECRET_KEY` is configured):
  - Total revenue from paid invoices in the period
  - Recurring subscription revenue
  - Currency
  - Invoice count

**Example Request:**
```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://api.ainaprotocol.com/financials/revenue?start_date=2025-01-01T00:00:00Z&end_date=2025-12-31T23:59:59Z"
```

**Example Response:**
```json
{
  "period": {
    "start_date": "2025-01-01T00:00:00+00:00",
    "end_date": "2025-12-31T23:59:59+00:00"
  },
  "subscriptions": {
    "user_subscriptions": {"total": 10, "active_paid": 5, "trials": 2},
    "contractors": {"total": 5, "active_paid": 3, "trials": 1},
    "aoao_organizations": {"total": 3, "active_paid": 2, "trials": 0},
    "pm_companies": {"total": 4, "active_paid": 2, "trials": 1}
  },
  "summary": {
    "total_subscriptions": 22,
    "total_active_paid": 12,
    "total_trials": 4
  },
  "stripe": {
    "total_revenue": 50000,
    "total_revenue_decimal": 500.00,
    "subscription_revenue": 45000,
    "subscription_revenue_decimal": 450.00,
    "currency": "usd",
    "invoice_count": 5
  }
}
```

### Subscription Breakdown

**Endpoint:** `GET /financials/subscriptions/breakdown`

Returns detailed revenue information for each paid subscription:
- Individual subscription revenue (amount, currency, billing interval)
- Total monthly revenue (all subscriptions converted to monthly)
- Total annual revenue (all subscriptions converted to annual)

**Example Response:**
```json
{
  "success": true,
  "total_subscriptions": 12,
  "total_monthly_revenue": 120000,
  "total_monthly_revenue_decimal": 1200.00,
  "total_annual_revenue": 1440000,
  "total_annual_revenue_decimal": 14400.00,
  "subscriptions": [
    {
      "subscription_type": "contractor",
      "subscription_id": "uuid",
      "company_name": "ABC Contractors",
      "subscription_tier": "paid",
      "subscription_status": "active",
      "stripe_subscription_id": "sub_...",
      "revenue": {
        "amount": 5000,
        "amount_decimal": 50.00,
        "currency": "usd",
        "interval": "month",
        "status": "active"
      }
    }
  ]
}
```

**Note:** If `STRIPE_SECRET_KEY` is not configured, revenue data will show an error message but subscription counts will still be available.

## Implementation Details

### Files Created/Modified

1. **`core/stripe_helpers.py`** - Stripe integration functions
   - `verify_stripe_session()` - Verifies Checkout Session
   - `verify_stripe_payment_intent()` - Verifies Payment Intent
   - `verify_contractor_subscription()` - Verifies subscription status
   - `get_subscription_revenue()` - Gets revenue info for a subscription
   - `get_total_revenue_for_period()` - Gets total revenue from Stripe for a period

2. **`routers/stripe_webhooks.py`** - Webhook handler
   - Processes subscription events
   - Updates subscription status in database
   - Handles payment events

3. **`routers/financials.py`** - Financials endpoints (Super Admin only)
   - `/financials/revenue` - Revenue summary with Stripe integration
   - `/financials/subscriptions/breakdown` - Detailed subscription breakdown

4. **`core/rate_limiter.py`** - Rate limiting functionality
   - `require_rate_limit()` - Enforces rate limits
   - `get_rate_limit_identifier()` - Gets unique identifier (IP or user ID)

5. **`dependencies/auth.py`** - Added `get_optional_auth()` function
   - Returns `CurrentUser` if token provided, `None` otherwise
   - Does not raise exceptions for missing tokens

6. **`routers/uploads.py`** - Updated download endpoint
   - Implements hybrid access control
   - Supports all three access methods

### Access Control Flow

```
Document Request
    ↓
Is document public?
    ├─ YES → Stripe payment provided?
    │       ├─ YES → Verify payment → Allow if valid
    │       └─ NO → Rate limit check → Allow free access
    └─ NO (PRIVATE) → Is user authenticated?
            ├─ YES → Is user the owner (uploaded_by)?
            │       ├─ YES → Allow access (owner)
            │       └─ NO → Check permissions
            │               ├─ Has access → Allow (authenticated)
            │               └─ No access → Deny (403 Forbidden)
            └─ NO → Deny (403 Forbidden)
                    NOTE: Stripe payments NOT allowed for private docs
```

## Testing

### Test Free Document Access

```bash
# Should work without auth
curl "http://localhost:8000/uploads/documents/{free_doc_id}/download"
```

### Test Private Document as Owner

```bash
# Upload a document first (sets you as owner)
# Then download with your auth token
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/uploads/documents/{doc_id}/download"
```

### Test Private Document with Stripe

1. Create a test Stripe Checkout Session with document ID in metadata
2. Complete the payment
3. Use the session ID to download:

```bash
curl "http://localhost:8000/uploads/documents/{doc_id}/download?stripe_session_id={session_id}"
```

### Test Authenticated Access

```bash
# Get auth token first
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r '.access_token')

# Use token to download
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/uploads/documents/{doc_id}/download"
```

## Production Considerations

1. **Rate Limiting**: The current implementation uses in-memory storage. For production with multiple instances, consider:
   - Redis-based rate limiting
   - Dedicated rate limiting service (e.g., Cloudflare, AWS WAF)

2. **Stripe Webhooks**: Consider implementing webhook handlers to:
   - Track successful payments
   - Update document access records
   - Handle refunds

3. **Caching**: Consider caching document metadata and access checks for better performance

4. **Monitoring**: Add logging and metrics for:
   - Payment verification success/failure rates
   - Rate limit hits
   - Access method distribution

## Troubleshooting

### "Stripe not configured" warning

- Ensure `STRIPE_SECRET_KEY` is set in environment variables
- The endpoint will still work for free documents and authenticated users
- Financials endpoints will return error messages but won't crash

### Payment verification fails

- Check that session/payment intent status is "paid" and "complete"
- Verify document ID is in session/payment intent metadata
- Check Stripe dashboard for payment status

### Subscription sync fails

- Verify `stripe_customer_id` or `stripe_subscription_id` is set in database
- Check Stripe dashboard to ensure subscription exists
- Verify `STRIPE_SECRET_KEY` is correct and has proper permissions

### Revenue data not showing

- Ensure `STRIPE_SECRET_KEY` is configured
- Check that subscriptions have valid `stripe_subscription_id` or `stripe_customer_id`
- Verify Stripe API key has read access to subscriptions and invoices
- Check server logs for Stripe API errors

### Webhook not processing

- Verify `STRIPE_WEBHOOK_SECRET` is set correctly
- Check webhook endpoint URL is accessible
- Verify webhook events are selected in Stripe Dashboard
- Check server logs for webhook processing errors

### Rate limit issues

- Free documents: 20 requests per minute per IP/user
- Adjust limits in `routers/uploads.py` if needed
- Consider user-based rate limiting for authenticated users

