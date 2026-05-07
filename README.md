# 🧠 SALAMANDER MINE — Quiz Mining on Base L2

Web mining platform on Base (Ethereum L2). Answer auto-generated quiz questions to mine SLAM tokens, swap with ETH via built-in DEX.

![Salamander Mining](https://img.shields.io/badge/Salamander-0a0a0f?style=flat-square)
![Base L2](https://img.shields.io/badge/Base-8453-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Alpine.js](https://img.shields.io/badge/Alpine.js-3.x-purple)

## Features

### 🧠 Quiz Mining
- **Auto-generated questions** — math, logic, pattern, binary, word problems
- **Adaptive difficulty** — Easy → Medium → Hard based on your streak
- **Time bonus** — faster answers = more SLAM
- **Streak multiplier** — ×1.0 → ×3.0 (5 correct = difficulty upgrade)
- **LLM questions** — optional OpenAI API for richer trivia/crypto questions

### 🔄 AMM Swap DEX
- **Constant product AMM** (x*y=k) with 0.3% fee
- **ETH → SLAM** (buy) and **SLAM → ETH** (sell)
- **Liquidity pools** — add/remove LP, earn trading fees
- **Slippage control** — 0.1% / 0.5% / 1.0%

### 📊 Leaderboard
- Top miners by total mined
- Streak records, difficulty level, accuracy stats

### 🎨 Dark Neon UI
- JetBrains Mono + Space Grotesk
- Base blue accent (#0052FF)
- Animated timer bar, streak fire effect
- Question type badges with color coding

### 🏗 Railway Ready
- One-click deploy from GitHub
- PostgreSQL auto-detection (falls back to SQLite)
- Dockerfile + health checks

## Quick Start

```bash
cd ~/salamander
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000

## Railway Deploy

1. Push to GitHub
2. Railway → New Project → Deploy from GitHub repo
3. Add PostgreSQL add-on (optional, falls back to SQLite)
4. Done! ✅

## Smart Contract Deployment

Deploy SLAM token + AMM swap contract on Base:

```bash
# Testnet (Base Sepolia)
export DEPLOYER_PRIVATE_KEY='0x...'
python3 scripts/deploy.py --testnet

# Mainnet (Base)
python3 scripts/deploy.py
```

Output saved to `contracts.json`. Update `.env` with deployed addresses.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/mining.db` | PostgreSQL or SQLite URL |
| `SECRET_KEY` | auto-generated | JWT secret |
| `RPC_URL` | `https://mainnet.base.org` | Base RPC endpoint |
| `CONTRACT_ADDRESS` | `0x000...` | SLAM token contract address |
| `SWAP_ADDRESS` | `0x000...` | AMM swap contract address |
| `CHAIN_ID` | `8453` | Base mainnet chain ID |
| `OPENAI_API_KEY` | _(empty)_ | Optional: LLM question generation |
| `LLM_MODEL` | `gpt-4o-mini` | Optional: LLM model for quiz questions |

## API

### Mining
- `POST /api/mine` — Quiz mining
  - `action: "start"` → Get first question
  - `action: "answer"` → Submit answer, get reward + next question
  - `action: "question"` → Get current/new question
  - `action: "status"` → Mining stats (streak, accuracy, difficulty)
  - `action: "stop"` → End session
- `POST /api/claim` — Claim mined SLAM tokens `{ wallet }`
- `GET /api/leaderboard` — Top 20 miners
- `GET /api/stats` — Global stats
- `GET /api/quiz/history` — Quiz answer history per wallet

### Config
- `GET /health` — Health check + LLM status
- `GET /api/config` — Chain config + contract addresses

## Question Types

| Type | Example | Difficulty |
|------|---------|------------|
| Math | `What is 27 × 8?` | Easy/Medium |
| Pattern | `3, 7, 11, 15, ?` | Easy/Medium |
| Logic | `(12 + 8) × 3 = ?` | Medium |
| Word Math | A miner found N blocks... | Easy/Medium |
| Binary | `Convert 42 to binary` | Easy/Medium/Hard |
| LLM Trivia | Auto-generated via OpenAI | Medium/Hard |

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL/SQLite
- **Frontend:** Alpine.js + TailwindCSS + ethers.js
- **Chain:** Base (8453) — OP Stack L2
- **Contracts:** Solidity 0.8.24, Constant Product AMM
- **Deploy:** Railway with Docker

## License

MIT
