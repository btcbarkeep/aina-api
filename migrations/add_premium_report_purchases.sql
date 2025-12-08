-- Migration: Create premium_report_purchases table
-- Tracks premium report purchases from ainaprotocol.com via Stripe

CREATE TABLE IF NOT EXISTS premium_report_purchases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_email TEXT NOT NULL,
    customer_name TEXT,
    report_type TEXT NOT NULL, -- e.g., 'building', 'unit', 'contractor', 'custom'
    report_id TEXT, -- ID of the generated report (if stored)
    building_id UUID REFERENCES buildings(id) ON DELETE SET NULL,
    unit_id UUID REFERENCES units(id) ON DELETE SET NULL,
    contractor_id UUID REFERENCES contractors(id) ON DELETE SET NULL,
    stripe_session_id TEXT UNIQUE, -- Stripe Checkout Session ID
    stripe_payment_intent_id TEXT UNIQUE, -- Stripe Payment Intent ID
    stripe_customer_id TEXT, -- Stripe Customer ID
    amount_cents INTEGER NOT NULL, -- Amount in cents
    amount_decimal NUMERIC(10, 2) NOT NULL, -- Amount in dollars
    currency TEXT DEFAULT 'usd',
    payment_status TEXT DEFAULT 'pending', -- 'pending', 'paid', 'failed', 'refunded'
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_premium_report_purchases_customer_email ON premium_report_purchases(customer_email);
CREATE INDEX IF NOT EXISTS idx_premium_report_purchases_report_type ON premium_report_purchases(report_type);
CREATE INDEX IF NOT EXISTS idx_premium_report_purchases_purchased_at ON premium_report_purchases(purchased_at DESC);
CREATE INDEX IF NOT EXISTS idx_premium_report_purchases_payment_status ON premium_report_purchases(payment_status);
CREATE INDEX IF NOT EXISTS idx_premium_report_purchases_stripe_session_id ON premium_report_purchases(stripe_session_id);
CREATE INDEX IF NOT EXISTS idx_premium_report_purchases_stripe_payment_intent_id ON premium_report_purchases(stripe_payment_intent_id);

-- RLS policies
ALTER TABLE premium_report_purchases ENABLE ROW LEVEL SECURITY;

-- Admins can read all premium report purchases
CREATE POLICY "Admins can view all premium report purchases" ON premium_report_purchases
FOR SELECT USING (
    EXISTS (SELECT 1 FROM auth.users WHERE id = auth.uid() AND (raw_user_meta_data->>'role' = 'admin' OR raw_user_meta_data->>'role' = 'super_admin'))
);

-- System can insert premium report purchases (via webhook or API)
CREATE POLICY "System can create premium report purchases" ON premium_report_purchases
FOR INSERT WITH CHECK (true); -- Allow inserts (webhook/API will handle auth)

-- Admins can update premium report purchases
CREATE POLICY "Admins can update premium report purchases" ON premium_report_purchases
FOR UPDATE USING (
    EXISTS (SELECT 1 FROM auth.users WHERE id = auth.uid() AND (raw_user_meta_data->>'role' = 'admin' OR raw_user_meta_data->>'role' = 'super_admin'))
);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_premium_report_purchases_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_premium_report_purchases_updated_at ON premium_report_purchases;
CREATE TRIGGER update_premium_report_purchases_updated_at
    BEFORE UPDATE ON premium_report_purchases
    FOR EACH ROW
    EXECUTE FUNCTION update_premium_report_purchases_updated_at();

-- Comments
COMMENT ON TABLE premium_report_purchases IS 'Tracks premium report purchases from ainaprotocol.com via Stripe payments';
COMMENT ON COLUMN premium_report_purchases.report_type IS 'Type of report: building, unit, contractor, custom';
COMMENT ON COLUMN premium_report_purchases.stripe_session_id IS 'Stripe Checkout Session ID (unique)';
COMMENT ON COLUMN premium_report_purchases.stripe_payment_intent_id IS 'Stripe Payment Intent ID (unique, alternative to session)';
COMMENT ON COLUMN premium_report_purchases.amount_cents IS 'Payment amount in cents';
COMMENT ON COLUMN premium_report_purchases.amount_decimal IS 'Payment amount in dollars (for display)';

