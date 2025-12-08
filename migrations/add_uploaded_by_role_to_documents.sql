-- Migration: Add uploaded_by_role to documents table (performance optimization)
-- This denormalized field stores the role of the user who uploaded the document
-- to avoid lookups when displaying documents in reports

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS uploaded_by_role TEXT;

-- Add index for filtering by uploader role
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by_role ON documents(uploaded_by_role);

-- Add comment
COMMENT ON COLUMN documents.uploaded_by_role IS 'Denormalized role of the user who uploaded the document (for performance). Populated automatically on document creation/update.';

