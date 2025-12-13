import time

import requests
import json
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solders.solders import Keypair
from solders.transaction import VersionedTransaction
from solders.commitment_config import CommitmentLevel
from solders.rpc.requests import SendVersionedTransaction
from solders.rpc.config import RpcSendTransactionConfig


client = Client("https://api.mainnet-beta.solana.com/")
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


def get_balance(keypair: Keypair) -> float:
    response = client.get_balance(keypair.pubkey())
    data = response.to_json()
    data = json.loads(data)
    sol_balance = data["result"]["value"] / 10 ** 9

    return sol_balance


def complete_official_transaction(action: str, mint: str, keypair: Keypair, slippage, priority_fee,
                                  denominated_in_sol: str, pool: str, amount=0.01,
                                  rpc_url="https://api.mainnet-beta.solana.com/", loggers=None):
    retries = 0
    if rpc_url == "" or not rpc_url:
        rpc_url = "https://api.mainnet-beta.solana.com/"
    response = requests.post(url="https://pumpportal.fun/api/trade-local", data={
        "publicKey": str(keypair.pubkey()),
        "action": action,  # "buy" or "sell"
        "mint": mint,  # contract address of the token you want to trade
        "amount": amount,  # amount of SOL or tokens to trade
        "denominatedInSol": denominated_in_sol,  # "true" if amount is amount of SOL, "false" if amount is number of tokens
        "slippage": slippage,  # percent slippage allowed
        "priorityFee": priority_fee,  # amount to use as priority fee
        "pool": pool  # exchange to trade on. "pump", "raydium", "pump-amm" or "auto"
    })
    tx = VersionedTransaction(VersionedTransaction.from_bytes(response.content).message, [keypair])
    config = RpcSendTransactionConfig(preflight_commitment=CommitmentLevel.Confirmed)
    response = requests.post(
        url=rpc_url,  # https://mainnet.helius-rpc.com/?api-key=<your-api-key>  // better with helius (more reliable)
        headers={"Content-Type": "application/json"},
        data=SendVersionedTransaction(tx, config).to_json()
    )
    try:
        loggers.log_general_message(f"SUCCESS: {action.upper()} | {amount} | {mint} | {pool} | https://solscan.io/tx/{response.json()['result']}")
    except KeyError:
        if retries == 5:
            loggers.log_general_message(f"FINAL FAILURE TO {action.upper()} {amount} of {mint} in pool '{pool}' after {retries} retries.")
            return retries
        loggers.log_general_message(f"FAILED TO {action.upper()} {amount} of {mint} in pool '{pool}'")
        time.sleep(3)
        loggers.log_general_message("Retrying...")
        complete_official_transaction(action, mint, keypair, slippage, priority_fee, denominated_in_sol, pool, amount,
                                      rpc_url, loggers)
        retries += 1
    return retries
