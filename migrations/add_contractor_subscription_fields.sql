-- Migration: Add subscription tier fields to contractors table
-- This enables paid/free tier support for contractors with Stripe integration

ALTER TABLE contractors
ADD COLUMN IF NOT EXISTS subscription_tier TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'paid')),
ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT,
ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT,
ADD COLUMN IF NOT EXISTS subscription_status TEXT CHECK (subscription_status IN ('active', 'canceled', 'past_due', 'unpaid', 'trialing', 'incomplete', 'incomplete_expired'));

-- Add comments for documentation
COMMENT ON COLUMN contractors.subscription_tier IS 'Contractor subscription tier: "free" or "paid" (defaults to "free")';
COMMENT ON COLUMN contractors.stripe_customer_id IS 'Stripe customer ID for paid subscriptions';
COMMENT ON COLUMN contractors.stripe_subscription_id IS 'Stripe subscription ID for paid subscriptions';
COMMENT ON COLUMN contractors.subscription_status IS 'Stripe subscription status (e.g., "active", "canceled", "past_due")';

-- Create index for faster queries by subscription tier
CREATE INDEX IF NOT EXISTS idx_contractors_subscription_tier ON contractors(subscription_tier);
CREATE INDEX IF NOT EXISTS idx_contractors_stripe_customer_id ON contractors(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contractors_stripe_subscription_id ON contractors(stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

