from pydantic import BaseModel

class AdminCreateUser(BaseModel):
    full_name: str
    email: str
    organization_name: str  # replaces hoa_name
    role: str = "hoa"
    building_id: int = 0
