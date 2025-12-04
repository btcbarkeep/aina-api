from typing import Optional, Dict, Any
from pydantic import BaseModel, EmailStr


class AdminCreateUser(BaseModel):
    """
    Payload used by admins when creating a new Supabase Auth user.

    This model supports:
    - full_name
    - email
    - organization_name
    - phone
    - role (admin, super_admin, aoao, property_manager, contractor, contractor_staff)
    - contractor_id (optional UUID string) - Only used for contractor accounts
    - metadata (optional dict for any future expansion)
    - permissions (optional list of permission strings)

    Password is handled by Supabase automatically via:
        supabase.auth.admin.create_user({"email": email, "password": auto_generated})
    """

    full_name: Optional[str] = None
    email: EmailStr
    organization_name: Optional[str] = None
    phone: Optional[str] = None

    # Default role
    role: str = "aoao"     # admin can override this

    # Only used for contractor accounts
    contractor_id: Optional[str] = None

    # For optional overrides (permissions, access flags, etc.)
    metadata: Optional[Dict[str, Any]] = None
    
    # Permissions list
    permissions: Optional[list] = None

