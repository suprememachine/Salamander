#!/usr/bin/env python3
"""
Deploy BaseMineToken + BaseMineSwap contracts on Base L2
Usage: python3 scripts/deploy.py [--testnet]

Requires:
  - DEPLOYER_PRIVATE_KEY env var
  - RPC_URL env var (or defaults to Base mainnet)
"""

import os, sys, json
from web3 import Web3

# ── Config ──

BASE_RPC = "https://mainnet.base.org"
BASE_SEPOLIA_RPC = "https://sepolia.base.org"

PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY", "")
CHAIN_ID = 8453  # Base mainnet

# ── Contract ABIs (minimal) ──

# Compile with: solc --abi --bin contracts/BaseMineToken.sol contracts/BaseMineSwap.sol

def get_rpc():
    """Get RPC URL"""
    if "--testnet" in sys.argv:
        print("⚠️  Deploying to Base SEPOLIA testnet")
        return BASE_SEPOLIA_RPC, 84532
    else:
        print("🚀 Deploying to Base MAINNET")
        return BASE_RPC, 8453

def compile_sol():
    """Compile Solidity contracts using solc"""
    import subprocess, tempfile

    contracts_dir = os.path.join(os.path.dirname(__file__), "..", "contracts")
    output_dir = os.path.join(os.path.dirname(__file__), "..", "build")
    os.makedirs(output_dir, exist_ok=True)

    token_sol = os.path.join(contracts_dir, "BaseMineToken.sol")
    swap_sol = os.path.join(contracts_dir, "BaseMineSwap.sol")

    # Check if solc is available
    result = subprocess.run(["solc", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ solc not installed. Install with:")
        print("   pip install solc-select && solc-select install 0.8.24 && solc-select use 0.8.24")
        sys.exit(1)

    # Compile both contracts
    for sol_file in [token_sol, swap_sol]:
        result = subprocess.run([
            "solc",
            "--abi", "--bin",
            "--evm-version", "cancun",
            "--optimize", "--optimize-runs", "200",
            "-o", output_dir,
            "--overwrite",
            sol_file
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Compilation error:\n{result.stderr}")
            sys.exit(1)
        print(f"✅ Compiled {os.path.basename(sol_file)}")

    return output_dir

def load_artifacts(build_dir, name):
    """Load compiled ABI and bytecode"""
    abi_path = os.path.join(build_dir, f"{name}.abi")
    bin_path = os.path.join(build_dir, f"{name}.bin")

    with open(abi_path) as f:
        abi = json.load(f)
    with open(bin_path) as f:
        bytecode = f.read().strip()

    return abi, bytecode

def deploy():
    """Deploy both contracts"""
    rpc_url, chain = get_rpc()

    if not PRIVATE_KEY:
        print("❌ Set DEPLOYER_PRIVATE_KEY env var first!")
        print("   export DEPLOYER_PRIVATE_KEY='0x...'")
        sys.exit(1)

    # Compile
    build_dir = compile_sol()

    # Connect
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"❌ Cannot connect to {rpc_url}")
        sys.exit(1)
    print(f"✅ Connected to {rpc_url}")

    account = w3.eth.account.from_key(PRIVATE_KEY)
    print(f"📍 Deployer: {account.address}")
    balance = w3.eth.get_balance(account.address)
    print(f"💰 Balance: {w3.from_wei(balance, 'ether')} ETH")

    # ── Deploy BaseMineToken ──
    print("\n📝 Deploying BaseMineToken (BMINE)...")
    token_abi, token_bytecode = load_artifacts(build_dir, "BaseMineToken")
    TokenContract = w3.eth.contract(abi=token_abi, bytecode=token_bytecode)

    nonce = w3.eth.get_transaction_count(account.address)
    tx = TokenContract.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 1_000_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  TX: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    token_address = receipt.contractAddress
    print(f"  ✅ BaseMineToken deployed at: {token_address}")
    print(f"  Gas used: {receipt.gasUsed}")

    # ── Deploy BaseMineSwap ──
    print("\n📝 Deploying BaseMineSwap...")
    swap_abi, swap_bytecode = load_artifacts(build_dir, "BaseMineSwap")
    SwapContract = w3.eth.contract(abi=swap_abi, bytecode=swap_bytecode)

    nonce = w3.eth.get_transaction_count(account.address)
    tx = SwapContract.constructor(token_address).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 1_500_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  TX: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    swap_address = receipt.contractAddress
    print(f"  ✅ BaseMineSwap deployed at: {swap_address}")
    print(f"  Gas used: {receipt.gasUsed}")

    # ── Set minter on token to swap contract ──
    print("\n📝 Setting minter on BaseMineToken...")
    token_contract = w3.eth.contract(address=token_address, abi=token_abi)
    nonce = w3.eth.get_transaction_count(account.address)
    tx = token_contract.functions.setMinter(account.address).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 100_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    print(f"  ✅ Minter set")

    # ── Save addresses ──
    addresses = {
        "chain": chain,
        "rpc_url": rpc_url,
        "token_address": token_address,
        "swap_address": swap_address,
        "deployer": account.address,
    }

    config_path = os.path.join(os.path.dirname(__file__), "..", "contracts.json")
    with open(config_path, "w") as f:
        json.dump(addresses, f, indent=2)

    print("\n" + "="*50)
    print("🎉 DEPLOYMENT COMPLETE!")
    print("="*50)
    print(f"Network:     {'Base Mainnet' if chain == 8453 else 'Base Sepolia'}")
    print(f"Token:       {token_address}")
    print(f"Swap (DEX):  {swap_address}")
    print(f"Deployer:    {account.address}")
    print(f"Explorer:    https://{'basescan.org' if chain == 8453 else 'sepolia.basescan.org'}/address/{token_address}")
    print(f"\nSaved to: contracts.json")
    print(f"\nUpdate .env with:")
    print(f"  CONTRACT_ADDRESS={token_address}")
    print(f"  SWAP_ADDRESS={swap_address}")

if __name__ == "__main__":
    deploy()
