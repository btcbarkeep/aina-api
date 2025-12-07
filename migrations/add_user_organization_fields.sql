-- Migration: Add organization ID fields to user metadata
-- Note: These are stored in auth.users.user_metadata, not in a separate table
-- This migration is informational - actual updates happen via Supabase Auth API

-- Since user metadata is stored in auth.users (managed by Supabase Auth),
-- we can't directly add columns. Instead, we'll update the application code
-- to support these fields in user metadata:
--   - aoao_organization_id (UUID)
--   - pm_company_id (UUID)

-- This migration file documents the schema change.
-- The actual implementation will be in the application code (models/user.py, routers/admin.py, etc.)

COMMENT ON SCHEMA public IS 'User organization links are stored in auth.users.user_metadata as JSON fields: aoao_organization_id and pm_company_id';

