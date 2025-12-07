-- Migration: Add contractor-level building and unit access
-- This allows contractors to have building/unit access
-- that is inherited by all users linked to that contractor

-- Contractor Building Access
CREATE TABLE IF NOT EXISTS contractor_building_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id UUID NOT NULL REFERENCES contractors(id) ON DELETE CASCADE,
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(contractor_id, building_id)
);

CREATE INDEX IF NOT EXISTS idx_contractor_building_access_contractor ON contractor_building_access(contractor_id);
CREATE INDEX IF NOT EXISTS idx_contractor_building_access_building ON contractor_building_access(building_id);

COMMENT ON TABLE contractor_building_access IS 'Maps contractors to buildings they have access to. All users linked to the contractor inherit this access.';

-- Contractor Unit Access
CREATE TABLE IF NOT EXISTS contractor_unit_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id UUID NOT NULL REFERENCES contractors(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(contractor_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_contractor_unit_access_contractor ON contractor_unit_access(contractor_id);
CREATE INDEX IF NOT EXISTS idx_contractor_unit_access_unit ON contractor_unit_access(unit_id);

COMMENT ON TABLE contractor_unit_access IS 'Maps contractors to units they have access to. All users linked to the contractor inherit this access.';

