-- Migration: Create access_requests table
-- Allows users to request access to buildings/units (e.g., PM requesting to manage a building)

CREATE TABLE IF NOT EXISTS access_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    request_type TEXT NOT NULL CHECK (request_type IN ('building', 'unit')),
    building_id UUID REFERENCES buildings(id) ON DELETE CASCADE,
    unit_id UUID REFERENCES units(id) ON DELETE CASCADE,
    organization_type TEXT CHECK (organization_type IN ('pm_company', 'aoao_organization')),
    organization_id UUID,  -- PM company or AOAO organization ID
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    notes TEXT,
    admin_notes TEXT,  -- Admin-only notes
    reviewed_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Ensure either building_id or unit_id is provided based on request_type
    CONSTRAINT check_request_type_building CHECK (
        (request_type = 'building' AND building_id IS NOT NULL AND unit_id IS NULL) OR
        (request_type = 'unit' AND unit_id IS NOT NULL)
    )
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_access_requests_requester ON access_requests(requester_user_id);
CREATE INDEX IF NOT EXISTS idx_access_requests_status ON access_requests(status);
CREATE INDEX IF NOT EXISTS idx_access_requests_building ON access_requests(building_id) WHERE building_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_access_requests_unit ON access_requests(unit_id) WHERE unit_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_access_requests_created_at ON access_requests(created_at DESC);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_access_requests_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_access_requests_updated_at ON access_requests;
CREATE TRIGGER update_access_requests_updated_at
    BEFORE UPDATE ON access_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_access_requests_updated_at();

-- Add comments
COMMENT ON TABLE access_requests IS 'Requests from users to gain access to buildings or units (e.g., PM requesting to manage a building)';
COMMENT ON COLUMN access_requests.request_type IS 'Type of request: "building" or "unit"';
COMMENT ON COLUMN access_requests.organization_type IS 'Type of organization making the request (if applicable)';
COMMENT ON COLUMN access_requests.organization_id IS 'PM company or AOAO organization ID (if applicable)';
COMMENT ON COLUMN access_requests.status IS 'Request status: pending, approved, or rejected';
COMMENT ON COLUMN access_requests.admin_notes IS 'Admin-only notes for internal use';

