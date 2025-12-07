# Testing Checklist - Business Subscription Architecture

## Pre-Testing Setup

1. **Run Database Migrations:**
   ```sql
   -- Run in order:
   migrations/add_aoao_organizations.sql
   migrations/add_property_management_companies.sql
   migrations/add_user_subscriptions.sql (if not already run)
   ```

2. **Verify Environment Variables:**
   - `STRIPE_SECRET_KEY` - For subscription verification
   - `STRIPE_WEBHOOK_SECRET` - For webhook signature verification
   - `TRIAL_SELF_SERVICE_MAX_DAYS` - Default: 14
   - `TRIAL_ADMIN_MAX_DAYS` - Default: 180

## Testing Scenarios

### 1. Business Entity Creation

**Test AOAO Organizations:**
- [ ] `POST /aoao-organizations` - Create organization
- [ ] Verify organization appears in `GET /aoao-organizations`
- [ ] Verify duplicate organization names are rejected
- [ ] Verify subscription_tier defaults to "free"

**Test PM Companies:**
- [ ] `POST /pm-companies` - Create company
- [ ] Verify company appears in `GET /pm-companies`
- [ ] Verify duplicate company names are rejected
- [ ] Verify subscription_tier defaults to "free"

**Test Contractors:**
- [ ] Verify existing contractor creation still works
- [ ] Verify subscription fields are present

### 2. User Creation & Linking

**Test User with Contractor:**
- [ ] `POST /admin/create-account` with `contractor_id`
- [ ] Verify contractor_id is stored in user metadata
- [ ] Verify contractor exists validation works (try invalid ID)
- [ ] Verify user can access their contractor via `GET /contractors/{id}`

**Test User with AOAO Organization:**
- [ ] `POST /admin/create-account` with `aoao_organization_id`
- [ ] Verify aoao_organization_id is stored in user metadata
- [ ] Verify organization exists validation works (try invalid ID)
- [ ] Verify user can access their organization via `GET /aoao-organizations/{id}`

**Test User with PM Company:**
- [ ] `POST /admin/create-account` with `pm_company_id`
- [ ] Verify pm_company_id is stored in user metadata
- [ ] Verify company exists validation works (try invalid ID)
- [ ] Verify user can access their company via `GET /pm-companies/{id}`

**Test User Updates:**
- [ ] `PATCH /admin/users/{id}` to add organization IDs
- [ ] `PATCH /admin/users/{id}` to change organization IDs
- [ ] `PATCH /admin/users/{id}` to remove organization IDs (set to null)
- [ ] Verify validation prevents invalid organization IDs

### 3. Trial Endpoints

**Test Business Trials (Admin Only):**
- [ ] `POST /subscriptions/contractors/{id}/start-trial?trial_days=30`
- [ ] `POST /subscriptions/aoao-organizations/{id}/start-trial?trial_days=30`
- [ ] `POST /subscriptions/pm-companies/{id}/start-trial?trial_days=30`
- [ ] Verify non-admin users get 403 error
- [ ] Verify trial limits are enforced (max 180 days for admin)
- [ ] Verify subscription_status is set to "trialing"
- [ ] Verify subscription_tier is set to "paid"

**Test User Trials:**
- [ ] `POST /subscriptions/me/start-trial?trial_days=14` (self-service)
- [ ] `POST /subscriptions/users/{id}/start-trial?trial_days=30` (admin)
- [ ] Verify self-service limit (max 14 days)
- [ ] Verify admin can grant longer trials (up to 180 days)
- [ ] Verify duplicate trial attempts are rejected

### 4. Subscription Validation

**Test Organization Subscription Inheritance:**
- [ ] Create contractor with paid subscription
- [ ] Create user linked to that contractor
- [ ] Verify user inherits access (subscription check returns true)
- [ ] Repeat for AOAO organization
- [ ] Repeat for PM company

**Test Individual User Subscriptions:**
- [ ] Create user without organization link
- [ ] Grant individual subscription
- [ ] Verify subscription check works
- [ ] Test that organization subscription takes precedence over individual

### 5. Access Control

**Test AOAO Organization Access:**
- [ ] AOAO user can access their own organization
- [ ] AOAO user cannot access other organizations
- [ ] Admin can access all organizations

**Test PM Company Access:**
- [ ] Property manager can access their own company
- [ ] Property manager cannot access other companies
- [ ] Admin can access all companies

**Test Contractor Access:**
- [ ] Verify existing contractor access control still works

### 6. Sync Endpoints

**Test Subscription Sync:**
- [ ] `POST /contractors/{id}/sync-subscription`
- [ ] `POST /aoao-organizations/{id}/sync-subscription`
- [ ] `POST /pm-companies/{id}/sync-subscription`
- [ ] `POST /subscriptions/me/sync` (user subscription)
- [ ] Verify all sync endpoints work with valid Stripe IDs
- [ ] Verify error handling for missing Stripe IDs

### 7. Stripe Webhook

**Test Webhook Handling:**
- [ ] Send test webhook for contractor subscription
- [ ] Send test webhook for AOAO organization subscription
- [ ] Send test webhook for PM company subscription
- [ ] Send test webhook for user subscription
- [ ] Verify all entity types are updated correctly
- [ ] Verify webhook signature validation works

### 8. Edge Cases

**Test Invalid References:**
- [ ] Try to create user with non-existent contractor_id
- [ ] Try to create user with non-existent aoao_organization_id
- [ ] Try to create user with non-existent pm_company_id
- [ ] Verify all return 400 errors with clear messages

**Test Role/Organization Mismatch:**
- [ ] Try to link contractor_id to AOAO user (should work, but verify behavior)
- [ ] Try to link aoao_organization_id to contractor user (should work, but verify behavior)
- [ ] Consider if you want to add validation to prevent mismatches

**Test Multiple Organization Links:**
- [ ] Try to link user to both contractor AND AOAO organization
- [ ] Verify system handles this gracefully (currently allowed)
- [ ] Consider if you want to restrict to one organization type per user

### 9. User Listing & Retrieval

**Test Admin Endpoints:**
- [ ] `GET /admin/users` - Verify organization IDs are returned
- [ ] `GET /admin/users/{id}` - Verify organization IDs are returned
- [ ] Filter users by organization (if needed in future)

### 10. Subscription Status Checks

**Test Subscription Status:**
- [ ] Verify users with organization subscriptions can access protected endpoints
- [ ] Verify users with individual subscriptions can access protected endpoints
- [ ] Verify users without subscriptions are blocked (for AOAO role)
- [ ] Verify free tier users can access (for property_manager, contractor, owner)

## Common Issues to Watch For

1. **UUID Format Issues:**
   - Ensure all IDs are valid UUIDs
   - Check for string vs UUID object mismatches

2. **Metadata Storage:**
   - Verify organization IDs are stored correctly in user_metadata
   - Check that null values are handled properly

3. **Access Control:**
   - Verify users can only access their own organization
   - Verify admins can access everything

4. **Subscription Inheritance:**
   - Verify organization subscriptions are checked first
   - Verify individual subscriptions are checked as fallback

5. **Trial Limits:**
   - Verify self-service limit (14 days) is enforced
   - Verify admin limit (180 days) is enforced
   - Verify error messages are clear

## Recommended Test Order

1. **Database Setup** - Run migrations
2. **Business Entity Creation** - Create test organizations/companies
3. **User Creation** - Create users linked to organizations
4. **Access Control** - Verify users can only access their own org
5. **Trial Endpoints** - Test granting trials
6. **Subscription Validation** - Test inheritance
7. **Sync Endpoints** - Test manual sync
8. **Webhook** - Test Stripe webhook (if Stripe is configured)

## Success Criteria

✅ All business entities can be created  
✅ Users can be linked to organizations  
✅ Organization IDs are validated on user creation/update  
✅ Access control works correctly  
✅ Trials can be granted to all business types  
✅ Subscription inheritance works  
✅ Sync endpoints work for all business types  
✅ Webhook handles all entity types  
✅ No linter errors  
✅ All endpoints return appropriate status codes  

## Notes

- Organization IDs are stored in `auth.users.user_metadata` (JSON), not in a separate table
- This means you can't use database foreign keys, so validation is done in application code
- Consider adding database-level validation if needed in the future
- All three business types (contractors, AOAO orgs, PM companies) work identically

