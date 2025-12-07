-- Migration: Add user subscription support for role-based tiers
-- This enables paid/free tier support for user roles (AOAO, property_manager, contractor, owner)

-- Create user_subscriptions table
CREATE TABLE IF NOT EXISTS user_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('aoao', 'property_manager', 'contractor', 'owner', 'aoao_staff', 'contractor_staff')),
    subscription_tier TEXT NOT NULL DEFAULT 'free' CHECK (subscription_tier IN ('free', 'paid')),
    subscription_status TEXT CHECK (subscription_status IN ('active', 'canceled', 'past_due', 'unpaid', 'trialing', 'incomplete', 'incomplete_expired')),
    
    -- Stripe integration
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    
    -- Trial support (especially for AOAO role)
    is_trial BOOLEAN DEFAULT FALSE,
    trial_started_at TIMESTAMPTZ,
    trial_ends_at TIMESTAMPTZ,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Ensure one subscription per user per role
    UNIQUE(user_id, role)
);

-- Add comments for documentation
COMMENT ON TABLE user_subscriptions IS 'Tracks subscription status for user roles. AOAO role requires paid subscription (with trial support). Other roles support both free and paid tiers.';
COMMENT ON COLUMN user_subscriptions.role IS 'User role that this subscription applies to';
COMMENT ON COLUMN user_subscriptions.subscription_tier IS 'Subscription tier: "free" or "paid"';
COMMENT ON COLUMN user_subscriptions.subscription_status IS 'Stripe subscription status (e.g., "active", "canceled", "past_due")';
COMMENT ON COLUMN user_subscriptions.stripe_customer_id IS 'Stripe customer ID for paid subscriptions';
COMMENT ON COLUMN user_subscriptions.stripe_subscription_id IS 'Stripe subscription ID for paid subscriptions';
COMMENT ON COLUMN user_subscriptions.is_trial IS 'Whether the subscription is currently in trial period';
COMMENT ON COLUMN user_subscriptions.trial_started_at IS 'When the trial period started';
COMMENT ON COLUMN user_subscriptions.trial_ends_at IS 'When the trial period ends';

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_id ON user_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_role ON user_subscriptions(role);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_subscription_tier ON user_subscriptions(subscription_tier);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_stripe_customer_id ON user_subscriptions(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_stripe_subscription_id ON user_subscriptions(stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_trial ON user_subscriptions(is_trial, trial_ends_at) WHERE is_trial = TRUE;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_user_subscriptions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_user_subscriptions_updated_at ON user_subscriptions;
CREATE TRIGGER update_user_subscriptions_updated_at
    BEFORE UPDATE ON user_subscriptions
    FOR EACH ROW
    EXECUTE FUNCTION update_user_subscriptions_updated_at();

