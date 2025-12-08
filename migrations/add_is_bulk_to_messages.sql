-- Migration: Add is_bulk field to messages table
-- This field marks bulk messages/announcements for UI display

ALTER TABLE messages
ADD COLUMN IF NOT EXISTS is_bulk BOOLEAN DEFAULT FALSE;

-- Create index for filtering bulk messages
CREATE INDEX IF NOT EXISTS idx_messages_is_bulk ON messages(is_bulk);

-- Add comment
COMMENT ON COLUMN messages.is_bulk IS 'If true, this is a bulk message/announcement sent to multiple recipients';

