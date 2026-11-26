from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Cookie, HTTPException
from pwdlib import PasswordHash
from app.core.config import settings
from app.db.database import db_session

password_hash=PasswordHash.recommended()
ALGORITHM="HS256"
COOKIE_NAME="evidencearch_session"

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, encoded: str) -> bool:
    try: return password_hash.verify(password,encoded)
    except Exception: return False

def create_access_token(user_id: str) -> str:
    now=datetime.now(timezone.utc)
    payload={"sub":user_id,"iat":now,"exp":now+timedelta(minutes=settings.jwt_expire_minutes)}
    return jwt.encode(payload,settings.jwt_secret,algorithm=ALGORITHM)

def get_current_user(evidencearch_session: str | None=Cookie(default=None)):
    if not evidencearch_session: raise HTTPException(401,"Please sign in to continue.")
    try:
        payload=jwt.decode(evidencearch_session,settings.jwt_secret,algorithms=[ALGORITHM])
        user_id=payload.get("sub")
        if not user_id: raise ValueError("token subject missing")
    except (jwt.InvalidTokenError,ValueError):
        raise HTTPException(401,"Your session is invalid or expired. Please sign in again.")
    with db_session() as db:
        row=db.execute("SELECT * FROM users WHERE user_id=? AND is_active=1",(user_id,)).fetchone()
        if not row: raise HTTPException(401,"Account is unavailable. Please sign in again.")
        return dict(row)

def require_case_owner(case_row,user):
    owner=case_row["investigator_id"]
    if owner is None or owner!=user["user_id"]:
        raise HTTPException(404,"Case not found.")
