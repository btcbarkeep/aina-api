# Subscription Architecture

## Overview

There are **two types of subscriptions** in the system:

1. **Contractor Company Subscriptions** (`contractors` table)
   - For business entities/companies (e.g., "Burger's Plumbing")
   - When a company pays, it's stored in the `contractors` table
   - All users linked to that company inherit access

2. **User Role Subscriptions** (`user_subscriptions` table)
   - For individual users based on their role
   - Stored per user per role
   - Independent of company subscriptions

## The Relationship

- **Contractors** are business entities in the `contractors` table
- **Users** are individuals in `auth.users`
- Users with role "contractor" can be linked to a contractor company via `contractor_id` in their metadata
- A contractor company can have multiple users linked to it

## Subscription Priority (for contractor users)

When checking if a user with role "contractor" has access:

1. **First**: Check if their linked contractor company has a paid subscription
   - If yes → user has access (inherited from company)
   - If no → continue to step 2

2. **Second**: Check if the user has an individual subscription for their "contractor" role
   - If yes → user has access (individual subscription)
   - If no → user does not have access

## Use Cases

### Use Case 1: Company Pays
- Company "Burger's Plumbing" subscribes (stored in `contractors` table)
- All users linked to that company get access automatically
- No need for individual user subscriptions

### Use Case 2: Individual User Pays
- User John has role "contractor" but is not linked to a company (or company doesn't have subscription)
- John subscribes individually (stored in `user_subscriptions` table)
- Only John gets access

### Use Case 3: Both Company and Individual
- Company has subscription → all users get access
- Individual user also has subscription → redundant but harmless
- Company subscription takes precedence

## Is This Duplication?

**No, it's intentional flexibility:**

- **Contractor subscriptions** = company-level billing (one payment covers all employees)
- **User subscriptions** = individual-level billing (each user pays separately)

This allows for:
- B2B scenarios (companies pay for their team)
- B2C scenarios (individual contractors pay for themselves)
- Hybrid scenarios (some users covered by company, others pay individually)

## Recommendation

Keep both subscription types. The system checks company subscription first, then falls back to individual subscription. This provides maximum flexibility without duplication issues.

