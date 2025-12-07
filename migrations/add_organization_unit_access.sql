-- Migration: Add organization-level unit access
-- This allows AOAO organizations and PM companies to have unit access
-- that is inherited by all users in that organization

-- AOAO Organization Unit Access
CREATE TABLE IF NOT EXISTS aoao_organization_unit_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aoao_organization_id UUID NOT NULL REFERENCES aoao_organizations(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(aoao_organization_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_aoao_org_unit_access_org ON aoao_organization_unit_access(aoao_organization_id);
CREATE INDEX IF NOT EXISTS idx_aoao_org_unit_access_unit ON aoao_organization_unit_access(unit_id);

COMMENT ON TABLE aoao_organization_unit_access IS 'Maps AOAO organizations to units they have access to. All users in the organization inherit this access.';

-- PM Company Unit Access
CREATE TABLE IF NOT EXISTS pm_company_unit_access (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pm_company_id UUID NOT NULL REFERENCES property_management_companies(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(pm_company_id, unit_id)
);

CREATE INDEX IF NOT EXISTS idx_pm_company_unit_access_company ON pm_company_unit_access(pm_company_id);
CREATE INDEX IF NOT EXISTS idx_pm_company_unit_access_unit ON pm_company_unit_access(unit_id);

COMMENT ON TABLE pm_company_unit_access IS 'Maps property management companies to units they have access to. All users in the company inherit this access.';

