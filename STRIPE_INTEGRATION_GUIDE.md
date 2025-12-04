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
STRIPE_SECRET_KEY=sk_test_...  # Your Stripe secret key
STRIPE_WEBHOOK_SECRET=whsec_...  # Optional: for webhook verification
```

### 2. Install Dependencies

The Stripe SDK has been added to `requirements.txt`. Install with:

```bash
pip install -r requirements.txt
```

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

## Implementation Details

### Files Created/Modified

1. **`core/stripe_helpers.py`** - Stripe payment verification functions
   - `verify_stripe_session()` - Verifies Checkout Session
   - `verify_stripe_payment_intent()` - Verifies Payment Intent

2. **`core/rate_limiter.py`** - Rate limiting functionality
   - `require_rate_limit()` - Enforces rate limits
   - `get_rate_limit_identifier()` - Gets unique identifier (IP or user ID)

3. **`dependencies/auth.py`** - Added `get_optional_auth()` function
   - Returns `CurrentUser` if token provided, `None` otherwise
   - Does not raise exceptions for missing tokens

4. **`routers/uploads.py`** - Updated download endpoint
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

### Payment verification fails

- Check that session/payment intent status is "paid" and "complete"
- Verify document ID is in session/payment intent metadata
- Check Stripe dashboard for payment status

### Rate limit issues

- Free documents: 20 requests per minute per IP/user
- Adjust limits in `routers/uploads.py` if needed
- Consider user-based rate limiting for authenticated users

