#!/usr/bin/env python3
"""
Salamander Mining — Quiz-based mining on Base L2
Users connect wallet, answer auto-generated questions to mine SLAM tokens
"""
import os, json, time, secrets
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, Column, String, Float, Integer, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

from app.questions import generate_question, verify_answer, get_difficulty_config

# ─── Config ───

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/mining.db")
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
RPC_URL = os.getenv("RPC_URL", "https://mainnet.base.org")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")
SWAP_ADDRESS = os.getenv("SWAP_ADDRESS", "0x0000000000000000000000000000000000000000")
CHAIN_ID = int(os.getenv("CHAIN_ID", "8453"))

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

# ─── In-memory session store (current question per wallet) ───
# {wallet: {question, answer, type, started_at, difficulty, question_id}}
active_sessions: dict = {}

# ─── Models ───

class Miner(Base):
    __tablename__ = "miners"
    wallet = Column(String(42), primary_key=True, unique=True)
    total_mined = Column(Float, default=0.0)
    balance = Column(Float, default=0.0)           # claimed balance on-chain
    blocks_mined = Column(Integer, default=0)       # questions answered correctly
    streak = Column(Integer, default=0)              # current answer streak
    best_streak = Column(Integer, default=0)         # best streak ever
    difficulty = Column(Integer, default=1)          # 1-3 adaptive difficulty
    questions_answered = Column(Integer, default=0)
    questions_correct = Column(Integer, default=0)
    last_mine = Column(Float, default=0.0)
    created_at = Column(Float, default=0.0)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet = Column(String(42))
    tx_hash = Column(String(66))
    amount = Column(Float, default=0.0)
    tx_type = Column(String(20))  # "mine", "claim", "streak_bonus"
    timestamp = Column(Float)

class QuizHistory(Base):
    __tablename__ = "quiz_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet = Column(String(42))
    question = Column(String(500))
    user_answer = Column(String(200))
    correct_answer = Column(String(200))
    correct = Column(Integer, default=0)  # 0/1
    difficulty = Column(Integer, default=1)
    reward = Column(Float, default=0.0)
    time_taken = Column(Float, default=0.0)  # seconds
    timestamp = Column(Float, default=0.0)

def init_db():
    Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Salamander Mining", version="2.0.0", lifespan=lifespan)

# ─── Static files ───

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ─── Pydantic models ───

class MineRequest(BaseModel):
    wallet: str
    action: str  # "start", "answer", "question", "stop", "status"
    answer: Optional[str] = None

class ClaimRequest(BaseModel):
    wallet: str

# ─── API ───

@app.get("/health")
async def health():
    use_llm = bool(os.getenv("OPENAI_API_KEY"))
    return {
        "status": "ok",
        "service": "base-mining-quiz",
        "chain": "base",
        "llm": use_llm,
    }

@app.get("/api/config")
async def get_config():
    contracts_file = Path("contracts.json")
    if contracts_file.exists():
        try:
            deployed = json.loads(contracts_file.read_text())
            return {
                "rpc_url": deployed.get("rpc_url", RPC_URL),
                "contract_address": deployed.get("token_address", CONTRACT_ADDRESS),
                "swap_address": deployed.get("swap_address", SWAP_ADDRESS),
                "chain_id": deployed.get("chain", CHAIN_ID),
            }
        except:
            pass
    return {
        "rpc_url": RPC_URL,
        "contract_address": CONTRACT_ADDRESS,
        "swap_address": SWAP_ADDRESS,
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
            db.flush()

        # ─── START: Generate first question ───
        if req.action == "start":
            q = generate_question(miner.difficulty)
            qid = secrets.token_hex(8)
            active_sessions[wallet] = {
                "question": q["question"],
                "answer": q["answer"],
                "type": q.get("type", "general"),
                "started_at": now,
                "difficulty": miner.difficulty,
                "question_id": qid,
            }
            cfg = get_difficulty_config(miner.difficulty)
            db.commit()
            return {
                "status": "question",
                "question": q["question"],
                "question_type": q.get("type", "general"),
                "difficulty": miner.difficulty,
                "difficulty_name": cfg["name"],
                "time_limit": cfg["time_limit"],
                "reward": cfg["reward"],
                "accuracy_bonus": cfg["accuracy_bonus"],
                "question_id": qid,
                "streak": miner.streak,
                "streak_multiplier": min(1 + miner.streak * 0.1, 3.0),
                "hint": q.get("hint"),
            }

        # ─── ANSWER: Verify and reward ───
        elif req.action == "answer":
            if wallet not in active_sessions:
                return {"status": "no_active_question", "message": "Call start first"}

            if not req.answer:
                return {"status": "error", "message": "No answer provided"}

            session = active_sessions[wallet]
            time_taken = now - session["started_at"]
            is_correct = verify_answer(
                session["question"], req.answer, session["answer"]
            )

            reward = 0.0
            streak_bonus = 0.0
            time_bonus = 0.0

            cfg = get_difficulty_config(session["difficulty"])

            if is_correct:
                # Base reward
                reward = cfg["reward"]

                # Accuracy bonus (faster = more bonus)
                if time_taken < cfg["time_limit"] * 0.3:
                    time_bonus = cfg["accuracy_bonus"] * 2  # super fast
                elif time_taken < cfg["time_limit"] * 0.6:
                    time_bonus = cfg["accuracy_bonus"]
                elif time_taken < cfg["time_limit"]:
                    time_bonus = cfg["accuracy_bonus"] * 0.5

                # Streak bonus
                miner.streak = (miner.streak or 0) + 1
                if miner.streak > (miner.best_streak or 0):
                    miner.best_streak = miner.streak
                streak_multiplier = min(1 + miner.streak * 0.1, 3.0)
                streak_bonus = reward * (streak_multiplier - 1)

                # Total reward
                total = reward + time_bonus + streak_bonus
                total = round(total, 6)

                miner.total_mined += total
                miner.blocks_mined = (miner.blocks_mined or 0) + 1
                miner.questions_correct = (miner.questions_correct or 0) + 1

                # Adaptive difficulty: upgrade after 5 correct in a row
                if miner.streak >= 5 and miner.difficulty < 3:
                    miner.difficulty = min(miner.difficulty + 1, 3)

                result_msg = f"+{total} SLAM! 🎉"
            else:
                # Wrong answer — streak broken
                miner.streak = 0
                # Degrade difficulty after 2 wrong in a row
                if miner.difficulty > 1:
                    miner.difficulty = max(miner.difficulty - 1, 1)

            miner.questions_answered = (miner.questions_answered or 0) + 1
            miner.last_mine = now

            # Log quiz history
            hist = QuizHistory(
                wallet=wallet,
                question=session["question"][:500],
                user_answer=str(req.answer)[:200],
                correct_answer=str(session["answer"])[:200],
                correct=1 if is_correct else 0,
                difficulty=session["difficulty"],
                reward=round(reward + time_bonus + streak_bonus, 6) if is_correct else 0,
                time_taken=round(time_taken, 2),
                timestamp=now,
            )
            db.add(hist)

            # Generate next question
            next_q = generate_question(miner.difficulty)
            next_qid = secrets.token_hex(8)
            active_sessions[wallet] = {
                "question": next_q["question"],
                "answer": next_q["answer"],
                "type": next_q.get("type", "general"),
                "started_at": now,
                "difficulty": miner.difficulty,
                "question_id": next_qid,
            }
            next_cfg = get_difficulty_config(miner.difficulty)

            db.commit()

            response = {
                "status": "correct" if is_correct else "wrong",
                "correct_answer": session["answer"],
                "reward": round(reward + time_bonus + streak_bonus, 6) if is_correct else 0,
                "time_taken": round(time_taken, 2),
                "total_mined": round(miner.total_mined, 6),
                "streak": miner.streak,
                "streak_multiplier": min(1 + miner.streak * 0.1, 3.0),
                "difficulty": miner.difficulty,
                "difficulty_name": next_cfg["name"],
                # Next question
                "next_question": next_q["question"],
                "next_type": next_q.get("type", "general"),
                "next_question_id": next_qid,
                "next_time_limit": next_cfg["time_limit"],
                "next_reward": next_cfg["reward"],
                "hint": next_q.get("hint"),
            }

            if is_correct:
                response["time_bonus"] = round(time_bonus, 6)
                response["streak_bonus"] = round(streak_bonus, 6)

            return response

        # ─── QUESTION: Get current/new question ───
        elif req.action == "question":
            cfg = get_difficulty_config(miner.difficulty)
            if wallet in active_sessions:
                session = active_sessions[wallet]
                return {
                    "status": "question",
                    "question": session["question"],
                    "question_type": session.get("type", "general"),
                    "difficulty": session["difficulty"],
                    "difficulty_name": cfg["name"],
                    "time_limit": cfg["time_limit"],
                    "question_id": session["question_id"],
                    "time_elapsed": round(now - session["started_at"], 1),
                    "streak": miner.streak or 0,
                    "streak_multiplier": min(1 + (miner.streak or 0) * 0.1, 3.0),
                }

            q = generate_question(miner.difficulty)
            qid = secrets.token_hex(8)
            active_sessions[wallet] = {
                "question": q["question"],
                "answer": q["answer"],
                "type": q.get("type", "general"),
                "started_at": now,
                "difficulty": miner.difficulty,
                "question_id": qid,
            }
            db.commit()
            return {
                "status": "question",
                "question": q["question"],
                "question_type": q.get("type", "general"),
                "difficulty": miner.difficulty,
                "difficulty_name": cfg["name"],
                "time_limit": cfg["time_limit"],
                "reward": cfg["reward"],
                "question_id": qid,
                "streak": miner.streak or 0,
                "streak_multiplier": min(1 + (miner.streak or 0) * 0.1, 3.0),
                "hint": q.get("hint"),
            }

        # ─── STOP: End mining session ───
        elif req.action == "stop":
            if wallet in active_sessions:
                del active_sessions[wallet]
            return {
                "status": "stopped",
                "total_mined": round(miner.total_mined, 6),
                "streak": miner.streak or 0,
                "best_streak": miner.best_streak or 0,
            }

        # ─── STATUS ───
        elif req.action == "status":
            has_question = wallet in active_sessions
            cfg = get_difficulty_config(miner.difficulty)
            return {
                "wallet": wallet,
                "has_active_question": has_question,
                "total_mined": round(miner.total_mined or 0, 6),
                "balance": round(miner.balance or 0, 6),
                "blocks_mined": miner.blocks_mined or 0,
                "questions_answered": miner.questions_answered or 0,
                "questions_correct": miner.questions_correct or 0,
                "accuracy": round(
                    (miner.questions_correct / max(miner.questions_answered, 1)) * 100, 1
                ),
                "streak": miner.streak or 0,
                "best_streak": miner.best_streak or 0,
                "difficulty": miner.difficulty or 1,
                "difficulty_name": cfg["name"],
                "streak_multiplier": min(1 + (miner.streak or 0) * 0.1, 3.0),
                "current_question": active_sessions.get(wallet, {}).get("question"),
                "time_elapsed": round(
                    now - active_sessions[wallet]["started_at"], 1
                ) if has_question else 0,
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

        if (miner.total_mined or 0) < 1.0:
            raise HTTPException(status_code=400, detail="Need at least 1.0 tokens to claim")

        amount = round(miner.total_mined, 6)
        tx_hash = "0x" + secrets.token_hex(32)

        tx = Transaction(
            wallet=wallet, tx_hash=tx_hash, amount=amount,
            tx_type="claim", timestamp=now
        )
        db.add(tx)
        miner.balance = (miner.balance or 0) + amount
        miner.total_mined = 0.0
        db.commit()

        return {
            "status": "claimed",
            "amount": amount,
            "tx_hash": tx_hash,
            "message": f"Claimed {amount} SLAM tokens!",
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
            "total_mined": round(m.total_mined or 0, 6),
            "blocks_mined": m.blocks_mined or 0,
            "streak": m.streak or 0,
            "best_streak": m.best_streak or 0,
            "difficulty": m.difficulty or 1,
            "accuracy": round(
                (m.questions_correct / max(m.questions_answered, 1)) * 100, 1
            ),
        }
        for m in miners
    ]


@app.get("/api/stats")
async def stats():
    db = SessionLocal()
    try:
        total_miners = db.query(Miner).count()
        total_questions = db.execute(text("SELECT COALESCE(SUM(questions_answered), 0) FROM miners")).scalar()
        total_correct = db.execute(text("SELECT COALESCE(SUM(questions_correct), 0) FROM miners")).scalar()
        result = db.execute(text("SELECT COALESCE(SUM(total_mined), 0) FROM miners")).scalar()
        return {
            "total_miners": total_miners,
            "active_miners": len(active_sessions),
            "total_mined": round(result, 6) if result else 0.0,
            "total_questions": int(total_questions or 0),
            "total_correct": int(total_correct or 0),
        }
    except Exception as e:
        return {"total_miners": 0, "active_miners": 0, "total_mined": 0.0, "error": str(e)[:100]}
    finally:
        db.close()


@app.get("/api/quiz/history")
async def quiz_history(wallet: str, limit: int = 10):
    """Get recent quiz answers for a wallet"""
    db = SessionLocal()
    try:
        history = (
            db.query(QuizHistory)
            .filter_by(wallet=wallet.lower())
            .order_by(QuizHistory.timestamp.desc())
            .limit(min(limit, 50))
            .all()
        )
        return [
            {
                "question": h.question,
                "correct_answer": h.correct_answer,
                "user_answer": h.user_answer,
                "correct": bool(h.correct),
                "difficulty": h.difficulty,
                "reward": h.reward,
                "time_taken": h.time_taken,
            }
            for h in history
        ]
    finally:
        db.close()


# ─── Frontend ───

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path("app/templates/index.html")
    if html_path.exists():
        return HTMLResponse(html_path.read_text())
    return HTMLResponse("<h1>Salamander Mining</h1><p>Index not found</p>")
