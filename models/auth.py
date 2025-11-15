# models/auth.py
from sqlmodel import SQLModel

class LoginRequest(SQLModel):
    username: str
    password: str

class TokenResponse(SQLModel):
    access_token: str
    token_type: str = "bearer"
