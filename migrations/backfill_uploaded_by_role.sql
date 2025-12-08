-- Migration: Backfill uploaded_by_role for existing documents
-- This updates existing documents to have the uploaded_by_role field populated
-- based on the user's current role in their metadata
-- Note: Both "super_admin" and "admin" are normalized to "admin" for display purposes

-- Update documents where uploaded_by_role is NULL and uploaded_by exists
-- This uses a subquery to get the role from auth.users metadata and normalizes it
UPDATE documents d
SET uploaded_by_role = (
    SELECT 
        CASE 
            WHEN (raw_user_meta_data->>'role') = 'super_admin' THEN 'admin'
            WHEN (raw_user_meta_data->>'role') = 'admin' THEN 'admin'
            WHEN (raw_user_meta_data->>'role') IS NOT NULL 
            THEN raw_user_meta_data->>'role'
            ELSE 'aoao'  -- Default fallback
        END
    FROM auth.users u
    WHERE u.id::text = d.uploaded_by::text
    LIMIT 1
)
WHERE d.uploaded_by_role IS NULL 
  AND d.uploaded_by IS NOT NULL;

-- If the above doesn't work due to auth.users access restrictions,
-- you may need to run this via a Supabase function or manually update
-- via the admin API. Alternatively, the application will populate it
-- when documents are next updated.

COMMENT ON COLUMN documents.uploaded_by_role IS 'Denormalized role of the user who uploaded the document. Both "super_admin" and "admin" are stored as "admin" for display purposes. Backfilled for existing documents, automatically set for new documents.';

