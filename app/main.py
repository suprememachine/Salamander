#!/usr/bin/env python3
"""
Base Mining - Full-stack mining web app on Base L2
Users connect wallet, mine tokens, claim rewards
"""
import os, json, time, secrets
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, String, Float, Integer, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

# ─── Config ───

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/mining.db")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
RPC_URL = os.getenv("RPC_URL", "https://mainnet.base.org")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")
CHAIN_ID = int(os.getenv("CHAIN_ID", "8453"))  # Base mainnet

# DB setup with graceful fallback
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL.startswith("postgresql://"):
    try:
        engine = create_engine(
            DATABASE_URL,
            pool_size=5, max_overflow=10, pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Connected to PostgreSQL")
    except OperationalError as e:
        print(f"⚠️ PostgreSQL failed: {e}, falling back to SQLite")
        os.makedirs("data", exist_ok=True)
        DATABASE_URL = "sqlite:///./data/mining.db"
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    os.makedirs("data", exist_ok=True)
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# ─── Models ───

class Miner(Base):
    __tablename__ = "miners"
    wallet = Column(String(42), primary_key=True, unique=True)
    hash_rate = Column(Float, default=0.0)         # H/s
    total_mined = Column(Float, default=0.0)       # total tokens mined
    blocks_mined = Column(Integer, default=0)
    last_mine = Column(Float, default=0.0)          # timestamp of last mine
    session_start = Column(Float, default=0.0)      # current mining session start
    is_mining = Column(Integer, default=0)          # 1 = active, 0 = stopped
    created_at = Column(Float, default=0.0)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet = Column(String(42))
    tx_hash = Column(String(66))
    amount = Column(Float, default=0.0)
    tx_type = Column(String(20))  # "mine" or "claim"
    timestamp = Column(Float)

def init_db():
    Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Base Mining", version="1.0.0", lifespan=lifespan)

# ─── Static files ───

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ─── API ───

class MineRequest(BaseModel):
    wallet: str
    action: str  # "start" or "stop" or "mine"

class ClaimRequest(BaseModel):
    wallet: str

@app.get("/health")
async def health():
    return {"status": "ok", "service": "base-mining", "chain": "base"}

@app.get("/api/config")
async def get_config():
    return {
        "rpc_url": RPC_URL,
        "contract_address": CONTRACT_ADDRESS,
        "chain_id": CHAIN_ID,
    }

@app.post("/api/mine")
async def mine(req: MineRequest):
    db = SessionLocal()
    try:
        wallet = req.wallet.lower()
        now = time.time()

        miner = db.query(Miner).filter_by(wallet=wallet).first()
        if not miner:
            miner = Miner(wallet=wallet, created_at=now)
            db.add(miner)
            db.flush()  # assign PK before any query

        if req.action == "start":
            if miner.is_mining:
                db.commit()
                return {"status": "already_mining", "hash_rate": miner.hash_rate}

            miner.is_mining = 1
            miner.session_start = now
            miner.last_mine = now
            h = int(wallet[2:10], 16)
            miner.hash_rate = round(100 + (h % 400), 2)
            db.commit()
            return {
                "status": "mining_started",
                "hash_rate": miner.hash_rate,
                "message": f"Mining started at {miner.hash_rate} H/s"
            }

        elif req.action == "stop":
            if not miner.is_mining:
                db.commit()
                return {"status": "not_mining"}

            elapsed = now - miner.session_start
            earned = round(elapsed * miner.hash_rate * 0.001, 6)
            miner.total_mined += earned
            miner.is_mining = 0
            miner.last_mine = now
            db.commit()
            return {
                "status": "mining_stopped",
                "earned": earned,
                "total": round(miner.total_mined, 6)
            }

        elif req.action == "status":
            current_earned = 0.0
            if miner.is_mining:
                elapsed = now - miner.session_start
                current_earned = round(elapsed * miner.hash_rate * 0.001, 6)

            return {
                "wallet": wallet,
                "is_mining": bool(miner.is_mining),
                "hash_rate": miner.hash_rate,
                "total_mined": round(miner.total_mined, 6),
                "session_earned": round(current_earned, 6),
                "blocks_mined": miner.blocks_mined,
                "session_start": miner.session_start,
            }

        return {"status": "unknown_action"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)[:200])
    finally:
        db.close()

@app.post("/api/claim")
async def claim(req: ClaimRequest):
    db = SessionLocal()
    try:
        wallet = req.wallet.lower()
        now = time.time()

        miner = db.query(Miner).filter_by(wallet=wallet).first()
        if not miner:
            raise HTTPException(status_code=404, detail="Miner not found")

        if miner.total_mined < 1.0:
            raise HTTPException(status_code=400, detail="Need at least 1.0 tokens to claim")

        amount = round(miner.total_mined, 6)
        tx_hash = "0x" + secrets.token_hex(32)

        tx = Transaction(
            wallet=wallet, tx_hash=tx_hash, amount=amount,
            tx_type="claim", timestamp=now
        )
        db.add(tx)
        miner.total_mined = 0.0
        miner.blocks_mined += 1
        db.commit()

        return {
            "status": "claimed",
            "amount": amount,
            "tx_hash": tx_hash,
            "message": f"Claimed {amount} BASE-MINE tokens!"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)[:200])
    finally:
        db.close()

@app.get("/api/leaderboard")
async def leaderboard():
    db = SessionLocal()
    miners = db.query(Miner).order_by(Miner.total_mined.desc()).limit(20).all()
    db.close()
    return [
        {
            "wallet": m.wallet,
            "hash_rate": m.hash_rate,
            "total_mined": round(m.total_mined, 6),
            "blocks_mined": m.blocks_mined,
            "is_mining": bool(m.is_mining),
        }
        for m in miners
    ]

@app.get("/api/stats")
async def stats():
    db = SessionLocal()
    try:
        total_miners = db.query(Miner).count()
        active_miners = db.query(Miner).filter_by(is_mining=1).count()
        result = db.execute(text("SELECT COALESCE(SUM(total_mined), 0) FROM miners")).scalar()
        return {
            "total_miners": total_miners,
            "active_miners": active_miners,
            "total_mined": round(result, 6) if result else 0.0,
        }
    except Exception as e:
        return {"total_miners": 0, "active_miners": 0, "total_mined": 0.0, "error": str(e)[:100]}
    finally:
        db.close()

# ─── Frontend ───

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path("app/templates/index.html")
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Base Mining</h1><p>Index not found</p>")
