-- Migration: Fix RLS policies for premium_report_purchases table
-- This removes the problematic RLS policies that query auth.users directly
-- and disables RLS (access is controlled at API level)

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Admins can view all premium report purchases" ON premium_report_purchases;
DROP POLICY IF EXISTS "System can create premium report purchases" ON premium_report_purchases;
DROP POLICY IF EXISTS "Admins can update premium report purchases" ON premium_report_purchases;

-- Disable RLS (access is controlled at API level via /financials endpoints)
ALTER TABLE premium_report_purchases DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE premium_report_purchases IS 'Tracks premium report purchases from ainaprotocol.com via Stripe payments. RLS disabled - access controlled at API level (super_admin only).';

