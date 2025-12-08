-- Migration: Create document_email_logs table
-- Tracks all document emails sent via the /documents/send-email endpoint

CREATE TABLE IF NOT EXISTS document_email_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    sender_email TEXT NOT NULL,
    sender_name TEXT,
    recipient_emails TEXT[] NOT NULL,  -- Array of recipient email addresses
    document_ids UUID[] NOT NULL,  -- Array of document IDs that were sent
    subject TEXT NOT NULL,
    message TEXT,  -- Optional message from sender
    status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'failed', 'partial')),
    error_message TEXT,  -- Error message if status is 'failed' or 'partial'
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_document_email_logs_sender ON document_email_logs(sender_user_id);
CREATE INDEX IF NOT EXISTS idx_document_email_logs_sent_at ON document_email_logs(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_email_logs_status ON document_email_logs(status);
CREATE INDEX IF NOT EXISTS idx_document_email_logs_document_ids ON document_email_logs USING GIN(document_ids);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_document_email_logs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_document_email_logs_updated_at ON document_email_logs;
CREATE TRIGGER update_document_email_logs_updated_at
    BEFORE UPDATE ON document_email_logs
    FOR EACH ROW
    EXECUTE FUNCTION update_document_email_logs_updated_at();

-- Add comments
COMMENT ON TABLE document_email_logs IS 'Tracks all document emails sent via the /documents/send-email endpoint';
COMMENT ON COLUMN document_email_logs.sender_user_id IS 'User who sent the documents';
COMMENT ON COLUMN document_email_logs.recipient_emails IS 'Array of recipient email addresses';
COMMENT ON COLUMN document_email_logs.document_ids IS 'Array of document IDs that were sent';
COMMENT ON COLUMN document_email_logs.status IS 'Status: sent (success), failed (error), partial (some recipients failed)';

