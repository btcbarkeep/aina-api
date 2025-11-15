from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import Session
from database import get_session
from core.security import hash_password
from core.auth_helpers import verify_password_setup_token
from models.user import User

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/set-password")
def set_password(token: str, new_password: str, session: Session = Depends(get_session)):
    """
    User sets their password for first time using token email.
    """
    email = verify_password_setup_token(token)

    user = session.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(new_password)
    session.add(user)
    session.commit()

    return {"status": "success", "message": "Password created. You may now log in."}
