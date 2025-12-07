-- Make filename column nullable in documents table
-- This allows bulk uploads (which use document_url, not S3) to leave filename blank
-- S3 uploads will still populate filename from title, but it's not required

ALTER TABLE documents 
ALTER COLUMN filename DROP NOT NULL;

-- Add a comment explaining the change
COMMENT ON COLUMN documents.filename IS 'Optional filename metadata. Required for S3 uploads (auto-generated from title), optional for bulk uploads with external URLs.';

