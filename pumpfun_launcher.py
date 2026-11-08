"""
Pump.fun launcher bot (Solana) via the PumpPortal local-transaction API.

Setup:
    pip install requests solders base58
    export PRIVATE_KEY="<base58 secret key of a DEDICATED, small-balance wallet>"
    export RPC_URL="https://api.mainnet-beta.solana.com"   # better: Helius/QuickNode

Usage:
    python pumpfun_launcher.py            # dry run (default): prints what it WOULD launch
    python pumpfun_launcher.py --live     # really launches

Edit TEMPLATES below (name, symbol, description, image path, socials).
Use a burner wallet. Never put your main wallet key in a script.
"""
import argparse, csv, itertools, os, random, sys, time
import base58, requests
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.commitment_config import CommitmentLevel
from solders.rpc.requests import SendVersionedTransaction
from solders.rpc.config import RpcSendTransactionConfig

# ---------------- CONFIG ----------------
RPC_URL = os.getenv("RPC_URL", "https://api.mainnet-beta.solana.com")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
DEV_BUY_SOL = 0.05          # initial buy by deployer (0 = none)
SLIPPAGE = 10               # percent
PRIORITY_FEE = 0.0005       # SOL
MAX_LAUNCHES = 5            # hard cap per run
MIN_DELAY, MAX_DELAY = 60, 180   # seconds between launches (rate limit)
LOG_FILE = "launches.csv"

TEMPLATES = [
    {
        "name": "Example Coin",
        "symbol": "EXMPL",
        "description": "Describe the coin honestly here.",
        "image": "images/example.png",
        "twitter": "",
        "telegram": "",
        "website": "",
    },
    # add more templates...
]
# ----------------------------------------


def upload_metadata(t: dict) -> str:
    """Uploads image + metadata to pump.fun IPFS, returns metadata URI."""
    with open(t["image"], "rb") as f:
        files = {"file": (os.path.basename(t["image"]), f, "image/png")}
        data = {
            "name": t["name"], "symbol": t["symbol"],
            "description": t["description"],
            "twitter": t.get("twitter", ""), "telegram": t.get("telegram", ""),
            "website": t.get("website", ""), "showName": "true",
        }
        r = requests.post("https://pump.fun/api/ipfs", data=data, files=files, timeout=60)
    r.raise_for_status()
    return r.json()["metadataUri"]


def launch(t: dict, signer: Keypair) -> str:
    uri = upload_metadata(t)
    mint = Keypair()
    body = {
        "publicKey": str(signer.pubkey()),
        "action": "create",
        "tokenMetadata": {"name": t["name"], "symbol": t["symbol"], "uri": uri},
        "mint": str(mint.pubkey()),
        "denominatedInSol": "true",
        "amount": DEV_BUY_SOL,
        "slippage": SLIPPAGE,
        "priorityFee": PRIORITY_FEE,
        "pool": "pump",
    }
    r = requests.post("https://pumpportal.fun/api/trade-local", data=body, timeout=60)
    r.raise_for_status()
    tx = VersionedTransaction(
        VersionedTransaction.from_bytes(r.content).message, [signer, mint]
    )
    cfg = RpcSendTransactionConfig(preflight_commitment=CommitmentLevel.Confirmed)
    payload = SendVersionedTransaction(tx, cfg).to_json()
    resp = requests.post(RPC_URL, headers={"Content-Type": "application/json"},
                         data=payload, timeout=60).json()
    if "error" in resp:
        raise RuntimeError(resp["error"])
    return f"{mint.pubkey()} | tx {resp['result']}"


def log(row):
    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "symbol", "result"])
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="actually send transactions")
    args = ap.parse_args()

    signer = None
    if args.live:
        if not PRIVATE_KEY:
            sys.exit("Set PRIVATE_KEY env var (burner wallet).")
        signer = Keypair.from_bytes(base58.b58decode(PRIVATE_KEY))

    for i, t in zip(range(MAX_LAUNCHES), itertools.cycle(TEMPLATES)):
        print(f"[{i+1}/{MAX_LAUNCHES}] {t['name']} (${t['symbol']})")
        if not args.live:
            print("  dry run - nothing sent")
        else:
            try:
                res = launch(t, signer)
                print("  launched:", res)
                log([time.strftime("%F %T"), t["symbol"], res])
            except Exception as e:
                print("  FAILED:", e)
                log([time.strftime("%F %T"), t["symbol"], f"error: {e}"])
        if i + 1 < MAX_LAUNCHES:
            d = random.randint(MIN_DELAY, MAX_DELAY)
            print(f"  waiting {d}s...")
            time.sleep(d)


if __name__ == "__main__":
    main()
