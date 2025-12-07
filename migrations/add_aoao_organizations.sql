-- Migration: Create aoao_organizations table
-- AOAO organizations are business entities (like contractors) that can have subscriptions

CREATE TABLE IF NOT EXISTS aoao_organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_name TEXT NOT NULL UNIQUE,
    phone TEXT,
    email TEXT,
    website TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    contact_person TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    notes TEXT,
    
    -- Subscription fields
    subscription_tier TEXT NOT NULL DEFAULT 'free' CHECK (subscription_tier IN ('free', 'paid')),
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    subscription_status TEXT CHECK (subscription_status IN ('active', 'canceled', 'past_due', 'unpaid', 'trialing', 'incomplete', 'incomplete_expired')),
    
    -- Trial tracking (stored in subscription_status='trialing' and can track dates if needed)
    -- Note: Trial dates can be tracked via created_at + subscription_status, or add explicit fields if needed
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_aoao_organizations_subscription_tier ON aoao_organizations(subscription_tier);
CREATE INDEX IF NOT EXISTS idx_aoao_organizations_stripe_customer_id ON aoao_organizations(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_aoao_organizations_stripe_subscription_id ON aoao_organizations(stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_aoao_organizations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_aoao_organizations_updated_at ON aoao_organizations;
CREATE TRIGGER update_aoao_organizations_updated_at
    BEFORE UPDATE ON aoao_organizations
    FOR EACH ROW
    EXECUTE FUNCTION update_aoao_organizations_updated_at();

-- Add comments
COMMENT ON TABLE aoao_organizations IS 'AOAO organizations (business entities) that can have subscriptions. Users can be linked to organizations via aoao_organization_id in user metadata.';
COMMENT ON COLUMN aoao_organizations.subscription_tier IS 'Subscription tier: "free" or "paid"';
COMMENT ON COLUMN aoao_organizations.subscription_status IS 'Stripe subscription status';

