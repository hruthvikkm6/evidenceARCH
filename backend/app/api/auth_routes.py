import sqlite3, uuid
from fastapi import APIRouter, HTTPException, Response, Depends
from app.core.config import settings
from app.core.security import COOKIE_NAME, create_access_token, get_current_user, hash_password, verify_password
from app.db.database import db_session
from app.schemas.contracts import SignupRequest, LoginRequest, UserOut
from app.services.repository import now

router=APIRouter(prefix="/api/v1/auth",tags=["authentication"])

def public_user(row):
    return {"user_id":row["user_id"],"full_name":row["full_name"],"email":row["email"],"role":row["role"],"is_active":bool(row["is_active"]),"created_at":row["created_at"]}

def set_session(response:Response,user_id:str):
    response.set_cookie(COOKIE_NAME,create_access_token(user_id),max_age=settings.jwt_expire_minutes*60,httponly=True,secure=settings.cookie_secure,samesite="lax",path="/api")

@router.post("/signup",response_model=UserOut,status_code=201)
def signup(body:SignupRequest,response:Response):
    email=str(body.email).strip().lower(); user_id=str(uuid.uuid4()); timestamp=now()
    try:
        with db_session() as db:
            first_user=db.execute("SELECT count(*) FROM users").fetchone()[0]==0
            db.execute("INSERT INTO users(user_id,full_name,email,password_hash,role,is_active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(user_id,body.full_name,email,hash_password(body.password),"INVESTIGATOR",1,timestamp,timestamp))
            if first_user:
                db.execute("UPDATE cases SET investigator_id=? WHERE investigator_id IS NULL",(user_id,))
            row=db.execute("SELECT * FROM users WHERE user_id=?",(user_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409,"An account with this email already exists.") from exc
    set_session(response,user_id)
    return public_user(row)

@router.post("/login",response_model=UserOut)
def login(body:LoginRequest,response:Response):
    with db_session() as db: row=db.execute("SELECT * FROM users WHERE email=? COLLATE NOCASE",(str(body.email).strip(),)).fetchone()
    if not row or not row["is_active"] or not verify_password(body.password,row["password_hash"]):
        raise HTTPException(401,"Email or password is incorrect.")
    set_session(response,row["user_id"])
    return public_user(row)

@router.post("/logout")
def logout(response:Response):
    response.delete_cookie(COOKIE_NAME,path="/api",httponly=True,secure=settings.cookie_secure,samesite="lax")
    return {"message":"Signed out."}

@router.get("/me",response_model=UserOut)
def me(user=Depends(get_current_user)):
    return public_user(user)
