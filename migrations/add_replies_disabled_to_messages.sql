-- Migration: Add replies_disabled field to messages table
-- This field indicates if replies are disabled for a message (bulk announcements)

ALTER TABLE messages
ADD COLUMN IF NOT EXISTS replies_disabled BOOLEAN DEFAULT FALSE;

-- Add index for filtering
CREATE INDEX IF NOT EXISTS idx_messages_replies_disabled ON messages(replies_disabled);

-- Add comment
COMMENT ON COLUMN messages.replies_disabled IS 'If true, only admins can reply to this message (used for bulk announcements)';

