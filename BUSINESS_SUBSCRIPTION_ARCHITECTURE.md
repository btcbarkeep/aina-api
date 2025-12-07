# Business Subscription Architecture

## Overview

The system now supports **two types of subscriptions**:

1. **Business/Organization Subscriptions** - For companies/organizations (contractors, AOAO orgs, PM companies)
2. **Individual User Subscriptions** - For individual users (owners, admins, etc.)

## Business Entities

Three business entity types can have subscriptions:

### 1. Contractors (`contractors` table)
- Business entities (e.g., "Burger's Plumbing")
- Have subscription fields: `subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`
- Users can be linked via `contractor_id` in user metadata

### 2. AOAO Organizations (`aoao_organizations` table)
- Business entities (e.g., "ABC AOAO Management")
- Have subscription fields: `subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`
- Users can be linked via `aoao_organization_id` in user metadata

### 3. Property Management Companies (`property_management_companies` table)
- Business entities (e.g., "XYZ Property Management")
- Have subscription fields: `subscription_tier`, `stripe_customer_id`, `stripe_subscription_id`, `subscription_status`
- Users can be linked via `pm_company_id` in user metadata

## Individual Users

Users with these roles are **individual** (not tied to businesses):
- `admin` - No subscription required
- `super_admin` - No subscription required
- `owner` - Can have individual subscription

Users with these roles are **business-linked** (can inherit from organization):
- `contractor` - Linked via `contractor_id`
- `aoao` - Linked via `aoao_organization_id`
- `property_manager` - Linked via `pm_company_id`

## Subscription Priority

When checking if a user has access:

1. **First**: Check if their linked business/organization has a paid subscription
   - If yes → user has access (inherited from organization)
   - If no → continue to step 2

2. **Second**: Check if the user has an individual subscription
   - If yes → user has access (individual subscription)
   - If no → user does not have access

## Trial Endpoints

### Business Trials (Admin Only)

```bash
# Grant trial to contractor
POST /subscriptions/contractors/{contractor_id}/start-trial?trial_days=30

# Grant trial to AOAO organization
POST /subscriptions/aoao-organizations/{organization_id}/start-trial?trial_days=30

# Grant trial to PM company
POST /subscriptions/pm-companies/{company_id}/start-trial?trial_days=30
```

**Admin limits:** 1-180 days (configurable via `TRIAL_ADMIN_MAX_DAYS`)

### Individual User Trials

```bash
# User starts their own trial
POST /subscriptions/me/start-trial?trial_days=14

# Admin grants trial to user
POST /subscriptions/users/{user_id}/start-trial?trial_days=30
```

**Self-service limits:** 1-14 days (configurable via `TRIAL_SELF_SERVICE_MAX_DAYS`)  
**Admin limits:** 1-180 days (configurable via `TRIAL_ADMIN_MAX_DAYS`)

## API Endpoints

### AOAO Organizations

- `GET /aoao-organizations` - List all (admin only)
- `GET /aoao-organizations/{id}` - Get one
- `POST /aoao-organizations` - Create (admin only)
- `PATCH /aoao-organizations/{id}` - Update (admin only)
- `DELETE /aoao-organizations/{id}` - Delete (admin only)

### Property Management Companies

- `GET /pm-companies` - List all (admin only)
- `GET /pm-companies/{id}` - Get one
- `POST /pm-companies` - Create (admin only)
- `PATCH /pm-companies/{id}` - Update (admin only)
- `DELETE /pm-companies/{id}` - Delete (admin only)

## Database Migrations

Run these migrations in order:

1. `migrations/add_aoao_organizations.sql` - Creates `aoao_organizations` table
2. `migrations/add_property_management_companies.sql` - Creates `property_management_companies` table
3. `migrations/add_user_subscriptions.sql` - Creates `user_subscriptions` table (if not already run)

**Note:** User organization links (`aoao_organization_id`, `pm_company_id`) are stored in `auth.users.user_metadata` as JSON fields, not in a separate table.

## User Metadata Fields

Users can have these organization links in their metadata:
- `contractor_id` - Links to `contractors` table
- `aoao_organization_id` - Links to `aoao_organizations` table
- `pm_company_id` - Links to `property_management_companies` table

## Example Workflow

1. **Create AOAO Organization:**
   ```bash
   POST /aoao-organizations
   {
     "organization_name": "ABC AOAO Management",
     "email": "info@abc-aoao.com"
   }
   ```

2. **Create User Linked to Organization:**
   ```bash
   POST /admin/users
   {
     "email": "john@abc-aoao.com",
     "role": "aoao",
     "aoao_organization_id": "org-uuid-here"
   }
   ```

3. **Grant Trial to Organization:**
   ```bash
   POST /subscriptions/aoao-organizations/{org_id}/start-trial?trial_days=30
   ```

4. **All users linked to that organization now have access** (inherited from organization subscription)

## Benefits

- **B2B Support**: Organizations can pay for their entire team
- **B2C Support**: Individual users can pay for themselves
- **Flexibility**: Users can inherit from organization OR have individual subscriptions
- **Consistent Model**: All business entities (contractors, AOAO orgs, PM companies) work the same way

