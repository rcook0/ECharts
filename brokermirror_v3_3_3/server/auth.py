import os, time
from jose import jwt, JWTError
from passlib.hash import bcrypt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import select
from db import get_db
from models import User
SECRET=os.getenv("WL_JWT_SECRET","change-me")
ALGO="HS256"
AUTH_SCHEME=HTTPBearer()
def make_token(user, ttl_s=3600):
    now=int(time.time())
    return jwt.encode({"sub":str(user.id),"role":user.role,"exp":now+ttl_s,"iat":now}, SECRET, algorithm=ALGO)
def current_user(db: Session=Depends(get_db), creds: HTTPAuthorizationCredentials=Depends(AUTH_SCHEME)) -> User:
    try:
        payload=jwt.decode(creds.credentials, SECRET, algorithms=[ALGO]); uid=int(payload["sub"])
    except JWTError:
        raise HTTPException(401,"invalid token")
    u=db.get(User, uid)
    if not u: raise HTTPException(401,"user not found")
    return u
def require_admin(u: User=Depends(current_user))->User:
    if u.role!="admin": raise HTTPException(403,"admin required")
    return u
def verify_password(pwd: str, hash_: str)->bool:
    try: return bcrypt.verify(pwd, hash_)
    except Exception: return False
