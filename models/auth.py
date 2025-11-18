from pydantic import BaseModel, EmailStr


# -----------------------------------------------------
# LOGIN REQUEST (using Supabase email/password)
# -----------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr           # FIX: Supabase login requires email
    password: str             # Plain password sent to Supabase


# -----------------------------------------------------
# TOKEN RESPONSE (Supabase session JWT)
# -----------------------------------------------------
class TokenResponse(BaseModel):
    access_token: str         # Supabase access token (JWT)
    refresh_token: str        # Supabase refresh token
    expires_in: int           # Seconds until expiration
    token_type: str = "bearer"
