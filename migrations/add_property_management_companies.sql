-- Migration: Create property_management_companies table
-- Property management companies are business entities (like contractors) that can have subscriptions

CREATE TABLE IF NOT EXISTS property_management_companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL UNIQUE,
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
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_pm_companies_subscription_tier ON property_management_companies(subscription_tier);
CREATE INDEX IF NOT EXISTS idx_pm_companies_stripe_customer_id ON property_management_companies(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pm_companies_stripe_subscription_id ON property_management_companies(stripe_subscription_id) WHERE stripe_subscription_id IS NOT NULL;

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_pm_companies_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_pm_companies_updated_at ON property_management_companies;
CREATE TRIGGER update_pm_companies_updated_at
    BEFORE UPDATE ON property_management_companies
    FOR EACH ROW
    EXECUTE FUNCTION update_pm_companies_updated_at();

-- Add comments
COMMENT ON TABLE property_management_companies IS 'Property management companies (business entities) that can have subscriptions. Users can be linked to companies via pm_company_id in user metadata.';
COMMENT ON COLUMN property_management_companies.subscription_tier IS 'Subscription tier: "free" or "paid"';
COMMENT ON COLUMN property_management_companies.subscription_status IS 'Stripe subscription status';

