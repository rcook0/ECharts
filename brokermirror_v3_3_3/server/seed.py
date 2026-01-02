from passlib.hash import bcrypt
from sqlalchemy import select
from db import SessionLocal
from models import User, Wallet, PaperAccount
import time
def ensure_user(db,email,role,pwd):
    u=db.scalar(select(User).where(User.email==email))
    if u: return u
    u=User(email=email, role=role, password_hash=bcrypt.hash(pwd))
    db.add(u); db.flush()
    for c,bal in (("USD",10000.0),("BTC",0.0),("XAU",0.0)):
        db.add(Wallet(user_id=u.id, currency=c, balance=bal))
    db.add(PaperAccount(user_id=u.id,cash_usd=100000.0,peak_equity=100000.0,created_at=int(time.time()*1000)))
    db.commit(); return u
if __name__=="__main__":
    from db import engine, Base
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ensure_user(db,"admin@local","admin","admin123")
        ensure_user(db,"demo@user.local","user","demo123")
