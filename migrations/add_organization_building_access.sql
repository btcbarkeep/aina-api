-- Migration: Add organization-level building access
-- This allows AOAO organizations and PM companies to have building access
-- that is inherited by all users in that organization

-- AOAO Organization Building Access
CREATE TABLE IF NOT EXISTS aoao_organization_building_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aoao_organization_id UUID NOT NULL REFERENCES aoao_organizations(id) ON DELETE CASCADE,
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(aoao_organization_id, building_id)
);

CREATE INDEX IF NOT EXISTS idx_aoao_org_building_access_org ON aoao_organization_building_access(aoao_organization_id);
CREATE INDEX IF NOT EXISTS idx_aoao_org_building_access_building ON aoao_organization_building_access(building_id);

COMMENT ON TABLE aoao_organization_building_access IS 'Maps AOAO organizations to buildings they have access to. All users in the organization inherit this access.';

-- PM Company Building Access
CREATE TABLE IF NOT EXISTS pm_company_building_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pm_company_id UUID NOT NULL REFERENCES property_management_companies(id) ON DELETE CASCADE,
    building_id UUID NOT NULL REFERENCES buildings(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pm_company_id, building_id)
);

CREATE INDEX IF NOT EXISTS idx_pm_company_building_access_company ON pm_company_building_access(pm_company_id);
CREATE INDEX IF NOT EXISTS idx_pm_company_building_access_building ON pm_company_building_access(building_id);

COMMENT ON TABLE pm_company_building_access IS 'Maps property management companies to buildings they have access to. All users in the company inherit this access.';

