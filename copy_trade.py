import argparse
import asyncio

import requests
from solders.transaction import VersionedTransaction
from solders.keypair import Keypair
from solders.commitment_config import CommitmentLevel
from solders.rpc.requests import SendVersionedTransaction
from solders.rpc.config import RpcSendTransactionConfig
import websockets
import json
from base import PumpTrade, keepalive_ping
import time

queue = asyncio.Queue()
first_response = True
test_wallet_holdings = dict()


async def receiver(ws):
    global first_response
    while True:
        response = await ws.recv()
        data = json.loads(response)
        if first_response:
            print(data)
            print("\n")
            first_response = False
        else:
            await queue.put(data)


async def processor(args, keypair):
    while True:
        data = await queue.get()
        trade = PumpTrade(data)
        make_transaction(trade, args, keypair)


async def subscribe(args):
    uri = "wss://pumpportal.fun/api/data"
    keypair = Keypair.from_base58_string(args.private_key)
    async with websockets.connect(uri) as websocket:
        payload = {
            "method": "subscribeAccountTrade",
            "keys": [args.wallet_to_copy]
        }
        await websocket.send(json.dumps(payload))
        try:
            await asyncio.gather(receiver(websocket), processor(args, keypair), keepalive_ping(websocket))
        except asyncio.CancelledError:
            print("\nWebSocket task cancelled.")


def complete_official_transaction(action: str, mint: str, args, denominated_in_sol: str, pool: str, private_key,
                                  amount=None):
    global test_wallet_holdings
    if amount is None:
        amount = args.amount
    response = requests.post(url="https://pumpportal.fun/api/trade-local", data={
        "publicKey": args.public_key,
        "action": action,  # "buy" or "sell"
        "mint": mint,  # contract address of the token you want to trade
        "amount": amount,  # amount of SOL or tokens to trade
        "denominatedInSol": denominated_in_sol,  # "true" if amount is amount of SOL, "false" if amount is number of tokens
        "slippage": args.slippage,  # percent slippage allowed
        "priorityFee": args.priority_fee,  # amount to use as priority fee
        "pool": pool  # exchange to trade on. "pump", "raydium", "pump-amm" or "auto"
    })
    tx = VersionedTransaction(VersionedTransaction.from_bytes(response.content).message, [private_key])
    config = RpcSendTransactionConfig(preflight_commitment=CommitmentLevel.Confirmed)
    response = requests.post(
        url="https://api.mainnet-beta.solana.com/", # https://mainnet.helius-rpc.com/?api-key=<your-api-key>  // better with helius
        headers={"Content-Type": "application/json"},
        data=SendVersionedTransaction(tx, config).to_json()
    )
    try:
        print(f"{action.upper()} | {amount} | {mint} | {pool} | https://solscan.io/tx/{response.json()['result']}")
    except KeyError:
        print(f"FAILED TO {action.upper()} {amount} of {mint} in pool '{pool}'")
        time.sleep(1)
        print("Retrying...")
        complete_official_transaction(action, mint, args, denominated_in_sol, pool, private_key, amount)

    if action == "sell":
        print("---------------------------------------------------------------------------------------------------")


def make_transaction(transaction: PumpTrade, args, keypair):
    global test_wallet_holdings

    transaction_token = transaction.mint
    if transaction.type == "buy":
        complete_official_transaction("buy", transaction_token, args, "true", transaction.pool, keypair)
        if transaction_token not in test_wallet_holdings:
            test_wallet_holdings[transaction_token] = 1

    elif transaction.type == "sell" and transaction_token in test_wallet_holdings:
        complete_official_transaction("sell", transaction_token, args, "false", transaction.pool, keypair, "100%")
        test_wallet_holdings.pop(transaction_token)

    else:
        print("Tracked wallet sold a token that was not found in your wallet "
              "(was probably bought before you started coping).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet_to_copy", help="Wallet address you wish to copy trades from", required=True, type=str)
    parser.add_argument("--public_key", help="Public key of your wallet", required=True, type=str)
    parser.add_argument("--private_key", help="Private key of your wallet", required=True, type=str)
    parser.add_argument("--amount", help="Amount you wish to buy per trade (in SOL)", required=True, type=float)
    parser.add_argument("--slippage", help="Slippage in %, e.g. 20 (means 20%)", default=20, type=float)
    parser.add_argument("--priority_fee", help="Priority fee in SOL", default=0, type=float)
    asyncio.run(subscribe(parser.parse_args()))
