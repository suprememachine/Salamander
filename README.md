# ⛏ BASE MINE — Mining on Base L2

Web mining platform on Base (Ethereum L2). Connect wallet, mine tokens, claim rewards.

![Base Mining](https://img.shields.io/badge/Base-8453-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Alpine.js](https://img.shields.io/badge/Alpine.js-3.x-purple)

## Features

- 🔗 **Wallet Connect** — MetaMask / Coinbase Wallet via ethers.js
- ⛏ **Mining Simulator** — Hash rate-based token accumulation
- 📊 **Leaderboard** — Top miners by token balance
- 🎨 **Dark Neon UI** — JetBrains Mono, animated mining visualizer
- 🏗 **Railway Ready** — One-click deploy with PostgreSQL auto-detection

## Quick Start

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000

## Railway Deploy

1. Push to GitHub
2. Railway → New Project → Deploy from GitHub repo
3. Add PostgreSQL add-on (optional, falls back to SQLite)
4. Done! ✅

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./data/mining.db` | PostgreSQL or SQLite URL |
| `SECRET_KEY` | auto-generated | JWT secret |
| `RPC_URL` | `https://mainnet.base.org` | Base RPC endpoint |
| `CONTRACT_ADDRESS` | `0x000...` | Mining token contract (optional) |
| `CHAIN_ID` | `8453` | Base mainnet chain ID |

## API

- `GET /health` — Health check
- `GET /api/config` — Chain config
- `POST /api/mine` — Start/stop/status mining `{ wallet, action }`
- `POST /api/claim` — Claim mined tokens `{ wallet }`
- `GET /api/leaderboard` — Top 20 miners
- `GET /api/stats` — Global stats

## Tech Stack

- **Backend:** FastAPI + SQLAlchemy + PostgreSQL/SQLite
- **Frontend:** Alpine.js + TailwindCSS + ethers.js
- **Chain:** Base (8453) — OP Stack L2
- **Deploy:** Railway with Docker

## License

MIT
