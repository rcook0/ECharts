from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String,Integer,Float,ForeignKey,JSON,BigInteger,Text
from db import Base

class User(Base):
    __tablename__="users"
    id: Mapped[int]=mapped_column(primary_key=True)
    email: Mapped[str]=mapped_column(String(190),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(32),default="user")
    first_name: Mapped[str]=mapped_column(String(120),default="")
    last_name: Mapped[str]=mapped_column(String(120),default="")
    phone: Mapped[str]=mapped_column(String(120),default="")
    kyc_status: Mapped[str]=mapped_column(String(32),default="unverified")
    kyc_level: Mapped[int]=mapped_column(Integer,default=0)
    kyc_submitted_at: Mapped[int|None]=mapped_column(BigInteger,nullable=True)
    kyc_verified_at: Mapped[int|None]=mapped_column(BigInteger,nullable=True)

class Wallet(Base):
    __tablename__="wallets"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    currency: Mapped[str]=mapped_column(String(10),index=True)
    balance: Mapped[float]=mapped_column(Float,default=0.0)

class Transaction(Base):
    __tablename__="transactions"
    id: Mapped[int]=mapped_column(primary_key=True)
    ext_id: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    ts: Mapped[int]=mapped_column(BigInteger)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    type: Mapped[str]=mapped_column(String(16))
    method: Mapped[str]=mapped_column(String(16))
    currency: Mapped[str]=mapped_column(String(10))
    amount: Mapped[float]=mapped_column(Float)
    fee: Mapped[float]=mapped_column(Float,default=0.0)
    status: Mapped[str]=mapped_column(String(16),default="pending")
    reference: Mapped[str|None]=mapped_column(String(64),nullable=True)
    instructions: Mapped[dict|None]=mapped_column(JSON,nullable=True)

class KycUpload(Base):
    __tablename__="kyc_uploads"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    kind: Mapped[str]=mapped_column(String(32))
    filename: Mapped[str]=mapped_column(String(255))
    content_type: Mapped[str]=mapped_column(String(64))
    bytes: Mapped[int]=mapped_column(Integer)
    sha256: Mapped[str]=mapped_column(String(64))
    ts: Mapped[int]=mapped_column(BigInteger)

class Audit(Base):
    __tablename__="audit"
    id: Mapped[int]=mapped_column(primary_key=True)
    ts: Mapped[int]=mapped_column(BigInteger)
    evt: Mapped[str]=mapped_column(String(64))
    data: Mapped[str]=mapped_column(Text)

class PaperTrade(Base):
    __tablename__="paper_trades"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    ts: Mapped[int]=mapped_column(BigInteger)
    symbol: Mapped[str]=mapped_column(String(32),index=True)
    side: Mapped[str]=mapped_column(String(4))  # BUY/SELL
    qty: Mapped[float]=mapped_column(Float)
    price: Mapped[float]=mapped_column(Float)

class PaperAccount(Base):
    __tablename__="paper_accounts"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),unique=True,index=True)
    cash_usd: Mapped[float]=mapped_column(Float,default=100000.0)
    peak_equity: Mapped[float]=mapped_column(Float,default=100000.0)
    created_at: Mapped[int]=mapped_column(BigInteger)

class PaperLedger(Base):
    __tablename__="paper_ledger"
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    ts: Mapped[int]=mapped_column(BigInteger)
    kind: Mapped[str]=mapped_column(String(24))        # e.g., trade_open, pnl_realized, deposit, adjust
    symbol: Mapped[str|None]=mapped_column(String(32),nullable=True)
    qty: Mapped[float|None]=mapped_column(Float,nullable=True)
    price: Mapped[float|None]=mapped_column(Float,nullable=True)
    realized: Mapped[float]=mapped_column(Float,default=0.0)
    cash_delta: Mapped[float]=mapped_column(Float,default=0.0)
    note: Mapped[str|None]=mapped_column(String(255),nullable=True)
    # v3.3 additions:
    source: Mapped[str]=mapped_column(String(24),default="market")   # market|admin|fabricated
    reason: Mapped[str|None]=mapped_column(String(64),nullable=True)
    sig: Mapped[str|None]=mapped_column(String(64),nullable=True)    # HMAC-SHA256 hex (trusted mode)
