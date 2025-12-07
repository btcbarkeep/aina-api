# Role-Based Subscription Guide

## Overview

The API now supports role-based subscriptions with the following rules:

1. **AOAO Role** - Must be paid (but supports free trials)
2. **Other Roles** (property_manager, contractor, owner) - Can have both free and paid tiers
3. **Admin Roles** (admin, super_admin) - No subscription required

## Database Schema

### `user_subscriptions` Table

Tracks subscription status for each user role:

- `id` - UUID primary key
- `user_id` - References `auth.users(id)`
- `role` - User role (aoao, property_manager, contractor, owner, etc.)
- `subscription_tier` - "free" or "paid"
- `subscription_status` - Stripe subscription status (active, canceled, past_due, etc.)
- `stripe_customer_id` - Stripe customer ID
- `stripe_subscription_id` - Stripe subscription ID
- `is_trial` - Whether subscription is in trial period
- `trial_started_at` - When trial started
- `trial_ends_at` - When trial ends
- `created_at`, `updated_at` - Timestamps

**Unique Constraint:** One subscription per user per role (`UNIQUE(user_id, role)`)

## Migration

Run the migration to create the table:

```sql
-- See migrations/add_user_subscriptions.sql
```

## API Endpoints

### Get My Subscriptions

```bash
GET /subscriptions/me
GET /subscriptions/me?role=aoao
```

Returns all subscriptions for the current user, optionally filtered by role.

### Get My Subscription by Role

```bash
GET /subscriptions/me/{role}
```

Returns subscription for a specific role.

### Sync Subscription from Stripe

```bash
POST /subscriptions/me/{role}/sync
```

Manually syncs subscription status from Stripe.

### Start Free Trial (Self-Service)

```bash
POST /subscriptions/me/start-trial?trial_days=14
```

**Users can start their own free trial** (per-user subscription).

- Automatically uses the authenticated user's role from their token
- Creates a subscription record **specifically for this user** in the `user_subscriptions` table
- **Does NOT affect other users** with the same role - each user has their own independent subscription
- Default trial duration is 14 days (1-180 days allowed)

**Important:** This is a per-user subscription, not a per-role subscription. Each user must start their own trial.

### Admin: Grant Free Trial to User

```bash
POST /subscriptions/users/{user_id}/start-trial?trial_days=14&role=property_manager
```

**Admin-only endpoint to grant a free trial to a specific user.**

- **Admin/Super Admin only** - requires admin authentication
- If `role` is not provided, automatically fetches the user's role from their metadata
- Creates a subscription record for the specified user
- Default trial duration is 14 days (1-180 days allowed)

**Example:**
```bash
# Grant 30-day trial to a user (auto-detects their role)
POST /subscriptions/users/7eaaa4b8-7067-4f89-975b-4ce2c85393db/start-trial?trial_days=30

# Grant trial for a specific role
POST /subscriptions/users/7eaaa4b8-7067-4f89-975b-4ce2c85393db/start-trial?trial_days=30&role=property_manager
```

**Requirements:**
- Role must support trials
- User must not already have an active paid subscription
- User must not already have an active trial

### Admin: Get User Subscriptions

```bash
GET /subscriptions/users/{user_id}
GET /subscriptions/users/{user_id}?role=aoao
```

Admin-only endpoint to view any user's subscriptions.

## Role Subscription Requirements

### AOAO Role

- **Requires Paid:** Yes
- **Supports Trial:** Yes
- **Supports Free Tier:** No

Users with AOAO role must have a paid subscription or be in an active trial period.

### Property Manager, Contractor, Owner Roles

- **Requires Paid:** No
- **Supports Trial:** Yes
- **Supports Free Tier:** Yes

These roles can operate on either free or paid tiers.

### Admin Roles

- **Requires Paid:** No
- **Supports Trial:** No
- **Supports Free Tier:** Yes

Admin roles don't require subscriptions.

## Stripe Integration

### Webhook Setup

1. Configure webhook endpoint in Stripe Dashboard:
   ```
   https://your-api.com/webhooks/stripe/subscription
   ```

2. Select events:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `customer.subscription.trial_will_end`

3. Add webhook signing secret to environment:
   ```bash
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

### Webhook Processing

The webhook automatically:
- Updates contractor subscriptions (if `stripe_customer_id` matches)
- Updates user subscriptions (if `stripe_customer_id` matches)
- Handles subscription status changes (active, canceled, past_due, etc.)
- Handles trial status

## Subscription Validation

Use `validate_role_subscription()` from `core.role_subscriptions` to check if a user's subscription meets role requirements:

```python
from core.role_subscriptions import validate_role_subscription

is_valid, error_message = validate_role_subscription(
    role="aoao",
    subscription_tier="paid",
    subscription_status="active",
    is_trial=False
)
```

## Trial Management

Trials are automatically tracked and validated:

- Trial start date is recorded
- Trial end date is checked on validation
- Expired trials are automatically marked as inactive
- AOAO role requires paid subscription after trial expires

## Example: Starting a Trial

```bash
# Start 14-day trial for current user's role (max 180 days)
# Automatically uses the authenticated user's role
curl -X POST "https://api.ainaprotocol.com/subscriptions/me/start-trial?trial_days=14" \
  -H "Authorization: Bearer {token}"
```

Response:
```json
{
  "id": "uuid",
  "user_id": "user-uuid",
  "role": "aoao",
  "subscription_tier": "paid",
  "subscription_status": "trialing",
  "is_trial": true,
  "trial_started_at": "2024-01-01T00:00:00Z",
  "trial_ends_at": "2024-01-15T00:00:00Z"
}
```

## Example: Syncing from Stripe

```bash
# Sync subscription status from Stripe
curl -X POST "https://api.ainaprotocol.com/subscriptions/me/aoao/sync" \
  -H "Authorization: Bearer {token}"
```

This will:
1. Fetch current subscription status from Stripe
2. Update the database record
3. Return the updated subscription

## Integration with CurrentUser

The `CurrentUser` model now includes optional subscription fields:

- `subscription_tier` - "free" or "paid"
- `subscription_status` - Stripe status
- `is_trial` - Whether in trial
- `trial_ends_at` - Trial end date

These fields are populated when subscription data is fetched (not automatically on every request for performance).

## Next Steps

1. **Run Migration:** Execute `migrations/add_user_subscriptions.sql`
2. **Configure Stripe Webhook:** Set up webhook endpoint in Stripe Dashboard
3. **Update Frontend:** Use subscription endpoints to check user subscription status
4. **Add Validation:** Optionally add subscription checks to protected endpoints

## Files Created/Modified

### New Files
- `migrations/add_user_subscriptions.sql` - Database migration
- `models/subscription.py` - Subscription Pydantic models
- `core/role_subscriptions.py` - Role subscription requirements and validation
- `core/subscription_helpers.py` - Helper functions for subscription management
- `routers/subscriptions.py` - Subscription management endpoints

### Modified Files
- `dependencies/auth.py` - Added subscription fields to `CurrentUser`
- `routers/stripe_webhooks.py` - Added user subscription handling
- `main.py` - Registered subscription and webhook routers
- `models/enums.py` - Added `SubscriptionTier` and `SubscriptionStatus` enums

