-- Migration: Add additional fields to contractors table and enforce unique company names
-- Date: 2025-01-27
-- Description: Adds city, state, zip_code, contact_person, contact_phone, contact_email, and notes fields
-- Also adds a unique constraint on company_name (case-insensitive)

-- Add new columns
ALTER TABLE contractors
ADD COLUMN IF NOT EXISTS city TEXT,
ADD COLUMN IF NOT EXISTS state TEXT,
ADD COLUMN IF NOT EXISTS zip_code TEXT,
ADD COLUMN IF NOT EXISTS contact_person TEXT,
ADD COLUMN IF NOT EXISTS contact_phone TEXT,
ADD COLUMN IF NOT EXISTS contact_email TEXT,
ADD COLUMN IF NOT EXISTS notes TEXT;

-- Add comments for documentation
COMMENT ON COLUMN contractors.city IS 'City where the contractor is located';
COMMENT ON COLUMN contractors.state IS 'State/Province where the contractor is located';
COMMENT ON COLUMN contractors.zip_code IS 'ZIP/Postal code';
COMMENT ON COLUMN contractors.contact_person IS 'Primary contact person name';
COMMENT ON COLUMN contractors.contact_phone IS 'Primary contact phone number';
COMMENT ON COLUMN contractors.contact_email IS 'Primary contact email address';
COMMENT ON COLUMN contractors.notes IS 'Additional notes about the contractor';

-- Create a unique index on company_name (case-insensitive)
-- This prevents duplicate company names at the database level
CREATE UNIQUE INDEX IF NOT EXISTS contractors_company_name_unique 
ON contractors (LOWER(TRIM(company_name)));

-- Note: If you have existing duplicate company names, you'll need to resolve them first
-- before this index can be created. To check for duplicates:
-- SELECT LOWER(TRIM(company_name)), COUNT(*) 
-- FROM contractors 
-- GROUP BY LOWER(TRIM(company_name)) 
-- HAVING COUNT(*) > 1;

